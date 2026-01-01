#!/bin/bash
#
# Add OAuth Credentials to Google Secret Manager
# This script creates secrets for OAuth credentials
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Add OAuth Credentials to Secret Manager${NC}"
echo -e "${GREEN}========================================${NC}"
echo

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
echo -e "${YELLOW}Using GCP Project: ${PROJECT_ID}${NC}"
echo

# Check if Secret Manager API is enabled
echo "Checking Secret Manager API..."
if ! gcloud services list --enabled 2>/dev/null | grep -q secretmanager; then
    echo -e "${YELLOW}Enabling Secret Manager API...${NC}"
    gcloud services enable secretmanager.googleapis.com || {
        echo -e "${RED}Failed to enable Secret Manager API${NC}"
        echo -e "${YELLOW}Please enable it manually in GCP Console:${NC}"
        echo "https://console.cloud.google.com/apis/library/secretmanager.googleapis.com"
        exit 1
    }
    echo "Waiting for API to be enabled..."
    sleep 5
fi

# Extract credentials
CLIENT_SECRET_FILE="secrets/client_secret_912533822336-dqcluei73t6is1q3k26srvvj2khond8f.apps.googleusercontent.com.json"

if [ ! -f "$CLIENT_SECRET_FILE" ]; then
    echo -e "${RED}Error: Client secret file not found at $CLIENT_SECRET_FILE${NC}"
    exit 1
fi

CLIENT_ID=$(cat "$CLIENT_SECRET_FILE" | grep -o '"client_id":"[^"]*' | cut -d'"' -f4)
CLIENT_SECRET=$(cat "$CLIENT_SECRET_FILE" | grep -o '"client_secret":"[^"]*' | cut -d'"' -f4)

echo "Extracted OAuth credentials from JSON file"
echo

# Create secrets
echo -e "${GREEN}[1/3] Creating secret: google-oauth-client-id${NC}"
if gcloud secrets describe google-oauth-client-id &>/dev/null; then
    echo -e "${YELLOW}  → Secret already exists, creating new version...${NC}"
    echo -n "$CLIENT_ID" | gcloud secrets versions add google-oauth-client-id --data-file=-
else
    echo -n "$CLIENT_ID" | gcloud secrets create google-oauth-client-id \
        --data-file=- \
        --replication-policy=automatic \
        --labels=app=finoptiagents,component=oauth
fi
echo -e "${GREEN}  ✓ Client ID stored${NC}"
echo

echo -e "${GREEN}[2/3] Creating secret: google-oauth-client-secret${NC}"
if gcloud secrets describe google-oauth-client-secret &>/dev/null; then
    echo -e "${YELLOW}  → Secret already exists, creating new version...${NC}"
    echo -n "$CLIENT_SECRET" | gcloud secrets versions add google-oauth-client-secret --data-file=-
else
    echo -n "$CLIENT_SECRET" | gcloud secrets create google-oauth-client-secret \
        --data-file=- \
        --replication-policy=automatic \
        --labels=app=finoptiagents,component=oauth
fi
echo -e "${GREEN}  ✓ Client Secret stored${NC}"
echo

echo -e "${GREEN}[3/3] Creating secret: google-oauth-credentials-json${NC}"
if gcloud secrets describe google-oauth-credentials-json &>/dev/null; then
    echo -e "${YELLOW}  → Secret already exists, creating new version...${NC}"
    gcloud secrets versions add google-oauth-credentials-json --data-file="$CLIENT_SECRET_FILE"
else
    gcloud secrets create google-oauth-credentials-json \
        --data-file="$CLIENT_SECRET_FILE" \
        --replication-policy=automatic \
        --labels=app=finoptiagents,component=oauth
fi
echo -e "${GREEN}  ✓ Full credentials JSON stored${NC}"
echo

# Grant access to compute service account (if it exists)
COMPUTE_SA="${PROJECT_ID%%:*}@appspot.gserviceaccount.com"
echo -e "${YELLOW}Granting access to Compute Engine service account...${NC}"
for secret in google-oauth-client-id google-oauth-client-secret google-oauth-credentials-json; do
    gcloud secrets add-iam-policy-binding "$secret" \
        --member="serviceAccount:${COMPUTE_SA}" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet 2>/dev/null || true
done

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Secrets Created Successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "Created secrets:"
echo "  ✓ google-oauth-client-id"
echo "  ✓ google-oauth-client-secret"
echo "  ✓ google-oauth-credentials-json"
echo
echo "View secrets in GCP Console:"
echo "https://console.cloud.google.com/security/secret-manager?project=${PROJECT_ID}"
echo
echo "To access secrets in your application:"
echo "  gcloud secrets versions access latest --secret=google-oauth-client-id"
echo "  gcloud secrets versions access latest --secret=google-oauth-client-secret"
echo
