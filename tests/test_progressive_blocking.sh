#!/bin/bash
# Test Multi-Tier Progressive Blocking System (Stage 3 rewrite, #15).
#
# What changed and why: the old script drove the security layer over HTTP
# from localhost — but SecurityManager whitelists 127.0.0.1 BEFORE every
# blocking/rate-limit check, so no request from this script could ever be
# blocked, and its tier expectations contradicted the severity math anyway
# (one SQL injection carries severity 3, so the first offense lands on
# 'moderate', not 'warning'; the old script expected 'warning').
#
# The tier/escalation logic is now tested directly, with a non-localhost IP,
# by tests/test_security_units.py (14 unit tests, no server needed).
# This script runs that suite, plus the two HTTP checks that CAN pass from
# localhost: the server answers, and localhost is NOT blocked by design.
# Exit code is non-zero when anything fails (the old script always exited 0).
#
# Usage: ./tests/test_progressive_blocking.sh  (from the project root)

BASE_URL="${BASE_URL:-http://localhost:5000}"
BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILED=0

fail() { echo -e "${RED}✗ FAIL${NC}: $1"; FAILED=$((FAILED + 1)); }
pass() { echo -e "${GREEN}✓ PASS${NC}: $1"; }

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Multi-Tier Progressive Blocking Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# --- 1. Tier math + escalation (real assertions, fake non-localhost IP) ---
echo -e "${BLUE}=== 1. Blocking tiers + severity math (unit tests) ===${NC}"
PYBIN=".venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="python3"
if "$PYBIN" tests/test_security_units.py > /tmp/slushai-unit-tests.log 2>&1; then
    pass "SecurityManager unit tests pass (tiers, severity, UA, rate limit)"
    tail -3 /tmp/slushai-unit-tests.log
else
    fail "SecurityManager unit tests failed — see /tmp/slushai-unit-tests.log"
    tail -20 /tmp/slushai-unit-tests.log
fi
echo ""

# --- 2. HTTP smoke: server answers, localhost is not blocked by design ---
echo -e "${BLUE}=== 2. Localhost is whitelisted by design (HTTP) ===${NC}"
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/" 2>/dev/null || echo "000")
if [ "$code" = "200" ] || [ "$code" = "302" ]; then
    pass "GET / returns $code from localhost (whitelisted, not blocked)"
else
    fail "GET / returned $code (server down? start it first)"
fi

# An obvious attack payload from localhost must NOT get the IP blocked —
# the whitelist comes first by design. (The blocking itself is proven by
# the unit tests above, with a non-localhost IP.)
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/favorites/add" \
    -H "Content-Type: application/json" \
    -d '{"model_path": "x\x27 OR 1=1--"}' 2>/dev/null || echo "000")
if [ "$code" = "302" ] || [ "$code" = "200" ]; then
    pass "Attack-shaped POST from localhost is not IP-blocked (whitelist by design; auth wall returns $code)"
else
    fail "Attack-shaped POST from localhost returned $code (expected 302/200)"
fi
echo ""

# --- Summary ---
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Test Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Tier reference (security.py BLOCKING_TIERS + ATTACK_SEVERITY):"
echo -e "  1 violation  -> warning (5 min)"
echo -e "  2 violations -> minor (30 min)"
echo -e "  3 violations -> moderate (2 hours)"
echo -e "  5 violations -> serious (12 hours)"
echo -e "  7 violations -> severe (24 hours)"
echo -e "  30+ violations -> permanent"
echo -e "  Severity: SQLi/command/traversal +3, XSS +2, UA/rate-limit +1"
echo ""
if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}Progressive blocking test complete — all checks passed.${NC}"
    exit 0
else
    echo -e "${RED}Progressive blocking test FAILED ($FAILED failure(s)).${NC}"
    exit 1
fi
