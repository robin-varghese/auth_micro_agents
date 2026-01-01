# OAuth Secret Manager - Quick Reference

## ✅ Status: Configured and Working

**Project:** `vector-search-poc`  
**Secrets:** 3 OAuth credentials stored in Secret Manager  
**Configuration:** Application loads from Secret Manager only

---

## Quick Commands

### Access Secrets (CLI)
```bash
# Client ID
gcloud secrets versions access latest --secret=google-oauth-client-id --project=vector-search-poc

# Client Secret  
gcloud secrets versions access latest --secret=google-oauth-client-secret --project=vector-search-poc

# Full JSON
gcloud secrets versions access latest --secret=google-oauth-credentials-json --project=vector-search-poc
```

### Test Python Integration
```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform
python3 ui/oauth_config.py
```

**Expected Output:**
```
✅ Successfully loaded OAuth credentials from Secret Manager
Client ID: 912533822336-dqcluei...
Client Secret: GOCSPX-21Z...
Redirect URI: http://localhost:8501/_oauth_callback
```

---

## Configuration

### .env Settings
```bash
USE_SECRET_MANAGER=true
GOOGLE_CLOUD_PROJECT=vector-search-poc
GOOGLE_PROJECT_ID=vector-search-poc
```

### OAuth Credentials Location
- ❌ Not in `.env` (removed for security)
- ❌ Not in JSON file (deleted)
- ✅ In Google Secret Manager

---

## Usage in Code

```python
from ui.oauth_config import load_oauth_config

# Load OAuth credentials
config = load_oauth_config()

# Use credentials
CLIENT_ID = config['client_id']
CLIENT_SECRET = config['client_secret']
REDIRECT_URI = config['redirect_uri']
```

---

## Secrets Overview

| Secret Name | Contains | Version |
|-------------|----------|---------|
| `google-oauth-client-id` | OAuth Client ID | 1 |
| `google-oauth-client-secret` | OAuth Client Secret | 1 |
| `google-oauth-credentials-json` | Full OAuth JSON | 1 |

**Console:** https://console.cloud.google.com/security/secret-manager?project=vector-search-poc

---

## Security Notes

✅ **Current Security Posture:**
- Credentials stored in Secret Manager (encrypted at rest)
- Access controlled via IAM
- No secrets in source code or .env
- Audit logging enabled

🔒 **Best Practices Applied:**
- Automatic replication for HA
- Service account access only
- Secrets versioned
- Local credentials deleted

---

## Troubleshooting

### Error: "Failed to access secret"
**Fix:** Authenticate with application default credentials
```bash
gcloud auth application-default login
```

### Error: "Permission denied"
**Fix:** Verify service account has `roles/secretmanager.secretAccessor`

### Error: Module not found
**Fix:** Install dependencies
```bash
pip install google-cloud-secret-manager
```

---

**Created:** 2025-12-31  
**Project:** vector-search-poc  
**Status:** ✅ Production Ready
