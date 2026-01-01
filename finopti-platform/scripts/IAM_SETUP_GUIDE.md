# GCP IAM Setup - Quick Reference Guide

## Pre-Setup Checklist

Before running the scripts, ensure you have:

- [ ] **GCP Project Access**: Active GCP project with billing enabled
- [ ] **Required IAM Roles**:
  - `roles/resourcemanager.organizationAdmin` OR `roles/iam.organizationRoleAdmin` (for groups)
  - `roles/resourcemanager.projectIamAdmin` (for role assignments)
- [ ] **Cloud Identity or Google Workspace**: Configured for your organization domain
- [ ] **gcloud CLI**: Installed and authenticated (`gcloud auth login`)
- [ ] **Organization Domain**: Know your domain (e.g., `cloudroaster.com`)

Check your current permissions:
```bash
gcloud projects get-iam-policy $(gcloud config get-value project) \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:$(gcloud config get-value account)" \
  --format="table(bindings.role)"
```

---

## Execution Order

Run these scripts in order:

### 1️⃣ Create Groups
```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform
./scripts/setup_iam_groups.sh
```
**Input:** Organization domain (e.g., `cloudroaster.com`)

### 2️⃣ Assign Users
```bash
./scripts/assign_users_to_groups.sh
```
**Input:** User emails for each group (suggested below)

### 3️⃣ Assign Roles
```bash
./scripts/assign_roles_to_groups.sh
```
**Input:** Organization domain

### 4️⃣ Verify Setup
```bash
./scripts/verify_iam_setup.sh
```
**Input:** Organization domain

---

## Suggested User Assignments

Based on your PHASE_2_OAUTH_IMPLEMENTATION.md:

### GCloud Admins Group
Users who need full GCP compute access:
- `admin@cloudroaster.com`
- (Add additional admin users as needed)

### Monitoring Admins Group
Users who need observability access:
- `monitoring@cloudroaster.com`

### Developers Group
Users with read-only access:
- (Add test users as needed)

---

## Group-to-Role Mapping

| Group | IAM Roles | Purpose |
|-------|-----------|---------|
| **finopti-gcloud-admins** | `compute.admin`<br>`iam.serviceAccountUser`<br>`monitoring.viewer` | Full compute management, can create/delete VMs |
| **finopti-monitoring-admins** | `monitoring.admin`<br>`logging.admin`<br>`compute.viewer` | View and manage monitoring/logging |
| **finopti-developers** | `compute.viewer`<br>`monitoring.viewer` | Read-only access for development |

---

## Verification Commands

### Check if a group exists
```bash
gcloud identity groups describe finopti-gcloud-admins@cloudroaster.com
```

### List group members
```bash
gcloud identity groups memberships list \
  --group-email="finopti-gcloud-admins@cloudroaster.com"
```

### Check IAM policy bindings
```bash
gcloud projects get-iam-policy $(gcloud config get-value project) \
  --flatten="bindings[].members" \
  --filter="bindings.members:finopti-*" \
  --format="table(bindings.role, bindings.members)"
```

### Check if user is in group
```bash
gcloud identity groups memberships check-transitive-membership \
  --group-email="finopti-gcloud-admins@cloudroaster.com" \
  --member-email="admin@cloudroaster.com"
```

---

## Common Issues & Solutions

### ❌ "Permission denied" when creating groups
**Cause:** Missing Cloud Identity admin permissions  
**Solutions:**
1. Request `roles/resourcemanager.organizationAdmin` from your org admin
2. Use Google Workspace Admin Console to create groups manually
3. Use fallback: Hardcoded group mappings in OPA (testing only)

### ❌ "Organization not found"
**Cause:** Cloud Identity not set up for domain  
**Solutions:**
1. Set up Cloud Identity for your organization
2. Verify domain ownership
3. Use an existing Google Workspace domain

### ❌ Groups created but not showing in IAM
**Cause:** Propagation delay  
**Solution:** Wait 5-10 minutes and refresh

### ❌ User not found when adding to group
**Cause:** User doesn't exist in your organization  
**Solutions:**
1. Invite user to your Cloud Identity organization first
2. Verify email address is correct
3. Use an existing user from your organization

---

## Testing the Setup

After completing the setup, test with different users:

**Test 1: GCloud Admin Access**
```bash
# Login as admin@cloudroaster.com
gcloud auth login
gcloud compute instances list
# Should succeed - admin has compute.admin role
```

**Test 2: Monitoring Admin Access**
```bash
# Login as monitoring@cloudroaster.com
gcloud auth login
gcloud monitoring time-series list
# Should succeed - monitoring admin has monitoring.admin role

gcloud compute instances create test-vm --zone=us-central1-a
# Should fail - monitoring admin does not have compute.admin
```

---

## Next Steps After Setup

Once you've verified the IAM setup is complete:

1. ✅ **OAuth Client Setup**
   - Create OAuth 2.0 client in GCP Console
   - Configure redirect URIs
   - Save client ID and secret

2. ✅ **Update Environment Variables**
   - Add `GOOGLE_OAUTH_CLIENT_ID` to `.env`
   - Add `GOOGLE_OAUTH_CLIENT_SECRET` to `.env`

3. ✅ **Proceed to Phase 2.2**
   - Implement Streamlit OAuth integration
   - Update UI to use real Google login

Refer to `PHASE_2_OAUTH_IMPLEMENTATION.md` for detailed next steps.

---

## Cleanup (If Needed)

To completely remove the IAM setup:

```bash
# Remove all role bindings
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/scripts

# Run cleanup (manual - create if needed)
for group in finopti-gcloud-admins finopti-monitoring-admins finopti-developers; do
  # Remove role bindings
  gcloud projects remove-iam-policy-binding $(gcloud config get-value project) \
    --member="group:${group}@cloudroaster.com" \
    --all --quiet 2>/dev/null || true
  
  # Delete group
  gcloud identity groups delete "${group}@cloudroaster.com" --quiet 2>/dev/null || true
done
```

---

**Created:** 2025-12-31  
**For:** FinOptiAgents Phase 2.1 - GCP IAM Setup
