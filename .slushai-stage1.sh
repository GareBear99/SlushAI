#!/usr/bin/env bash
# SlushAI Stage 1 run driver — setup + auth verification (unattended).
# Run from the project root in a terminal:
#   bash .slushai-stage1.sh
# Everything it does is logged to logs/stage1-run.log and
# logs/stage1-auth-results.txt. It never prints secrets: credential checks are
# done by observing server behaviour (redirects / status codes), never by
# reading .env contents or printing values.
# It starts the server localhost-only (127.0.0.1), niced, with torch threads
# capped so the Mac stays usable while Gary works.
set -u
set -o pipefail
cd "$(dirname "$0")"
LOG="logs/stage1-run.log"
RES="logs/stage1-auth-results.txt"
mkdir -p logs
exec > >(tee -a "$LOG") 2>&1
say() { echo "[stage1 $(date +%H:%M:%S)] $*"; }
pass() { echo "PASS: $*" | tee -a "$RES"; }
fail() { echo "FAIL: $*" | tee -a "$RES"; }
note() { echo "NOTE: $*" | tee -a "$RES"; }
: > "$RES"
say "=== SlushAI Stage 1: setup + auth verification ==="

# ---------- 1. Recon ----------
say "--- recon ---"
PY=python3
for cand in python3 python3.12 python3.11 python3.10; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
say "python: $PY $($PY --version 2>&1)"
say "pip: $($PY -m pip --version 2>&1 | head -1)"
if command -v sqlite3 >/dev/null 2>&1; then say "sqlite3 CLI: available"; else say "sqlite3 CLI: MISSING (will use python fallback)"; fi
if pgrep -f "python.*viewer/app.py" >/dev/null 2>&1; then say "NOTE: an app.py server is already running (pids: $(pgrep -f 'python.*viewer/app.py' | tr '\n' ' '))"; else say "no app.py server running"; fi
if lsof -iTCP:5000 -sTCP:LISTEN >/dev/null 2>&1; then
  PORT=5001; say "port 5000 is IN USE (AirPlay Receiver likely) -> using 5001"
else
  PORT=5000; say "port 5000 is free -> using 5000"
fi
echo "PORT=$PORT" > logs/stage1-port.txt
say "HF weights cache:"; ls ~/.cache/huggingface/hub 2>/dev/null | head -5 || say "  (no HF cache dir)"
if [ -f logs/users.db ]; then
  say "users.db schema (UNIQUE check):"
  sqlite3 logs/users.db ".schema users" 2>/dev/null | grep -i "email\|UNIQUE" || $PY -c "import sqlite3; print([r for r in sqlite3.connect('logs/users.db').execute(\"SELECT sql FROM sqlite_master WHERE type='table' AND name='users'\")])"
  say "user count: $(sqlite3 logs/users.db 'SELECT COUNT(*) FROM users;' 2>/dev/null || echo '?')"
  say "accounts from 127.0.0.1: $(sqlite3 logs/users.db "SELECT COUNT(*) FROM users WHERE signup_ip='127.0.0.1';" 2>/dev/null || echo '?')"
  say "duplicate emails: $(sqlite3 logs/users.db 'SELECT email, COUNT(*) c FROM users GROUP BY email HAVING c > 1;' 2>/dev/null || echo '?')"
  say "security.db tables: $(sqlite3 logs/security.db ".tables" 2>/dev/null || echo '?')"
  sqlite3 logs/security.db ".schema" 2>/dev/null | grep -i "block" | head -3 || true
else
  say "no logs/users.db yet (fresh DB will be created on first run)"
fi

