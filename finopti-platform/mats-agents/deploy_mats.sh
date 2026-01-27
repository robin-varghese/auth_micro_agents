#!/bin/bash
# MATS v2.0 - Build and Deploy Script

set -e

echo "🚀 MATS v2.0 Build & Deploy Script"
echo "==================================="

# Colors
GREEN='\033[0.32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$PROJECT_ROOT"

echo -e "${YELLOW}Project Root: $PROJECT_ROOT${NC}"

# Load environment
if [ -f .env ]; then
    echo -e "${GREEN}✓ Loading .env file${NC}"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${RED}✗ No .env file found!${NC}"
    echo "Please create .env with required variables:"
    echo "  - GOOGLE_API_KEY"
    echo "  - GCP_PROJECT_ID"
    echo "  - GITHUB_PERSONAL_ACCESS_TOKEN"
    echo "  - MATS_RCA_BUCKET"
    exit 1
fi

# Pre-flight Checks
echo ""
echo "Pre-flight checks..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker installed${NC}"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}✗ Docker Compose not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose installed${NC}"

# Check gcloud config
if [ ! -d "$HOME/.config/gcloud" ]; then
    echo -e "${YELLOW}⚠ gcloud config not found at ~/.config/gcloud${NC}"
    echo "Run: gcloud auth login && gcloud auth application-default login"
fi

# Check Sequential Thinking MCP image
if ! docker images | grep -q "sequentialthinking"; then
    echo -e "${YELLOW}⚠ Sequential Thinking MCP image not found${NC}"
    echo "Please build or pull: sequentialthinking"
fi

# Build MATS Services
echo ""
echo "Building MATS services..."

echo -e "${YELLOW}Building mats-orchestrator...${NC}"
docker build -t mats-orchestrator:latest \
    -f mats-agents/mats-orchestrator/Dockerfile .
echo -e "${GREEN}✓ mats-orchestrator built${NC}"

# Optional: Build/rebuild team lead agents if needed
# docker build -t mats-sre-agent:latest -f mats-agents/mats-sre-agent/Dockerfile .
# docker build -t mats-investigator-agent:latest -f mats-agents/mats-investigator-agent/Dockerfile .
# docker build -t mats-architect-agent:latest -f mats-agents/mats-architect-agent/Dockerfile .

# Start Services
echo ""
echo "Starting MATS services..."
docker-compose up -d mats-orchestrator

# Wait for health check
echo ""
echo "Waiting for orchestrator to be healthy..."
for i in {1..30}; do
    if curl -f http://localhost:8080/health &> /dev/null; then
        echo -e "${GREEN}✓ Orchestrator is healthy${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Orchestrator failed to start${NC}"
        docker logs mats-orchestrator
        exit 1
    fi
    echo -n "."
    sleep 2
done

# Display Status
echo ""
echo "==================================="
echo -e "${GREEN}✓ MATS v2.0 Deployment Complete${NC}"
echo "==================================="
echo ""
echo "Services:"
echo "  Orchestrator: http://localhost:8080"
echo "  Health Check: http://localhost:8080/health"
echo ""
echo "Troubleshoot endpoint:"
echo "  POST http://localhost:8080/troubleshoot"
echo ""
echo "View logs:"
echo "  docker logs -f mats-orchestrator"
echo ""
echo "Run verification:"
echo "  cd mats-agents/mats-orchestrator"
echo "  python verify_agent.py"
echo ""
