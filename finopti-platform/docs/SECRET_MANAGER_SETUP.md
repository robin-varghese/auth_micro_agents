# Adding OAuth Credentials to Google Secret Manager

## Quick Start

Run the provided script:

```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform
./scripts/add_oauth_to_secret_manager.sh
```

---

## Manual Steps (If Script Fails)

### Step 1: Enable Secret Manager API

```bash
# Enable the API
gcloud services enable secretmanager.googleapis.com --project=coolpics-hosting
```

**Or via Console:**
1. Go to [Secret Manager API](https://console.cloud.google.com/apis/library/secretmanager.googleapis.com?project=coolpics-hosting)
2. Click "ENABLE"

### Step 2: Create Secrets

**Option A: Using gcloud CLI**

```bash
# Client ID
echo -n "YOUR_CLIENT_ID" | \
  gcloud secrets create google-oauth-client-id \
    --data-file=- \
    --replication-policy=automatic \
    --project=coolpics-hosting

# Client Secret
echo -n "YOUR_CLIENT_SECRET" | \
  gcloud secrets create google-oauth-client-secret \
    --data-file=- \
    --replication-policy=automatic \
    --project=coolpics-hosting

# Full JSON credentials
gcloud secrets create google-oauth-credentials-json \
  --data-file=secrets/client_secret_YOUR_CLIENT_ID.json \
  --replication-policy=automatic \
  --project=coolpics-hosting
```

**Option B: Via GCP Console**

1. Go to [Secret Manager](https://console.cloud.google.com/security/secret-manager?project=coolpics-hosting)
2. Click "CREATE SECRET"
3. Create each secret:
   - **Name:** `google-oauth-client-id`
   - **Secret value:** `YOUR_CLIENT_ID`
   - Click "CREATE SECRET"
4. Repeat for `google-oauth-client-secret` and `google-oauth-credentials-json`

### Step 3: Grant Access (Optional)

Grant access to your service accounts:

```bash
# Example: Grant access to Compute Engine default service account
PROJECT_NUMBER=$(gcloud projects describe coolpics-hosting --format="value(projectNumber)")
SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in google-oauth-client-id google-oauth-client-secret google-oauth-credentials-json; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=coolpics-hosting
done
```

---

## Troubleshooting

### Permission Denied

**Error:** `Permission 'secretmanager.secrets.create' denied`

**Solutions:**

1. **Check Your Permissions:**
   ```bash
   gcloud projects get-iam-policy coolpics-hosting \
     --flatten="bindings[].members" \
     --filter="bindings.members:user:robin@cloudroaster.com" \
     --format="table(bindings.role)"
   ```

2. **Grant Required Role:**
   
   You need one of these roles:
   - `roles/secretmanager.admin` (full access)
   - `roles/secretmanager.secretCreator` (create only)
   
   Ask project owner to grant:
   ```bash
   gcloud projects add-iam-policy-binding coolpics-hosting \
     --member="user:robin@cloudroaster.com" \
     --role="roles/secretmanager.admin"
   ```

3. **Use Console:** If you have console access but not gcloud permissions, create secrets via the web console.

### Secret Already Exists

**Error:** `Secret already exists`

**Solution:** Add a new version instead:
```bash
echo -n "NEW_VALUE" | gcloud secrets versions add SECRET_NAME --data-file=-
```

---

## Using Secrets in Your Application

### Accessing Secrets

```bash
# Get latest version
gcloud secrets versions access latest --secret=google-oauth-client-id

# Get specific version
gcloud secrets versions access 1 --secret=google-oauth-client-id
```

### In Python Code

```python
from google.cloud import secretmanager

def get_secret(secret_id, project_id="coolpics-hosting"):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Usage
CLIENT_ID = get_secret("google-oauth-client-id")
CLIENT_SECRET = get_secret("google-oauth-client-secret")
```

### Update config.py (For FinOptiAgents)

Add to `app/config.py` or similar:

```python
import os
from google.cloud import secretmanager

def get_oauth_credentials():
    """Load OAuth credentials from Secret Manager or .env"""
    use_secret_manager = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"
    
    if use_secret_manager:
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "coolpics-hosting")
        
        def get_secret(secret_id):
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        
        return {
            "client_id": get_secret("google-oauth-client-id"),
            "client_secret": get_secret("google-oauth-client-secret"),
        }
    else:
        return {
            "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        }
```

---

## Verify Secrets

```bash
# List all secrets
gcloud secrets list --project=coolpics-hosting

# View secret metadata
gcloud secrets describe google-oauth-client-id --project=coolpics-hosting

# Access secret value (for testing)
gcloud secrets versions access latest --secret=google-oauth-client-id --project=coolpics-hosting
```

---

## Security Best Practices

✅ **DO:**
- Use Secret Manager for production deployments
- Grant least-privilege access (use `secretAccessor` role, not `admin`)
- Enable audit logging for secret access
- Rotate secrets regularly
- Use automatic replication for high availability

❌ **DON'T:**
- Store secrets in `.env` files in production
- Commit secrets to git
- Grant `secretmanager.admin` to service accounts
- Share secret values in plain text

---

## Next Steps

After creating secrets:

1. ✅ Verify secrets are created in Console
2. Update `USE_SECRET_MANAGER=true` in `.env` (for production)
3. Test secret access from your application
4. Remove secrets from `.env` file (for production)
5. Update deployment scripts to use Secret Manager

---

**Created:** 2025-12-31  
**Project:** coolpics-hosting  
**Secrets:**
- `google-oauth-client-id`
- `google-oauth-client-secret`
- `google-oauth-credentials-json`
