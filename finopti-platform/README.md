# FinOptiAgents Platform

A microservices-based AI agent platform for Google Cloud operations, built with APISIX API Gateway, Flask agents, and Model Context Protocol (MCP) servers.

## 🏗️ Architecture

```
┌─────────────┐
│  Client/UI  │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│ APISIX Gateway   │ ← API Gateway (Port 9080)
│  (Port 9080)     │
└──────┬───────────┘
       │
       ├─────────────┬──────────────┬────────────────┐
       ▼             ▼              ▼                ▼
┌────────────┐ ┌─────────┐  ┌─────────────┐  ┌──────────┐
│Orchestrator│ │ GCloud  │  │  Monitoring │  │   MCP    │
│   Agent    │ │  Agent  │  │    Agent    │  │ Servers  │
└──────┬─────┘ └────┬────┘  └──────┬──────┘  └────┬─────┘
       │            │              │               │
       └────────────┴──────────────┴───────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   MCP Servers   │
                  │  (JSON-RPC 2.0) │
                  │                 │
                  │ • GCloud MCP    │
                  │ • Monitoring    │
                  └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker Desktop
- Python 3.11+
- GCP credentials (for Secret Manager)

### 1. Authenticate with GCP

```bash
gcloud auth application-default login
```

### 2. Deploy the Platform

```bash
cd finopti-platform
./deploy-local.sh
```

The script will:
- ✅ Check GCP authentication
- ✅ Build all Docker images
- ✅ Start all services
- ✅ Configure APISIX routes

### 3. Verify Deployment

```bash
# Run comprehensive test suite
python3 run_tests.py

# Or run specific test phases
python3 run_tests.py --mcp-only      # Test MCP servers
python3 run_tests.py --agents-only   # Test agents
python3 run_tests.py --e2e-only      # Test end-to-end flow
```

## 🌐 Access Points

| Service | Direct Access | Via APISIX Gateway |
|---------|---------------|-------------------|
| **UI** | http://localhost:8501 | - |
| **Orchestrator** | http://localhost:15000 | http://localhost:9080/orchestrator |
| **GCloud Agent** | http://localhost:15001 | http://localhost:9080/agent/gcloud |
| **Monitoring Agent** | http://localhost:15002 | http://localhost:9080/agent/monitoring |
| **GCloud MCP** | http://localhost:6001 | http://localhost:9080/mcp/gcloud |
| **Monitoring MCP** | http://localhost:6002 | http://localhost:9080/mcp/monitoring |
| **APISIX Admin** | - | http://localhost:9180 |
| **APISIX Dashboard** | - | http://localhost:9000 |
| **OPA** | http://localhost:8181 | - |

## 📋 Components

### Agents (Flask + Natural Language Interface)

- **Orchestrator**: Main routing agent with OPA authorization
- **GCloud Agent**: Handles GCP infrastructure operations
- **Monitoring Agent**: Manages monitoring and observability queries

### MCP Servers (JSON-RPC 2.0)

- **GCloud MCP**: Executes gcloud commands (create_vm, delete_vm, list_vms)
- **Monitoring MCP**: Provides metrics and logs (check_cpu, check_memory, query_logs)

### Infrastructure

- **APISIX**: API Gateway with routing, auth, and observability
- **OPA**: Policy-based authorization
- **etcd**: APISIX backend storage
- **Streamlit UI**: Web interface for interactions

## 🔧 Configuration

### Secret Manager (Production)

All configuration is loaded from Google Secret Manager:

```
google-api-key
google-project-id
finoptiagents-llm
bigquery-dataset-id
apisix-admin-key
... and more
```

### Environment Variables (Development)

See `.env.template` for all required variables. The platform automatically:
1. Checks for GCP authentication
2. Loads secrets from Secret Manager
3. Falls back to `.env` if `USE_SECRET_MANAGER=false`

## 🧪 Testing

### Comprehensive Test Suite

```bash
# Run all tests (15 tests across 4 phases)
python3 run_tests.py

# Phases:
# 1. MCP Server Tests (4 tests)
# 2. APISIX Gateway Tests (3 tests)
# 3. Agent Tests (6 tests)
# 4. End-to-End Tests (2 tests)
```

### Individual Test Scripts

```bash
# Test MCP servers directly
python3 test_gcloud_mcp.py
python3 test_monitoring_mcp.py

# Test APISIX routing
python3 test_apisix_routes.py

# Test end-to-end flow
python3 test_final.py
```

### Expected Results

All 15 tests should pass:
- ✅ MCP servers healthy and responding
- ✅ APISIX routing configured correctly
- ✅ All agents accessible via gateway
- ✅ End-to-end flow: Agent → APISIX → MCP working

## 📡 API Usage

### Example: List VMs via GCloud Agent

```bash
curl -X POST http://localhost:15001/execute \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "list all vms",
    "user_email": "admin@cloudroaster.com"
  }'
