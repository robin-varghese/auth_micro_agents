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

# Stop any existing containers
echo "Stopping existing containers..."
docker-compose down 2>/dev/null || true

# Build images
echo ""
echo "Building Docker images..."
docker-compose build

# Start services
echo ""
echo "Starting services..."
docker-compose up -d

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
echo "  - APISIX Dashboard: http://localhost:9000"
echo "  - OPA:            http://localhost:8181"
echo ""
echo "Test Users:"
echo "  - admin@cloudroaster.com (GCloud access)"
echo "  - monitoring@cloudroaster.com (Monitoring access)"
echo "  - robin@cloudroaster.com (No access - for testing denial)"
echo ""
echo "View logs:"
echo "  docker-compose logs -f [service-name]"
echo ""
echo "Stop platform:"
echo "  docker-compose down"
echo ""
echo "📝 Note: All configuration is loaded from Secret Manager"
echo "   No .env file is used or required."
echo ""
