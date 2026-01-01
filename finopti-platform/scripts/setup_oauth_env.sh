#!/bin/bash
#
# Update .env with OAuth Credentials
# This script safely adds OAuth credentials to your .env file
#

set -e

CLIENT_SECRET_FILE="opa_policy/client_secret_912533822336-dqcluei73t6is1q3k26srvvj2khond8f.apps.googleusercontent.com.json"
ENV_FILE=".env"

echo "========================================="
echo "OAuth Credentials Setup"
echo "========================================="
echo

# Extract credentials from JSON
CLIENT_ID=$(cat "$CLIENT_SECRET_FILE" | grep -o '"client_id":"[^"]*' | cut -d'"' -f4)
CLIENT_SECRET=$(cat "$CLIENT_SECRET_FILE" | grep -o '"client_secret":"[^"]*' | cut -d'"' -f4)

echo "Extracted OAuth Credentials:"
echo "  Client ID: $CLIENT_ID"
echo "  Client Secret: ${CLIENT_SECRET:0:10}..."
echo

# Check if .env exists, if not create from template
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env from .env.template..."
    cp .env.template .env
fi

# Update or add OAuth credentials
echo "Updating .env with OAuth credentials..."

# Remove old OAuth entries if they exist
sed -i.bak '/^GOOGLE_OAUTH_CLIENT_ID=/d' .env
sed -i.bak '/^GOOGLE_OAUTH_CLIENT_SECRET=/d' .env
sed -i.bak '/^GOOGLE_OAUTH_REDIRECT_URI=/d' .env

# Add new OAuth entries
cat >> .env << EOF

# === Google OAuth Configuration (Added automatically) ===
GOOGLE_OAUTH_CLIENT_ID=$CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET=$CLIENT_SECRET
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501/_oauth_callback
EOF

echo "✓ OAuth credentials added to .env"
echo

# Move client secret to secure location
SECRETS_DIR="secrets"
mkdir -p "$SECRETS_DIR"

if [ -f "$CLIENT_SECRET_FILE" ]; then
    echo "Moving client secret to $SECRETS_DIR/..."
    mv "$CLIENT_SECRET_FILE" "$SECRETS_DIR/"
    echo "✓ Client secret moved to $SECRETS_DIR/"
fi

echo
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo
echo "OAuth credentials configured:"
echo "  ✓ GOOGLE_OAUTH_CLIENT_ID set"
echo "  ✓ GOOGLE_OAUTH_CLIENT_SECRET set"
echo "  ✓ GOOGLE_OAUTH_REDIRECT_URI set to http://localhost:8501/_oauth_callback"
echo
echo "Next steps:"
echo "  1. Implement OAuth in Streamlit UI (ui/app.py)"
echo "  2. Update docker-compose.yml to pass OAuth env vars"
echo "  3. Test OAuth flow with admin@cloudroaster.com"
echo
