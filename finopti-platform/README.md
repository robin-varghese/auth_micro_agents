# FinOptiAgents Platform

The **FinOptiAgents Platform** is an enterprise-grade AI microservices architecture designed to automate Google Cloud operations. It leverages the **Google Agent Development Kit (ADK)** to build autonomous agents that interact through a **Service Mesh** secured by **Google OAuth** and analyzed via full-stack **Observability**.

---

## 🏗️ High-Level Architecture

The platform follows a strict **Microservices & Service Mesh** pattern where all traffic is mediated by **Apache APISIX**.

```mermaid
flowchart TB
    User["Streamlit UI<br>(Port 8501)"] -->|OAuth Bearer Token| APISIX["Apache APISIX Gateway<br>(Port 9080)"]

    subgraph "Service Mesh / Data Plane"
        APISIX -->|Route /orchestrator| Orch["Orchestrator Agent<br>(Google ADK)"]
        APISIX -->|Route /agent/gcloud| GAgent["GCloud Agent<br>(Google ADK)"]
        APISIX -->|Route /agent/monitoring| MAgent["Monitoring Agent<br>(Google ADK)"]

        Orch -->|Consult Policy| OPA["OPA Sidecar<br>(AuthZ Policy)"]
        
        Orch -.->|Delegation via Mesh| APISIX
        GAgent -.->|Tool Call| GMCP["GCloud MCP Server<br>(Node.js)"]
        MAgent -.->|Tool Call| MMCP["Monitoring MCP Server<br>(Python)"]
    end

    subgraph "Observability Stack"
        Promtail["Promtail<br>(Log Collector)"] --> Loki["Loki<br>(Log Aggregation)"]
        Loki --> Grafana["Grafana<br>(Visualization)"]
        APISIX -.->|Metrics| Prometheus["Prometheus"]
    end
```

### Key Components

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| **Service Mesh** | Apache APISIX | Centralized Routing, Rate Limiting, Observability Injection |
| **Orchestrator** | Google ADK (Python) | Intent Detection, Plan Generation, Agent Delegation |
| **Sub-Agents** | Google ADK (Python) | Domain-specific execution (GCloud resource mgmt, Monitoring) |
| **Mock Servers** | MCP Protocol | Standardized tool execution for GCloud and Monitoring tools |
| **Frontend** | Streamlit + OAuth | User Interface with Google Sign-In integration |
| **Security** | OPA (Rego) | Fine-grained Role-Based Access Control (RBAC) |
| **Config** | Secret Manager | Secure storage for API keys and Service Account credentials |

---

## 🔐 Authentication & Authorization

### Authentication Layer (Google OAuth)
The platform uses **Google OAuth 2.0** for user identity.
1. User clicks "Login with Google" in Streamlit.
2. Credentials are exchanged for an **ID Token** (JWT).
3. The JWT is passed as a `Bearer` token in the `Authorization` header to APISIX.
4. **APISIX** validates the token signature against Google's public keys.

### Authorization Layer (OPA)
We use **Open Policy Agent (OPA)** for decoupled authorization.
- The **Orchestrator** queries OPA before delegating tasks.
- **Policy File**: `opa_policy/authz.rego`
- **Logic**: Maps user email → Role → Allowed Agents.
    - `admin@`: Access to `gcloud` agent.
    - `monitoring@`: Access to `monitoring` agent only.

---

## 🤖 Google ADK & Agent Implementation

We use the **Google Agent Development Kit (ADK)** to structure our agents.

### Agent Structure (`orchestrator_adk/`, `sub_agents/`)
Each agent is a standalone microservice containing:
- **`agent.py`**: The ADK configuration (Model, Tools, Instructions).
- **`main.py`**: Flask wrapper to expose the agent via HTTP.
- **`structured_logging.py`**: Standardized logging for Observability.

### Plugins & Tooling
Agents execute actions via **Tools** defined using the ADK's `FunctionTool` or **MCP Clients**.
- **GCloud Agent**: Uses tools to call the `gcloud-mcp` server.
- **Monitoring Agent**: Uses tools to call the `monitoring-mcp` server.

**Example Agent Definition (Snippet):**
```python
model = Model(model_name="gemini-1.5-flash")
agent = Agent(
    model=model,
    tools=[list_vms, create_vm],  # Tools defined via MCP
    system_instruction="You are a GCloud infrastructure expert..."
)
```

