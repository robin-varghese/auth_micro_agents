#!/bin/bash

# FinOptiAgents Platform - Quick Start Script
# This script helps you get started with the FinOptiAgents platform

set -e

echo "========================================="
echo "FinOptiAgents Platform - Quick Start"
echo "========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is running
echo "Checking prerequisites..."
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker Desktop and try again.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}⚠️  docker-compose command not found. Trying 'docker compose' instead...${NC}"
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo -e "${GREEN}✅ Docker Compose is available${NC}"
echo ""

# Function to show menu
show_menu() {
    echo "========================================="
    echo "What would you like to do?"
    echo "========================================="
    echo "1) Start all services"
    echo "2) Stop all services"
    echo "3) View service status"
    echo "4) View logs (all services)"
    echo "5) View logs (specific service)"
    echo "6) Run automated tests"
    echo "7) Clean up (stop and remove containers)"
    echo "8) Exit"
    echo ""
}

# Function to start services
start_services() {
    echo -e "${YELLOW}Starting all services...${NC}"
    $DOCKER_COMPOSE up -d
    echo ""
    echo -e "${GREEN}✅ Services started successfully!${NC}"
    echo ""
    echo "Waiting for services to be ready (30 seconds)..."
    sleep 30
    echo ""
    $DOCKER_COMPOSE ps
    echo ""
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}🚀 Platform is ready!${NC}"
    echo -e "${GREEN}=========================================${NC}"
    echo ""
    echo "Access points:"
    echo "  - Streamlit UI:      http://localhost:8501"
    echo "  - APISIX Gateway:    http://localhost:9080"
    echo "  - APISIX Dashboard:  http://localhost:9000"
    echo "  - OPA:               http://localhost:8181"
    echo ""
}

# Function to stop services
stop_services() {
    echo -e "${YELLOW}Stopping all services...${NC}"
    $DOCKER_COMPOSE stop
    echo -e "${GREEN}✅ Services stopped${NC}"
}

# Function to view status
view_status() {
    echo "Service Status:"
    echo "========================================="
    $DOCKER_COMPOSE ps
}

# Function to view all logs
view_all_logs() {
    echo -e "${YELLOW}Showing logs (Ctrl+C to exit)...${NC}"
    $DOCKER_COMPOSE logs -f --tail=50
}

# Function to view specific service logs
view_service_logs() {
    echo "Available services:"
    echo "  - orchestrator"
    echo "  - gcloud_agent"
    echo "  - monitoring_agent"
    echo "  - gcloud_mcp"
    echo "  - monitoring_mcp"
    echo "  - apisix"
    echo "  - opa"
    echo "  - ui"
    echo ""
    read -p "Enter service name: " service_name
    echo -e "${YELLOW}Showing logs for $service_name (Ctrl+C to exit)...${NC}"
    $DOCKER_COMPOSE logs -f --tail=100 "$service_name"
}

# Function to run automated tests
run_tests() {
    echo "========================================="
    echo "Running Automated Tests"
    echo "========================================="
    echo ""
    
    echo "Test 1: OPA Authorization - Admin accessing GCloud (Should ALLOW)"
    curl -s -X POST http://localhost:8181/v1/data/finopti/authz \
      -H "Content-Type: application/json" \
      -d '{"input": {"user_email": "admin@cloudroaster.com", "target_agent": "gcloud"}}' | python3 -m json.tool
    echo ""
    
    echo "Test 2: OPA Authorization - Monitoring user accessing GCloud (Should DENY)"
    curl -s -X POST http://localhost:8181/v1/data/finopti/authz \
      -H "Content-Type: application/json" \
      -d '{"input": {"user_email": "monitoring@cloudroaster.com", "target_agent": "gcloud"}}' | python3 -m json.tool
    echo ""
    
    echo "Test 3: Orchestrator - Admin creating VM (Should SUCCEED)"
    curl -s -X POST http://localhost:9080/orchestrator/ask \
      -H "X-User-Email: admin@cloudroaster.com" \
      -H "Content-Type: application/json" \
      -d '{"prompt": "create a VM instance"}' | python3 -m json.tool
    echo ""
    
    echo "Test 4: Orchestrator - Monitoring user checking CPU (Should SUCCEED)"
    curl -s -X POST http://localhost:9080/orchestrator/ask \
      -H "X-User-Email: monitoring@cloudroaster.com" \
      -H "Content-Type: application/json" \
      -d '{"prompt": "check CPU usage"}' | python3 -m json.tool
    echo ""
    
    echo "Test 5: Orchestrator - Unauthorized access (Should FAIL with 403)"
    curl -s -X POST http://localhost:9080/orchestrator/ask \
      -H "X-User-Email: monitoring@cloudroaster.com" \
      -H "Content-Type: application/json" \
      -d '{"prompt": "create a VM"}' | python3 -m json.tool
    echo ""
    
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}Tests completed!${NC}"
    echo -e "${GREEN}=========================================${NC}"
}

# Function to clean up
cleanup() {
    echo -e "${YELLOW}Stopping and removing all containers...${NC}"
    read -p "This will remove all containers and volumes. Continue? (y/N): " confirm
    if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
        $DOCKER_COMPOSE down -v
        echo -e "${GREEN}✅ Cleanup completed${NC}"
    else
        echo "Cleanup cancelled"
    fi
}

# Main menu loop
while true; do
    show_menu
    read -p "Enter your choice (1-8): " choice
    echo ""
    
    case $choice in
        1)
            start_services
            ;;
        2)
            stop_services
            ;;
        3)
            view_status
            ;;
        4)
            view_all_logs
            ;;
        5)
            view_service_logs
            ;;
        6)
            run_tests
            ;;
        7)
            cleanup
            ;;
        8)
            echo "Exiting. Thank you!"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice. Please enter 1-8.${NC}"
            ;;
    esac
    
    echo ""
    read -p "Press Enter to continue..."
    clear
done
