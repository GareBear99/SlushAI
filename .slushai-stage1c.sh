#!/usr/bin/env bash
# SlushAI Stage 1c — auth verification fix-up.
# Runs ONLY the auth checks against the server that .slushai-stage1.sh already
# started (port in logs/stage1-port.txt). Starts nothing, launches nothing.
# Fixes vs the stage1 script: TEST_UID (bash $UID is readonly — using UID
# silently reused Gary's Unix uid 501), Google placeholder detection, and a
# date-aware errors.log check (the old line-grep flagged a Nov 2025 entry).
set -u
set -o pipefail
cd "$(dirname "$0")"
RES="logs/stage1c-auth-results.txt"
LOG="logs/stage1c-run.log"
mkdir -p logs
exec > >(tee -a "$LOG") 2>&1
say() { echo "[stage1c $(date +%H:%M:%S)] $*"; }
pass() { echo "PASS: $*" | tee -a "$RES"; }
fail() { echo "FAIL: $*" | tee -a "$RES"; }
note() { echo "NOTE: $*" | tee -a "$RES"; }
: > "$RES"
say "=== SlushAI Stage 1c: auth verification (server already running) ==="

PORT=$(cat logs/stage1-port.txt 2>/dev/null | sed 's/PORT=//')
BASE="http://127.0.0.1:$PORT"
say "BASE=$BASE (server pid $(cat logs/stage1-server.pid 2>/dev/null || echo '?'))"
curl -s -o /dev/null -w "health: %{http_code}\n" "$BASE/api/health" || { say "FATAL: server not answering"; exit 1; }

JAR=/tmp/ai3d-stage1c-cookies.txt; rm -f "$JAR"
JQ() { .venv/bin/python -c "import sys, json; d=json.load(sys.stdin); print(d$1)" 2>/dev/null; }
TODAY=$(date +%Y-%m-%d)
ERR_BEFORE=$(grep -c "$TODAY" logs/errors.log 2>/dev/null || true)

# Google auth: redirect must carry a REAL client id, not the placeholder.
GLOC=$(curl -s -o /dev/null -w "%{http_code} %{redirect_url}" "$BASE/auth/login")
say "GET /auth/login -> $GLOC"
if echo "$GLOC" | grep -qi "YOUR_GOOGLE_CLIENT_ID_HERE\|YOUR_.*_HERE\|placeholder"; then
  fail "Google login redirects to Google but with a PLACEHOLDER client_id (YOUR_GOOGLE_CLIENT_ID_HERE) — Google credentials are NOT configured. Gary must supply GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET, with redirect URI http://localhost:5000/auth/callback (or the SLUSHAI_PORT value) registered in Google Cloud."
elif echo "$GLOC" | grep -q "accounts.google.com"; then
  pass "Google login redirects to accounts.google.com with a real client_id"
else
  fail "Google login does NOT redirect to Google: $GLOC"
fi

# Signup (live; cap count is 1 < 3). Reuse the test user if it already exists.
TEST_EMAIL="stage1test@slushai.local"
TEST_USER="stageonetest"
TEST_PASS="Test1234"
TEST_UID=$(sqlite3 logs/users.db "SELECT id FROM users WHERE email='$TEST_EMAIL';" 2>/dev/null || echo "")
if [ -n "$TEST_UID" ]; then say "test user already exists (id $TEST_UID) — reusing it"; fi
if [ -z "$TEST_UID" ]; then
  SIGNUP_BODY=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/email/signup" -H 'Content-Type: application/json' -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASS\", \"name\": \"Stage One\", \"username\": \"$TEST_USER\", \"newsletter\": false}")
  SIGNUP_CODE=$(echo "$SIGNUP_BODY" | tail -n1)
  echo "$SIGNUP_BODY" | sed '$d' | tee /tmp/ai3d-stage1c-signup.json
  if [ "$SIGNUP_CODE" = "201" ]; then
    TEST_UID=$(JQ "['user_id']" < /tmp/ai3d-stage1c-signup.json)
    pass "signup -> 201, user_id=$TEST_UID"
  else
    fail "signup -> HTTP $SIGNUP_CODE (body above)"
  fi
fi

