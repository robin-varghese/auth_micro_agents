# Google OAuth Setup Guide - Phase 2

## 📋 Overview

This guide walks through creating Google OAuth 2.0 credentials for the FinOptiAgents Platform. The platform currently supports **hybrid authentication**:
- **OAuth Mode**: Real Google authentication (when credentials configured)
- **Simulated Mode**: Development authentication (fallback when no credentials)

---

## 🔐 Step 1: Create OAuth 2.0 Credentials

### 1.1 Navigate to GCP Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project: **vector-search-poc** (or your project)
3. Navigate to: **APIs & Services** → **Credentials**

### 1.2 Create OAuth Client ID

1. Click **+ CREATE CREDENTIALS**
2. Select **OAuth 2.0 Client ID**
3. If prompted, configure OAuth consent screen first (see Step 2)

### 1.3 Configure OAuth Client

**Application type**: Web application  
**Name**: FinOptiAgents Platform  
**Authorized JavaScript origins**: (leave empty for now)  
**Authorized redirect URIs**:
```
http://localhost:8501
http://localhost:8501/_oauth_callback
```

Click **CREATE**

### 1.4 Save Credentials

After creation, you'll see:
- **Client ID**: `xxxxx.apps.googleusercontent.com`
- **Client Secret**: `GOCSPX-xxxxx`

**⚠️ Important**: Download the JSON or copy these values securely!

---

## 🎨 Step 2: Configure OAuth Consent Screen

### 2.1 Navigate to Consent Screen

1. **APIs & Services** → **OAuth consent screen**
2. Choose **Internal** (for cloudroaster.com users only) or **External** (for testing)
3. Click **CREATE**

### 2.2 App Information

**App name**: FinOptiAgents Platform  
**User support email**: robin@cloudroaster.com  
**App logo**: (optional)  
**Application home page**: http://localhost:8501  
**Application privacy policy**: (optional for internal)  
**Application terms of service**: (optional for internal)  
**Authorized domains**: cloudroaster.com  
**Developer contact email**: robin@cloudroaster.com

Click **SAVE AND CONTINUE**

### 2.3 Scopes

Click **ADD OR REMOVE SCOPES**

**Required scopes**:
- `openid`
- `email`
- `profile`

**Optional scopes** (for group membership):
- `https://www.googleapis.com/auth/userinfo.email`
- `https://www.googleapis.com/auth/userinfo.profile`

> [!NOTE]
> Group membership requires Google Workspace and additional API enablement

Click **UPDATE** → **SAVE AND CONTINUE**

### 2.4 Test Users (if External)

If using **External** consent screen, add test users:
- robin@cloudroaster.com
- admin@cloudroaster.com
- monitoring@cloudroaster.com

Click **SAVE AND CONTINUE**

### 2.5 Summary

Review your settings and click **BACK TO DASHBOARD**

---

## 🔧 Step 3: Configure Platform

### 3.1 Add Credentials to Environment

Create or edit `.env` file:

```bash
cd finopti-platform

# Option 1: Edit .env directly
cat >> .env << EOF
GOOGLE_OAUTH_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-xxxxx
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501
EOF
```

### 3.2 Restart Services

```bash
# Restart UI to pick up new environment variables
docker-compose restart ui

# Check UI logs
docker-compose logs -f ui
```

---

## 👥 Step 4: Create IAM Groups (Optional)

### 4.1 Prerequisites

- Google Workspace access
- Permission to create groups
- Cloud Identity enabled

### 4.2 Create Groups

**Option A: Via Google Admin Console** (if you have Workspace):

```
1. admin.google.com → Groups
2. Create group:
   - Name: FinOpti GCloud Admins
   - Email: finopti-gcloud-admins@cloudroaster.com
   - Members: robin@cloudroaster.com, admin@cloudroaster.com

3. Repeat for:
   - finopti-monitoring-admins@cloudroaster.com
   - finopti-developers@cloudroaster.com
```

**Option B: Via gcloud CLI**:

```bash
# Create groups
gcloud identity groups create finopti-gcloud-admins@cloudroaster.com \
  --organization=cloudroaster.com \
  --display-name="FinOpti GCloud Admins"

# Add members
gcloud identity groups memberships add \
  --group-email=finopti-gcloud-admins@cloudroaster.com \
  --member-email=robin@cloudroaster.com
```

