# MATS (Multimodal Autonomous Troubleshooting System)

**MATS** is an enterprise-grade AI microservices architecture designed to automate Google Cloud operations. It leverages the **Google Agent Development Kit (ADK)** to build autonomous agents that interact through a **Service Mesh** secured by **Google OAuth** and analyzed via full-stack **Observability**.

---

## 🏗️ High-Level Architecture

The platform follows a strict **Microservices & Service Mesh** pattern where user traffic is mediated by **Apache APISIX**, but **MCP Tool Execution** is handled via high-performance direct **Asyncio Subprocesses**.

```mermaid
flowchart TB
    User["Streamlit UI<br>(Port 8501)"] -->|OAuth Bearer Token| APISIX["Apache APISIX Gateway<br>(Port 9080)"]

    subgraph "Service Mesh / Data Plane"
        APISIX -->|Route /orchestrator| Orch["Orchestrator Agent<br>(Google ADK)"]
        APISIX -->|Route /agent/gcloud| GAgent["GCloud Agent<br>(Google ADK)"]
        APISIX -->|Route /agent/monitoring| MAgent["Monitoring Agent<br>(Google ADK)"]
        APISIX -->|Route /agent/github| GHAgent["GitHub Agent"]
        APISIX -->|Route /agent/storage| SAgent["Storage Agent"]
        APISIX -->|Route /agent/db| DBAgent["DB Agent"]
        APISIX -->|Route /agent/brave| Brave["Brave Agent"]
        APISIX -->|Route /agent/filesystem| FS["Filesystem Agent"]
        APISIX -->|Route /agent/analytics| Analytics["Analytics Agent"]
        APISIX -->|Route /agent/puppeteer| Puppet["Puppeteer Agent"]
        APISIX -->|Route /agent/sequential| Seq["Sequential Agent"]
        APISIX -->|Route /agent/googlesearch| GSearch["Google Search Agent"]
        APISIX -->|Route /agent/code| Code["Code Exec Agent"]

        Orch -->|Consult Policy| OPA["OPA Sidecar<br>(AuthZ Policy)"]
        Orch -.->|Delegation via Mesh| APISIX
        
        %% Direct MCP Integration (Stdio)
        GAgent -.->|Spawn (Stdio)| GMCP["GCloud MCP Container"]
        MAgent -.->|Spawn (Stdio)| MMCP["Monitoring MCP Container"]
        GHAgent -.->|Spawn (Stdio)| GHMCP["GitHub MCP Container"]
        SAgent -.->|Spawn (Stdio)| SMCP["Storage MCP Container"]
        DBAgent -.->|Tool Call| DBMCP["DB Toolbox MCP"]
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
| **Service Mesh** | Apache APISIX | Centralized Routing, Rate Limiting, Observability Injection for User & Agent traffic |
| **Orchestrator** | Google ADK (Python) | Intent Detection, Plan Generation, Agent Delegation |
| **Sub-Agents** | Google ADK (Python) | Domain-specific execution (GCloud resource mgmt, Monitoring) |
| **MCP Integration**| Asyncio Stdio | **Direct Docker Spawning** for standardized tool execution (No HTTP overhead) |
| **Frontend** | Streamlit + OAuth | User Interface with Google Sign-In integration |
| **Security** | OPA (Rego) | Fine-grained Role-Based Access Control (RBAC) |
| **Config** | Secret Manager | Secure storage for API keys and Service Account credentials |

---

## 🐳 Docker Services & Images

| Service | Container Name | Image / Build Context | Internal Port | Protocol | Description |
|---------|----------------|-----------------------|---------------|----------|-------------|
| **APISIX** | `finopti-apisix` | `apache/apisix:3.7.0-debian` | 9080, 9180, 9091 | HTTP | API Gateway, Admin API, Prometheus Metrics |
| **Etcd** | `finopti-etcd` | `gcr.io/etcd-development/etcd:v3.5.0` | 2379 | HTTP/gRPC | Configuration storage for APISIX |
| **OPA** | `finopti-opa` | `openpolicyagent/opa:latest` | 8181 | HTTP | Authorization Policy Engine |
| **Orchestrator** | `finopti-orchestrator` | `build: orchestrator_adk/` | 5000 | HTTP | Main ADK Agent (Brain) |
| **GCloud Agent** | `finopti-gcloud-agent` | `build: sub_agents/gcloud_agent_adk/` | 5001 | HTTP | Wrapper for GCloud operations |
| **Monitoring Agent** | `finopti-monitoring-agent` | `build: sub_agents/monitoring_agent_adk/` | 5002 | HTTP | Wrapper for Observability tools |
| **GCloud MCP** | `finopti-gcloud-mcp` | `finopti-gcloud-mcp` | N/A | Stdio | Spawned on-demand by GCloud Agent |
| **Monitoring MCP** | `finopti-monitoring-mcp` | `finopti-monitoring-mcp` | N/A | Stdio | Spawned on-demand by Monitoring Agent |
| **Loki** | `finopti-loki` | `grafana/loki:2.9.3` | 3100 | HTTP | Log Aggregation System |
| **Promtail** | `finopti-promtail` | `grafana/promtail:3.0.0` | N/A | HTTP | Log Collector & Shipper |
| **Grafana** | `finopti-grafana` | `grafana/grafana:10.2.3` | 3000 | HTTP | Visualization Dashboard (UI on 3001) |
| **Streamlit UI** | `finopti-ui` | `build: ui/` | 8501 | HTTP | Frontend Application |
| **GitHub Agent** | `finopti-github-agent` | `build: sub_agents/github_agent_adk/` | 5003 | HTTP | Wrapper for GitHub operations |
| **Storage Agent** | `finopti-storage-agent` | `build: sub_agents/storage_agent_adk/` | 5004 | HTTP | Wrapper for GCS operations |
| **DB Agent** | `finopti-db-agent` | `build: sub_agents/db_agent_adk/` | 5005 | HTTP | Wrapper for Database Toolbox |
| **GitHub MCP** | `finopti-github-mcp` | `finopti-github-mcp` | N/A | Stdio | Spawned on-demand by GitHub Agent |
| **Storage MCP** | `finopti-storage-mcp` | `finopti-storage-mcp` | N/A | Stdio | Spawned on-demand by Storage Agent |
| **DB Toolbox MCP**| `finopti-db-mcp-toolbox`| `us-central1-docker.pkg.dev/...`| 5000 | HTTP | Still accessed via HTTP (Toolbox pattern) |
| **Brave Search Agent** | `finopti-brave-agent` | `build: sub_agents/brave_search_agent_adk/` | 5006 | HTTP | Wrapper for Brave Search MCP |
| **Filesystem Agent** | `finopti-filesystem-agent` | `build: sub_agents/filesystem_agent_adk/` | 5007 | HTTP | Wrapper for Filesystem MCP |
| **Analytics Agent** | `finopti-analytics-agent` | `build: sub_agents/analytics_agent_adk/` | 5008 | HTTP | Wrapper for Google Analytics MCP |
| **Puppeteer Agent** | `finopti-puppeteer-agent` | `build: sub_agents/puppeteer_agent_adk/` | 5009 | HTTP | Wrapper for Browser Automation MCP |
| **Sequential Agent** | `finopti-sequential-agent` | `build: sub_agents/sequential_thinking_agent_adk/` | 5010 | HTTP | Cognitive Reasoning Agent |
| **Google Search Agent** | `finopti-googlesearch-agent` | `build: sub_agents/googlesearch_agent_adk/` | 5011 | HTTP | Native ADK Google Search Tool |
| **Code Exec Agent** | `finopti-code-agent` | `build: sub_agents/code_execution_agent_adk/` | 5012 | HTTP | Native ADK Python Execution Tool |

---

## �️ Comprehensive Observability

We implement a **Single Pane of Glass** observability strategy. **Log flow is confirmed from all containers to Loki.**

### 1. Structured Logging (The "Trace ID")
Every request is assigned a `trace_id` by APISIX. This ID is propagated to Orchestrator and Agents.

### 2. The Stack (Loki + Grafana)
- **Promtail**: Scrapes Docker container logs.
- **Loki**: Aggregates logs without indexing full text (efficient).
- **Grafana**: Visualizes logs and metrics.

### 3. Troubleshooting with Grafana
Access Grafana at **http://localhost:3001** (Default: `admin`/`admin`).

#### Verified Log Queries:
- **All Platform Logs**: `{com_docker_compose_project="finopti-platform"}`
- **Specific Service**: `{container=~"finopti-orchestrator.*"}`
- **Errors**: `{com_docker_compose_project="finopti-platform"} |= "ERROR"`

  volumes:
    - loki-data:/loki
  ```
