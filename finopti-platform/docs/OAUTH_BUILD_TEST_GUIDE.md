# Phase 2.2: OAuth Integration - Build & Test Guide

## ✅ Status: Ready to Deploy and Test

All OAuth code is implemented and tested. The UI now loads credentials from Secret Manager.

---

## Build and Deploy

### Step 1: Rebuild UI Container

The UI container needs to be rebuilt with the new dependencies:

```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform

# Rebuild just the UI service
docker-compose build ui

# Or rebuild all services
docker-compose build
```

### Step 2: Start All Services

```bash
# Start all services in detached mode
docker-compose up -d

# Check logs
docker-compose logs -f ui
```

### Step 3: Verify Services are Running

```bash
# Check service status
docker-compose ps

# Expected output: All services should be "Up"
```

---

## Testing OAuth Flow

### Test 1: Access the UI

1. **Open Browser:** http://localhost:8501

2. **Verify OAuth Status:**
   - Look in sidebar for: "✅ OAuth Enabled (Secret Manager)"
   - You should see two tabs: "Google OAuth" and "Simulated"

### Test 2: OAuth Login Flow

**Login with Admin User:**

1. Click "Google OAuth" tab
2. Click "🔐 Login with Google" button
3. **Browser redirects to Google**
4. Sign in with: `admin@cloudroaster.com`
5. Grant permissions
6. **Redirect back to Streamlit**
7. Verify you're logged in (green checkmark in sidebar)

**Expected Result:**
- ✅ User logged in as "Admin User"
- ✅ Email shown: admin@cloudroaster.com
- ✅ Auth method: "🔐 Google OAuth"

### Test 3: Test Authorization (GCloud Admin)

With admin@cloudroaster.com logged in:

1. **Try GCloud prompt:** "List all VMs"
   - ✅ Should work (admin has gcloud_admin role)

2. **Check response** in chat interface
   - Should see successful response from GCloud agent

### Test 4: Logout and Login as Monitoring User

1. Click "🚪 Logout"
2. Click "🔐 Login with Google" again
3. Sign in with: `monitoring@cloudroaster.com`

**Expected Result:**
- ✅ Logged in as "Monitoring User"  
- ✅ Email: monitoring@cloudroaster.com

### Test 5: Test Authorization (Monitoring Admin)

With monitoring@cloudroaster.com logged in:

