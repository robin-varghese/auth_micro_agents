# UI Testing Guide - FinOptiAgents Platform

## 🎯 Architecture & Request Flow

The platform now runs on a **Service Mesh** architecture with **Google OAuth** authentication and full **Observability**.

```
User (Browser)
    ↓
Streamlit UI (Port 8501)
    ↓
APISIX Gateway (Port 9080)
    ↓
Orchestrator Agent (ADK)
    ↓ (Intent Detection + OPA Authorization)
APISIX Gateway (Port 9080)
    ↓
Sub-Agent (GCloud or Monitoring ADK)
    ↓
APISIX Gateway (Port 9080)
    ↓
MCP Server (GCloud or Monitoring)
```

**Observability Stack:**
- **Logs:** Captured by Promtail, stored in Loki.
- **Visualization:** Grafana (Port 3001).

---

## 🚀 Deployment for Testing

**Prerequisite:** You must have GCP credentials configured (run `gcloud auth application-default login`). All application secrets are loaded from **Google Secret Manager**.

```bash
# Start the platform
./deploy-local.sh

# Stop the platform
docker-compose down
```

---

## 🔐 Login Instructions (Google OAuth)

1. Open browser: **http://localhost:8501**
2. Verify visual indicator: "✅ OAuth Enabled (Secret Manager)" in sidebar.
3. Click "🔐 **Login with Google**" button.
4. Authenticate with a test account.

### Test Users & Roles

| Email | Role | Accessible Agents | Description |
|-------|------|-------------------|-------------|
| **admin@cloudroaster.com** | `gcloud_admin` | ✅ GCloud<br>❌ Monitoring | Infrastructure Admin |
| **monitoring@cloudroaster.com** | `observability_admin` | ❌ GCloud<br>✅ Monitoring | Observability Team |
| **robin@cloudroaster.com** | `none` | ❌ None | User with no access (for negative testing) |

---

## 🧪 Test Prompts & Expected Results

### Test 1: List Virtual Machines (GCloud)
*User: admin@cloudroaster.com*

**Prompt**: 
```
List all my virtual machines
```

**Expected Result**:
- **Target Agent**: `gcloud`
- **Authorization**: ✅ Access granted
- **Result**: List of VMs (e.g., `example-vm-1`, `example-vm-2`)

### Test 2: Create VM Instance (GCloud)
*User: admin@cloudroaster.com*

**Prompt**:
```
Create a new VM instance
```

**Expected Result**:
- **Target Agent**: `gcloud`
- **Action**: `create_vm`
- **Result**: Success message with VM details.

### Test 3: Access Denial (Negative Test)
*User: monitoring@cloudroaster.com*

**Prompt**:
```
List all my virtual machines
```

**Expected Result**:
- **Authorization**: ❌ Access denied
- **Message**: User `monitoring@cloudroaster.com` does not have permission to access `gcloud`.

### Test 4: Check CPU Usage (Monitoring)
*User: monitoring@cloudroaster.com*

**Prompt**:
```
Check the CPU usage of my servers
```

**Expected Result**:
- **Target Agent**: `monitoring`
- **Authorization**: ✅ Access granted
- **Result**: CPU utilization metrics (e.g., "CPU Usage is 45%").

---

## 🔍 Observability Verification

After running the tests, verify the backend observability:

1. **Grafana Dashboard**: Open **http://localhost:3001** (admin/admin).
2. **Explore Logs**:
   - Go to "Explore".
   - Select "Loki" datasource.
   - Query: `{container_name=~"finopti.+"}`
   - Verify: You should see structured logs from Orchestrator and Agents.

---

## 🎨 UI Features to Verify

1. **OAuth Flow**:
   - [ ] Redirects to Google and back.
   - [ ] Sidebar shows logged-in user email and avatar.
   - [ ] Token is securely passed to backend (invisible to user).

2. **Chat Interface**:
   - [ ] "Target Agent" shown with correct emoji (☁️ for GCloud, 📊 for Monitoring).
   - [ ] "View Raw Response" expander shows full JSON.
   - [ ] Authorization status (Granted/Denied) clearly visible.

---

## 🐛 Troubleshooting

### "OAuth Disabled" in Sidebar
- **Cause**: Application cannot access Secret Manager.
- **Fix**: Run `gcloud auth application-default login` and restart `deploy-local.sh`.

### "403 Unauthorized" (Unexpected)
- **Check OPA**: Ensure `opa_policy/authz.rego` maps your email to the correct role.
- **Inspect Logs**: `docker-compose logs -f opa` to see authorization decisions.

### Connection Refused (Port 8501/9080)
- **Check Containers**: Run `docker-compose ps`.
- **Note**: Internal ports (5000, 5001, 5002) are **NOT** exposed to host anymore. You must go through APISIX (9080) or the UI (8501).

---

## 📝 Document History

| Version | Date       | Author | Revision Summary |
|---------|------------|--------|------------------|
| 1.1.0   | 2026-01-01 | Antigravity AI | Updated for Service Mesh architecture, OAuth flow, and Observability testing. |
