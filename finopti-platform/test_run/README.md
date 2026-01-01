# FinOptiAgents Platform - Test Run Documentation

This directory contains comprehensive documentation for the FinOptiAgents platform implementation.

## 📚 Documentation Files

### 1. [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)
**Size**: ~8.4 KB

**Contents**:
- Architecture overview with Mermaid diagram
- Complete request flow documentation
- Component details for all services
- Technology stack specifications
- Comprehensive verification plan
- Production considerations

**Use this for**:
- Understanding the architecture
- Planning deployment
- Reviewing technical decisions
- Verification testing

### 2. [WALKTHROUGH.md](./WALKTHROUGH.md)
**Size**: ~23 KB

**Contents**:
- Complete implementation summary
- Detailed project structure
- Component-by-component breakdown
- Request flow examples with code
- Complete testing guide (automated & manual)
- Customization instructions
- Troubleshooting guide
- Production readiness checklist

**Use this for**:
- Learning how everything works together
- Testing the platform
- Debugging issues
- Understanding code flow
- Customizing components

### 3. [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)
**Size**: ~7.4 KB

**Contents**:
- Quick start commands
- Access points and URLs
- Test users and credentials
- Quick test commands
- Common troubleshooting steps
- Key file locations

**Use this for**:
- Daily operations
- Quick testing
- Common commands
- Troubleshooting cheat sheet

## ⚙️ Configuration Setup

### Option 1: Local Development (.env file)

```bash
# 1. Copy template
cp .env.template .env

# 2. Edit with your values
vim .env

# 3. Add minimum required values:
GOOGLE_API_KEY=your-gemini-api-key
GCP_PROJECT_ID=your-project-id
USE_SECRET_MANAGER=false  # Use .env instead of Secret Manager
```

### Option 2: Production (Secret Manager)

```bash
# Secrets are pre-configured in GCP Secret Manager
# No .env file needed - config will auto-load from Secret Manager

# Required secrets (already created in your GCP project):
# - google-api-key
# - google-project-id  
# - finoptiagents-llm
# - bigquery-dataset-id
# ... and more (see .env.template for full list)
```

See [`config/README.md`](../config/README.md) for complete configuration guide.

## 🚀 Quick Start

### First Time Setup

1. **Authenticate with GCP** (for Secret Manager):
   ```bash
   gcloud auth application-default login
   ```

2. **Start the platform**:
   ```bash
   cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform
   ./deploy-local.sh
   # Or manually:
   docker-compose up -d
   ```

3. **Verify deployment**:
   ```bash
   docker-compose ps
   # All services should show "Up" or "Up (healthy)"
   ```

> **📝 Note**: Services now use updated ports (15000-15002) to avoid macOS conflicts.  
> **🔐 Security**: All configuration loaded from Google Secret Manager (no .env files with secrets).

2. **Open the UI**:
   - Navigate to http://localhost:8501
   - Select a user from dropdown
   - Click "Login"
   - Start chatting!

3. **Run tests**:
   - See [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) for test commands
   - See [WALKTHROUGH.md](./WALKTHROUGH.md) for detailed test scenarios

## 📖 Reading Guide

### For Developers
1. Start with [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) to understand architecture
2. Read [WALKTHROUGH.md](./WALKTHROUGH.md) for implementation details
3. Keep [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) handy for commands

