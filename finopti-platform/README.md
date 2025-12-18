# FinOptiAgents Platform 🤖

A complete, runnable Local Docker Compose prototype for a FinOps Agentic Platform with Hub-and-Spoke architecture.

## 🏗️ Architecture

The platform uses a Hub-and-Spoke architecture where a central **Orchestrator Agent** routes tasks to specialized **Sub-Agents**. All traffic flows through **Apache APISIX** for observability and standardized routing. **Open Policy Agent (OPA)** provides role-based access control (RBAC).

```
┌─────────────┐
│ Streamlit UI│
│  (Port 8501)│
└──────┬──────┘
       │ HTTP + X-User-Email header
       ↓
┌──────────────────┐
│  Apache APISIX   │
│   (Port 9080)    │
│  API Gateway     │
└────────┬─────────┘
         │
    ┌────┴─────┐
    ↓          ↓
┌─────────┐  ┌──────────┐
│Orchestr.│→ │   OPA    │
│(Port    │  │(Port 8181│
│ 5000)   │  │  RBAC    │
└────┬────┘  └──────────┘
     │
     ├─→ /agent/gcloud ────→ GCloud Agent (5001) ──→ /mcp/gcloud ──→ GCloud MCP (6001)
     │
     └─→ /agent/monitoring → Monitoring Agent (5002) → /mcp/monitoring → Monitoring MCP (6002)
```

### Components

1. **Streamlit UI** (Port 8501): Frontend with simulated Google Auth and chat interface
2. **Apache APISIX** (Port 9080): Central API Gateway for routing and observability
3. **Etcd** (Port 2379): Key-value store backing APISIX
4. **Orchestrator Agent** (Port 5000): Central hub for intent detection and request routing
5. **OPA** (Port 8181): Authorization service with RBAC policies
6. **GCloud Agent** (Port 5001): Sub-agent for Google Cloud infrastructure tasks
7. **Monitoring Agent** (Port 5002): Sub-agent for observability operations
8. **GCloud MCP Server** (Port 6001): Mock Model Context Protocol server for GCloud tools
9. **Monitoring MCP Server** (Port 6002): Mock MCP server for monitoring tools
10. **APISIX Dashboard** (Port 9000): Optional web UI for managing APISIX

## 🚀 Quick Start

### Prerequisites

- Docker Desktop installed and running
- Docker Compose (v1.29+ or Docker Compose V2)
- At least 4GB RAM available for Docker

### 1. Start All Services

```bash
cd finopti-platform
docker-compose up -d
```

This will:
- Pull required images
- Build all custom services
- Start services in dependency order
- Initialize APISIX routes

### 2. Verify Services are Running

```bash
docker-compose ps
```

Expected output: All services should show status "Up" or "Up (healthy)"

### 3. Access the UI

Open your browser and navigate to:

```
http://localhost:8501
```

### 4. Test the Platform

