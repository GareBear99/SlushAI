#!/usr/bin/env bash
# SlushAI Stage 1 generation test — runs AFTER requirements-triposr.txt installs.
# Launched in the background by .slushai-stage1.sh. Results go to
# logs/stage1-gen-results.txt. The server must already be running (started by
# stage1-run.sh, pid in logs/stage1-server.pid, port in logs/stage1-port.txt).
set -u
cd "$(dirname "$0")"
RES="logs/stage1-gen-results.txt"
LOG="logs/stage1-gen.log"
mkdir -p logs
exec > >(tee -a "$LOG") 2>&1
say() { echo "[stage1b $(date +%H:%M:%S)] $*"; }
pass() { echo "PASS: $*" | tee -a "$RES"; }
fail() { echo "FAIL: $*" | tee -a "$RES"; }
note() { echo "NOTE: $*" | tee -a "$RES"; }
: > "$RES"
say "=== SlushAI Stage 1b: TripoSR generation test ==="

PORT=$(cat logs/stage1-port.txt 2>/dev/null | sed 's/PORT=//')
BASE="http://127.0.0.1:$PORT"
say "using port $PORT (BASE=$BASE)"

# 1. TripoSR import smoke test (CPU) — confirms torch + vendor package import
say "--- TripoSR import smoke test ---"
if .venv/bin/python -c "import torch; import sys; sys.path.insert(0, '.'); from vendors.TripoSR.tsr import TSR; print('torch', torch.__version__, '| TSR import OK')" 2>&1 | tail -5; then
  pass "torch + TSR import OK"
else
  fail "torch/TSR import failed — see above; cannot generate"
  exit 1
fi

# 2. Fixture image
say "--- fixture image ---"
if [ ! -f assets/example.png ]; then
  (cd assets && ../.venv/bin/python make_sample.py) || { fail "make_sample.py failed"; exit 1; }
fi
ls -la assets/example.png

# 3. Login as the stage-1 test user
say "--- login as stage1test ---"
JAR=/tmp/ai3d-stage1b-cookies.txt; rm -f "$JAR"
LOGIN_CODE=$(curl -s -c "$JAR" -o /tmp/ai3d-stage1b-login.json -w "%{http_code}" -X POST "$BASE/auth/email/login" -H 'Content-Type: application/json' -d '{"email": "stage1test@slushai.local", "password": "Test1234", "remember_me": true}')
say "login -> HTTP $LOGIN_CODE"
if [ "$LOGIN_CODE" != "200" ]; then fail "login failed: $(cat /tmp/ai3d-stage1b-login.json | head -c 300)"; exit 1; fi

# 4. Generate
say "--- POST /api/generate (backend=triposr) ---"
ls outputs/*.obj 2>/dev/null > /tmp/ai3d-stage1b-objs-before.txt || true
GEN_CODE=$(curl -s -b "$JAR" -o /tmp/ai3d-stage1b-gen.json -w "%{http_code}" -X POST "$BASE/api/generate" -F "image=@assets/example.png" -F "backend=triposr")
say "generate -> HTTP $GEN_CODE"
cat /tmp/ai3d-stage1b-gen.json
TASK_ID=$(.venv/bin/python -c "import json; print(json.load(open('/tmp/ai3d-stage1b-gen.json')).get('task_id',''))" 2>/dev/null)
if [ "$GEN_CODE" != "200" ]; then fail "generate -> HTTP $GEN_CODE (body above)"; exit 1; fi
if [ -z "$TASK_ID" ]; then fail "generate 200 but no task_id in response"; exit 1; fi
pass "generate accepted, task_id=$TASK_ID"

# 5. Poll /api/task/<id>/status (the get_task_status fix) + filesystem for output
say "--- polling task status + outputs (up to 15 min; first run also downloads ~2 GB of TripoSR weights) ---"
START=$(date +%s)
DONE=0
for i in $(seq 1 60); do
  sleep 15
  ST=$(curl -s -b "$JAR" "$BASE/api/task/$TASK_ID/status" 2>/dev/null)
  say "t+$(( $(date +%s) - START ))s task status: $(echo "$ST" | head -c 250)"
  ls outputs/*.obj 2>/dev/null | grep -vxFf /tmp/ai3d-stage1b-objs-before.txt > /tmp/ai3d-stage1b-objs-new.txt || true
  if [ -s /tmp/ai3d-stage1b-objs-new.txt ]; then
    say "new .obj files:"; cat /tmp/ai3d-stage1b-objs-new.txt
    DONE=1; break
  fi
done
if [ "$DONE" != 1 ]; then
  fail "no new .obj file appeared under outputs/ within 15 minutes"
  tail -40 logs/viewer.log 2>/dev/null
  exit 1
fi
pass "new .obj output appeared under outputs/"

# 6. Verify the output is a real TripoSR mesh, not the proc cube
for f in $(cat /tmp/ai3d-stage1b-objs-new.txt); do
  V=$(grep -c '^v ' "$f" || true)
  S=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f")
  say "output $f: $V vertices, $S bytes"
  if [ "$V" -gt 1000 ]; then pass "$f is a real mesh ($V verts, not the 8-vert proc cube)"; else fail "$f has only $V vertices — looks like a fallback cube, not TripoSR"; fi
done

# 7. GLB/texture siblings?
ls -la outputs/ | tail -15
say "--- viewer.log tail (generation entries) ---"
grep -i "generation_complete\|generation_failed\|Executing queued task" logs/viewer.log 2>/dev/null | tail -5 || true

say "=== Stage 1b done — results in $RES ==="
cat "$RES"