# ---------- 2. Venv + core deps ----------
say "--- venv + core deps ---"
if [ ! -x .venv/bin/python ]; then
  if [ -d .venv ]; then say "removing stale/broken .venv (no bin/python — left over from 2025-11-25)"; rm -rf .venv; fi
  say "creating .venv with $PY"
  "$PY" -m venv .venv || { say "FATAL: venv creation failed"; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
.venv/bin/python -m pip install --upgrade pip wheel setuptools -q 2>&1 | tail -2
say "installing requirements-core.txt (Flask stack + pipeline libs)..."
if .venv/bin/python -m pip install -r requirements-core.txt 2>&1 | tail -3; then
  say "core deps installed"
else
  say "FATAL: core deps install failed (see above)"; exit 1
fi
if ! .venv/bin/python -c "import flask, flask_socketio, flask_login, flask_limiter, authlib, bcrypt, jwt, requests, dotenv; print('core imports OK')"; then
  say "FATAL: core deps import check failed"; exit 1
fi

# ---------- 3. Syntax check on everything edited ----------
say "--- syntax check ---"
if .venv/bin/python -m py_compile viewer/app.py src/ai3d/utils/user_manager.py src/ai3d/utils/task_queue.py src/ai3d/utils/security.py src/ai3d/cli.py src/ai3d/pipeline.py; then
  say "py_compile OK on edited files"
else
  say "FATAL: syntax error in edited files"; exit 1
fi

# ---------- 4. Start server (localhost only, niced) ----------
say "--- start server ---"
export SLUSHAI_PORT="$PORT"
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
nohup nice -n 10 .venv/bin/python viewer/app.py > logs/stage1-server.log 2>&1 &
SRVPID=$!
echo "$SRVPID" > logs/stage1-server.pid
say "server pid $SRVPID on 127.0.0.1:$PORT (log: logs/stage1-server.log)"
BASE="http://127.0.0.1:$PORT"
ok=0
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/health" || echo 000)
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 1
done
if [ "$ok" != 1 ]; then say "FATAL: server did not answer /api/health"; tail -30 logs/stage1-server.log; exit 1; fi
say "health OK: $(curl -s "$BASE/api/health" | head -c 300)"

# ---------- 5. Auth verification ----------
say "--- auth verification ---"
JAR=/tmp/ai3d-stage1-cookies.txt; rm -f "$JAR"
JQ() { .venv/bin/python -c "import sys, json; d=json.load(sys.stdin); print(d$1)" 2>/dev/null; }

# 5a. Landing page served, byte-identical to the file on disk
curl -s "$BASE/" -o /tmp/ai3d-stage1-landing.html
if grep -q "SlushAI 3D Modeller" /tmp/ai3d-stage1-landing.html; then
  if [ "$(md5 -q /tmp/ai3d-stage1-landing.html 2>/dev/null)" = "$(md5 -q viewer/landing.html 2>/dev/null)" ]; then
    pass "GET / serves landing.html byte-identical to viewer/landing.html (sign-in page unchanged)"
  else
    fail "GET / serves landing.html but bytes differ from viewer/landing.html"
  fi
else
  fail "GET / did not return the landing page"
fi

# 5b. Google auth button target
GLOC=$(curl -s -o /dev/null -w "%{http_code} %{redirect_url}" "$BASE/auth/login")
say "GET /auth/login -> $GLOC"
if echo "$GLOC" | grep -qi "YOUR_GOOGLE_CLIENT_ID_HERE\|YOUR_.*_HERE\|placeholder"; then
  fail "Google login redirects to Google but with a PLACEHOLDER client_id (YOUR_GOOGLE_CLIENT_ID_HERE) — Google credentials are NOT configured. Gary must supply GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET, with redirect URI http://localhost:5000/auth/callback (or the SLUSHAI_PORT value) registered in Google Cloud."
elif echo "$GLOC" | grep -q "accounts.google.com"; then
  pass "Google login redirects to accounts.google.com with a real client_id"
elif echo "$GLOC" | grep -q "^302"; then
  note "Google login redirects somewhere unexpected: $GLOC"
else
  fail "Google login does NOT redirect to Google: $GLOC (credentials likely missing — Gary must supply GOOGLE_CLIENT_ID/SECRET + redirect URI)"
fi

# 5c. Signup (live if the 3-per-IP cap allows, else DB-copy function test)
SIGNUP_IP_COUNT=$(sqlite3 logs/users.db "SELECT COUNT(*) FROM users WHERE signup_ip='127.0.0.1';" 2>/dev/null || echo 0)
TEST_EMAIL="stage1test@slushai.local"
TEST_USER="stageonetest"
TEST_PASS="Test1234"
TEST_UID=$(sqlite3 logs/users.db "SELECT id FROM users WHERE email='$TEST_EMAIL';" 2>/dev/null || echo "")
if [ -n "$TEST_UID" ]; then
  say "test user already exists (id $TEST_UID) — reusing it"
fi
if [ -z "$TEST_UID" ]; then
if [ "$SIGNUP_IP_COUNT" -lt 3 ]; then
  say "signup_ip count is $SIGNUP_IP_COUNT (< 3) — attempting live signup"
  SIGNUP_BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/email/signup" -H 'Content-Type: application/json' -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASS\", \"name\": \"Stage One\", \"username\": \"$TEST_USER\", \"newsletter\": false}")
  SIGNUP_CODE=$(echo "$SIGNUP_BODY" | tail -n1)
  echo "$SIGNUP_BODY" | sed '$d' | tee /tmp/ai3d-stage1-signup.json
  if [ "$SIGNUP_CODE" = "201" ]; then
    TEST_UID=$(JQ "['user_id']" < /tmp/ai3d-stage1-signup.json)
    pass "signup -> 201, user_id=$TEST_UID"
  else
    fail "signup -> HTTP $SIGNUP_CODE (body above)"
  fi
