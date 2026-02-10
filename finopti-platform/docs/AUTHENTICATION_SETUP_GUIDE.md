# FinOptiAgents - Authentication & Authorization Setup Guide

**Comprehensive guide for setting up OAuth, IAM, and Secret Manager integration**

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [GCP IAM Setup](#gcp-iam-setup)
4. [OAuth Secret Manager Configuration](#oauth-secret-manager-configuration)
5. [Build & Deployment](#build--deployment)
6. [Testing & Verification](#testing--verification)
7. [Troubleshooting](#troubleshooting)
8. [Security Best Practices](#security-best-practices)

---

## Overview

The FinOptiAgents platform uses a multi-layered authentication and authorization system:

- **Authentication**: Google OAuth 2.0 for user identity verification
- **Authorization**: OPA (Open Policy Agent) for role-based access control
- **Credential Management**: Google Secret Manager for secure OAuth credential storage
- **IAM**: Google Cloud IAM groups for role-to-user mappings

### Authentication Flow

```
User → Google OAuth → Streamlit UI → APISIX (JWT validation) → 
Orchestrator → OPA (authorization) → Sub-Agents
```

### Dual Auth Modes

1. **Google OAuth** (Production): Real Google authentication with JWT tokens
2. **Simulated Auth** (Testing): Quick user selection for agentic testing

---

## Prerequisites

Before starting, ensure you have:

### Required Access & Tools

- [x] **GCP Project**: Active project with billing enabled
- [x] **gcloud CLI**: Installed and authenticated (`gcloud auth login`)
- [x] **Required IAM Roles**:
  - `roles/resourcemanager.organizationAdmin` OR `roles/iam.organizationRoleAdmin` (for groups)
  - `roles/resourcemanager.projectIamAdmin` (for role assignments)
  - `roles/secretmanager.secretAccessor` (for Secret Manager)
- [x] **Cloud Identity or Google Workspace**: Configured for your organization domain
- [x] **Organization Domain**: Know your domain (e.g., `cloudroaster.com`)

### Verify Your Permissions

```bash
gcloud projects get-iam-policy $(gcloud config get-value project) \\
  --flatten="bindings[].members" \\
  --filter="bindings.members:user:$(gcloud config get-value account)" \\
  --format="table(bindings.role)"
```

### Billing Status

> **IMPORTANT**: Billing must be enabled on your GCP project for Secret Manager to work.

**Check billing status:**
```bash
gcloud billing projects describe $(gcloud config get-value project)
```

**If billing was previously disabled:**
- Payment issues will prevent Secret Manager access
- After payment, allow 5-10 minutes for services to restore
- You may need to restart containers to reload credentials

---

## GCP IAM Setup

### Step 1: Create IAM Groups

Create three security groups for role-based access control:

```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform
./scripts/setup_iam_groups.sh
```

**Input:** Organization domain (e.g., `cloudroaster.com`)

**Groups Created:**
- `finopti-gcloud-admins@cloudroaster.com` - Full GCP compute access
- `finopti-monitoring-admins@cloudroaster.com` - Monitoring/observability access
- `finopti-developers@cloudroaster.com` - Read-only development access

### Step 2: Assign Users to Groups

```bash
./scripts/assign_users_to_groups.sh
```

**Suggested User Assignments:**

| User Email | Group | Purpose |
|-----------|-------|---------|
| `admin@cloudroaster.com` | finopti-gcloud-admins | Full admin access for testing |
| `monitoring@cloudroaster.com` | finopti-monitoring-admins | Observability testing |
| `robin@cloudroaster.com` | finopti-developers | Limited developer access |

### Step 3: Assign Roles to Groups

```bash
./scripts/assign_roles_to_groups.sh
```

**Group-to-Role Mapping:**

| Group | IAM Roles | Purpose |
|-------|-----------|---------|
| **finopti-gcloud-admins** | `compute.admin`<br>`iam.serviceAccountUser`<br>`monitoring.viewer` | Full compute management |
| **finopti-monitoring-admins** | `monitoring.admin`<br>`logging.admin`<br>`compute.viewer` | Monitoring & logging |
| **finopti-developers** | `compute.viewer`<br>`monitoring.viewer` | Read-only access |

### Step 4: Verify IAM Setup

```bash
./scripts/verify_iam_setup.sh
```

**Manual Verification Commands:**

```bash
# Check if a group exists
gcloud identity groups describe finopti-gcloud-admins@cloudroaster.com

# List group members
gcloud identity groups memberships list \\
  --group-email="finopti-gcloud-admins@cloudroaster.com"

# Check IAM policy bindings
gcloud projects get-iam-policy $(gcloud config get-value project) \\
  --flatten="bindings[].members" \\
  --filter="bindings.members:finopti-*" \\
  --format="table(bindings.role, bindings.members)"
```

---

## OAuth Secret Manager Configuration

### Architecture

OAuth credentials are stored securely in Google Secret Manager, not in code or environment files.

**Benefits:**
- ✅ Encrypted at rest
- ✅ IAM-controlled access
- ✅ Audit logging enabled
- ✅ Automatic replication for HA
- ✅ No secrets in source code

### Create OAuth Client

1. Go to [Google Cloud Console - Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **"Create Credentials"** → **"OAuth 2.0 Client ID"**
3. **Application type**: Web application
4. **Name**: `finopti-streamlit-ui`
5. **Authorized redirect URIs**:
   - `http://localhost:8501/_oauth_callback` (development)
   - `https://your-domain.com/_oauth_callback` (production)
6. Click **"Create"**
7. **Save** Client ID and Client Secret

### Store Credentials in Secret Manager

```bash
# Set your project
export PROJECT_ID="vector-search-poc"

# Create Client ID secret
echo -n "YOUR_CLIENT_ID.apps.googleusercontent.com" | \\
  gcloud secrets create google-oauth-client-id \\
    --project=$PROJECT_ID \\
    --data-file=-

# Create Client Secret
echo -n "YOUR_CLIENT_SECRET" | \\
  gcloud secrets create google-oauth-client-secret \\
    --project=$PROJECT_ID \\
    --data-file=-

# Create full OAuth JSON (optional)
cat > /tmp/oauth.json << EOF
{
  "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
  "client_secret": "YOUR_CLIENT_SECRET",
  "redirect_uri": "http://localhost:8501/_oauth_callback"
}
EOF

gcloud secrets create google-oauth-credentials-json \\
  --project=$PROJECT_ID \\
  --data-file=/tmp/oauth.json

rm /tmp/oauth.json
```

### Verify Secrets

```bash
# List OAuth secrets
gcloud secrets list --project=vector-search-poc | grep oauth

# Access Client ID (testing only)
gcloud secrets versions access latest \\
  --secret=google-oauth-client-id \\
  --project=vector-search-poc

# Test Python integration
cd ui
python3 oauth_config.py
```

**Expected Output:**
```
✅ Successfully loaded OAuth credentials from Secret Manager
Client ID: 912533822336-dqcluei...
Client Secret: GOCSPX-21Z...
Redirect URI: http://localhost:8501/_oauth_callback
```

### Secrets Overview

| Secret Name | Contains | Purpose |
|-------------|----------|---------|
| `google-oauth-client-id` | OAuth Client ID | JWT token validation |
| `google-oauth-client-secret` | OAuth Client Secret | Token exchange |
| `google-oauth-credentials-json` | Full OAuth JSON | Backup/reference |

**Console Link:** https://console.cloud.google.com/security/secret-manager?project=vector-search-poc

---

## Build & Deployment

### Environment Configuration

The UI container is configured to use Secret Manager by default:

**docker-compose.yml (lines 442-450):**
```yaml
environment:
  APISIX_URL: "http://apisix:9080"
  USE_SECRET_MANAGER: "true"
  GOOGLE_CLOUD_PROJECT: "vector-search-poc"
  GOOGLE_PROJECT_ID: "vector-search-poc"
  # Fallback OAuth env vars (only used if Secret Manager fails)
  GOOGLE_OAUTH_CLIENT_ID: "${GOOGLE_OAUTH_CLIENT_ID:-}"
  GOOGLE_OAUTH_CLIENT_SECRET: "${GOOGLE_OAUTH_CLIENT_SECRET:-}"
  GOOGLE_OAUTH_REDIRECT_URI: "${GOOGLE_OAUTH_REDIRECT_URI:-}"
```

### Build Commands

```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform

# Rebuild UI container
docker-compose build ui

# Or rebuild all services
docker-compose build

# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f ui
```

### Verify Deployment

```bash
# Check service status
docker-compose ps

# Verify OAuth is enabled inside container
docker-compose exec ui python3 -c \\
  "import oauth_helper; print(oauth_helper.get_oauth_status())"
```

**Expected Output:**
```
✅ OAuth Enabled (Secret Manager)
```

### Restart After Billing Restoration

If your GCP account billing was disabled and then restored:

```bash
# Restart UI to reload Secret Manager credentials
docker-compose restart ui

# Verify OAuth status
docker-compose exec ui python3 -c \\
  "import oauth_helper; print(oauth_helper.get_oauth_status())"
```

---

## Testing & Verification

### Access the UI

1. **Open Browser:** http://localhost:8501
2. **Verify OAuth Status**: Look for dual auth tabs in sidebar
3. **Check OAuth Enabled**: Should show "✅ OAuth Enabled (Secret Manager)"

### Test 1: OAuth Login Flow (Admin User)

1. Click **"Google OAuth"** tab (default)
2. Click **"🔐 Login with Google"** button
3. Browser redirects to Google
4. Sign in with: `admin@cloudroaster.com`
5. Grant permissions
6. Redirect back to Streamlit

**Expected Result:**
- ✅ User logged in as "Admin User"
- ✅ Email shown: admin@cloudroaster.com
- ✅ Auth method: "🔐 Google OAuth"
- ✅ JWT token stored in session

### Test 2: GCloud Admin Authorization

With admin@cloudroaster.com logged in:

1. **Try GCloud prompt:** "List all VMs in my google cloud project vector-search-poc"
2. **Expected:** ✅ Request succeeds (admin has `gcloud_admin` role)
3. **Check response:** Should see VM list or "no VMs found"

### Test 3: Monitoring User

1. Click **"🚪 Logout"**
2. Click **"🔐 Login with Google"**
3. Sign in with: `monitoring@cloudroaster.com`

**Test Authorization:**
- **GCloud prompt:** "List all VMs" → ❌ Should be denied
- **Monitoring prompt:** "Show CPU metrics" → ✅ Should succeed

### Test 4: Simulated Auth (Agentic Testing)

1. Click **"Simulated"** tab
2. Select user from dropdown
3. Click **"🚀 Login (Simulated)"**

**Use Case:** Fast testing for agentic workflows without Google OAuth flow

### Verification Checklist

#### OAuth Configuration
- [ ] UI shows "✅ OAuth Enabled (Secret Manager)"
- [ ] "Login with Google" button appears
- [ ] Clicking button redirects to Google
- [ ] Both "Google OAuth" and "Simulated" tabs visible

#### Authentication Flow
- [ ] Google login page appears
- [ ] Can sign in with admin@cloudroaster.com
- [ ] Can sign in with monitoring@cloudroaster.com
- [ ] Redirects back to Streamlit after auth
- [ ] User info displayed in sidebar
- [ ] JWT token in session state

#### Authorization (OPA)
- [ ] admin@cloudroaster.com can access GCloud agent
- [ ] admin@cloudroaster.com CANNOT access Monitoring agent
- [ ] monitoring@cloudroaster.com can access Monitoring agent
- [ ] monitoring@cloudroaster.com CANNOT access GCloud agent

#### Headers & Tokens
- [ ] Authorization header sent: `Bearer <JWT>`
- [ ] X-User-Email header sent: `user@domain.com`
- [ ] APISIX receives and validates JWT
- [ ] Orchestrator receives user email

---

## Troubleshooting

### Issue: OAuth Login Not Showing

**Symptoms:**
- Only "Simulated" auth tab visible
- No "Google OAuth" tab
- No "Login with Google" button

**Root Cause:** OAuth credentials not accessible (most common: billing disabled)

**Solution:**

```bash
# 1. Check billing status
gcloud billing projects describe $(gcloud config get-value project)

# 2. If billing enabled, verify secrets exist
gcloud secrets list --project=vector-search-poc | grep oauth

# 3. Test OAuth config locally
cd ui
python3 oauth_config.py

# 4. Restart UI container to reload credentials
docker-compose restart ui

# 5. Verify OAuth enabled
docker-compose exec ui python3 -c \\
  "import oauth_helper; print(oauth_helper.get_oauth_status())"
```

**Expected after fix:**
```
✅ OAuth Enabled (Secret Manager)
```

### Issue: "Failed to access secret"

**Cause:** Secret Manager permission or authentication issue

**Fix:**
```bash
# Authenticate with application default credentials
gcloud auth application-default login

# Verify service account has access
gcloud projects get-iam-policy $(gcloud config get-value project) \\
  --flatten="bindings[].members" \\
  --filter="bindings.role:roles/secretmanager.secretAccessor"
```

### Issue: Redirect Loop

**Cause:** Redirect URI mismatch

**Check:**
1. Go to: APIs & Services → Credentials
2. Check OAuth 2.0 Client
3. Verify redirect URI: `http://localhost:8501/_oauth_callback`

**Update Secret Manager if needed:**
```bash
echo -n "http://localhost:8501/_oauth_callback" | \\
  gcloud secrets versions add google-oauth-redirect-uri \\
    --project=vector-search-poc \\
    --data-file=-
```

### Issue: "Token verification failed"

**Cause:** Client ID mismatch

**Check:**
```bash
# Verify Client ID in Secret Manager matches OAuth client
gcloud secrets versions access latest \\
  --secret=google-oauth-client-id \\
  --project=vector-search-poc

# Compare with OAuth client in Console
# https://console.cloud.google.com/apis/credentials
```

### Issue: Authorization Always Denied

**Check OPA Policy:**
```bash
# Verify OPA policy has correct user emails
docker-compose exec opa cat /policies/authz.rego | grep -A 2 "user_role"
```

**Expected:**
```rego
user_role["gcloud_admin"] {
    user_email == "admin@cloudroaster.com"
}
user_role["observability_admin"] {
    user_email == "monitoring@cloudroaster.com"
}
```

### Issue: "Permission denied" when creating groups

**Cause:** Missing Cloud Identity admin permissions

**Solutions:**
1. Request `roles/resourcemanager.organizationAdmin` from your org admin
2. Use Google Workspace Admin Console to create groups manually
3. Fallback: Use hardcoded group mappings in OPA (testing only)

### Issue: Container Fails to Start

**Check logs:**
```bash
docker-compose logs ui
```

**Common issues:**
- Missing dependencies: Rebuild with `docker-compose build ui`
- Port conflict: Stop other services using port 8501
- Secret Manager permission: Check service account permissions

### Debug Commands

```bash
# Check OAuth config in container
docker-compose exec ui python3 -c \\
  "from oauth_helper import OAUTH_ENABLED, CREDENTIALS_SOURCE; \\
   print(f'Enabled: {OAUTH_ENABLED}, Source: {CREDENTIALS_SOURCE}')"

# Check APISIX JWT validation logs
docker-compose logs apisix | grep -i jwt

# Check orchestrator authorization logs
docker-compose logs orchestrator | grep -i authorization

# Check OPA policy decisions
docker-compose logs opa | grep -i authz
```

---

## Security Best Practices

### Current Security Posture

✅ **Implemented:**
- Credentials stored in Secret Manager (encrypted at rest)
- IAM-controlled access to secrets
- No secrets in source code or .env files
- Audit logging enabled
- Automatic secret replication for HA
- Service account-only access
- Secret versioning

### Production Recommendations

🔒 **For Production Deployment:**

1. **Use HTTPS**
   - Update redirect URI to use HTTPS
   - Configure SSL/TLS certificates
   - Enable HSTS headers

2. **Token Management**
   - Implement token refresh (OAuth tokens expire in 1 hour)
   - Add token revocation support
   - Monitor token usage

3. **Additional Security**
   - Enable CSRF protection
   - Implement rate limiting
   - Add comprehensive audit logging
   - Use VPC Service Controls
   - Enable DLP for sensitive data

4. **Secret Rotation**
   ```bash
   # Rotate OAuth client secret annually
   # Create new OAuth client
   # Update Secret Manager
   # Update GCP Console credentials
   ```

### Secret Manager Access Control

**Principle of Least Privilege:**

```bash
# Grant read-only access to UI service account
gcloud secrets add-iam-policy-binding google-oauth-client-id \\
  --project=vector-search-poc \\
  --member="serviceAccount:ui-service@PROJECT.iam.gserviceaccount.com" \\
  --role="roles/secretmanager.secretAccessor"
```

---

## Expected End-to-End Flow

```
1. User opens http://localhost:8501
   ↓
2. UI checks oauth_helper.is_oauth_enabled()
   → Loads credentials from Secret Manager
   → If successful: OAUTH_ENABLED = True
   ↓
3. User sees dual auth tabs: "Google OAuth" | "Simulated"
   ↓
4. User clicks "🔐 Login with Google"
   ↓
5. Redirect to: https://accounts.google.com/o/oauth2/v2/auth?...
   ↓
6. User authenticates with Google
   ↓
7. Google redirects to: http://localhost:8501/_oauth_callback?code=...
   ↓
8. Streamlit (oauth_helper.py):
   - Exchanges code for JWT token
   - Verifies JWT signature
   - Stores JWT in st.session_state.id_token
   - Extracts user email and name
   ↓
9. User sends message in chat
   ↓
10. UI sends POST to: http://apisix:9080/orchestrator/ask
    Headers:
    - Authorization: Bearer <JWT>
    - X-User-Email: user@domain.com
    ↓
11. APISIX validates JWT with Google public keys
    ↓
12. APISIX forwards to Orchestrator with headers
    ↓
13. Orchestrator calls OPA for authorization
    Input: {user_email, target_agent}
    ↓
14. OPA checks user_email against policy:
    - admin@cloudroaster.com → gcloud_admin → allow gcloud
    - monitoring@cloudroaster.com → observability_admin → allow monitoring
    ↓
15. Return response (allow/deny) to user
```

---

## Quick Reference Commands

### Setup
```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform

# Full setup
./scripts/setup_iam_groups.sh
./scripts/assign_users_to_groups.sh
./scripts/assign_roles_to_groups.sh
./scripts/verify_iam_setup.sh
```

### Build & Deploy
```bash
# Rebuild and start
docker-compose build ui
docker-compose up -d

# View logs
docker-compose logs -f ui orchestrator opa apisix

# Verify OAuth
docker-compose exec ui python3 -c \\
  "import oauth_helper; print(oauth_helper.get_oauth_status())"
```

### Testing
```bash
# Open browser
open http://localhost:8501

# Test OAuth flow
# 1. Click "Login with Google"
# 2. Sign in with admin@cloudroaster.com or monitoring@cloudroaster.com
# 3. Test agent access
```

### Troubleshooting
```bash
# Check secrets
gcloud secrets list --project=vector-search-poc | grep oauth

# Test OAuth config
python3 ui/oauth_config.py

# Restart UI
docker-compose restart ui

# Check logs
docker-compose logs ui | grep -i oauth
```

---

## Cleanup (If Needed)

To completely remove the IAM and OAuth setup:

```bash
# Remove all role bindings
cd scripts

for group in finopti-gcloud-admins finopti-monitoring-admins finopti-developers; do
  # Remove role bindings
  gcloud projects remove-iam-policy-binding $(gcloud config get-value project) \\
    --member="group:${group}@cloudroaster.com" \\
    --all --quiet 2>/dev/null || true
  
  # Delete group
  gcloud identity groups delete "${group}@cloudroaster.com" \\
    --quiet 2>/dev/null || true
done

# Delete OAuth secrets (DANGEROUS - will break authentication)
gcloud secrets delete google-oauth-client-id --project=vector-search-poc --quiet
gcloud secrets delete google-oauth-client-secret --project=vector-search-poc --quiet
gcloud secrets delete google-oauth-credentials-json --project=vector-search-poc --quiet
```

---

## Document History

| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 2.0.0 | 2026-02-09 | Antigravity AI | Merged IAM, OAuth, and Secret Manager guides. Added billing restoration troubleshooting. |
| 1.0.0 | 2026-01-01 | Antigravity AI | Initial separate guides (IAM_SETUP_GUIDE, OAUTH_SECRET_MANAGER_GUIDE, OAUTH_BUILD_TEST_GUIDE) |

---

**Status:** ✅ Production Ready  
**Last Updated:** 2026-02-09  
**Project:** vector-search-poc  
**Platform:** FinOptiAgents
