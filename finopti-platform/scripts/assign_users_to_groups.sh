#!/bin/bash
#
# Assign Users to IAM Groups
# Provisions users to the created IAM groups
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Assign Users to IAM Groups${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Get organization domain
echo -e "${YELLOW}Enter your organization domain (e.g., cloudroaster.com):${NC}"
read -r ORG_DOMAIN

if [ -z "$ORG_DOMAIN" ]; then
    echo -e "${RED}Error: Organization domain is required${NC}"
    exit 1
fi

echo
echo -e "${GREEN}Adding users to groups...${NC}"
echo

# Function to add user to group
add_user_to_group() {
    local user_email=$1
    local group_email=$2
    
    echo -e "${YELLOW}Adding ${user_email} to ${group_email}${NC}"
    
    # Check if membership exists
    if gcloud identity groups memberships describe \
        --group-email="$group_email" \
        --member-email="$user_email" &>/dev/null; then
        echo -e "${YELLOW}  → User already a member, skipping...${NC}"
    else
        if gcloud identity groups memberships add \
            --group-email="$group_email" \
            --member-email="$user_email" 2>/dev/null; then
            echo -e "${GREEN}  ✓ Added successfully${NC}"
        else
            echo -e "${RED}  ✗ Failed to add user${NC}"
            echo -e "${YELLOW}  → Ensure user exists and you have permissions${NC}"
        fi
    fi
}

# GCloud Admins Group
echo
echo -e "${GREEN}[1] FinOpti GCloud Admins${NC}"
GROUP_EMAIL="finopti-gcloud-admins@${ORG_DOMAIN}"

echo "Enter user emails (one per line, empty line to finish):"
while true; do
    read -r email
    if [ -z "$email" ]; then
        break
    fi
    add_user_to_group "$email" "$GROUP_EMAIL"
done

# Monitoring Admins Group
echo
echo -e "${GREEN}[2] FinOpti Monitoring Admins${NC}"
GROUP_EMAIL="finopti-monitoring-admins@${ORG_DOMAIN}"

echo "Enter user emails (one per line, empty line to finish):"
while true; do
    read -r email
    if [ -z "$email" ]; then
        break
    fi
    add_user_to_group "$email" "$GROUP_EMAIL"
done

# Developers Group
echo
echo -e "${GREEN}[3] FinOpti Developers${NC}"
GROUP_EMAIL="finopti-developers@${ORG_DOMAIN}"

echo "Enter user emails (one per line, empty line to finish):"
while true; do
    read -r email
    if [ -z "$email" ]; then
        break
    fi
    add_user_to_group "$email" "$GROUP_EMAIL"
done

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}User assignment complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "Next step: Assign IAM roles to groups"
echo "Run: ./assign_roles_to_groups.sh"
echo