---

## 👁️ Comprehensive Observability

We implement a **Single Pane of Glass** observability strategy.

### 1. Structured Logging (The "Trace ID")
Every request is assigned a `trace_id` by APISIX. This ID is propagated to:
- Orchestrator
- Sub-Agents
- MCP Servers

This allows us to trace a single user prompt across the entire microservices chain.

### 2. The Stack (Loki + Grafana)
- **Promtail**: Scrapes Docker container logs.
- **Loki**: Aggregates logs without indexing full text (efficient).
- **Grafana**: Visualizes logs and metrics.

### 3. Troubleshooting with Grafana
Access Grafana at **http://localhost:3001** (Default: `admin`/`admin`).

**Common Queries:**
- **Find all logs for a request**: `{trace_id="<id_from_ui>"}`
- **Filter errors**: `{container_name=~"finopti.+"} |= "ERROR"`
- **Agent Performance**: `{service="orchestrator"}` to see reasoning steps.

---

## 🚀 Getting Started

### Prerequisites
1. **Docker Desktop**: Running locally.
2. **GCP Project**: With Secret Manager API enabled.
3. **Google Auth**: Run `gcloud auth application-default login`.

### Deployment
The platform uses **Google Secret Manager** for all configuration.

```bash
# 1. Clone & Setup
git clone <repo>
cd finopti-platform

# 2. Deploy (Builds images & starts containers)
./deploy-local.sh
```

### Access Points
- **UI**: [http://localhost:8501](http://localhost:8501)
- **Grafana**: [http://localhost:3001](http://localhost:3001)
- **APISIX Admin**: [http://localhost:9180](http://localhost:9180)

---

## 🧪 Testing Strategy

We adhere to a rigorous testing pyramid using `pytest` and custom test runners.

### Test Suite (`run_tests.py`)
Run the comprehensive suite to validate the entire platform:

```bash
python3 run_tests.py
```

### Test Phases
1. **MCP Phase**: Validates that Mock Servers respond to JSON-RPC.
2. **APISIX Phase**: Verifies Gateway routing and Upstream health.
3. **Agent Phase**: Tests individual agents (Orchestrator, GCloud) in isolation.
4. **End-to-End (E2E) Phase**: Simulates a real user prompt flowing through the system.

### BigQuery Analytics Testing
Set `BQ_ANALYTICS_ENABLED=true` in Secret Manager to enable cost analysis testing. The `run_tests.py` script will verify that rows are inserted into BigQuery during E2E tests.

---

## 📂 Project Directory Structure

```text
finopti-platform/
├── orchestrator_adk/       # 🧠 The Brain: Main ADK Agent
├── sub_agents/             # 🦾 The Arms: Specialized ADK Agents
│   ├── gcloud_agent_adk/   # Handles Compute/Infra tasks
│   └── monitoring_agent_adk/# Handles Logs/Metrics tasks
├── ui/                     # 🖥️ Streamlit Frontend
├── config/                 # ⚙️ Shared Config (Secret Manager)
├── apisix_conf/            # 🚦 Gateway Routes & Plugins
├── opa_policy/             # 🛡️ AuthZ Rules (Rego)
├── observability/          # 👁️ Loki/Promtail/Grafana Config
├── docs/                   # 📚 Detailed Documentation
├── scripts/                # 🔧 DevOps & Setup Scripts
├── deploy-local.sh         # 🚀 Main Entry Point
└── run_tests.py            # 🧪 Test Runner
```

---

## 🐛 Troubleshooting & FAQ

**Q: "OAuth Disabled" in UI?**
A: Ensure your GCP user has access to the Secret Manager secrets defined in `SECRET_MANAGER_SETUP.md`.

**Q: Agents can't talk to each other?**
A: Check `docker-compose ps`. All containers must be healthy. ensure `finopti-net` bridge network is effectively bridging them.

**Q: How to add a new plugin?**
A:
1. Define the tool in `sub_agents/<agent>/tools.py`.
2. Register it in `agent.py`.
3. Rebuild the agent container: `docker-compose build <service>`.

---

**Last Updated:** 2026-01-01
**Status:** Production Ready

---

## 📝 Document History

| Version | Date       | Author | Revision Summary |
|---------|------------|--------|------------------|
| 1.1.0   | 2026-01-01 | Antigravity AI | Comprehensive update covering Service Mesh, ADK, and Observability architecture. |