1. **Try GCloud prompt:** "List all VMs"
   - ❌ Should be denied (monitoring user doesn't have gcloud_admin role)
   - Error message: "Access denied" or similar

2. **Try Monitoring prompt:** "Check CPU usage"
   - ✅ Should work (monitoring user has observability_admin role)

---

## Verification Checklist

### OAuth Configuration
- [ ] UI shows "✅ OAuth Enabled (Secret Manager)"
- [ ] "Login with Google" button appears
- [ ] Clicking button redirects to Google

### Authentication Flow
- [ ] Google login page appears
- [ ] Can sign in with admin@cloudroaster.com
- [ ] Can sign in with monitoring@cloudroaster.com
- [ ] Redirects back to Streamlit after auth
- [ ] User info displayed in sidebar
- [ ] JWT token in session state

### Authorization (OPA)
- [ ] admin@cloudroaster.com can access GCloud agent
- [ ] admin@cloudroaster.com CANNOT access Monitoring agent
- [ ] monitoring@cloudroaster.com can access Monitoring agent
- [ ] monitoring@cloudroaster.com CANNOT access GCloud agent

### Headers & Tokens
- [ ] Authorization header sent: `Bearer <JWT>`
- [ ] X-User-Email header sent: `user@domain.com`
- [ ] APISIX receives and validates JWT
- [ ] Orchestrator receives user email

---

## Troubleshooting

### Issue: "OAuth Disabled" message

**Check:**
```bash
# Verify Secret Manager credentials are accessible
cd ui
python3 -c "from oauth_helper import OAUTH_ENABLED, CREDENTIALS_SOURCE; print(f'Enabled: {OAUTH_ENABLED}, Source: {CREDENTIALS_SOURCE}')"
```

**Solution:** Ensure Secret Manager has credentials and permissions are set

### Issue: Redirect Loop

**Cause:** Redirect URI mismatch

**Check GCP Console:**
1. Go to: APIs & Services → Credentials
2. Check OAuth 2.0 Client
3. Verify redirect URI: `http://localhost:8501/_oauth_callback`

**Update if needed:**
```bash
# Correct URI should be:
http://localhost:8501/_oauth_callback
```

### Issue: "Token verification failed"

**Cause:** Client ID mismatch

**Check:**
```bash
# Verify Client ID in Secret Manager matches OAuth client
gcloud secrets versions access latest --secret=google-oauth-client-id --project=vector-search-poc
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
```

### Issue: Container Fails to Start

**Check logs:**
```bash
docker-compose logs ui
```

**Common issues:**
- Missing dependencies: Rebuild with `docker-compose build ui`
- Port conflict: Stop other services using port 8501
- Secret Manager permission: Check service account permissions

---

## Debug Commands

### Check OAuth Config in Container

```bash
# Exec into UI container
docker-compose exec ui /bin/sh

# Test OAuth config
python3 -c "from oauth_helper import OAUTH_ENABLED, CREDENTIALS_SOURCE; print(f'OAuth: {OAUTH_ENABLED}, Source: {CREDENTIALS_SOURCE}')"
```

### Check APISIX Logs

```bash
# View APISIX logs for JWT validation
docker-compose logs apisix | grep -i jwt
docker-compose logs apisix | grep -i auth
```

### Check Orchestrator Logs  

```bash
# View orchestrator logs for authorization
docker-compose logs orchestrator | grep -i authorization
docker-compose logs orchestrator | grep "X-User-Email"
```

### Check OPA Logs

```bash
# View OPA policy decisions
docker-compose logs opa | grep -i authz
```

---

## Expected End-to-End Flow

```
1. User clicks "Login with Google"
   ↓
2. Redirect to: https://accounts.google.com/o/oauth2/v2/auth?...
   ↓
3. User authenticates with Google
   ↓
4. Google redirects to: http://localhost:8501/_oauth_callback?code=...
   ↓
5. Streamlit exchanges code for JWT token
   ↓
6. Store JWT in st.session_state.id_token
   ↓
7. User sends message in chat
   ↓
8. UI sends POST to: http://apisix:9080/orchestrator/ask
   Headers:
   - Authorization: Bearer <JWT>
   - X-User-Email: user@domain.com
   ↓
9. APISIX validates JWT with Google public keys
   ↓
10. APISIX forwards to Orchestrator with headers
    ↓
11. Orchestrator calls OPA for authorization
    Input: {user_email, target_agent}
    ↓
12. OPA checks user_email against policy
    - admin@cloudroaster.com → gcloud_admin → allow gcloud
    - monitoring@cloudroaster.com → observability_admin → allow monitoring
    ↓
13. Return response (allow/deny) to user
```

---

## Next Steps After Testing

Once OAuth is working:

1. **Production Deployment:**
   - Use HTTPS instead of HTTP
   - Update redirect URI to production domain
   - Enable token refresh mechanism

2. **Security Enhancements:**
   - Add CSRF protection
   - Implement rate limiting
   - Enable comprehensive audit logging

3. **Advanced Features:**
   - Token refresh (tokens expire in 1 hour)
   - Remember user preference
   - Better error messages

---

## Quick Start Commands

```bash
# Full deployment
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform

# Rebuild and start
docker-compose build ui
docker-compose up -d

# View logs
docker-compose logs -f ui orchestrator opa apisix

# Open browser
open http://localhost:8501

# Test login
# Click "Login with Google"
# Sign in with admin@cloudroaster.com or monitoring@cloudroaster.com
```

---

**Status:** ✅ Ready to deploy and test  
**Estimated Test Time:** 15-20 minutes  
**Next:** Build container and test OAuth flow
