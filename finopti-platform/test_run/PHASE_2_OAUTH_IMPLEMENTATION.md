# Phase 2: Google OAuth & GCP IAM Integration - Implementation Plan

**Status**: Ready to Implement  
**Prerequisites**: Phase 1 (Platform Deployment) ✅ Complete  
**Start Date**: TBD (Tomorrow)  
**Estimated Effort**: 2-3 days

---

## 📋 Overview

Replace simulated authentication (dropdown selector) with real Google OAuth 2.0 login integrated with GCP IAM groups for enterprise-grade authentication and authorization.

### Current State
- ✅ Platform fully operational with 17/17 tests passing
- ✅ Simulated auth working (dropdown selection)
- ❌ No real Google OAuth login
- ❌ No GCP IAM group integration

### Target State
- ✅ Real Google OAuth 2.0 login with consent screen
- ✅ GCP IAM groups for role-based access control
- ✅ APISIX JWT token validation
- ✅ OPA group-based authorization policies

---

## 🎯 Architecture Changes

### Authentication Flow
```
User → "Login with Google" button
  ↓
Google OAuth Consent Screen
  ↓
User authenticates & grants permissions
  ↓
Redirect back with auth code
  ↓
Streamlit exchanges code for JWT token
  ↓
JWT stored in session
  ↓
Every API request includes: Authorization: Bearer <JWT>
  ↓
APISIX validates JWT with Google public keys
  ↓
APISIX extracts user email + groups from claims
  ↓
Orchestrator receives validated user info
  ↓
OPA checks permissions based on GCP IAM groups
```

---

## 🔨 Implementation Phases

### Phase 2.1: GCP Configuration (Manual Setup Required)

**Location**: GCP Console  
**Owner**: User (Robin)  
**Duration**: 1-2 hours

#### Tasks:

**1. Enable Google Identity Platform**
```bash
# In GCP Console
1. Navigate to: APIs & Services → Credentials
2. Click: Create Credentials → OAuth 2.0 Client ID
3. Application type: Web application
4. Name: FinOptiAgents Platform
5. Authorized redirect URIs:
   - http://localhost:8501/_oauth_callback
   - http://localhost:8501/component/streamlit_oauth_component.login_button/
```

**2. Configure OAuth Consent Screen**
```
App Information:
  - App name: FinOptiAgents Platform
  - User support email: robin@cloudroaster.com
  - Developer contact: robin@cloudroaster.com

Scopes:
  - email
  - profile
  - openid
  - https://www.googleapis.com/auth/cloud-platform (optional for group access)

Test Users (if using external):
  - robin@cloudroaster.com
  - admin@cloudroaster.com
  - monitoring@cloudroaster.com
```

**3. Create GCP IAM Groups**

**Option A: Via Google Workspace Admin Console** (if available):
```
Groups to create:
1. finopti-gcloud-admins@cloudroaster.com
   - Members: robin@cloudroaster.com, admin@cloudroaster.com
   
2. finopti-monitoring-admins@cloudroaster.com
   - Members: monitoring@cloudroaster.com
   
3. finopti-developers@cloudroaster.com
   - Members: [test users]
```

**Option B: Via gcloud CLI**:
```bash
# Create groups
gcloud identity groups create finopti-gcloud-admins@cloudroaster.com \
  --organization=cloudroaster.com \
  --display-name="FinOpti GCloud Admins"

gcloud identity groups create finopti-monitoring-admins@cloudroaster.com \
  --organization=cloudroaster.com \
  --display-name="FinOpti Monitoring Admins"

# Add members
gcloud identity groups memberships add \
  --group-email=finopti-gcloud-admins@cloudroaster.com \
  --member-email=robin@cloudroaster.com

gcloud identity groups memberships add \
  --group-email=finopti-gcloud-admins@cloudroaster.com \
  --member-email=admin@cloudroaster.com
```

**4. Grant IAM Roles to Groups**
```bash
# GCloud Admins - Full compute access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="group:finopti-gcloud-admins@cloudroaster.com" \
  --role="roles/compute.admin"

# Monitoring Admins - Monitoring access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="group:finopti-monitoring-admins@cloudroaster.com" \
  --role="roles/monitoring.viewer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="group:finopti-monitoring-admins@cloudroaster.com" \
  --role="roles/logging.viewer"
```

