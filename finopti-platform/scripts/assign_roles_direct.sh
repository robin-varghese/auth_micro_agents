#!/bin/bash
#
# Direct IAM Role Assignment (No Groups Required)
# Assigns IAM roles directly to users for FinOptiAgents platform
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FinOptiAgents Direct IAM Setup${NC}"
echo -e "${GREEN}(No Cloud Identity Required)${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Get current project
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No GCP project set${NC}"
    exit 1
fi

echo -e "${YELLOW}Using GCP Project: ${PROJECT_ID}${NC}"
echo

# Function to assign role to user
assign_role_to_user() {
    local user_email=$1
    local role=$2
    local description=$3
    
    echo -e "${YELLOW}Assigning ${role} to ${user_email}${NC}"
    echo -e "  ${description}"
    
    if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="user:${user_email}" \
        --role="$role" \
        --condition=None \
        --quiet 2>/dev/null; then
        echo -e "${GREEN}  ✓ Role assigned successfully${NC}"
    else
        echo -e "${RED}  ✗ Failed to assign role${NC}"
    fi
    echo
}

echo -e "${GREEN}Assigning IAM roles directly to users...${NC}"
echo

# GCloud Admin User
echo -e "${GREEN}[1] GCloud Admin User${NC}"
echo "Enter the email for GCloud admin user (leave empty to skip):"
read -r GCLOUD_ADMIN_EMAIL

if [ -n "$GCLOUD_ADMIN_EMAIL" ]; then
    assign_role_to_user "$GCLOUD_ADMIN_EMAIL" "roles/compute.admin" "Full Compute Engine administration"
    assign_role_to_user "$GCLOUD_ADMIN_EMAIL" "roles/iam.serviceAccountUser" "Use service accounts for VM operations"
    assign_role_to_user "$GCLOUD_ADMIN_EMAIL" "roles/monitoring.viewer" "View monitoring data"
fi

# Monitoring Admin User
echo
echo -e "${GREEN}[2] Monitoring Admin User${NC}"
echo "Enter the email for Monitoring admin user (leave empty to skip):"
read -r MONITORING_ADMIN_EMAIL

if [ -n "$MONITORING_ADMIN_EMAIL" ]; then
    assign_role_to_user "$MONITORING_ADMIN_EMAIL" "roles/monitoring.admin" "Full monitoring administration"
    assign_role_to_user "$MONITORING_ADMIN_EMAIL" "roles/logging.admin" "Full logging administration"
    assign_role_to_user "$MONITORING_ADMIN_EMAIL" "roles/compute.viewer" "View compute resources"
fi

# Developer User (optional)
echo
echo -e "${GREEN}[3] Developer User (Optional)${NC}"
echo "Enter the email for Developer user (leave empty to skip):"
read -r DEVELOPER_EMAIL

if [ -n "$DEVELOPER_EMAIL" ]; then
    assign_role_to_user "$DEVELOPER_EMAIL" "roles/compute.viewer" "View compute resources"
    assign_role_to_user "$DEVELOPER_EMAIL" "roles/monitoring.viewer" "View monitoring data"
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}IAM Role Assignment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "Users configured:"
[ -n "$GCLOUD_ADMIN_EMAIL" ] && echo "  - GCloud Admin: $GCLOUD_ADMIN_EMAIL"
[ -n "$MONITORING_ADMIN_EMAIL" ] && echo "  - Monitoring Admin: $MONITORING_ADMIN_EMAIL"
[ -n "$DEVELOPER_EMAIL" ] && echo "  - Developer: $DEVELOPER_EMAIL"
echo
echo "Next steps:"
echo "  1. Update OPA policy to use user-based authorization"
echo "  2. Test OAuth flow with these users"
echo