See the [Testing](#-testing) section below for detailed test scenarios.

## 👥 Users & Roles

The prototype includes three mock users for testing:

| Email | Role | Access |
|-------|------|--------|
| `admin@cloudroaster.com` | `gcloud_admin` | ✅ GCloud Agent |
| `monitoring@cloudroaster.com` | `observability_admin` | ✅ Monitoring Agent |
| `robin@cloudroaster.com` | `developer` | ❌ No agent access (for testing denials) |

## 🔄 Request Flow

### Successful Request Flow

1. **User** selects identity in Streamlit UI (simulated Google Auth)
2. **User** enters prompt: "create a VM instance"
3. **UI** sends `POST http://apisix:9080/orchestrator/ask` with header `X-User-Email: admin@cloudroaster.com`
4. **APISIX** routes to Orchestrator Agent
5. **Orchestrator** detects intent: `gcloud` (keyword matching)
6. **Orchestrator** calls OPA: `POST http://opa:8181/v1/data/finopti/authz`
   ```json
   {
     "input": {
       "user_email": "admin@cloudroaster.com",
       "target_agent": "gcloud"
     }
   }
   ```
7. **OPA** returns: `{"allow": true, "reason": "Access granted..."}`
8. **Orchestrator** forwards to `POST http://apisix:9080/agent/gcloud`
9. **APISIX** routes to GCloud Agent
10. **GCloud Agent** calls `POST http://apisix:9080/mcp/gcloud`
11. **APISIX** routes to GCloud MCP Server
12. **GCloud MCP** returns mock result: `{"result": "VM Instance Created"}`
13. Response flows back through the chain to UI

### Denied Request Flow

1. User: `monitoring@cloudroaster.com`
2. Prompt: "create a VM instance"
3. Intent detected: `gcloud`
4. OPA check: `{"allow": false, "reason": "Role 'observability_admin' does not have access to 'gcloud' agent"}`
5. **Orchestrator** returns 403 error
6. UI displays: "403 Unauthorized: ..."

## 🧪 Testing

### Automated Tests

#### 1. Check Service Health

```bash
# Check all services are healthy
docker-compose ps

# Check APISIX health
curl http://localhost:9080/health

# Check OPA health
curl http://localhost:8181/health

# Check Orchestrator health
curl http://localhost:5000/health
```

#### 2. Test OPA Policy Directly

```bash
# Test: Admin accessing GCloud (should allow)
curl -X POST http://localhost:8181/v1/data/finopti/authz \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "user_email": "admin@cloudroaster.com",
      "target_agent": "gcloud"
    }
  }'

# Expected: {"result": {"allow": true, "reason": "Access granted..."}}

# Test: Monitoring user accessing GCloud (should deny)
curl -X POST http://localhost:8181/v1/data/finopti/authz \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "user_email": "monitoring@cloudroaster.com",
      "target_agent": "gcloud"
    }
  }'

# Expected: {"result": {"allow": false, "reason": "...does not have access..."}}
```

#### 3. Test Orchestrator via APISIX

```bash
# Test: Admin creating VM
curl -X POST http://localhost:9080/orchestrator/ask \
  -H "X-User-Email: admin@cloudroaster.com" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create a VM instance"}'

# Expected: Success response with VM details

# Test: Monitoring user accessing monitoring
curl -X POST http://localhost:9080/orchestrator/ask \
  -H "X-User-Email: monitoring@cloudroaster.com" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "check CPU usage"}'

# Expected: Success response with CPU metrics

# Test: Unauthorized access
curl -X POST http://localhost:9080/orchestrator/ask \
  -H "X-User-Email: monitoring@cloudroaster.com" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create a VM"}'

# Expected: 403 error
```

### Manual UI Tests

#### Test Scenario 1: Admin Accessing GCloud ✅

1. Open `http://localhost:8501`
2. Select user: `admin@cloudroaster.com`
3. Click "Login"
4. Enter prompt: `create a VM instance`
5. **Expected**: Success message with VM creation details

#### Test Scenario 2: Monitoring User Accessing Monitoring ✅

1. Logout (if logged in)
2. Select user: `monitoring@cloudroaster.com`
3. Click "Login"
4. Enter prompt: `check CPU usage`
5. **Expected**: Success message with CPU metrics

#### Test Scenario 3: Unauthorized Access (Monitoring → GCloud) ❌

1. Login as: `monitoring@cloudroaster.com`
2. Enter prompt: `create a VM instance`
3. **Expected**: Error message: "403 Unauthorized: Role 'observability_admin' does not have access to 'gcloud' agent"

#### Test Scenario 4: Developer with No Access ❌

1. Login as: `robin@cloudroaster.com`
2. Enter prompt: `create a VM instance` OR `check CPU usage`
3. **Expected**: Error message: "403 Unauthorized: Role 'developer' does not have access..."

#### Test Scenario 5: Multiple Operations

1. Login as `admin@cloudroaster.com`
2. Try these prompts:
   - "create a VM instance"
   - "list all VMs"
   - "delete a VM"
3. **Expected**: Different responses based on the action detected

## 📊 Observability

### View APISIX Dashboard

```
http://localhost:9000
```

Default credentials:
- Username: `admin`
- Password: `admin`

### View Service Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f orchestrator
docker-compose logs -f apisix
docker-compose logs -f opa

# Follow logs for debugging
docker-compose logs -f --tail=100 orchestrator
```

### APISIX Metrics (Prometheus)

```
http://localhost:9091/apisix/prometheus/metrics
```

## 🛠️ Development

### Modify OPA Policy

Edit `opa_policy/authz.rego` and restart OPA:

```bash
docker-compose restart opa
```

### Update Orchestrator Logic

Edit `orchestrator/main.py`, then rebuild:

```bash
docker-compose up -d --build orchestrator
```

### Add New Routes to APISIX

Edit `apisix_conf/init_routes.sh` and run:

```bash
docker-compose restart apisix-init
```

Or add routes via Admin API:

```bash
curl -X PUT http://localhost:9180/apisix/admin/routes/6 \
  -H "X-API-KEY: finopti-admin-key" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

## 🔍 Troubleshooting

### Services Not Starting

```bash
# Check logs
docker-compose logs

# Remove all containers and start fresh
docker-compose down -v
docker-compose up -d
```

### APISIX Routes Not Working

```bash
# Re-run route initialization
docker-compose restart apisix-init

# Check routes
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: finopti-admin-key" | jq
```

### UI Can't Connect to APISIX

Ensure you're accessing the UI from the host machine at `http://localhost:8501`. The UI container connects to APISIX via the Docker network.

If accessing from outside Docker network, modify `ui/app.py`:

```python
APISIX_URL = "http://localhost:9080"  # Instead of http://apisix:9080
```

### OPA Policy Not Working

```bash
# Check OPA is loading policies
docker-compose logs opa

# Test policy directly
curl http://localhost:8181/v1/data/finopti/authz
```

## 🧹 Cleanup

### Stop All Services

```bash
docker-compose down
```

### Remove All Data (Volumes)

```bash
docker-compose down -v
```

### Remove Built Images

```bash
docker-compose down --rmi all
```

## 📁 Project Structure

```
finopti-platform/
├── apisix_conf/
│   ├── config.yaml           # APISIX configuration
│   └── init_routes.sh        # Route initialization script
├── opa_policy/
│   └── authz.rego           # OPA RBAC policy
├── orchestrator/
│   ├── main.py              # Orchestrator service
│   ├── requirements.txt
│   └── Dockerfile
├── sub_agents/
│   ├── gcloud_agent/
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── monitoring_agent/
│       ├── main.py
│       ├── requirements.txt
│       └── Dockerfile
├── mcp_servers/
│   ├── gcloud_mcp/
│   │   ├── server.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── monitoring_mcp/
│       ├── server.py
│       ├── requirements.txt
│       └── Dockerfile
├── ui/
│   ├── app.py               # Streamlit UI
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml       # Main orchestration
└── README.md               # This file
```

## 🔮 Next Steps

This is a **prototype** for local development. For production deployment:

### Security Enhancements

- [ ] Replace mock Google Auth with real OAuth2/OIDC flow
- [ ] Add TLS/SSL certificates for APISIX
- [ ] Implement proper secret management (Vault, Secret Manager)
- [ ] Add API key rotation for APISIX Admin API
- [ ] Implement rate limiting and DDoS protection

### Agent Improvements

- [ ] Replace mock MCP servers with actual GCloud and Monitoring MCP implementations
- [ ] Improve intent detection with LLM/NLP instead of keyword matching
- [ ] Add conversation history and context management
- [ ] Implement multi-turn conversations
- [ ] Add support for more agents (AWS, Azure, etc.)

### Operational Excellence

- [ ] Add comprehensive logging and tracing (OpenTelemetry)
- [ ] Implement health checks and readiness probes
- [ ] Add metrics collection and dashboards (Grafana)
- [ ] Set up alerting for failures
- [ ] Implement circuit breakers and retry logic
- [ ] Add request validation and sanitization

### Deployment

- [ ] Create Kubernetes manifests
- [ ] Set up CI/CD pipelines
- [ ] Implement blue-green or canary deployments
- [ ] Add autoscaling for agents
- [ ] Set up multi-region deployment

## 📝 License

This is a prototype/demo project. Modify as needed for your use case.

## 🤝 Contributing

This is a prototype. Feel free to:
1. Replace mock MCP servers with real implementations
2. Improve intent detection logic
3. Add more agents and capabilities
4. Enhance the UI/UX

## 📧 Support

For issues or questions about this prototype, please refer to the official documentation:
- [Apache APISIX Documentation](https://apisix.apache.org/docs/)
- [Open Policy Agent Documentation](https://www.openpolicyagent.org/docs/)
- [Streamlit Documentation](https://docs.streamlit.io/)

---

**Built with ❤️ for FinOps and Agentic AI**
