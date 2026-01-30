#!/bin/bash

# FinOpti Platform - Reset, Deploy, and Verify Script
# This script cleans up the local Docker environment for the platform, 
# rebuilds containers, and runs the verification suite.

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🧹 Starting Clean-up Phase...${NC}"

# 1. Cleaner Teardown
# -v: Remove volumes (database data, etc.)
# --remove-orphans: Remove containers not defined in the compose file
# --rmi local: Remove images built locally by compose (forces fresh build)
echo "Stopping and removing containers, networks, volumes, and local images..."
docker-compose down -v --remove-orphans --rmi local

# Optional: Prune build cache if you want a TRULY fresh start (uncomment if needed)
# echo "Pruning build cache..."
# docker builder prune -f

echo -e "${GREEN}✅ Clean-up Complete.${NC}"
echo ""

echo -e "${YELLOW}🏗️  Deployment Phase...${NC}"

# 2. Fresh Build and Deploy
# --build: Build images before starting containers
echo "Building and starting services..."
docker-compose up -d --build

echo -e "${GREEN}✅ Services Started.${NC}"
echo ""

echo -e "${YELLOW}⏳ Health Check Phase...${NC}"

# 3. Wait for Health
# We increase the wait time to allow for the "Cold Start" storm to settle.
WAIT_TIME=90
echo "Waiting ${WAIT_TIME} seconds for general stabilization..."
sleep $WAIT_TIME

# Explicitly wait for Postgres to be healthy to avoid db_agent timeouts
echo "Checking Postgres health..."
max_retries=30
counter=0
while [ $counter -lt $max_retries ]; do
    if docker inspect --format '{{.State.Health.Status}}' finopti-db-postgres | grep -q "healthy"; then
        echo -e "${GREEN}✅ Postgres is healthy.${NC}"
        break
    fi
    echo "Waiting for Postgres to be healthy... ($counter/$max_retries)"
    sleep 5
    counter=$((counter+1))
done

if [ $counter -eq $max_retries ]; then
    echo -e "${RED}❌ Timeout waiting for Postgres health.${NC}"
    exit 1
fi

# Optional: Check docker ps to show user what's running
docker-compose ps

echo -e "${GREEN}✅ Environment Ready.${NC}"
echo ""

echo -e "${YELLOW}🚀 Verification Phase...${NC}"

# 4. Run Test Suite
echo "Running Test Suite (tests/run_suite.py)..."
python3 tests/run_suite.py

# Capture exit code of the test suite
TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}🎉 SUCCESS: Platform reset and verified successfully!${NC}"
else
    echo -e "${RED}❌ FAILURE: Test suite failed.${NC}"
fi

exit $TEST_EXIT_CODE
