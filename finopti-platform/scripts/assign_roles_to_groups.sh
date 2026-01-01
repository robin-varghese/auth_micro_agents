#!/bin/bash
#
# Assign IAM Roles to Groups
# Grants GCP IAM roles to the created groups
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Assign IAM Roles to Groups${NC}"
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

# Get organization domain
echo -e "${YELLOW}Enter your organization domain (e.g., cloudroaster.com):${NC}"
read -r ORG_DOMAIN

if [ -z "$ORG_DOMAIN" ]; then
    echo -e "${RED}Error: Organization domain is required${NC}"
    exit 1
fi

echo
echo -e "${GREEN}Assigning IAM roles to groups...${NC}"
echo

# Function to assign role to group
assign_role() {
    local group_email=$1
    local role=$2
    local description=$3
    
    echo -e "${YELLOW}Assigning ${role} to ${group_email}${NC}"
    echo -e "  ${description}"
    
    if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="group:${group_email}" \
        --role="$role" \
        --condition=None \
        --quiet 2>/dev/null; then
        echo -e "${GREEN}  ✓ Role assigned successfully${NC}"
    else
        echo -e "${RED}  ✗ Failed to assign role${NC}"
    fi
    echo
}

# GCloud Admins - Full compute access
echo -e "${GREEN}[1] GCloud Admins Group${NC}"
GROUP_EMAIL="finopti-gcloud-admins@${ORG_DOMAIN}"

assign_role "$GROUP_EMAIL" "roles/compute.admin" "Full Compute Engine administration"
assign_role "$GROUP_EMAIL" "roles/iam.serviceAccountUser" "Use service accounts for VM operations"
assign_role "$GROUP_EMAIL" "roles/monitoring.viewer" "View monitoring data"

# Monitoring Admins - Monitoring and logging access
echo -e "${GREEN}[2] Monitoring Admins Group${NC}"
GROUP_EMAIL="finopti-monitoring-admins@${ORG_DOMAIN}"

assign_role "$GROUP_EMAIL" "roles/monitoring.admin" "Full monitoring administration"
assign_role "$GROUP_EMAIL" "roles/logging.admin" "Full logging administration"
assign_role "$GROUP_EMAIL" "roles/compute.viewer" "View compute resources"

# Developers - Limited read access
echo -e "${GREEN}[3] Developers Group${NC}"
GROUP_EMAIL="finopti-developers@${ORG_DOMAIN}"

assign_role "$GROUP_EMAIL" "roles/compute.viewer" "View compute resources"
assign_role "$GROUP_EMAIL" "roles/monitoring.viewer" "View monitoring data"

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Role assignment complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "To verify the setup, run:"
echo "  ./verify_iam_setup.sh"
echo
echo "To view current IAM policy:"
echo "  gcloud projects get-iam-policy $PROJECT_ID"
echo
