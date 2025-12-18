# FinOptiAgents Platform - Quick Reference

## 🚀 Quick Start Commands

### Start the Platform
```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform
docker-compose up -d
```

### Check Status
```bash
docker-compose ps
```

### Stop the Platform
```bash
docker-compose down
```

### Clean Reset
```bash
docker-compose down -v
docker-compose up -d
```

## 🌐 Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| **Streamlit UI** | http://localhost:8501 | Select user from dropdown |
| **APISIX Gateway** | http://localhost:9080 | N/A |
| **APISIX Dashboard** | http://localhost:9000 | admin / admin |
| **OPA** | http://localhost:8181 | N/A |
| **Prometheus Metrics** | http://localhost:9091/apisix/prometheus/metrics | N/A |

## 👥 Test Users

| Email | Role | Access |
|-------|------|--------|
| admin@cloudroaster.com | gcloud_admin | ✅ GCloud Agent |
| monitoring@cloudroaster.com | observability_admin | ✅ Monitoring Agent |
| robin@cloudroaster.com | developer | ❌ No Access |

## 🧪 Quick Tests

### Test 1: OPA Authorization (Admin → GCloud)
```bash
curl -X POST http://localhost:8181/v1/data/finopti/authz \
  -H "Content-Type: application/json" \
  -d '{"input": {"user_email": "admin@cloudroaster.com", "target_agent": "gcloud"}}'

# Expected: {"result": {"allow": true, ...}}
```

### Test 2: OPA Authorization (Monitoring → GCloud) - Should Deny
```bash
curl -X POST http://localhost:8181/v1/data/finopti/authz \
  -H "Content-Type: application/json" \
  -d '{"input": {"user_email": "monitoring@cloudroaster.com", "target_agent": "gcloud"}}'

# Expected: {"result": {"allow": false, ...}}
```

### Test 3: Orchestrator (Admin Creates VM)
```bash
curl -X POST http://localhost:9080/orchestrator/ask \
  -H "X-User-Email: admin@cloudroaster.com" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create a VM instance"}'

# Expected: 200 OK with VM details
```

### Test 4: Orchestrator (Monitoring Checks CPU)
```bash
curl -X POST http://localhost:9080/orchestrator/ask \
  -H "X-User-Email: monitoring@cloudroaster.com" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "check CPU usage"}'

# Expected: 200 OK with CPU metrics
```

### Test 5: Unauthorized Access - Should Fail
```bash
curl -X POST http://localhost:9080/orchestrator/ask \
  -H "X-User-Email: monitoring@cloudroaster.com" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create a VM"}'

# Expected: 403 Forbidden
```

## 💬 UI Test Prompts

### GCloud Operations (Use with admin@cloudroaster.com)
- "create a VM instance"
- "list all VMs"
- "delete a VM"

### Monitoring Operations (Use with monitoring@cloudroaster.com)
- "check CPU usage"
- "check memory usage"
- "query error logs"
- "get metrics"

### Unauthorized Tests
- Login as monitoring@cloudroaster.com → "create a VM" → Should get 403
- Login as robin@cloudroaster.com → Any prompt → Should get 403

## 📊 View Logs

### All Services
```bash
docker-compose logs -f
```

### Specific Service
```bash
docker-compose logs -f orchestrator
docker-compose logs -f apisix
docker-compose logs -f opa
docker-compose logs -f ui
```

### Last 100 Lines
```bash
docker-compose logs --tail=100 orchestrator
```

## 🏗️ Architecture Overview

```
User (Streamlit)
    ↓
APISIX (Gateway)
    ↓
Orchestrator (Hub)
    ↓
OPA (Authorization) → Allow/Deny
    ↓
APISIX
    ↓
Sub-Agents (GCloud/Monitoring)
    ↓
APISIX
    ↓
MCP Servers (Tools)
```