else
  note "signup_ip count is $SIGNUP_IP_COUNT (>= 3) — live signup is capped; verifying create_email_user against a COPY of the DB instead"
  cp logs/users.db /tmp/ai3d-stage1-users-copy.db
  COPY_OUT=$(.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from src.ai3d.utils.user_manager import UserManager
m = UserManager('/tmp/ai3d-stage1-users-copy.db')
print(m.create_email_user('$TEST_EMAIL', '$TEST_PASS', 'Stage One', '$TEST_USER', False))
" 2>&1)
  say "DB-copy create_email_user: $COPY_OUT"
  echo "$COPY_OUT" | grep -q "(True" && pass "create_email_user works on a DB copy (live signup capped by the 3-per-IP rule)" || fail "create_email_user failed on DB copy: $COPY_OUT"
  # Live 403 path check (A-8: must be JSON, not HTML)
  CAP_BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/email/signup" -H 'Content-Type: application/json' -d "{\"email\": \"capcheck@slushai.local\", \"password\": \"$TEST_PASS\", \"name\": \"Cap Check\", \"username\": \"capcheck1\", \"newsletter\": false}")
  echo "$CAP_BODY" | sed '$d' | grep -q '"error"' && pass "capped signup returns JSON error (not an HTML page)" || fail "capped signup did not return JSON: $(echo "$CAP_BODY" | head -c 200)"
  TEST_UID=$(sqlite3 logs/users.db "SELECT id FROM users WHERE email='$TEST_EMAIL';" 2>/dev/null || echo "")
fi
fi

if [ -n "$TEST_UID" ]; then
  # 5d. Verification code from the DB (own test account only) -> verify
  # (Skip if the account is already verified from an earlier run: the token
  # is cleared on verify, so there is no code to present.)
  ALREADY_VERIFIED=$(sqlite3 logs/users.db "SELECT email_verified FROM users WHERE id=$TEST_UID;" 2>/dev/null || echo 0)
  if [ "$ALREADY_VERIFIED" = "1" ]; then
    pass "test user already verified (from an earlier run) — code check skipped"
  else
  CODE=$(sqlite3 logs/users.db "SELECT verification_token FROM users WHERE id=$TEST_UID;" 2>/dev/null)
  if [ -n "$CODE" ]; then
    VERIFY_CODE=$(curl -s -o /tmp/ai3d-stage1-verify.json -w "%{http_code}" -X POST "$BASE/auth/email/verify-code" -H 'Content-Type: application/json' -d "{\"user_id\": $TEST_UID, \"code\": \"$CODE\"}")
    if [ "$VERIFY_CODE" = "200" ]; then pass "verify-code -> 200 (email verified)"; else fail "verify-code -> HTTP $VERIFY_CODE: $(cat /tmp/ai3d-stage1-verify.json)"; fi
  else
    fail "no verification code found in DB for test user $TEST_UID"
  fi
  fi
  # 5e. Login
  LOGIN_CODE=$(curl -s -c "$JAR" -o /tmp/ai3d-stage1-login.json -w "%{http_code}" -X POST "$BASE/auth/email/login" -H 'Content-Type: application/json' -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASS\", \"remember_me\": true}")
  if [ "$LOGIN_CODE" = "200" ]; then pass "email login -> 200"; else fail "email login -> HTTP $LOGIN_CODE: $(cat /tmp/ai3d-stage1-login.json)"; fi
  # 5f. Profile — the A-1 check
  PROF_CODE=$(curl -s -b "$JAR" -o /tmp/ai3d-stage1-profile.json -w "%{http_code}" "$BASE/api/user/profile")
  if [ "$PROF_CODE" = "200" ]; then
    pass "GET /api/user/profile -> 200 (KeyError 'user_id' fixed)"
    .venv/bin/python -c "
import json
p = json.load(open('/tmp/ai3d-stage1-profile.json'))
print('  profile keys:', sorted(p.keys()))
print('  user_id:', p.get('user_id'), '| name:', p.get('name'), '| badge:', p.get('badge_name'), '| quota:', p.get('quota'))
assert p.get('user_id') == $TEST_UID, 'user_id mismatch'
assert 'used_this_week' in p.get('quota', {}), 'quota keys wrong'
assert 'weekly_limit' in p.get('quota', {}), 'quota keys wrong'
print('  profile content OK')
" && pass "profile content correct (user_id, badge, quota.used_this_week/weekly_limit)" || fail "profile content wrong (see above)"
  else
    fail "GET /api/user/profile -> HTTP $PROF_CODE: $(cat /tmp/ai3d-stage1-profile.json | head -c 300)"
  fi
  # 5g. PIN flow on the SAME test user (promote to moderator, then restore)
  sqlite3 logs/users.db "UPDATE users SET subscription_tier='moderator' WHERE id=$TEST_UID;"
  PIN_LOGIN=$(curl -s -c "$JAR" -o /tmp/ai3d-stage1-pinlogin.json -w "%{http_code}" -X POST "$BASE/auth/email/login" -H 'Content-Type: application/json' -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASS\", \"remember_me\": true}")
  PIN_REQ=$(.venv/bin/python -c "import json; print(json.load(open('/tmp/ai3d-stage1-pinlogin.json')).get('requires_pin'))" 2>/dev/null)
  if [ "$PIN_REQ" = "True" ]; then
    PIN=$(sqlite3 logs/users.db "SELECT verification_token FROM users WHERE id=$TEST_UID;" 2>/dev/null)
    PIN_CODE=$(curl -s -b "$JAR" -o /tmp/ai3d-stage1-pin.json -w "%{http_code}" -X POST "$BASE/auth/email/verify-pin" -H 'Content-Type: application/json' -d "{\"user_id\": $TEST_UID, \"pin\": \"$PIN\", \"remember_me\": true}")
    if [ "$PIN_CODE" = "200" ]; then pass "PIN verify -> 200 (datetime UnboundLocalError fixed, B-1 verified live)"; else fail "PIN verify -> HTTP $PIN_CODE: $(cat /tmp/ai3d-stage1-pin.json | head -c 300)"; fi
  else
    fail "moderator login did not ask for a PIN (HTTP $PIN_LOGIN): $(cat /tmp/ai3d-stage1-pinlogin.json | head -c 300)"
  fi
  sqlite3 logs/users.db "UPDATE users SET subscription_tier='free' WHERE id=$TEST_UID;"
  say "test user tier restored to free"
else
  fail "no test user id — skipping verify/login/profile/PIN checks"
fi

# 5h. Rate-limit path must return 429, not 500 (do this LAST: it burns the login budget for a minute)
say "rate-limit probe: 11 bad logins, expecting 429 on the 11th"
LAST=""
for i in $(seq 1 11); do
  LAST=$(curl -s -o /tmp/ai3d-stage1-rl.json -w "%{http_code}" -X POST "$BASE/auth/email/login" -H 'Content-Type: application/json' -d "{\"email\": \"nobody@slushai.local\", \"password\": \"Wrong1234\", \"remember_me\": false}")
  sleep 0.2
done
say "11th bad login -> HTTP $LAST: $(head -c 200 /tmp/ai3d-stage1-rl.json)"
if [ "$LAST" = "429" ]; then pass "rate limit returns 429 (not a 500 crash)"; else fail "rate limit probe ended HTTP $LAST, expected 429"; fi

# ---------- 6. Errors check (today's date only — a line-grep flags old entries) ----------
say "--- new errors.log check ---"
TODAY=$(date +%Y-%m-%d)
if grep "$TODAY" logs/errors.log 2>/dev/null | grep -E "KeyError|UnboundLocalError|RequestLimit" | head -5; then
  fail "new KeyError/UnboundLocalError/RequestLimit entries in errors.log (see above)"
else
  pass "no new KeyError/UnboundLocalError/RequestLimit entries in errors.log"
fi

say "=== Stage 1 auth verification done — results in $RES ==="
cat "$RES"

# ---------- 7. TripoSR deps in the background, then generation test ----------
say "--- launching TripoSR install + generation test in the background ---"
( .venv/bin/python -m pip install -r requirements-pipeline.txt > logs/stage1-pipeline-install.log 2>&1 && echo "pipeline deps OK" || echo "pipeline deps FAILED (see logs/stage1-pipeline-install.log)"; .venv/bin/python -m pip install -r requirements-triposr.txt > logs/stage1-triposr-install.log 2>&1 && say "TripoSR deps installed OK" && bash .slushai-stage1b.sh ) > logs/stage1-triposr.log 2>&1 &
say "background TripoSR job started (log: logs/stage1-triposr-install.log, then logs/stage1-gen-results.txt)"
say "server left RUNNING on 127.0.0.1:$PORT (pid $SRVPID) for the generation test"
