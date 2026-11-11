#!/usr/bin/env bash
# Fix the PyMCubes/numpy ABI break, then resume the Stage 1 chain.
# PyMCubes 0.1.4 builds against oldest-supported-numpy (1.26.4 for cp312),
# so runtime numpy must be 1.26.4 too — numpy 2.5.4 breaks its import.
# Steps: downgrade numpy -> rebuild PyMCubes + xatlas (stage1d) -> vendor
# the cp312 xatlas wheel -> restart server -> stage1c -> stage1e.
set -u
set -o pipefail
cd "$(dirname "$0")"
exec > >(tee -a logs/numpy126-fix.log) 2>&1
say() { echo "[numpy126 $(date +%H:%M:%S)] $*"; }
say "=== numpy 1.26.4 fix + resume ==="
.venv/bin/python -m pip install "numpy==1.26.4" || { say "FATAL: numpy downgrade failed"; exit 1; }
.venv/bin/python -c "import numpy; print('numpy now', numpy.__version__)"
.venv/bin/python -m pip uninstall -y PyMCubes xatlas || true
bash .slushai-stage1d.sh || { say "FATAL: stage1d failed"; exit 1; }
cp /tmp/xatlas-build/wheels/xatlas-*.whl vendor/wheels/ 2>/dev/null && say "cp312 xatlas wheel vendored under vendor/wheels/" || say "NOTE: cp312 xatlas wheel copy failed (check /tmp/xatlas-build/wheels/)"

# ---------- restart server (localhost only, niced) ----------
say "--- restart server ---"
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

say "--- stage1c: auth re-verification ---"
bash .slushai-stage1c.sh || say "NOTE: stage1c reported failures (see logs/stage1c-auth-results.txt)"

say "--- stage1e: torch 2.2.2 + torchmcubes + generation test ---"
bash .slushai-stage1e.sh
say "=== numpy126 fix + resume done ==="