### 4.3 Grant IAM Roles

```bash
PROJECT_ID=vector-search-poc

# GCloud Admins - Full compute access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="group:finopti-gcloud-admins@cloudroaster.com" \
  --role="roles/compute.admin"

# Monitoring Admins - Monitoring access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="group:finopti-monitoring-admins@cloudroaster.com" \
  --role="roles/monitoring.viewer"
```

---

## 🧪 Step 5: Test OAuth Flow

### 5.1 Open UI

Navigate to: http://localhost:8501

### 5.2 Verify OAuth Enabled

In the sidebar, you should see:
```
✅ OAuth Enabled (Client ID: xxxxx...)
```

### 5.3 Test Login

1. Click **"Google OAuth"** tab
2. Click **"🔐 Login with Google"** button
3. You'll be redirected to Google consent screen
4. Authenticate with robin@cloudroaster.com
5. Grant permissions
6. You should be redirected back to UI
7. Verify you're logged in with OAuth indicator: **"🔐 Google OAuth"**

### 5.4 Test Simulated Fallback

1. Logout
2. Switch to **"Simulated"** tab
3. Select a user and login
4. Verify indicator shows: **"⚙️ Simulated Auth (Dev Mode)"**

---

## 🔍 Verification Checklist

Authentication Working:
- [ ] OAuth credentials created in GCP Console
- [ ] OAuth consent screen configured
- [ ] Credentials added to `.env` file
- [ ] UI shows "✅ OAuth Enabled" message
- [ ] "Login with Google" button appears
- [ ] OAuth redirect works (sends to Google)
- [ ] User can authenticate with Google account
- [ ] User redirected back to FinOptiAgents UI
- [ ] User shown as logged in with email
- [ ] Simulated auth still works as fallback
- [ ] Logout works for both auth methods

API Requests:
- [ ] OAuth login includes Bearer token in headers
- [ ] Simulated login uses X-User-Email only
- [ ] Agents can receive both auth types

---

## 🐛 Troubleshooting

### Issue: "OAuth Not Configured" message

**Cause**: Environment variables not set or UI not restarted

**Fix**:
```bash
# Check env vars are set
docker exec finopti-ui env | grep OAUTH

# Restart UI
docker-compose restart ui
```

### Issue: Redirect to Google fails

**Cause**: Invalid redirect URI in OAuth credentials

**Fix**: Ensure redirect URIs in GCP Console include:
- `http://localhost:8501`
- `http://localhost:8501/_oauth_callback`

### Issue: "Error 400: redirect_uri_mismatch"

**Cause**: Redirect URI in request doesn't match GCP Console

**Fix**: Check `GOOGLE_OAUTH_REDIRECT_URI` in `.env` matches exactly

### Issue: Token verification fails

**Cause**: Clock skew or invalid client secret

**Fix**:
```bash
# Check time sync
date

# Verify client secret is correct
docker exec finopti-ui env | grep CLIENT_SECRET
```

### Issue: Can't create groups

**Cause**: Need Google Workspace or Cloud Identity

**Solution**: Use OPA policy with email-based rules (already configured as fallback)

---

## 📊 Current Status

**UI Configuration**:
- ✅ Hybrid auth implemented (OAuth + Simulated)
- ✅ OAuth helper module created
- ✅ Tabbed login interface
- ✅ Bearer token support in API requests
- ⏳ OAuth credentials needed from GCP Console

**What Works Now**:
- Simulated auth (development mode)
- All existing functionality maintained
- Ready for OAuth when credentials configured

**What's Needed**:
- Create OAuth 2.0 credentials
- Add to `.env` file
- Restart UI
- Test OAuth login flow

---

## ⏭️ Next Steps

After OAuth is working:

1. **Phase 2.3**: Configure APISIX JWT validation
2. **Phase 2.4**: Update OPA for group-based policies
3. **Phase 2.5**: Update Orchestrator for JWT claims
4. **Phase 2.6**: End-to-end testing

---

## 📞 Support

If you need help:
1. Check UI logs: `docker-compose logs ui`
2. Check browser console: F12 → Console tab
3. Verify environment variables are set
4. Test with simulated auth first

---

**Platform Version**: v1.0 + OAuth  
**Last Updated**: 2025-12-19
