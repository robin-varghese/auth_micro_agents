# UI Testing Guide - FinOptiAgents Platform

## 🎯 Complete Request Flow

```
User (Browser)
    ↓
Streamlit UI (Port 8501)
    ↓
APISIX Gateway (Port 9080)
    ↓
Orchestrator Agent
    ↓ (Intent Detection + OPA Authorization)
APISIX Gateway (Port 9080)
    ↓
Sub-Agent (GCloud or Monitoring)
    ↓
APISIX Gateway (Port 9080)
    ↓
MCP Server (JSON-RPC)
    ↓
Response flows back through the chain
```

## 🔐 Login Instructions

1. Open browser: **http://localhost:8501**
2. Select user from dropdown: **robin@cloudroaster.com**
3. Click **🚀 Login** button
4. You should see the chat interface

**Your Permissions**: 
- Role: `gcloud_admin`
- Access: Full access to GCloud operations
- Authorization: Enforced by OPA

## 🧪 Test Prompts & Expected Results

### Test 1: List Virtual Machines (GCloud)

**Prompt**: 
```
List all my virtual machines
```

**Expected Flow**:
```
UI → APISIX → Orchestrator 
    ↓ (Detects: "gcloud" agent)
    ↓ (OPA: ✓ Authorized)
    → APISIX → GCloud Agent
    → APISIX → GCloud MCP
    ← Returns VM list
```

**Expected Result**:
```
🎯 Target Agent: gcloud
✅ Authorization: Access granted: User 'robin@cloudroaster.com' with role 'gcloud_admin' can access 'gcloud' agent

🤖 Agent: gcloud
⚙️ Action: list_vms

✅ Result: VMs listed successfully

Found 2 instances:
- example-vm-1 (us-central1-a) - RUNNING
- example-vm-2 (us-east1-b) - STOPPED
```

### Test 2: Create VM Instance (GCloud)

**Prompt**:
```
Create a new VM instance
```

**Expected Flow**:
```
UI → APISIX → Orchestrator 
    ↓ (Detects: "gcloud" agent - keywords: "create", "vm")
    ↓ (OPA: ✓ Authorized)
    → APISIX → GCloud Agent
    → APISIX → GCloud MCP
    ← Returns creation confirmation
```

**Expected Result**:
```
🎯 Target Agent: gcloud
✅ Authorization: Access granted

🤖 Agent: gcloud
⚙️ Action: create_vm

✅ Result: VM Instance 'demo-instance' created successfully in zone us-central1-a

Instance Details:
- Name: demo-instance (or test-vm-001)
- Zone: us-central1-a
- Machine Type: e2-micro
- Status: RUNNING
```

### Test 3: Check CPU Usage (Monitoring)

**Prompt**:
```
Check the CPU usage of my servers
```

**Expected Flow**:
```
UI → APISIX → Orchestrator 
    ↓ (Detects: "monitoring" agent - keywords: "cpu", "usage")
    ↓ (OPA: ✓ Authorized - gcloud_admin has monitoring access)
    → APISIX → Monitoring Agent
    → APISIX → Monitoring MCP
    ← Returns CPU metrics
```

**Expected Result**:
```
🎯 Target Agent: monitoring
✅ Authorization: Access granted

🤖 Agent: monitoring
⚙️ Action: check_cpu

📊 CPU Usage is XX% (random value between 30-90%)
- Metric: cpu_utilization
- Value: XX%
```

### Test 4: Query Error Logs (Monitoring)

**Prompt**:
```
Show me the latest error logs
```

**Expected Flow**:
```
UI → APISIX → Orchestrator 
    ↓ (Detects: "monitoring" agent - keywords: "logs", "error")
    ↓ (OPA: ✓ Authorized)
    → APISIX → Monitoring Agent
    → APISIX → Monitoring MCP
    ← Returns log entries
```

**Expected Result**:
```
🎯 Target Agent: monitoring
✅ Authorization: Access granted

🤖 Agent: monitoring
⚙️ Action: query_logs

📝 Found 3 log entries:
- [ERROR] Database connection failed (database-server-1)
- [WARNING] High memory usage detected (app-server-2)
- [INFO] Backup completed successfully (backup-server-1)
```

## 🔍 Verification Checklist

For each test, verify:

- [ ] **Authorization**: Should show "Access granted" with your role
- [ ] **Target Agent**: Should correctly route to gcloud or monitoring based on keywords
- [ ] **Response**: Should contain actual data (VMs, metrics, logs)
- [ ] **No Errors**: Should not see 403 Forbidden or connection errors
- [ ] **Raw Response**: Click "🔍 View Raw Response" to see full JSON

## 🎨 UI Features to Verify

1. **Login Flow**:
   - [ ] User selection dropdown works
   - [ ] Login button enables chat interface
   - [ ] User info displayed in sidebar

2. **Chat Interface**:
   - [ ] Messages appear in chat history
   - [ ] User messages aligned right
   - [ ] Assistant responses formatted nicely
   - [ ] Spinner shows "Processing your request..."

3. **Response Formatting**:
   - [ ] Target agent shown with emoji
   - [ ] Authorization status visible
   - [ ] Data formatted as lists/bullets
   - [ ] Raw JSON available in expander

4. **Sidebar**:
   - [ ] User info displayed
   - [ ] Example prompts shown
   - [ ] Logout button works

## 🐛 Troubleshooting

### If you get "403 Unauthorized":
- Check OPA policy updated (robin@cloudroaster.com should be gcloud_admin)
- Restart OPA: `docker restart finopti-opa`

### If you get "Connection Error":
- Ensure all services running: `docker-compose ps`
- Check APISIX: `curl http://localhost:9080/`

### If response seems wrong:
- Check raw response JSON in expander
- Verify orchestrator detected correct agent
- Check authorization message

## 📊 Expected Behavior Summary

| Prompt Type | Agent Routed | Authorization | Expected Data |
|-------------|-------------|---------------|---------------|
| "list vms" | gcloud | ✓ Granted | 2 VMs (example-vm-1, example-vm-2) |
| "create vm" | gcloud | ✓ Granted | VM creation confirmation |
| "cpu usage" | monitoring | ✓ Granted | CPU percentage (30-90%) |
| "error logs" | monitoring | ✓ Granted | 3 log entries (ERROR/WARNING/INFO) |
| "check memory" | monitoring | ✓ Granted | Memory percentage |

## 🎯 Success Criteria

✅ **Test Passes If**:
1. Login completes without errors
2. All 4 test prompts return valid responses
3. Correct agent routing for each prompt
4. Authorization granted for robin@cloudroaster.com
5. Response includes expected data (VMs, metrics, logs)
6. No timeout or connection errors

## 📝 Test Report Template

After testing, you can report:

```
UI Test Results - robin@cloudroaster.com
========================================
Login: ✅/❌
Test 1 (List VMs): ✅/❌
Test 2 (Create VM): ✅/❌  
Test 3 (CPU Usage): ✅/❌
Test 4 (Error Logs): ✅/❌

Notes:
- [Any observations or issues]
```

---

**Test Date**: 2025-12-18  
**Platform Version**: v1.0  
**Total Tests**: 4 prompts + login flow
