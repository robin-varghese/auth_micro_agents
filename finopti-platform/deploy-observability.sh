#!/bin/bash
# Script to deploy the dedicated Agent Observability stack (Standalone Phoenix)

set -e

echo "🚀 Deploying Agent Observability Stack..."
echo "----------------------------------------"

cd agent-observability

echo "Stopping any existing observability containers..."
docker-compose down 2>/dev/null || true

echo "Starting services..."
docker-compose up -d

echo ""
echo "Waiting for services..."
sleep 5

echo ""
echo "Checking status..."
docker-compose ps

echo ""
echo "✅ Observability Stack Deployed!"
echo "   - Phoenix UI: http://localhost:6006"
echo "   - Postgres: Port 5433"