**5. Save OAuth Credentials**
```bash
# After creating OAuth client, download JSON and save as:
# finopti-platform/secrets/oauth_credentials.json

# Or add to Secret Manager:
gcloud secrets create google-oauth-client-id --data-file=-
gcloud secrets create google-oauth-client-secret --data-file=-
```

**Checklist**:
- [ ] OAuth 2.0 Client created
- [ ] OAuth consent screen configured
- [ ] 3 IAM groups created
- [ ] Members added to groups
- [ ] IAM roles granted to groups
- [ ] OAuth credentials saved securely

---

### Phase 2.2: Streamlit UI OAuth Integration

**Files to Modify**:
- `ui/app.py` - Main UI file
- `ui/requirements.txt` - Add OAuth dependencies

#### Changes:

**1. Add Dependencies** (`ui/requirements.txt`):
```txt
streamlit>=1.30.0
streamlit-oauth>=0.0.8
google-auth>=2.25.0
google-auth-oauthlib>=1.2.0
requests>=2.31.0
```

**2. Update UI App** (`ui/app.py`):

**Replace simulated auth section** (lines 32-71) with:
```python
import streamlit_oauth as oauth
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8501/_oauth_callback"

# Initialize OAuth
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.id_token = None

def handle_oauth_callback():
    """Handle OAuth callback and token exchange"""
    # Get authorization code from URL
    query_params = st.experimental_get_query_params()
    
    if 'code' in query_params:
        auth_code = query_params['code'][0]
        
        # Exchange code for tokens
        token_endpoint = "https://oauth2.googleapis.com/token"
        token_data = {
            'code': auth_code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        
        token_response = requests.post(token_endpoint, data=token_data)
        tokens = token_response.json()
        
        # Verify ID token
        id_token_jwt = tokens['id_token']
        user_info = id_token.verify_oauth2_token(
            id_token_jwt,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
        
        # Store in session
        st.session_state.authenticated = True
        st.session_state.user_email = user_info['email']
        st.session_state.id_token = id_token_jwt
        
        # Clear query params
        st.experimental_set_query_params()
        st.rerun()

# Check for OAuth callback
handle_oauth_callback()
```

**3. Update Login UI** (sidebar section):
```python
with st.sidebar:
    st.title("🤖 FinOptiAgents")
    st.markdown("---")
    
    if not st.session_state.authenticated:
        st.subheader("🔐 Login")
        
        # Google OAuth login button
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={GOOGLE_CLIENT_ID}&"
            f"redirect_uri={REDIRECT_URI}&"
            f"response_type=code&"
            f"scope=openid%20email%20profile&"
            f"access_type=offline"
        )
        
        st.markdown(f'<a href="{auth_url}" target="_self">'
                   f'<button style="width:100%">Login with Google</button></a>',
                   unsafe_allow_html=True)
    
    else:
        st.success("✅ Logged In")
        st.write(f"**Email:** {st.session_state.user_email}")
        
        if st.button("🚪 Logout"):
            st.session_state.authenticated = False
            st.session_state.user_email = None
            st.session_state.id_token = None
            st.rerun()
```

**4. Update API Requests** (send_message function):
```python
def send_message(prompt: str) -> dict:
    headers = {
        "Authorization": f"Bearer {st.session_state.id_token}",
        "X-User-Email": st.session_state.user_email,
        "Content-Type": "application/json"
    }
    # ... rest of function
```

**Checklist**:
- [ ] Dependencies added to requirements.txt
- [ ] OAuth config loaded from environment
- [ ] OAuth callback handler implemented
- [ ] Login button redirects to Google
- [ ] Token exchange implemented
- [ ] JWT stored in session
- [ ] Bearer token added to API requests

---

### Phase 2.3: APISIX JWT Validation

**Files to Modify**:
- `apisix_conf/config.yaml` - Enable JWT plugin
- Route configurations - Add JWT validation

#### Changes:

