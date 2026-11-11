#!/bin/bash
# SlushAI Stage 3 — Mac Phase I: SAFETY live-verification pass (Gary 05:40).
# Proves EACH fix live against the running server with TWO fresh test
# users (A generates, B must NOT see A's stuff). No fix is marked
# verified on code alone. Logs to /tmp/slushai-stage3-i.log.
# Cleanup at the end deletes both test users; users 1+3 must remain.
set -u
PROJECT=/Users/gary/projects/AI3DModeller
cd "$PROJECT" || { echo "FATAL: cannot cd to $PROJECT"; exit 1; }
LOG=/tmp/slushai-stage3-i.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "=== SlushAI Stage 3 Mac Phase I (SAFETY live verification) — $(date) ==="
BASE=http://127.0.0.1:5001
PY=.venv/bin/python
JAR_A=/tmp/slushai-safety-a-cookies.txt
JAR_B=/tmp/slushai-safety-b-cookies.txt
rm -f "$JAR_A" "$JAR_B"
PASS=0; FAIL=0
check() { # check "label" expected-code actual-code
    if [ "$2" = "$3" ]; then echo "  PASS: $1 (got $3)"; PASS=$((PASS+1));
    else echo "  FAIL: $1 (expected $2, got $3)"; FAIL=$((FAIL+1)); fi
}
echo "=== Pre-flight: remove any partial safetyA/safetyB rows from an aborted run ==="
"$PY" -c "
import sqlite3
c = sqlite3.connect('logs/users.db')
for email in ('safetyA@slushai.local', 'safetyB@slushai.local'):
    cur = c.execute('DELETE FROM users WHERE email = ?', (email,))
    if cur.rowcount: print(f'removed partial row: {email} ({cur.rowcount})')
c.commit()
" 2>/dev/null || echo "(no partial rows)"
check_contains_not() { # check_not "label" needle haystack
    if echo "$3" | grep -q "$2"; then echo "  FAIL: $1 (found '$2')"; FAIL=$((FAIL+1));
    else echo "  PASS: $1 (not present)"; PASS=$((PASS+1)); fi
}

