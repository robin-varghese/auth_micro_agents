#!/bin/bash
# FinOptiAgents Platform - Local Deployment Script for Docker Desktop
# Uses Google Secret Manager for all configuration (NO .env files)

set -e  # Exit on error

echo "======================================"
echo "FinOptiAgents - Docker Desktop Deployment"
echo "======================================"
echo ""
echo "🔐 Configuration: Google Secret Manager"
echo "   All secrets will be loaded from GCP Secret Manager"
echo "   Project: vector-search-poc"
echo ""

# Check if user is authenticated with GCP
echo "Checking GCP authentication..."
if ! gcloud auth application-default print-access-token &>/dev/null; then
    echo "❌ ERROR: Not authenticated with GCP"
    echo ""
    echo "Please run:"
    echo "  gcloud auth application-default login"
    echo ""
    exit 1
fi

echo "✅ GCP authentication OK"
echo ""

# Function to get services from docker-compose.yml
get_services() {
    # Grep service names, remove leading spaces and colon
    grep "^  [a-z0-9_-]\+:" docker-compose.yml | sed 's/^  //' | sed 's/://'
}

# Check if specific services are requested via args
SERVICES=$@

if [ -z "$SERVICES" ]; then
    # Interactive Mode
    echo "📋 Available Services:"
    echo ""
    
    # Read services into array
    # mapfile -t SERVICE_LIST < <(get_services) # Bash 4+
    # POSIX compatible way:
    SERVICE_LIST=($(get_services))
    
    i=1
    for service in "${SERVICE_LIST[@]}"; do
        echo "  $i) $service"
        ((i++))
    done
    
    echo ""
    echo "  a) ALL Services"
    echo ""
    
    read -p "Select services to deploy (e.g., '1 3 5' or 'a'): " SELECTION
    echo ""
    
    if [ "$SELECTION" == "a" ] || [ "$SELECTION" == "all" ] || [ "$SELECTION" == "A" ]; then
        echo "🚀 Deploying ALL services..."
        
        echo "Stopping existing containers..."
        docker-compose down 2>/dev/null || true
        
        echo "Building Docker images..."
        docker-compose build
        
        echo "Starting services..."
        docker-compose up -d
        
    else
        SELECTED_SERVICES=""
        for num in $SELECTION; do
            # Validate if number
            if [[ "$num" =~ ^[0-9]+$ ]]; then
                # Adjust index (1-based to 0-based)
                if [ "$num" -ge 1 ] && [ "$num" -le "${#SERVICE_LIST[@]}" ]; then
                    index=$((num-1))
                    service_name="${SERVICE_LIST[$index]}"
                    SELECTED_SERVICES="$SELECTED_SERVICES $service_name"
                else
                    echo "⚠️ Warning: Invalid selection '$num' (ignored)"
                fi
            else
                # Allow passing service names directly in interactive mode too?
                # Maybe simple match
                 echo "⚠️ Warning: Invalid input '$num' (ignored)"
            fi
        done
        
        if [ -z "$SELECTED_SERVICES" ]; then
            echo "❌ No valid services selected. Exiting."
            exit 1
        fi
        
        echo "🚀 Deploying SELECTED services:$SELECTED_SERVICES"
        docker-compose up -d --build $SELECTED_SERVICES
    fi

else
    # Non-Interactive Mode (Arguments provided)
    echo "🚀 Deploying SPECIFIC services via arguments: $SERVICES"
    docker-compose up -d --build $SERVICES
fi

# Wait for services
echo ""
echo "Waiting for services to be ready..."
sleep 20

# Check status
echo ""
echo "Checking service status..."
docker-compose ps

# Display access information
echo ""
echo "======================================"
echo "✅ Deployment Complete!"
echo "======================================"
echo ""
echo "Access Points:"
echo "  - UI:             http://localhost:8501"
echo "  - APISIX:         http://localhost:9080"
echo "  - APISIX Admin:   http://localhost:9180"
echo "  - OPA:            http://localhost:8181"
echo ""
echo "Logs:"
echo "  docker-compose logs -f [service-name]"
echo ""
