#!/bin/bash

echo "Starting Mesh & Observability Verification..."

# 1. Test Gateway Access (Should Succeed)
echo "Testing APISIX Gateway Access..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9080/orchestrator/health)
if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ Gateway Access: SUCCESS"
else
    echo "❌ Gateway Access: FAILED (Code: $HTTP_CODE)"
fi

# 2. Test Direct Access (Should Fail)
echo "Testing Direct Container Access (Mesh Enforcement)..."
# Check 15000 (Orchestrator)
if curl --connect-timeout 2 http://localhost:15000/health > /dev/null 2>&1; then
    echo "❌ Mesh Enforcement: FAILED (Port 15000 is open)"
else
    echo "✅ Mesh Enforcement: SUCCESS (Port 15000 is closed)"
fi

# Check 15001 (GCloud Agent)
if curl --connect-timeout 2 http://localhost:15001/health > /dev/null 2>&1; then
    echo "❌ Mesh Enforcement: FAILED (Port 15001 is open)"
else
    echo "✅ Mesh Enforcement: SUCCESS (Port 15001 is closed)"
fi

# Check 15002 (Monitoring Agent)
if curl --connect-timeout 2 http://localhost:15002/health > /dev/null 2>&1; then
    echo "❌ Mesh Enforcement: FAILED (Port 15002 is open)"
else
    echo "✅ Mesh Enforcement: SUCCESS (Port 15002 is closed)"
fi

# 3. Test Grafana Access (Should Succeed)
echo "Testing Grafana Access..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health)
if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ Grafana Access: SUCCESS"
else
    echo "❌ Grafana Access: FAILED (Code: $HTTP_CODE)"
fi