```

Response:
```json
{
  "agent": "gcloud",
  "action": "list_vms",
  "result": {
    "success": true,
    "count": 2,
    "instances": [
      {"name": "vm-1", "status": "RUNNING", "zone": "us-central1-a"},
      {"name": "vm-2", "status": "STOPPED", "zone": "us-east1-b"}
    ]
  }
}
```

### Example: Check CPU via Monitoring Agent

```bash
curl -X POST http://localhost:15002/execute \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "check cpu usage",
    "user_email": "monitoring@cloudroaster.com"
  }'
```

## 🛠️ Development

### Building Individual Services

```bash
# Build specific service
docker-compose build orchestrator
docker-compose build gcloud_agent
docker-compose build monitoring_agent

# Restart service
docker-compose restart orchestrator
```

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f orchestrator
docker-compose logs -f gcloud_agent
docker-compose logs -f apisix
```

### APISIX Route Management

```bash
# List all routes
curl http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: finopti-admin-key"

# View specific route
curl http://localhost:9180/apisix/admin/routes/1 \
  -H "X-API-KEY: finopti-admin-key"
```

## 📂 Project Structure

```
finopti-platform/
├── orchestrator_adk/          # Main orchestrator agent (ADK)
│   ├── main.py
│   ├── agent.py
│   └── Dockerfile
├── sub_agents/
│   ├── gcloud_agent_adk/     # GCloud operations agent (ADK)
│   ├── monitoring_agent_adk/ # Monitoring agent (ADK)
├── config/                    # Shared configuration module
│   ├── __init__.py           # Secret Manager integration
│   └── README.md
├── apisix_conf/              # APISIX configuration
│   ├── config.yaml           # APISIX settings
│   └── init_routes.sh        # Route initialization
├── opa_policy/               # OPA authorization policies
├── ui/                       # Streamlit frontend
├── test_run/                 # Test documentation
│   ├── README.md
│   ├── QUICK_REFERENCE.md
│   └── WALKTHROUGH.md
├── run_tests.py              # Comprehensive test suite
├── deploy-local.sh           # Deployment script
├── docker-compose.yml        # Service orchestration
└── README.md                 # This file
```

## 🔐 Security

- **Secret Manager**: All production secrets stored in GCP Secret Manager
- **OPA Authorization**: Policy-based access control
- **APISIX Admin Key**: Secured admin API access
- **No .env in Git**: `.env` files are gitignored

## 🐛 Troubleshooting

### Services Not Starting

```bash
# Check service status
docker-compose ps

# View logs for failed service
docker-compose logs <service-name>

# Restart all services
docker-compose down && docker-compose up -d
```

### APISIX Routes Not Working

```bash
# Verify APISIX is healthy
curl http://localhost:9080/

# Check routes are configured
python3 run_tests.py --apisix-only

# Reinitialize routes
docker restart finopti-apisix-init
```

### Tests Failing

```bash
# Check all services are running
docker-compose ps

# Verify GCP authentication
gcloud auth application-default print-access-token

# Run tests with verbose output
python3 run_tests.py
```

## 📚 Documentation

- **[test_run/README.md](test_run/README.md)** - Detailed platform documentation
- **[test_run/QUICK_REFERENCE.md](test_run/QUICK_REFERENCE.md)** - Quick reference guide
- **[test_run/WALKTHROUGH.md](test_run/WALKTHROUGH.md)** - Step-by-step walkthrough
- **[config/README.md](config/README.md)** - Configuration guide

## 🎯 Key Features

- ✅ **Microservices Architecture**: Scalable and maintainable
- ✅ **API Gateway**: Centralized routing via APISIX
- ✅ **Natural Language Interface**: Agents accept plain English prompts
- ✅ **MCP Protocol**: Standard JSON-RPC 2.0 communication
- ✅ **Secret Manager Integration**: Secure configuration management
- ✅ **Comprehensive Testing**: 15 automated tests covering all components
- ✅ **OPA Authorization**: Policy-based access control
- ✅ **Observability**: Structured logging throughout

## 📊 Testing Results

Platform validation (15/15 tests passing):
- ✅ Phase 1: MCP Server Tests (4/4) 
- ✅ Phase 2: APISIX Gateway Tests (3/3)
- ✅ Phase 3: Agent Tests (6/6)
- ✅ Phase 4: End-to-End Tests (2/2)

## 🤝 Contributing

1. Create feature branch
2. Make changes
3. Run test suite: `python3 run_tests.py`
4. Submit pull request

## 📝 License

Internal use only

---

**Platform Status**: ✅ Fully Operational  
**Last Updated**: 2026-01-01  
**Architecture**: Google ADK + MCP + APISIX + Secret Manager
**Test Coverage**: 15/15 tests passing