mkuser() { # mkuser email username jar -> prints user_id or empty
    local EMAIL=$1 USERNAME=$2 JAR=$3
    local SIGNUP CODE VERIFY LOGIN NEW_UID
    SIGNUP=$(curl -s -c "$JAR" -X POST "$BASE/auth/email/signup" -H "Content-Type: application/json" \
        -d "{\"email\":\"$EMAIL\",\"password\":\"SafetyPass123!\",\"name\":\"Safety $USERNAME\",\"username\":\"$USERNAME\",\"newsletter\":false}")
    NEW_UID=$(echo "$SIGNUP" | "$PY" -c "import json,sys; print(json.load(sys.stdin).get('user_id',''))" 2>/dev/null)
    [ -z "$NEW_UID" ] && { echo "  SIGNUP FAILED for $EMAIL: $(echo "$SIGNUP" | head -c 300)"; echo ""; return 1; }
    CODE=$("$PY" -c "
import sqlite3
c = sqlite3.connect('logs/users.db')
r = c.execute('SELECT verification_token FROM users WHERE id = ?', ($NEW_UID,)).fetchone()
print(r[0] if r and r[0] else '')
" 2>/dev/null)
    [ -z "$CODE" ] && { echo "  NO VERIFICATION CODE for $EMAIL (uid $NEW_UID)"; echo ""; return 1; }
    VERIFY=$(curl -s -b "$JAR" -o /dev/null -w "%{http_code}" -X POST "$BASE/auth/email/verify-code" -H "Content-Type: application/json" -d "{\"user_id\": $NEW_UID, \"code\": \"$CODE\"}")
    LOGIN=$(curl -s -b "$JAR" -c "$JAR" -o /dev/null -w "%{http_code}" -X POST "$BASE/auth/email/login" -H "Content-Type: application/json" -d "{\"email\": \"$EMAIL\", \"password\": \"SafetyPass123!\", \"remember_me\": false}")
    echo "  user $USERNAME (id $NEW_UID): signup 201, verify $VERIFY, login $LOGIN"
    echo "$NEW_UID"
}

echo "=== Create two test users ==="
UID_A=$(mkuser "safetyA@slushai.local" "safetyA" "$JAR_A" | tail -1)
UID_B=$(mkuser "safetyB@slushai.local" "safetyB" "$JAR_B" | tail -1)
echo "UID_A=$UID_A UID_B=$UID_B"
[ -z "$UID_A" ] || [ -z "$UID_B" ] && { echo "FATAL: could not create both test users"; exit 1; }
echo ""
echo "=== User A generates a native model (SPSC path) ==="
GEN_RESP=$(curl -s -b "$JAR_A" -w "\n%{http_code}" -X POST "$BASE/api/generate" \
    -H "Origin: http://127.0.0.1:5001" \
    -F "image=@assets/example.png" -F "backend=native" -F "texture=native")
echo "Submit HTTP: $(echo "$GEN_RESP" | tail -1)"
TASK_A=$(echo "$GEN_RESP" | head -1 | "$PY" -c "import json,sys; print(json.load(sys.stdin).get('task_id',''))" 2>/dev/null)
echo "Task A: $TASK_A"
for i in $(seq 1 30); do
    sleep 2
    ST=$(curl -s -b "$JAR_A" "$BASE/api/task/$TASK_A/status")
    STATUS=$(echo "$ST" | "$PY" -c "import json,sys; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
    case "$STATUS" in completed|failed|error|cancelled) break ;; esac
done
FINAL_A=$(curl -s -b "$JAR_A" "$BASE/api/task/$TASK_A/status")
PREVIEW_A=$(echo "$FINAL_A" | "$PY" -c "import json,sys; d=json.load(sys.stdin); r=d.get('result') or {}; print(r.get('preview_path',''))" 2>/dev/null)
echo "Task A status: $STATUS, preview_path: $PREVIEW_A"
VERTS=0
[ -n "$PREVIEW_A" ] && [ -f "$PREVIEW_A" ] && VERTS=$(grep -c '^v ' "$PREVIEW_A")
echo "A's mesh vertices: $VERTS"
if [ "$STATUS" = "completed" ] && [ "$VERTS" -gt 100 ]; then echo "  PASS: SPSC path produced a correct mesh end to end ($VERTS verts)"; PASS=$((PASS+1));
else echo "  FAIL: SPSC end-to-end mesh (status=$STATUS, verts=$VERTS)"; FAIL=$((FAIL+1)); fi
FNAME_A=$(basename "$PREVIEW_A")
echo ""
echo "=== OWNERSHIP: user B must NOT see user A's stuff ==="
MODELS_B=$(curl -s -b "$JAR_B" "$BASE/api/models")
check_contains_not "B /api/models must not contain A's preview_path" "$PREVIEW_A" "$MODELS_B"
echo "  (B /api/models: $(echo "$MODELS_B" | head -c 200))"
CODE=$(curl -s -b "$JAR_B" -o /dev/null -w "%{http_code}" "$BASE/outputs/$FNAME_A")
check "B GET /outputs/<A's file>" "403" "$CODE"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/outputs/$FNAME_A")
check "Unauthenticated GET /outputs/<A's file>" "302" "$CODE"
CODE=$(curl -s -b "$JAR_B" -o /dev/null -w "%{http_code}" "$BASE/api/task/$TASK_A/status")
check "B GET /api/task/<A's task>/status" "403" "$CODE"
CODE=$(curl -s -b "$JAR_B" -o /dev/null -w "%{http_code}" "$BASE/api/logs")
check "B GET /api/logs (non-staff)" "403" "$CODE"
CODE=$(curl -s -b "$JAR_A" -o /dev/null -w "%{http_code}" "$BASE/api/logs")
check "A GET /api/logs (non-staff)" "403" "$CODE"
CODE=$(curl -s -b "$JAR_B" -o /dev/null -w "%{http_code}" "$BASE/api/thumbnail?path=$PREVIEW_A")
check "B GET /api/thumbnail?path=<A's file>" "403" "$CODE"
CODE=$(curl -s -b "$JAR_A" -o /dev/null -w "%{http_code}" "$BASE/api/thumbnail?path=$PREVIEW_A")
check "A GET /api/thumbnail?path=<own file> (must succeed)" "200" "$CODE"
CODE=$(curl -s -b "$JAR_A" -o /dev/null -w "%{http_code}" "$BASE/outputs/$FNAME_A")
check "A GET /outputs/<own file> (must succeed)" "200" "$CODE"
echo ""
echo "=== CATCH-ALL static route: sensitive files refused, safe files load ==="
for P in "/app.py" "/viewer/app.py" "/logs/users.db" "/.env" "/..%2Flogs%2Fusers.db" "/nonexistent.xyz"; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$P")
    check "GET $P" "404" "$CODE"
done
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/viewer/terms.html")
check "GET /viewer/terms.html (safe file must load)" "200" "$CODE"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/")
check "GET / (landing must load)" "200" "$CODE"
echo ""
echo "=== REMOVED routes: generate_url (SSRF) + generate_sync + /admin/api/* ==="
for URL in "http://127.0.0.1:5001/api/health" "http://169.254.169.254/latest/meta-data/" "http://localhost:5001/api/user/profile"; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/generate_url" -H "Content-Type: application/json" -d "{\"url\": \"$URL\"}")
    check "POST /api/generate_url (SSRF target $URL)" "405" "$CODE"
done
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/generate_url")
check "GET /api/generate_url" "404" "$CODE"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/generate_sync" -H "Content-Type: application/json" -d '{}')
check "POST /api/generate_sync" "405" "$CODE"
for P in "/admin/api/users" "/admin/api/login" "/admin/api/create-account"; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$P")
    check "GET $P" "404" "$CODE"
done
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/admin/api/create-account" -H "Content-Type: application/json" -d '{}')
check "POST /admin/api/create-account" "405" "$CODE"
echo ""
echo "=== CSRF: foreign Origin blocked, no-Origin + local Origin work ==="
CODE=$(curl -s -b "$JAR_A" -o /dev/null -w "%{http_code}" -X POST "$BASE/api/favorites/add" -H "Origin: https://evil.example" -H "Content-Type: application/json" -d "{\"model_path\": \"$PREVIEW_A\"}")
check "POST /api/favorites/add, foreign Origin" "403" "$CODE"
CODE=$(curl -s -b "$JAR_A" -o /dev/null -w "%{http_code}" -X POST "$BASE/api/favorites/add" -H "Content-Type: application/json" -d "{\"model_path\": \"$PREVIEW_A\"}")
if [ "$CODE" = "403" ]; then echo "  FAIL: POST /api/favorites/add, NO Origin (expected not-403, got 403)"; FAIL=$((FAIL+1));
else echo "  PASS: POST /api/favorites/add, NO Origin (got $CODE, not blocked as CSRF)"; PASS=$((PASS+1)); fi
CODE=$(curl -s -b "$JAR_A" -o /dev/null -w "%{http_code}" -X POST "$BASE/api/favorites/add" -H "Origin: http://127.0.0.1:5001" -H "Content-Type: application/json" -d "{\"model_path\": \"$PREVIEW_A\"}")
check "POST /api/favorites/add, local Origin (must succeed)" "200" "$CODE"
echo ""
echo "=== CSRF EXEMPTIONS still work (webhook + OAuth callback) ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/stripe/webhook" -H "Content-Type: application/json" -d '{}')
if [ "$CODE" = "403" ]; then echo "  FAIL: POST /api/stripe/webhook got 403 (CSRF exemption broken)"; FAIL=$((FAIL+1));
else echo "  PASS: POST /api/stripe/webhook not CSRF-blocked (got $CODE, expected 503 unconfigured)"; PASS=$((PASS+1)); fi
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/callback")
if [ "$CODE" = "403" ]; then echo "  FAIL: GET /auth/callback got 403"; FAIL=$((FAIL+1));
else echo "  PASS: GET /auth/callback not CSRF-blocked (got $CODE)"; PASS=$((PASS+1)); fi
echo ""
echo "=== SPSC stats visible ==="
curl -s -b "$JAR_A" "$BASE/api/queue/status" | "$PY" -c "import json,sys; d=json.load(sys.stdin); s=d.get('spsc') or {}; print('spsc:', s); print('PASS: spsc block present' if s.get('ring_capacity')==512 else 'FAIL: spsc block missing')" 2>/dev/null
echo ""
echo "=== SECRETS scan (filenames only, no values) ==="
echo "Files matching secret patterns (api_key/password/secret/token assignments, sk- keys):"
grep -rlE "(api[_-]?key|secret|password|passwd|private[_-]?key)[\"']?\s*[:=]\s*[\"'][^\"']{8,}" viewer/ src/ai3d/utils/ docs/ 2>/dev/null | head -20 || echo "(none found)"
echo "(Known: SETUP_COMPLETE.md + ADMIN_API.md hold plain-text secrets — Gary's call, rotation pending. Nothing new is to be copied or used.)"
echo ""
echo "=== Cleanup: delete test users A + B ==="
"$PY" -c "
import sqlite3
c = sqlite3.connect('logs/users.db')
for email, uid in (('safetyA@slushai.local', $UID_A), ('safetyB@slushai.local', $UID_B)):
    cur = c.execute('DELETE FROM users WHERE email = ? AND id = ?', (email, uid))
    print(f'deleted {email} (id {uid}): rows={cur.rowcount}')
c.commit()
for r in c.execute('SELECT id, email, username FROM users ORDER BY id'):
    print('remaining:', r)
"
rm -f "$JAR_A" "$JAR_B"
echo ""
echo "=== Phase I DONE — $(date) ==="
echo "SAFETY CHECKS: PASS=$PASS FAIL=$FAIL"
echo "Full log: $LOG"
echo "Live server stays RUNNING (pid $(cat /tmp/slushai-live-pid.txt 2>/dev/null))."