if [ -n "$TEST_UID" ]; then
  ALREADY_VERIFIED=$(sqlite3 logs/users.db "SELECT email_verified FROM users WHERE id=$TEST_UID;" 2>/dev/null || echo 0)
  if [ "$ALREADY_VERIFIED" = "1" ]; then
    pass "test user already verified (from an earlier run) — code check skipped"
  else
    CODE=$(sqlite3 logs/users.db "SELECT verification_token FROM users WHERE id=$TEST_UID;" 2>/dev/null)
    if [ -n "$CODE" ]; then
      VERIFY_CODE=$(curl -s -o /tmp/ai3d-stage1c-verify.json -w "%{http_code}" -X POST "$BASE/auth/email/verify-code" -H 'Content-Type: application/json' -d "{\"user_id\": $TEST_UID, \"code\": \"$CODE\"}")
      if [ "$VERIFY_CODE" = "200" ]; then pass "verify-code -> 200 (email verified)"; else fail "verify-code -> HTTP $VERIFY_CODE: $(cat /tmp/ai3d-stage1c-verify.json)"; fi
    else
      fail "no verification code found in DB for test user $TEST_UID"
    fi
  fi
  LOGIN_CODE=$(curl -s -c "$JAR" -o /tmp/ai3d-stage1c-login.json -w "%{http_code}" -X POST "$BASE/auth/email/login" -H 'Content-Type: application/json' -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASS\", \"remember_me\": true}")
  if [ "$LOGIN_CODE" = "200" ]; then pass "email login -> 200"; else fail "email login -> HTTP $LOGIN_CODE: $(cat /tmp/ai3d-stage1c-login.json)"; fi
  PROF_CODE=$(curl -s -b "$JAR" -o /tmp/ai3d-stage1c-profile.json -w "%{http_code}" "$BASE/api/user/profile")
  if [ "$PROF_CODE" = "200" ]; then
    pass "GET /api/user/profile -> 200 (KeyError 'user_id' fixed)"
    .venv/bin/python -c "
import json
p = json.load(open('/tmp/ai3d-stage1c-profile.json'))
print('  profile keys:', sorted(p.keys()))
print('  user_id:', p.get('user_id'), '| name:', p.get('name'), '| badge:', p.get('badge_name'), '| quota:', p.get('quota'))
assert p.get('user_id') == $TEST_UID, 'user_id mismatch'
assert 'used_this_week' in p.get('quota', {}), 'quota keys wrong'
assert 'weekly_limit' in p.get('quota', {}), 'quota keys wrong'
print('  profile content OK')
" && pass "profile content correct (user_id, badge, quota.used_this_week/weekly_limit)" || fail "profile content wrong (see above)"
  else
    fail "GET /api/user/profile -> HTTP $PROF_CODE: $(cat /tmp/ai3d-stage1c-profile.json | head -c 300)"
  fi
  sqlite3 logs/users.db "UPDATE users SET subscription_tier='moderator' WHERE id=$TEST_UID;"
  PIN_LOGIN=$(curl -s -c "$JAR" -o /tmp/ai3d-stage1c-pinlogin.json -w "%{http_code}" -X POST "$BASE/auth/email/login" -H 'Content-Type: application/json' -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASS\", \"remember_me\": true}")
  PIN_REQ=$(.venv/bin/python -c "import json; print(json.load(open('/tmp/ai3d-stage1c-pinlogin.json')).get('requires_pin'))" 2>/dev/null)
  if [ "$PIN_REQ" = "True" ]; then
    PIN=$(sqlite3 logs/users.db "SELECT verification_token FROM users WHERE id=$TEST_UID;" 2>/dev/null)
    PIN_CODE=$(curl -s -b "$JAR" -o /tmp/ai3d-stage1c-pin.json -w "%{http_code}" -X POST "$BASE/auth/email/verify-pin" -H 'Content-Type: application/json' -d "{\"user_id\": $TEST_UID, \"pin\": \"$PIN\", \"remember_me\": true}")
    if [ "$PIN_CODE" = "200" ]; then pass "PIN verify -> 200 (datetime UnboundLocalError fixed, B-1 verified live)"; else fail "PIN verify -> HTTP $PIN_CODE: $(cat /tmp/ai3d-stage1c-pin.json | head -c 300)"; fi
  else
    fail "moderator login did not ask for a PIN (HTTP $PIN_LOGIN): $(cat /tmp/ai3d-stage1c-pinlogin.json | head -c 300)"
  fi
  sqlite3 logs/users.db "UPDATE users SET subscription_tier='free' WHERE id=$TEST_UID;"
  say "test user tier restored to free"
else
  fail "no test user id — skipping verify/login/profile/PIN checks"
fi

say "rate-limit probe: 11 bad logins, expecting 429 on the 11th"
LAST=""
for i in $(seq 1 11); do
  LAST=$(curl -s -o /tmp/ai3d-stage1c-rl.json -w "%{http_code}" -X POST "$BASE/auth/email/login" -H 'Content-Type: application/json' -d "{\"email\": \"nobody@slushai.local\", \"password\": \"Wrong1234\", \"remember_me\": false}")
  sleep 0.2
done
say "11th bad login -> HTTP $LAST: $(head -c 200 /tmp/ai3d-stage1c-rl.json)"
if [ "$LAST" = "429" ]; then pass "rate limit returns 429 (not a 500 crash)"; else fail "rate limit probe ended HTTP $LAST, expected 429"; fi

say "--- errors.log check (today $TODAY only) ---"
ERR_NOW=$(grep -c "$TODAY" logs/errors.log 2>/dev/null || true)
say "errors.log lines dated today: before=$ERR_BEFORE now=$ERR_NOW"
if [ "$ERR_NOW" -gt "$ERR_BEFORE" ]; then
  grep "$TODAY" logs/errors.log | grep -E "KeyError|UnboundLocalError|RequestLimit" | head -5
  fail "new dated error entries appeared in errors.log during this run (see above)"
else
  pass "no new dated error entries in errors.log"
fi

say "=== Stage 1c done — results in $RES ==="
cat "$RES"
