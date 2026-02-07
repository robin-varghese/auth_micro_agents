#!/bin/bash
# Test script to verify routing logic fixes

set -e

echo "========================================="
echo "Testing Routing Logic Fixes"
echo "========================================="
echo ""

BASE_URL="http://localhost:8080"
USER_EMAIL="test@example.com"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function test_simple_operation() {
    echo -e "${YELLOW}Test 1: Simple operation - List VMs${NC}"
    echo "Expected: Route to gcloud_infrastructure_specialist"
    echo ""
    
    RESPONSE=$(curl -s -X POST "$BASE_URL/ask" \
        -H "Content-Type: application/json" \
        -H "X-User-Email: $USER_EMAIL" \
        -d '{"prompt": "List all VMs in project vector-search-poc"}')
    
    echo "Response: $RESPONSE"
    
    if echo "$RESPONSE" | grep -q "gcloud_infrastructure_specialist"; then
        echo -e "${GREEN}✓ PASS: Routed to gcloud agent${NC}"
    elif echo "$RESPONSE" | grep -q "mats-orchestrator"; then
        echo -e "${RED}✗ FAIL: Incorrectly routed to MATS${NC}"
        return 1
    else
        echo -e "${YELLOW}? UNKNOWN: Check response above${NC}"
    fi
    echo ""
}

function test_troubleshooting_request() {
    echo -e "${YELLOW}Test 2: Troubleshooting request${NC}"
    echo "Expected: Route to mats-orchestrator"
    echo ""
    
    RESPONSE=$(curl -s -X POST "$BASE_URL/ask" \
        -H "Content-Type: application/json" \
        -H "X-User-Email: $USER_EMAIL" \
        -d '{"prompt": "Why did my Cloud Run deployment fail?"}')
    
    echo "Response: $RESPONSE"
    
    if echo "$RESPONSE" | grep -q "mats-orchestrator"; then
        echo -e "${GREEN}✓ PASS: Routed to MATS${NC}"
    elif echo "$RESPONSE" | grep -q "gcloud_infrastructure_specialist"; then
        echo -e "${RED}✗ FAIL: Incorrectly routed to gcloud${NC}"
        return 1
    else
        echo -e "${YELLOW}? UNKNOWN: Check response above${NC}"
    fi
    echo ""
}

function test_storage_operation() {
    echo -e "${YELLOW}Test 3: Storage operation${NC}"
    echo "Expected: Route to storage agent (or gcloud if storage uses gcloud)"
    echo ""
    
    RESPONSE=$(curl -s -X POST "$BASE_URL/ask" \
        -H "Content-Type: application/json" \
        -H "X-User-Email: $USER_EMAIL" \
        -d '{"prompt": "Show me all GCS buckets"}')
    
    echo "Response: $RESPONSE"
    
    if echo "$RESPONSE" | grep -q "mats-orchestrator"; then
        echo -e "${RED}✗ FAIL: Incorrectly routed to MATS${NC}"
        return 1
    else
        echo -e "${GREEN}✓ PASS: Not routed to MATS${NC}"
    fi
    echo ""
}

function test_mats_guard() {
    echo -e "${YELLOW}Test 4: MATS guard - sending simple request directly to MATS${NC}"
    echo "Expected: MATS rejects with MISROUTED error"
    echo ""
    
    RESPONSE=$(curl -s -X POST "http://localhost:8084/troubleshoot" \
        -H "Content-Type: application/json" \
        -d '{
          "project_id": "vector-search-poc",
          "repo_url": "https://github.com/test/test",
          "user_request": "List all VMs in my project",
          "user_email": "test@example.com"
        }')
    
    echo "Response: $RESPONSE"
    
    if echo "$RESPONSE" | grep -qi "MISROUTED"; then
        echo -e "${GREEN}✓ PASS: MATS correctly rejected simple request${NC}"
    else
        echo -e "${RED}✗ FAIL: MATS did not reject simple request${NC}"
        return 1
    fi
    echo ""
}

function check_logs() {
    echo -e "${YELLOW}Checking orchestrator logs for routing decisions...${NC}"
    echo ""
    docker-compose logs --tail=50 orchestrator | grep -i "routing" || echo "No routing logs found"
    echo ""
}

# Run tests
echo "Starting tests..."
echo ""

test_simple_operation || true
test_troubleshooting_request || true
test_storage_operation || true
test_mats_guard || true

echo ""
echo "========================================="
echo "Detailed Logs"
echo "========================================="
check_logs

echo ""
echo "Test complete!"
