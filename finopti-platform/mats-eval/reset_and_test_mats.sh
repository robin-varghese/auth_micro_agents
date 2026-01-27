#!/bin/bash

# MATS - Reset, Deploy, and Verify Script
# This script cleans up MATS containers, rebuilds images, and runs the test suite.

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# MATS Services
MATS_SERVICES=(
    "mats-orchestrator"
    "mats-sre-agent"
    "mats-investigator-agent"
    "mats-architect-agent"
)

echo -e "${YELLOW}🧹 Starting MATS Clean-up Phase...${NC}"

# 1. Stop and remove MATS containers
echo "Stopping MATS containers..."
docker-compose stop "${MATS_SERVICES[@]}" 2>/dev/null || true

echo "Removing MATS containers..."
docker-compose rm -f "${MATS_SERVICES[@]}" 2>/dev/null || true

# 2. Remove MATS images for fresh build
echo "Removing MATS images..."
for service in "${MATS_SERVICES[@]}"; do
    docker rmi ${service}:latest 2>/dev/null || true
    docker rmi finopti-platform-${service} 2>/dev/null || true
done

echo -e "${GREEN}✅ MATS Clean-up Complete.${NC}"
echo ""

echo -e "${YELLOW}🏗️  MATS Deployment Phase...${NC}"

# 3. Fresh Build and Deploy
echo "Building MATS images..."
docker-compose build "${MATS_SERVICES[@]}"

echo "Starting MATS services..."
docker-compose up -d "${MATS_SERVICES[@]}"

echo -e "${GREEN}✅ MATS Services Started.${NC}"
echo ""

echo -e "${YELLOW}⏳ MATS Health Check Phase...${NC}"

# 4. Wait for services to stabilize
WAIT_TIME=45
echo "Waiting ${WAIT_TIME} seconds for MATS stabilization..."
sleep $WAIT_TIME

# 5. Check Orchestrator Health
echo "Checking MATS Orchestrator health..."
max_retries=30
counter=0
while [ $counter -lt $max_retries ]; do
    if curl -f http://localhost:8080/health &>/dev/null; then
        echo -e "${GREEN}✅ MATS Orchestrator is healthy.${NC}"
        break
    fi
    echo "Waiting for orchestrator health... ($counter/$max_retries)"
    sleep 2
    counter=$((counter+1))
done

if [ $counter -eq $max_retries ]; then
    echo -e "${RED}❌ Timeout waiting for MATS Orchestrator health.${NC}"
    echo "Logs:"
    docker logs mats-orchestrator | tail -50
    exit 1
fi

# 6. Check Team Lead Agents Health
echo "Checking Team Lead Agents..."
for port in 8081 8082 8083; do
    if curl -f http://localhost:${port}/health &>/dev/null; then
        echo -e "${GREEN}✅ Agent on port ${port} is healthy${NC}"
    else
        echo -e "${YELLOW}⚠️ Agent on port ${port} not responding (may be normal if health endpoint not implemented)${NC}"
    fi
done

# Show running containers
docker-compose ps mats-orchestrator mats-sre-agent mats-investigator-agent mats-architect-agent

echo -e "${GREEN}✅ MATS Environment Ready.${NC}"
echo ""

echo -e "${YELLOW}🚀 MATS Verification Phase...${NC}"

# 7. Run MATS Test Suite
echo "Running MATS Test Suite..."
cd mats-eval
python3 run_mats_tests.py

# Capture exit code
TEST_EXIT_CODE=$?

cd ..

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}🎉 SUCCESS: MATS reset and verified successfully!${NC}"
else
    echo -e "${RED}❌ FAILURE: MATS test suite failed.${NC}"
fi

exit $TEST_EXIT_CODE
