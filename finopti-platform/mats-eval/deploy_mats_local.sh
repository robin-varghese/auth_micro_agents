#!/bin/bash
# MATS - Local Deployment Script for Docker Desktop
# Deploys ONLY MATS-related services (Orchestrator + Team Lead Agents)

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "======================================"
echo "MATS - Docker Desktop Deployment"
echo "======================================"
echo ""
echo "🔐 Configuration: Google Secret Manager"
echo "   All secrets will be loaded from GCP Secret Manager"
echo ""

# Check GCP authentication
echo "Checking GCP authentication..."
if ! gcloud auth application-default print-access-token &>/dev/null; then
    echo -e "${RED}❌ ERROR: Not authenticated with GCP${NC}"
    echo ""
    echo "Please run:"
    echo "  gcloud auth application-default login"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ GCP authentication OK${NC}"
echo ""

# MATS Services
MATS_SERVICES=(
    "mats-orchestrator"
    "mats-sre-agent" 
    "mats-investigator-agent"
    "mats-architect-agent"
)

# Check if specific services requested
SERVICES=$@

if [ -z "$SERVICES" ]; then
    # Interactive Mode
    echo "📋 MATS Services:"
    echo ""
    
    i=1
    for service in "${MATS_SERVICES[@]}"; do
        echo "  $i) $service"
        ((i++))
    done
    
    echo ""
    echo "  a) ALL MATS Services"
    echo ""
    
    read -p "Select services to deploy (e.g., '1 2' or 'a'): " SELECTION
    echo ""
    
    if [ "$SELECTION" == "a" ] || [ "$SELECTION" == "all" ] || [ "$SELECTION" == "A" ]; then
        echo -e "${YELLOW}🚀 Deploying ALL MATS services...${NC}"
        
        echo "Stopping existing MATS containers..."
        docker-compose stop "${MATS_SERVICES[@]}" 2>/dev/null || true
        docker-compose rm -f "${MATS_SERVICES[@]}" 2>/dev/null || true
        
        echo "Building MATS Docker images..."
        docker-compose build "${MATS_SERVICES[@]}"
        
        echo "Starting MATS services..."
        docker-compose up -d "${MATS_SERVICES[@]}"
        
    else
        SELECTED_SERVICES=""
        for num in $SELECTION; do
            if [[ "$num" =~ ^[0-9]+$ ]]; then
                if [ "$num" -ge 1 ] && [ "$num" -le "${#MATS_SERVICES[@]}" ]; then
                    index=$((num-1))
                    service_name="${MATS_SERVICES[$index]}"
                    SELECTED_SERVICES="$SELECTED_SERVICES $service_name"
                else
                    echo -e "${YELLOW}⚠️ Warning: Invalid selection '$num' (ignored)${NC}"
                fi
            else
                echo -e "${YELLOW}⚠️ Warning: Invalid input '$num' (ignored)${NC}"
            fi
        done
        
        if [ -z "$SELECTED_SERVICES" ]; then
            echo -e "${RED}❌ No valid services selected. Exiting.${NC}"
            exit 1
        fi
        
        echo -e "${YELLOW}🚀 Deploying SELECTED services:$SELECTED_SERVICES${NC}"
        docker-compose up -d --build $SELECTED_SERVICES
    fi

else
    # Non-Interactive Mode
    echo -e "${YELLOW}🚀 Deploying SPECIFIC services: $SERVICES${NC}"
    docker-compose up -d --build $SERVICES
fi

# Wait for services
echo ""
echo "Waiting for MATS services to be ready..."
sleep 30

# Check orchestrator health
echo ""
echo "Checking MATS Orchestrator health..."
max_retries=20
counter=0
while [ $counter -lt $max_retries ]; do
    if curl -f http://localhost:8080/health &>/dev/null; then
        echo -e "${GREEN}✅ MATS Orchestrator is healthy${NC}"
        break
    fi
    echo "Waiting for orchestrator... ($counter/$max_retries)"
    sleep 3
    counter=$((counter+1))
done

if [ $counter -eq $max_retries ]; then
    echo -e "${RED}❌ Timeout waiting for orchestrator health${NC}"
    echo "Check logs: docker logs mats-orchestrator"
    exit 1
fi

# Check status
echo ""
echo "Checking MATS service status..."
docker-compose ps mats-orchestrator mats-sre-agent mats-investigator-agent mats-architect-agent

# Display access information
echo ""
echo "======================================"
echo -e "${GREEN}✅ MATS Deployment Complete!${NC}"
echo "======================================"
echo ""
echo "MATS Services:"
echo "  - Orchestrator:   http://localhost:8080"
echo "  - SRE Agent:      http://localhost:8081"
echo "  - Investigator:   http://localhost:8082"
echo "  - Architect:      http://localhost:8083"
echo ""
echo "Endpoints:"
echo "  - Health:         http://localhost:8080/health"
echo "  - Troubleshoot:   POST http://localhost:8080/troubleshoot"
echo "  - Via APISIX:     POST http://localhost:9080/mats/orchestrator/troubleshoot"
echo ""
echo "Logs:"
echo "  docker logs -f mats-orchestrator"
echo "  docker logs -f mats-sre-agent"
echo "  docker logs -f mats-investigator-agent"
echo "  docker logs -f mats-architect-agent"
echo ""