### For DevOps/SRE
1. Review [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for infrastructure
2. Check verification plan in [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)
3. Use [WALKTHROUGH.md](./WALKTHROUGH.md) for troubleshooting
4. Refer to production readiness section

### For Testers
1. Go straight to [WALKTHROUGH.md](./WALKTHROUGH.md) → Testing Guide
2. Use [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) for quick tests
3. Follow test scenarios step by step

### For Managers/Stakeholders
1. Read architecture section in [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)
2. Review implementation summary in [WALKTHROUGH.md](./WALKTHROUGH.md)
3. Check features implemented and validation checklist

## 🎯 Platform Overview

**FinOptiAgents** is a FinOps Agentic Platform built with **Google ADK (Agent Development Kit)** featuring:

- ✅ **14 Docker Services** orchestrated with Docker Compose
- ✅ **Apache APISIX** as central API Gateway
- ✅ **OPA** for RBAC authorization
- ✅ **3 Google ADK Agents**:
  - **Orchestrator ADK Agent** (Hub) - Intelligent routing with OPA integration
  - **GCloud ADK Agent** - GCP infrastructure management specialist
  - **Monitoring ADK Agent** - Cloud observability specialist
- ✅ **2 MCP Servers** for tool execution (gcloud CLI & monitoring)
- ✅ **Streamlit UI** with simulated Google Auth
- ✅ **Secret Manager Integration** for production configuration
- ✅ **Structured JSON Logging** with request ID tracing
- ✅ **~3,700 lines of code** (including ADK agents)

## 🌐 Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| Streamlit UI | http://localhost:8501 | Main user interface |
| Orchestrator | http://localhost:15000 | ADK Orchestrator agent |
| GCloud Agent | http://localhost:15001 | GCloud ADK agent |
| Monitoring Agent | http://localhost:15002 | Monitoring ADK agent |
| APISIX Gateway | http://localhost:9080 | API Gateway |
| APISIX Admin | http://localhost:9180 | Admin API |
| APISIX Dashboard | http://localhost:9000 | Admin console |
| APISIX Metrics | http://localhost:9191 | Prometheus metrics |
| OPA | http://localhost:8181 | Authorization API |

## 👥 Test Credentials

| Email | Role | Access |
|-------|------|--------|
| admin@cloudroaster.com | gcloud_admin | ✅ GCloud Agent |
| monitoring@cloudroaster.com | observability_admin | ✅ Monitoring Agent |
| robin@cloudroaster.com | developer | ❌ No Access |

## 🧪 Quick Test

### Via UI (Easiest)
1. Open http://localhost:8501
2. Select `admin@cloudroaster.com`
3. Click "Login"
4. Type: "create a VM instance"
5. See success response!

### Via API
```bash
curl -X POST http://localhost:9080/orchestrator/ask \
  -H "X-User-Email: admin@cloudroaster.com" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create a VM instance"}'
```

## 📊 Project Stats

- **Total Files**: ~35 (including ADK agents)
- **Total Code Lines**: ~3,700
- **Docker Services**: 14 (11 original + 3 ADK agents planned)
- **Exposed Ports**: 13
- **Agent Types**: 3 Google ADK agents
- **Configuration**: Secret Manager + .env fallback
- **Documentation**: 6 comprehensive guides

## 🔄 Common Tasks

### Start Platform
```bash
cd /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform
docker-compose up -d
```

### Check Status
```bash
docker-compose ps
```

### View Logs
```bash
docker-compose logs -f orchestrator
```

### Stop Platform
```bash
docker-compose down
```

### Clean Reset
```bash
docker-compose down -v
docker-compose up -d
```

## 🛠️ Customization

### Replace Mock MCP Servers
The user mentioned having actual agentic code. To replace:

```bash
# Replace GCloud MCP
cp /path/to/your/gcloud_mcp/server.py ../mcp_servers/gcloud_mcp/server.py

# Replace Monitoring MCP  
cp /path/to/your/monitoring_mcp/server.py ../mcp_servers/monitoring_mcp/server.py

# Rebuild
docker-compose up -d --build gcloud_mcp monitoring_mcp
```

### Add New Users
Edit `../opa_policy/authz.rego` and restart OPA:
```bash
docker-compose restart opa
```

See [WALKTHROUGH.md](./WALKTHROUGH.md) for detailed customization instructions.

## 📁 Directory Structure

```
finopti-platform/
├── test_run/                      # ← You are here
│   ├── IMPLEMENTATION_PLAN.md     # Architecture & design
│   ├── WALKTHROUGH.md             # Complete implementation guide
│   ├── QUICK_REFERENCE.md         # Quick commands & tests
│   └── README.md                  # This file
├── apisix_conf/                   # APISIX configuration
├── opa_policy/                    # OPA RBAC policies
├── orchestrator/                  # Orchestrator agent code
├── sub_agents/                    # GCloud & Monitoring agents
├── mcp_servers/                   # MCP mock servers
├── ui/                            # Streamlit UI
└── docker-compose.yml             # Service orchestration
```

## 🔍 Finding Information

### How do I...

**Start the platform?**
→ [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) → Quick Start Commands

**Configure Secret Manager or .env?**
→ [config/README.md](../config/README.md) → Configuration Guide

**Understand the architecture?**
→ [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) → Architecture Overview

**Test the platform?**
→ [WALKTHROUGH.md](./WALKTHROUGH.md) → Testing Guide

**Troubleshoot issues?**
→ [WALKTHROUGH.md](./WALKTHROUGH.md) → Troubleshooting

**Customize components?**
→ [WALKTHROUGH.md](./WALKTHROUGH.md) → Customization Points

**Prepare for production?**
→ [WALKTHROUGH.md](./WALKTHROUGH.md) → Production Readiness

**Run quick tests?**
→ [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) → Quick Tests

## ✅ Validation Checklist

Before considering the platform tested:

- [ ] All services start successfully (`docker-compose ps`)
- [ ] UI is accessible (http://localhost:8501)
- [ ] Admin can create VM (test in UI)
- [ ] Monitoring user can check CPU (test in UI)
- [ ] Unauthorized access is denied (test in UI)
- [ ] OPA authorization works (run API tests)
- [ ] Orchestrator routes correctly (run API tests)
- [ ] All health checks pass
- [ ] Logs show no errors

See [WALKTHROUGH.md](./WALKTHROUGH.md) → Validation Checklist for complete list.

## 🎯 Next Steps

1. ✅ **Read the documentation** (you're doing it!)
2. ⚙️ **Configure platform** (`.env` or Secret Manager)
3. 🔄 **Start the platform** (`docker-compose up -d`)
4. 🔄 **Test via UI** (http://localhost:8501)
5. 🔄 **Test ADK agents** (use new ADK-based agents)
6. 🔄 **Replace mock MCPs** with real implementations
7. 🔄 **Customize and extend**

## 📞 Support

For detailed information on any topic, refer to the appropriate documentation file:
- Architecture questions → [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)
- Implementation details → [WALKTHROUGH.md](./WALKTHROUGH.md)
- Quick commands → [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)

---

**Platform Location**: `/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform`

**Documentation Updated**: 2025-12-18

**Version**: 2.0 (Google ADK Integration)

**Key Features**: ADK Agents, Secret Manager, Structured Logging, Request Tracing