**1. Enable OpenID Connect Plugin** (`apisix_conf/config.yaml`):
```yaml
plugins:
  - jwt-auth
  - openid-connect
  - opa

plugin_attr:
  openid-connect:
    discovery: "https://accounts.google.com/.well-known/openid-configuration"
    client_id: "${GOOGLE_OAUTH_CLIENT_ID}"
    client_secret: "${GOOGLE_OAUTH_CLIENT_SECRET}"
    scope: "openid email profile"
    bearer_only: true
    realm: "finoptiagents"
    token_endpoint_auth_method: "client_secret_post"
```

**2. Update Route Configurations**:

Create new script: `apisix_conf/init_oauth_routes.sh`:
```bash
#!/bin/bash

ADMIN_KEY="finopti-admin-key"
APISIX_ADMIN="http://localhost:9180"

# Route: Orchestrator with JWT validation
curl -X PUT "$APISIX_ADMIN/apisix/admin/routes/3" \
  -H "X-API-KEY: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "orchestrator_oauth",
    "uri": "/orchestrator/*",
    "plugins": {
      "openid-connect": {
        "discovery": "https://accounts.google.com/.well-known/openid-configuration",
        "client_id": "'$GOOGLE_OAUTH_CLIENT_ID'",
        "bearer_only": true,
        "scope": "openid email profile",
        "set_userinfo_header": true
      },
      "proxy-rewrite": {
        "regex_uri": ["^/orchestrator(/.*)", "$1"]
      }
    },
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "orchestrator:5000": 1
      }
    }
  }'
```

**3. Configure JWT Claim Extraction**:

APISIX will automatically extract and forward headers:
- `X-Userinfo` - Full user info from Google
- `X-Access-Token` - Original JWT token
- `X-Id-Token` - ID token claims

**Checklist**:
- [ ] OpenID Connect plugin enabled
- [ ] Discovery URL configured (Google)
- [ ] All routes updated with JWT validation
- [ ] Claim extraction configured
- [ ] Headers forwarded to Orchestrator

---

### Phase 2.4: OPA Group-Based Policies

**Files to Modify**:
- `opa_policy/authz.rego` - Update authorization logic

#### Changes:

**Replace entire policy** (`opa_policy/authz.rego`):
```rego
package finopti

default allow = false

# Extract user email from input
user_email := input.user_email

# Extract groups from Google userinfo claims
# APISIX forwards this in X-Userinfo header, orchestrator parses it
user_groups[group] {
    group := input.user_claims.groups[_]
}

# Fallback: if no groups in claims, check custom group mapping
# This allows flexibility for users not in GCP Workspace
user_groups[group] {
    not input.user_claims.groups
    group := hardcoded_groups[user_email][_]
}

# Hardcoded fallback for testing (remove in production)
hardcoded_groups := {
    "admin@cloudroaster.com": ["finopti-gcloud-admins@cloudroaster.com"],
    "monitoring@cloudroaster.com": ["finopti-monitoring-admins@cloudroaster.com"]
}

# Map groups to roles
group_to_role := {
    "finopti-gcloud-admins@cloudroaster.com": "gcloud_admin",
    "finopti-monitoring-admins@cloudroaster.com": "observability_admin",
    "finopti-developers@cloudroaster.com": "developer"
}

# Determine user's roles from their groups
user_roles[role] {
    group := user_groups[_]
    role := group_to_role[group]
}

# Role permissions
role_permissions := {
    "gcloud_admin": ["gcloud"],
    "observability_admin": ["monitoring"],
    "developer": []
}

# Authorization decision
allow if {
    target_agent := input.target_agent
    role := user_roles[_]
    allowed_agents := role_permissions[role]
    target_agent in allowed_agents
}

# Reason messages
reason := sprintf("Access granted: User '%s' with role(s) %v can access '%s' agent", 
    [user_email, user_roles, input.target_agent]) if {
    allow
}

reason := sprintf("Access denied: User '%s' with role(s) %v cannot access '%s' agent",
    [user_email, user_roles, input.target_agent]) if {
    not allow
    count(user_roles) > 0
}

reason := "Access denied: User not found or no groups assigned" if {
    not allow
    count(user_roles) == 0
}

# Authorization response
authz := {
    "allow": allow,
    "user_email": user_email,
    "groups": user_groups,
    "roles": user_roles,
    "reason": reason
}
```