## 🔑 Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Etcd | 2379 | Config store |
| Orchestrator | 5000 | Main hub |
| GCloud Agent | 5001 | GCP operations |
| Monitoring Agent | 5002 | Observability |
| GCloud MCP | 6001 | GCloud tools |
| Monitoring MCP | 6002 | Monitoring tools |
| OPA | 8181 | Authorization |
| Streamlit UI | 8501 | Frontend |
| APISIX Dashboard | 9000 | Admin UI |
| APISIX Gateway | 9080 | API Gateway |
| APISIX Metrics | 9091 | Prometheus |
| APISIX Admin | 9180 | Admin API |

## 🛠️ Troubleshooting

### Services Not Starting
```bash
docker-compose down -v
docker-compose up -d
docker-compose logs
```

### Check Service Health
```bash
curl http://localhost:9080/health      # APISIX
curl http://localhost:8181/health      # OPA
curl http://localhost:5000/health      # Orchestrator
curl http://localhost:5001/health      # GCloud Agent
curl http://localhost:5002/health      # Monitoring Agent
curl http://localhost:6001/health      # GCloud MCP
curl http://localhost:6002/health      # Monitoring MCP
```

### Rebuild Services
```bash
docker-compose up -d --build
```

### View APISIX Routes
```bash
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: finopti-admin-key" | jq
```

## 🔄 Request Flow Example

```
1. UI sends: POST http://apisix:9080/orchestrator/ask
   Headers: X-User-Email: admin@cloudroaster.com
   Body: {"prompt": "create a VM"}

2. APISIX routes to: orchestrator:5000/ask

3. Orchestrator:
   - Detects intent: gcloud
   - Calls OPA: Is admin allowed to use gcloud?
   - OPA: Yes ✅

4. Orchestrator forwards to: http://apisix:9080/agent/gcloud

5. APISIX routes to: gcloud_agent:5001/execute

6. GCloud Agent calls: http://apisix:9080/mcp/gcloud

7. APISIX routes to: gcloud_mcp:6001

8. GCloud MCP executes and returns result

9. Response flows back: MCP → APISIX → Agent → APISIX → Orchestrator → APISIX → UI
```

## 📁 Key Files

| File | Description |
|------|-------------|
| `docker-compose.yml` | Service orchestration |
| `opa_policy/authz.rego` | RBAC policy |
| `orchestrator/main.py` | Central hub |
| `sub_agents/gcloud_agent/main.py` | GCloud agent |
| `sub_agents/monitoring_agent/main.py` | Monitoring agent |
| `mcp_servers/gcloud_mcp/server.py` | GCloud MCP mock |
| `mcp_servers/monitoring_mcp/server.py` | Monitoring MCP mock |
| `ui/app.py` | Streamlit UI |
| `apisix_conf/config.yaml` | APISIX config |
| `apisix_conf/init_routes.sh` | Route setup |

## 🔧 Customization

### Add New User
Edit `opa_policy/authz.rego`:
```rego
user_roles := {
    "newuser@example.com": "new_role"
}

role_permissions := {
    "new_role": ["gcloud", "monitoring"]
}
```

Then restart OPA:
```bash
docker-compose restart opa
```

### Replace Mock MCP
```bash
# Replace the file
cp /path/to/real/mcp/server.py mcp_servers/gcloud_mcp/server.py

# Rebuild
docker-compose up -d --build gcloud_mcp
```

## ✅ Success Indicators

### All Services Running
```bash
$ docker-compose ps
# All services should show "Up" or "Up (healthy)"
```

### UI Accessible
```bash
$ curl http://localhost:8501
# Should return HTML
```

### API Tests Pass
- OPA authorization works
- Orchestrator routes correctly
- Agents communicate with MCP servers
- UI displays responses

## 📚 Documentation

- **README.md** - Complete setup and usage guide
- **IMPLEMENTATION_PLAN.md** - Architecture and design
- **WALKTHROUGH.md** - Detailed implementation walkthrough
- **QUICK_REFERENCE.md** - This file

## 🎯 Next Steps

1. ✅ Start platform: `docker-compose up -d`
2. ✅ Test via UI: http://localhost:8501
3. ✅ Run automated tests (see above)
4. 🔄 Replace mock MCP servers with real implementations
5. 🔄 Add more agents and capabilities
6. 🔄 Deploy to production

---

**Platform Location**: `/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform`

**Documentation**: `test_run/` directory
