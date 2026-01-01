#!/bin/bash
#
# Verify IAM Groups and Roles Setup
# Checks group creation, memberships, and role assignments
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Verify IAM Groups and Roles Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Get current project
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No GCP project set${NC}"
    exit 1
fi

echo -e "${YELLOW}GCP Project: ${PROJECT_ID}${NC}"
echo

# Get organization domain
echo -e "${YELLOW}Enter your organization domain (e.g., cloudroaster.com):${NC}"
read -r ORG_DOMAIN

if [ -z "$ORG_DOMAIN" ]; then
    echo -e "${RED}Error: Organization domain is required${NC}"
    exit 1
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}1. Checking Groups${NC}"
echo -e "${GREEN}========================================${NC}"
echo

declare -a GROUPS=(
    "finopti-gcloud-admins"
    "finopti-monitoring-admins"
    "finopti-developers"
)

for group_name in "${GROUPS[@]}"; do
    GROUP_EMAIL="${group_name}@${ORG_DOMAIN}"
    echo -e "${BLUE}Group: ${GROUP_EMAIL}${NC}"
    
    if gcloud identity groups describe "$GROUP_EMAIL" &>/dev/null; then
        echo -e "${GREEN}  ✓ Group exists${NC}"
        
        # List members
        echo -e "${YELLOW}  Members:${NC}"
        gcloud identity groups memberships list \
            --group-email="$GROUP_EMAIL" \
            --format="value(preferredMemberKey.id)" 2>/dev/null || echo "    (none or access denied)"
    else
        echo -e "${RED}  ✗ Group does not exist${NC}"
    fi
    echo
done

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}2. Checking IAM Policy Bindings${NC}"
echo -e "${GREEN}========================================${NC}"
echo

echo -e "${YELLOW}Fetching IAM policy for project ${PROJECT_ID}...${NC}"
echo

# Get IAM policy and filter for our groups
IAM_POLICY=$(gcloud projects get-iam-policy "$PROJECT_ID" --format=json 2>/dev/null)

for group_name in "${GROUPS[@]}"; do
    GROUP_EMAIL="${group_name}@${ORG_DOMAIN}"
    echo -e "${BLUE}Group: ${GROUP_EMAIL}${NC}"
    
    # Extract roles for this group
    ROLES=$(echo "$IAM_POLICY" | jq -r ".bindings[] | select(.members[]? | contains(\"group:${GROUP_EMAIL}\")) | .role" 2>/dev/null)
    
    if [ -n "$ROLES" ]; then
        echo -e "${GREEN}  ✓ Has role bindings:${NC}"
        echo "$ROLES" | while read -r role; do
            echo "    - $role"
        done
    else
        echo -e "${RED}  ✗ No role bindings found${NC}"
    fi
    echo
done

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}3. Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Count successful groups
SUCCESS_COUNT=0
for group_name in "${GROUPS[@]}"; do
    GROUP_EMAIL="${group_name}@${ORG_DOMAIN}"
    if gcloud identity groups describe "$GROUP_EMAIL" &>/dev/null; then
        ((SUCCESS_COUNT++))
    fi
done

echo "Groups created: ${SUCCESS_COUNT}/${#GROUPS[@]}"
echo

if [ "$SUCCESS_COUNT" -eq "${#GROUPS[@]}" ]; then
    echo -e "${GREEN}✓ All groups created successfully!${NC}"
else
    echo -e "${YELLOW}⚠ Some groups are missing. Run setup_iam_groups.sh${NC}"
fi

echo
echo -e "${YELLOW}Full IAM policy for project:${NC}"
echo "  gcloud projects get-iam-policy $PROJECT_ID"
echo
echo -e "${YELLOW}To view a specific group:${NC}"
echo "  gcloud identity groups describe GROUP_EMAIL@${ORG_DOMAIN}"
echo
echo -e "${YELLOW}To view group members:${NC}"
echo "  gcloud identity groups memberships list --group-email=GROUP_EMAIL@${ORG_DOMAIN}"
echo