**Checklist**:
- [ ] Group extraction logic implemented
- [ ] Group-to-role mapping configured
- [ ] Role-based permissions defined
- [ ] Fallback for users without groups
- [ ] Reason messages updated

---

### Phase 2.5: Orchestrator Updates

**Files to Modify**:
- `orchestrator/main.py` - Extract JWT claims

#### Changes:

**Update `check_authorization` function**:
```python
def check_authorization(user_email: str, user_claims: dict, target_agent: str) -> dict:
    """
    Call OPA with user email and JWT claims.
    """
    try:
        opa_endpoint = f"{OPA_URL}/v1/data/finopti/authz"
        
        # Extract groups from userinfo (provided by APISIX)
        groups = user_claims.get('groups', [])
        
        payload = {
            "input": {
                "user_email": user_email,
                "target_agent": target_agent,
                "user_claims": {
                    "groups": groups
                }
            }
        }
        
        response = requests.post(opa_endpoint, json=payload, timeout=5)
        # ... rest of function
```

**Update `/ask` endpoint**:
```python
@app.route('/ask', methods=['POST'])
def ask():
    # Get user info from headers (populated by APISIX)
    user_email = request.headers.get('X-User-Email')
    userinfo_header = request.headers.get('X-Userinfo')
    
    # Parse userinfo claims
    import json
    user_claims = {}
    if userinfo_header:
        user_claims = json.loads(userinfo_header)
    
    # ... rest of function
    
    # Check authorization with claims
    auth_result = check_authorization(user_email, user_claims, target_agent)
```

**Checklist**:
- [ ] Userinfo header extraction
- [ ] Claims parsing from JSON
- [ ] Groups extracted from claims
- [ ] OPA called with groups
- [ ] Error handling for missing claims

---

### Phase 2.6: Environment & Secrets

**Files to Modify**:
- `.env.template` - Add OAuth vars
- `docker-compose.yml` - Add env vars

#### Changes:

**1. Update `.env.template`**:
```bash
# Google OAuth Configuration
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501/_oauth_callback

# GCP Project
GOOGLE_CLOUD_PROJECT=your-project-id

# JWT Configuration
JWT_ISSUER=https://accounts.google.com
JWT_AUDIENCE=${GOOGLE_OAUTH_CLIENT_ID}
```

**2. Update `docker-compose.yml`**:
```yaml
services:
  ui:
    environment:
      - GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}
      - GOOGLE_OAUTH_CLIENT_SECRET=${GOOGLE_OAUTH_CLIENT_SECRET}
      - GOOGLE_OAUTH_REDIRECT_URI=${GOOGLE_OAUTH_REDIRECT_URI}
  
  apisix:
    environment:
      - GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}
      - GOOGLE_OAUTH_CLIENT_SECRET=${GOOGLE_OAUTH_CLIENT_SECRET}
```

**Checklist**:
- [ ] OAuth env vars added to template
- [ ] Docker compose updated
- [ ] Secrets loaded from Secret Manager
- [ ] Deploy script updated

---

## 🧪 Testing Plan

### Unit Tests

**1. OAuth Flow Test** (`test_oauth.py`):
```python
def test_oauth_redirect():
    """Test OAuth redirect URL generation"""
    # Verify correct Google OAuth URL
    
def test_token_exchange():
    """Test token exchange (mocked)"""
    # Mock Google token endpoint
    # Verify token parsing
    
def test_jwt_validation():
    """Test JWT validation in APISIX"""
    # Mock valid/invalid JWT
    # Verify APISIX accepts/rejects
```

**2. Group Authorization Test** (`test_groups.py`):
```python
def test_group_extraction():
    """Test group extraction from JWT claims"""
    
def test_group_to_role_mapping():
    """Test OPA group-to-role logic"""
    
def test_authorization_with_groups():
    """Test end-to-end with different groups"""
```

### Integration Tests

**1. End-to-End OAuth Flow**:
- Manual browser test
- Automated Selenium test (optional)

