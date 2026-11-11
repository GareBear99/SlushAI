#!/bin/bash
# Comprehensive test script for AI3DModeller CLI (Meshy-like functionality)

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  AI3DModeller CLI Test Suite${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Test function
test_command() {
    local test_name="$1"
    local command="$2"
    local expect_success="${3:-true}"
    
    echo -e "${YELLOW}Testing: ${test_name}${NC}"
    
    if eval "$command" > /dev/null 2>&1; then
        if [ "$expect_success" = "true" ]; then
            echo -e "${GREEN}✓ PASS${NC}"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            echo -e "${RED}✗ FAIL (expected failure but succeeded)${NC}"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    else
        if [ "$expect_success" = "false" ]; then
            echo -e "${GREEN}✓ PASS (correctly failed)${NC}"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            echo -e "${RED}✗ FAIL${NC}"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    fi
    echo ""
}

# Test 1: Server Status (should be running)
echo -e "${CYAN}=== Server Tests ===${NC}"
test_command "Server Status Check" "./ai3d.sh status"

# Test 2: List Models
echo -e "${CYAN}=== Model Management Tests ===${NC}"
test_command "List Models" "./ai3d.sh list"

# Test 3: Model Stats
if [ -f "outputs/example_preview.obj" ]; then
    test_command "Model Statistics" "./ai3d.sh stats outputs/example_preview.obj"
fi

# Test 4: Log Commands
echo -e "${CYAN}=== Log Management Tests ===${NC}"
test_command "View Recent Logs" "./ai3d.sh logs-view"
test_command "Search Logs" "./ai3d.sh logs-search 'Session'"

# Test 5: Screenshot Commands
echo -e "${CYAN}=== Screenshot Tests ===${NC}"
test_command "List Screenshots" "./ai3d.sh screenshots"
test_command "Screenshot Command" "./ai3d.sh screenshot"

# Test 6: API Endpoints
echo -e "${CYAN}=== API Tests ===${NC}"
test_command "API Models Endpoint" "curl -s http://localhost:5000/api/models | python -m json.tool > /dev/null"
test_command "API Logs Endpoint" "curl -s http://localhost:5000/api/logs | python -m json.tool > /dev/null"

# Test 7: Generation (optional, can take time)
if [ "$1" = "--full" ]; then
    echo -e "${CYAN}=== Generation Tests (Full Suite) ===${NC}"
    if [ -f "tests/demo_images/example.png" ]; then
        test_command "Generate from Image" "./ai3d.sh generate tests/demo_images/example.png"
    fi
fi

# Test 8: Invalid Commands
echo -e "${CYAN}=== Error Handling Tests ===${NC}"
test_command "Invalid Command" "./ai3d.sh invalid_command" "false"
test_command "Missing File Stats" "./ai3d.sh stats nonexistent.obj" "false"
test_command "Missing Search Term" "./ai3d.sh logs-search" "false"

# Test 9: Python CLI Interface
echo -e "${CYAN}=== Python CLI Tests ===${NC}"
test_command "CLI Help" "python -m src.ai3d.cli --help"
test_command "Pipeline Command Help" "python -m src.ai3d.cli pipeline --help"
test_command "Reconstruct Command Help" "python -m src.ai3d.cli reconstruct --help"
test_command "Texture Command Help" "python -m src.ai3d.cli texture --help"

# Summary
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Test Summary${NC}"
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}Passed: ${TESTS_PASSED}${NC}"
echo -e "${RED}Failed: ${TESTS_FAILED}${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed${NC}"
    exit 1
fi
