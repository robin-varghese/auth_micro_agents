#!/bin/bash
#
# GCP IAM Groups Setup Script
# Creates IAM groups for FinOptiAgents platform
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FinOptiAgents IAM Groups Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not found. Please install it first.${NC}"
    exit 1
fi

# Get current project
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No GCP project set. Run: gcloud config set project PROJECT_ID${NC}"
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
echo -e "${GREEN}Creating IAM Groups...${NC}"
echo

# Group definitions
declare -a GROUPS=(
    "finopti-gcloud-admins:FinOpti GCloud Admins:Users with full GCP compute access"
    "finopti-monitoring-admins:FinOpti Monitoring Admins:Users with monitoring and logging access"
    "finopti-developers:FinOpti Developers:Developer users with limited access"
)

# Create groups
for group_def in "${GROUPS[@]}"; do
    IFS=':' read -r group_name display_name description <<< "$group_def"
    GROUP_EMAIL="${group_name}@${ORG_DOMAIN}"
    
    echo -e "${YELLOW}Creating group: ${GROUP_EMAIL}${NC}"
    
    # Check if group already exists
    if gcloud identity groups describe "$GROUP_EMAIL" &>/dev/null; then
        echo -e "${YELLOW}  → Group already exists, skipping...${NC}"
    else
        # Try to create the group
        if gcloud identity groups create "$GROUP_EMAIL" \
            --display-name="$display_name" \
            --description="$description" \
            --organization="$ORG_DOMAIN" 2>/dev/null; then
            echo -e "${GREEN}  ✓ Created successfully${NC}"
        else
            echo -e "${RED}  ✗ Failed to create group${NC}"
            echo -e "${YELLOW}  → This might be because you don't have Google Workspace${NC}"
            echo -e "${YELLOW}  → Alternative: Create groups manually in Cloud Identity or use fallback authentication${NC}"
        fi
    fi
    echo
done

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Groups created! Next steps:${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "1. Add users to groups using: ./assign_users_to_groups.sh"
echo "2. Assign IAM roles using: ./assign_roles_to_groups.sh"
echo
echo -e "${YELLOW}Note: If group creation failed, you can:${NC}"
echo "  - Create groups manually in Cloud Identity Console"
echo "  - Use Google Workspace Admin Console (if available)"
echo "  - Use hardcoded group mappings in OPA policy (for testing)"
echo
