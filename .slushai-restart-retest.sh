#!/usr/bin/env bash
# Restart the server with the task-queue deadlock fix, then re-run the
# generation test. The old server process holds a deadlocked request thread
# (first /api/generate after startup hung in add_task -> _start_worker on
# a non-reentrant lock), so it must be killed, not reloaded.
set -u
set -o pipefail
cd "$(dirname "$0")"
exec > >(tee -a logs/restart-retest.log) 2>&1
say() { echo "[restart $(date +%H:%M:%S)] $*"; }
say "=== restart with deadlock fix + generation retest ==="
.venv/bin/python -m py_compile src/ai3d/utils/task_queue.py || { say "FATAL: task_queue.py syntax error"; exit 1; }
say "task_queue.py compiles"
if [ -f logs/stage1-server.pid ]; then
  OLD_PID=$(cat logs/stage1-server.pid)
  if kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" && say "sent TERM to old server pid $OLD_PID"
  else
    say "old server pid $OLD_PID already gone"
  fi
fi
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/health 2>/dev/null || echo 000)
  [ "$code" != "200" ] && break
  sleep 1
done
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/health 2>/dev/null || echo 000)
[ "$code" = "200" ] && { say "FATAL: old server still answering on :5000"; exit 1; }
say "port 5000 free"
if lsof -iTCP:5000 -sTCP:LISTEN >/dev/null 2>&1; then
  PORT=5001; say "port 5000 is IN USE -> using 5001"
else
  PORT=5000; say "port 5000 is free -> using 5000"
fi
echo "PORT=$PORT" > logs/stage1-port.txt
export SLUSHAI_PORT="$PORT"
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
nohup nice -n 10 .venv/bin/python viewer/app.py > logs/stage1-server.log 2>&1 &
SRVPID=$!
echo "$SRVPID" > logs/stage1-server.pid
say "server pid $SRVPID on 127.0.0.1:$PORT"
BASE="http://127.0.0.1:$PORT"
ok=0
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/health" || echo 000)
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 1
done
[ "$ok" = 1 ] || { say "FATAL: server did not answer /api/health"; tail -30 logs/stage1-server.log; exit 1; }
say "health OK"
say "--- stage1b: generation test (retry) ---"
bash .slushai-stage1b.sh
say "=== restart + retest done ==="