**2. Group-Based Access**:
- User in gcloud-admins → can access GCloud agent
- User in monitoring-admins → can access Monitoring agent  
- User with no groups → 403 Forbidden

### Security Tests

**1. Invalid Token Test**:
```bash
curl -H "Authorization: Bearer invalid_token" \
  http://localhost:9080/orchestrator/ask
# Expected: 401 Unauthorized
```

**2. Expired Token Test**:
```bash
# Use expired JWT
curl -H "Authorization: Bearer <expired_jwt>" \
  http://localhost:9080/orchestrator/ask
# Expected: 401 Unauthorized
```

**3. No Token Test**:
```bash
curl http://localhost:9080/orchestrator/ask
# Expected: 401 Unauthorized
```

---

## 🔒 Security Considerations

### Production Requirements

> [!CAUTION]
> **Critical for Production**
> 
> 1. **HTTPS Required**: OAuth redirects MUST use HTTPS in production
> 2. **Secure Token Storage**: Use encrypted session cookies (not localStorage)
> 3. **Token Refresh**: Implement refresh token flow (tokens expire in 1 hour)
> 4. **CORS**: Configure strict CORS policies in APISIX
> 5. **Rate Limiting**: Add rate limiting to prevent brute force
> 6. **Audit Logging**: Log all auth attempts and token validations
> 7. **Secret Rotation**: Rotate OAuth client secret regularly

### Security Checklist

- [ ] HTTPS enabled (production)
- [ ] Secure session storage
- [ ] Token refresh implemented
- [ ] CORS configured
- [ ] Rate limiting added
- [ ] Audit logging enabled
- [ ] Secrets in Secret Manager (not .env)

---

## 📊 Success Criteria

### Functional

- [ ] User can click "Login with Google" and see OAuth consent screen
- [ ] User redirected back after authentication
- [ ] JWT token stored in session
- [ ] All API requests include Bearer token
- [ ] APISIX validates JWT with Google
- [ ] Groups extracted from JWT claims
- [ ] OPA authorizes based on groups
- [ ] Different users get different access based on groups

### Non-Functional

- [ ] OAuth flow completes in <5 seconds
- [ ] Token validation adds <100ms latency
- [ ] No secrets exposed in client-side code
- [ ] All errors handled gracefully
- [ ] User can logout and login again

---

## 🔄 Rollback Plan

If OAuth integration fails:

1. **Keep old UI**: Backup current `ui/app.py` as `ui/app_simulated.py`
2. **APISIX Fallback**: Remove JWT plugin, use X-User-Email header only
3. **OPA Compatibility**: Policy supports both email-based and group-based
4. **Quick Rollback**: `docker-compose restart ui apisix opa`

---

## 📝 Documentation Updates

After implementation:

- [ ] Update `README.md` with OAuth setup instructions
- [ ] Document OAuth credentials creation
- [ ] Document IAM group setup
- [ ] Update `UI_TESTING_GUIDE.md` with OAuth flow
- [ ] Add troubleshooting section for OAuth errors

---

## ⏭️ Next Steps After Phase 2

**Phase 3 Candidates**:
1. **HTTPS Setup**: Configure TLS certificates for production
2. **Token Refresh**: Implement refresh token flow
3. **Admin Dashboard**: UI for managing user groups/permissions
4. **Audit Logging**: Comprehensive authentication audit trail
5. **Multi-Project Support**: Support multiple GCP projects

---

## 📞 Support & Questions

**Before Starting**:
- Confirm GCP Console access
- Share OAuth client ID/secret securely
- Verify IAM groups created
- Test group membership

**During Implementation**:
- Test OAuth redirect locally first
- Verify JWT structure with jwt.io
- Check APISIX logs for validation errors
- Test with multiple users in different groups

---

**Ready to implement?** Start with Phase 2.1 (GCP setup) tomorrow!

---

**Files to be Modified**:
- `ui/app.py`
- `ui/requirements.txt`
- `apisix_conf/config.yaml`
- `apisix_conf/init_oauth_routes.sh` (new)
- `opa_policy/authz.rego`
- `orchestrator/main.py`
- `.env.template`
- `docker-compose.yml`

**Estimated Time**: 2-3 days (including testing)