This ensures that all logs and indices survive container restarts or upgrades.

#### 4. Summary Diagram
```mermaid
flowchart LR
    Container["Docker Container<br>(stdout/stderr)"] -->|Docker Socket| Promtail
    Promtail -->|Parse & Label| Loki["Loki Service"]
    
    subgraph "Loki Internal Storage"
        Loki -->|Index Metadata| Index["BoltDB Index<br>(/loki/boltdb-shipper-active)"]
        Loki -->|Compressed Logs| Chunks["Filesystem Chunks<br>(/loki/chunks)"]
    end
    
    subgraph "Host Persistence"
        Index & Chunks --> Vol["Docker Volume:<br>finopti-loki-data"]
    end



---

## 🛠️ Onboarding New Services for Observability

To ensure a new Docker container's logs are automatically ingested by the observability stack, follow these rules:

### Requirement 1: Use Docker Compose Project
Ensure your service is defined in `docker-compose.yml`. Promtail is configured to scrape all containers with the label:
`com.docker.compose.project=finopti-platform`
*(matches the default behavior when running `docker-compose up` in this directory)*

### Requirement 2: Log to Stdout/Stderr
Your application **MUST** write logs to standard output (`stdout`) or standard error (`stderr`).
- **Do not** write to local log files inside the container.
- For Python, ensure output is unbuffered in your `Dockerfile`:
  ```dockerfile
  ENV PYTHONUNBUFFERED=1
  ```

### Requirement 3: Use Structured JSON Logging (Recommended)
Promtail is configured to parse JSON logs and extract specific keys as indexed labels. For best results, your logs should be structured JSON with these fields:

```json
{
  "timestamp": "2026-01-05T12:00:00Z",
  "level": "INFO",
  "service": "my-service-name",
  "request_id": "12345-uuid",
  "user_email": "user@example.com",
  "message": "Operation completed successfully"
}
```

If you use simple text logging, it will still be captured, but you won't be able to filter efficiently by `request_id` or `user_email` in Grafana.

---

## �🔐 Authentication & Authorization

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
- **GCloud Agent**: Spawns `gcloud-mcp` container via Asyncio.
- **Monitoring Agent**: Spawns `monitoring-mcp` container via Asyncio.
- **GitHub Agent**: Spawns `github-mcp` container via Asyncio.
- **Storage Agent**: Spawns `storage-mcp` container via Asyncio.
- **GitHub Agent (`finopti-github-agent`)**:
  - **Dynamic Authentication**: Supports per-session **Personal Access Tokens (PAT)**.
    - **Default**: Uses `github-personal-access-token` from Secret Manager.
    - **Interactive**: If the default token fails or is missing, the agent will ask the user for a PAT via chat.

### 🛡️ Resilience: Reflect & Retry

The platform implements **active resilience** at the application layer using the Google ADK's `ReflectAndRetryToolPlugin`.

-   **Mechanism**: If an agent's tool call (e.g., a `gcloud` command) fails, the plugin intercepts the error and feeds it back to the LLM. The LLM then "reflects" on the error and attempts the call again with corrected parameters.
-   **Coverage**: Enabled on all Agents.

### 📊 Agent Analytics (BigQuery)

We use the **Google ADK BigQuery Analytics Plugin** to telemetrically log all ADK agent operations.

-   **Purpose**: Provides deep insights into agent behavior, token usage, tool execution success/failure, and user intent.
-   **Configuration**:
    -   `BQ_ANALYTICS_ENABLED`: Master switch (Set to `false` if causing shutdown delays).
    -   `BQ_ANALYTICS_DATASET`: Target Dataset (Default: `agent_analytics`).
    -   `BQ_ANALYTICS_TABLE`: Target Table (Default: `agent_events_v2`).

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
1. **APISIX Phase**: Verifies Gateway routing and Upstream health.
2. **Agent Phase**: Tests individual agents (Orchestrator, GCloud) in isolation.
3. **End-to-End (E2E) Phase**: Simulates a real user prompt flowing through the system.

---

## 📂 Project Directory Structure

```text
finopti-platform/
├── orchestrator_adk/       # 🧠 The Brain: Main ADK Agent
├── sub_agents/             # 🦾 The Arms: Specialized ADK Agents
│   ├── gcloud_agent_adk/   # 
│   ├── monitoring_agent_adk/
│   ├── github_agent_adk/   
│   ├── storage_agent_adk/  
│   ├── db_agent_adk/       
│   ├── brave_search_agent_adk/
│   ├── filesystem_agent_adk/
│   ├── analytics_agent_adk/
│   ├── puppeteer_agent_adk/
│   ├── sequential_thinking_agent_adk/
│   ├── googlesearch_agent_adk/
│   └── code_execution_agent_adk/
├── ui/                     # 🖥️ Streamlit Frontend
├── config/                 # ⚙️ Shared Config (Secret Manager)
├── apisix_conf/            # 🚦 Gateway Routes
├── opa_policy/             # 🛡️ AuthZ Rules
├── observability/          # 👁️ Loki/Promtail/Grafana Config
├── docs/                   # 📚 Detailed Documentation
├── scripts/                # 🔧 DevOps & Setup Scripts
├── deploy-local.sh         # 🚀 Main Entry Point
└── run_tests.py            # 🧪 Test Runner
```

### 📦 External Dependencies: MCP Servers

The platform relies on several external MCP servers, built from the [robin-varghese/mcp-server](https://github.com/robin-varghese/mcp-server/) repository:

1. **GCloud MCP Server** (`finopti-gcloud-mcp`)
2. **Monitoring MCP Server** (`finopti-monitoring-mcp`)
3. **GitHub MCP Server** (`finopti-github-mcp`)
4. **Google Storage MCP** (`finopti-storage-mcp`)
5. **Google Database Toolbox** (`finopti-db-toolbox`)

For build instructions, see [docs/mcp_server_build_strategy.md](docs/mcp_server_build_strategy.md).

---

## 📝 version History

| Version | Date       | Changes |
|---------|------------|---------|
| **2.1.0** | 2026-01-16 | **Expansion**: Added 7 new sub-agents for comprehensive capabilities: Brave Search, Filesystem, Google Analytics, Puppeteer, Sequential Thinking, Google Search (Native), and Code Execution (Native). Integrated Secret Manager for model configuration. |
| **2.0.0** | 2026-01-05 | **Architecture Overhaul**: Removed APISIX requirement for MCP protocols. Implemented direct, asynchronous stdio integration via Docker spawning for GCloud, Monitoring, GitHub, and Storage agents. Fixed timeout issues by optimizing I/O. |
| 1.1.0   | 2026-01-04 | MCP Refactoring - HTTP via APISIX (Deprecated in v2.0). |
| 1.0.1   | 2026-01-02 | Added dynamic GitHub PAT injection and auth/credentials flow documentation. |
| 1.0.0   | 2026-01-01 | Initial release: Google ADK integration, APISIX, OAuth, OPA, PLG stack. |
