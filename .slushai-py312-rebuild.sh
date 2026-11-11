#!/usr/bin/env bash
# Rebuild the SlushAI venv on Python 3.12 and re-run the whole Stage 1 chain.
# WHY: torch ships no macOS Intel wheels since 2.3.0; the last one is 2.2.2,
# which needs Python <=3.12. The old 3.13 venv is kept as .venv-py313-backup
# (delete it once the 3.12 venv proves out).
# Chain: stop old server -> new 3.12 venv -> core deps -> stage1d (xatlas
# cp312 wheel) -> restart server -> stage1c (auth re-verify) -> stage1e
# (torch 2.2.2 + torchmcubes + generation test).
set -u
set -o pipefail
cd "$(dirname "$0")"
exec > >(tee -a logs/py312-rebuild.log) 2>&1
say() { echo "[rebuild $(date +%H:%M:%S)] $*"; }
UV_PY="$HOME/.local/share/uv/python/cpython-3.12-macos-x86_64-none/bin/python3.12"
[ -x "$UV_PY" ] || { say "FATAL: $UV_PY missing — run .slushai-py312.sh first"; exit 1; }
say "=== venv rebuild on Python 3.12 ==="

# ---------- 1. Stop the old (3.13) server ----------
say "--- stopping old server ---"
if [ -f logs/stage1-server.pid ]; then
  OLD_PID=$(cat logs/stage1-server.pid)
  if kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" && say "sent TERM to server pid $OLD_PID"
  else
    say "server pid $OLD_PID already gone"
  fi
fi
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/health 2>/dev/null || echo 000)
  [ "$code" != "200" ] && break
  sleep 1
done
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/health 2>/dev/null || echo 000)
if [ "$code" = "200" ]; then say "FATAL: old server still answering on :5000"; exit 1; fi
say "port 5000 free"

# ---------- 2. Swap venvs ----------
say "--- swapping venvs ---"
if [ -d .venv ]; then
  if [ -d .venv-py313-backup ]; then
    say "removing previous .venv-py313-backup"
    rm -rf .venv-py313-backup
  fi
  mv .venv .venv-py313-backup && say "old 3.13 venv kept as .venv-py313-backup"
fi
"$UV_PY" -m venv .venv || { say "FATAL: venv creation with Python 3.12 failed"; exit 1; }
.venv/bin/python --version
.venv/bin/python -m pip install --upgrade pip wheel setuptools -q 2>&1 | tail -2
say "installing requirements-core.txt..."
.venv/bin/python -m pip install -r requirements-core.txt 2>&1 | tail -3 || { say "FATAL: core deps install failed"; exit 1; }
.venv/bin/python -c "import flask, flask_socketio, flask_login, flask_limiter, authlib, bcrypt, jwt, requests, dotenv; print('core imports OK')" || { say "FATAL: core import check failed"; exit 1; }

# ---------- 3. Syntax check ----------
say "--- syntax check ---"
.venv/bin/python -m py_compile viewer/app.py src/ai3d/utils/user_manager.py src/ai3d/utils/task_queue.py src/ai3d/utils/security.py src/ai3d/cli.py src/ai3d/pipeline.py || { say "FATAL: syntax error"; exit 1; }
say "py_compile OK"

# ---------- 4. xatlas cp312 wheel (stage1d) ----------
say "--- stage1d: pipeline deps + xatlas wheel for cp312 ---"
bash .slushai-stage1d.sh || { say "FATAL: stage1d failed"; exit 1; }

# ---------- 5. Restart server on the new venv ----------
say "--- restart server (localhost only, niced) ---"
if lsof -iTCP:5000 -sTCP:LISTEN >/dev/null 2>&1; then
  PORT=5001; say "port 5000 is IN USE (AirPlay Receiver likely) -> using 5001"
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

# ---------- 6. Auth re-verification under 3.12 ----------
say "--- stage1c: auth re-verification ---"
bash .slushai-stage1c.sh || say "NOTE: stage1c reported failures (see logs/stage1c-auth-results.txt)"

# ---------- 7. TripoSR deps + generation test ----------
say "--- stage1e: torch 2.2.2 + torchmcubes + generation test ---"
bash .slushai-stage1e.sh
say "=== rebuild done ==="
