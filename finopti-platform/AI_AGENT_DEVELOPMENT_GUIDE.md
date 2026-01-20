# FinOptiAgents Platform - AI Agent Development Instructions

**Version:** 2.0
**Last Updated:** 2026-01-05
**Purpose:** Mandatory guidelines for AI assistants implementing new agents

---

## ⚠️ CRITICAL ARCHITECTURE RULES

### Rule 1: Agent Traffic Routes Through APISIX
```
✅ CORRECT:   User → APISIX → Agent
```

### Rule 2: MCP Communication MUST Use Direct Stdio (Asyncio)
Agents MUST communicate with MCP servers by spawning them directly (e.g., via `docker run`) and communicating over standard input/output (Stdio).
**Do NOT use HTTP/APISIX for MCP calls.**
```python
# ✅ CORRECT (Asyncio Subprocess)
process = await asyncio.create_subprocess_exec("docker", "run", ...)
# Communicate via process.stdin / process.stdout

# ❌ INCORRECT
requests.post(f"{APISIX_URL}/mcp/service_name/", json=payload)
```

### Rule 3: Use Google ADK for Agent Intelligence
All agents MUST use `google.adk.agents.Agent` for LLM orchestration.

### Rule 4: ALL Logs MUST Go to Grafana/Loki
All stdout/stderr from containers is automatically collected by Promtail and sent to Loki.
Use structured logging for query-ability.

---

## Platform Architecture Overview

### Service Mesh Pattern
```
┌──────────────┐
│  Streamlit   │ (Port 8501) ← User authenticates via Google OAuth
│      UI      │                Gets GCP credentials
└──────┬───────┘
       │ HTTP + OAuth Token
       ▼
┌──────────────┐
│   APISIX     │ (Port 9080) ← Traffic Gateway
│   Gateway    │               Logs to Loki via Promtail
└──────┬───────┘
       │
   ┌───┴────────────────┐
   ▼                    ▼
┌───────────┐      ┌──────────┐
│Orchestr.  │      │   OPA    │
│  Agent    │◄─────│  Policy  │ (Validates OAuth + permissions)
└─────┬─────┘      └──────────┘
      │ Uses Gemini API Key
      ▼ HTTP via APISIX
┌──────────────────────────────┐
│    Sub-Agents (ADK-based)    │ Each uses:
│ • gcloud_agent_adk:5001      │ • User's GCP credentials
│ • monitoring_agent_adk:5002  │ • Gemini API Key
│ • github_agent_adk:5003      │ • Service-specific creds (e.g. GitHub PAT)
│ • storage_agent_adk:5004     │
│ • db_agent_adk:5005          │
│ • brave_search_agent_adk:5006│
│ • filesystem_agent_adk:5007  │
│ • analytics_agent_adk:5008   │
│ • puppeteer_agent_adk:5009   │
│ • sequential_thinking_agent_adk:5010 │
│ • googlesearch_agent_adk:5011│
│ • code_execution_agent_adk:5012 │
│                              │
│ ┌──────────────────────────┐ │
│ │ MCP Protocol (Stdio)     │ │
│ │ ▼ Direct Spawn (Docker)  │ │
│ │ ┌──────────────────────┐ │ │
│ │ │ MCP Server Container │ │ │
│ │ └──────────────────────┘ │ │
│ └──────────────────────────┘ │
└────┬─────────────────────────┘
     │ Logs to stdout → Promtail → Loki
     ▼
┌──────────────────────────────┐
│  Observability Stack         │
│ Grafana:3000 (UI)            │
│ Loki:3100 (Log aggregation)  │
│ Promtail (Log collector)     │
└──────────────────────────────┘
```

### Authentication & Credentials Flow

**1. User Authentication (Google OAuth)**
- User logs into Streamlit via Google OAuth
- OAuth provides: user email, access token
- User must have GCP credentials configured locally

**2. Agent Credentials**
```python
# Each agent receives and uses:
{
    "user_email": "user@example.com",      # From OAuth
    "google_api_key": os.getenv("GOOGLE_API_KEY"),  # For Gemini
    "gcp_credentials": "~/.config/gcloud",  # Mounted volume
    "service_specific": {...}  # e.g. GITHUB_PERSONAL_ACCESS_TOKEN
}
```

**3. GitHub MCP Specific Requirements**
```python
# GitHub MCP needs:
{
    "github_pat": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),  # From Secret Manager or env
    "repo_url": "https://github.com/user/repo",  # From user or config
    "user_info": {...}  # From OAuth if available
}
```

### Three Communication Layers

1. **Layer 1: User → Agent** (HTTP via APISIX)
   - Route: `/agent/{service_name}/*`
   - Always through APISIX
   - Carries OAuth token

2. **Layer 2: Agent Logic** (Google ADK)
   - LLM reasoning with Gemini (uses `GOOGLE_API_KEY`)
   - Tool orchestration
   - Retry/reflection
   - Uses user's GCP credentials

3. **Layer 3: Agent → MCP** (Direct Stdio via Asyncio)
   - **MUST use Asyncio Subprocess**
   - **MUST perform MCP Handshake** (initialize -> initialized)
   - Passes credentials via Environment Variables to spawned container

---

## Standard Agent Tooling Patterns

The platform supports two primary patterns for agent capabilities:

### 1. MCP Wrapper Agents (Asyncio Stdio)
These agents spawn a separate Docker container for the Model Context Protocol (MCP) server.
- **GCloud Agent**: Spawns `finopti-gcloud-mcp`
- **Monitoring Agent**: Spawns `finopti-monitoring-mcp`
- **GitHub Agent**: Spawns `finopti-github-mcp`
- **Storage Agent**: Spawns `finopti-storage-mcp`
- **Brave Search Agent**: Spawns `finopti-brave-search-mcp`
- **Filesystem Agent**: Spawns `finopti-filesystem-mcp`
- **Analytics Agent**: Spawns `finopti-google-analytics-mcp`
- **Puppeteer Agent**: Spawns `finopti-puppeteer-mcp`

### 2. Native ADK Tool Agents
These agents use the ADK's native tool libraries or logic directly within the python process.
- **Google Search Agent**: Uses `google.adk.tools.google_search`
- **Code Execution Agent**: Uses `google.adk.code_executors.BuiltInCodeExecutor`
- **Sequential Agent**: Uses internal Chain-of-Thought logic

---

## Google ADK Plugins (MANDATORY)

All agents MUST include two ADK plugins for proper operation, analytics, and error handling.

### Plugin 1: BigQuery Analytics Plugin

**Purpose:** Tracks all agent interactions, LLM calls, tool executions, and errors to BigQuery for analytics.

**Configuration:**
```python
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)

# Initialize Plugin
bq_plugin = BigQueryAgentAnalyticsPlugin(
    # Project/Dataset/Table passed to Constructor
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    # Config object for behavior
    config=BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
        batch_size=1,
        max_content_length=100 * 1024
    )
)
```

### Plugin 2: Reflect and Retry Tool Plugin

[... same as before ...]

---

## Mandatory File Structure for New Agents

```
sub_agents/{agent_name}_adk/
├── agent.py           # Core Logic: Agent + App + Plugins + Auth
├── main.py            # Entrypoint: Flask HTTP wrapper
├── requirements.txt   # Dependencies (google-adk, google-cloud-secret-manager)
├── Dockerfile         # Container build definition
├── manifest.json      # Agent Metadata (ID, Description, Tools)
├── instructions.json  # System Instructions / Persona
└── verify_agent.py    # Self-Verification Script (MANDATORY)
```

### Required Components in Each File

#### 1. `agent.py` Structure (Standard ADK Pattern)

All agents must use the `App` wrapper to support plugins and `InMemoryRunner` for execution.

```python
import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.genai import types
from google.cloud import secretmanager

# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- AUTHENTICATION ---
def setup_auth():
    """Ensure GOOGLE_API_KEY is set (Check Env -> Secret Manager)."""
    if os.getenv("GOOGLE_API_KEY"):
        return

    project_id = os.getenv("GCP_PROJECT_ID")
    if project_id:
        try:
            client = secretmanager.SecretManagerServiceClient()
            secret_name = "google-api-key"
            name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            api_key = response.payload.data.decode("UTF-8")
            os.environ["GOOGLE_API_KEY"] = api_key
            logger.info("Loaded GOOGLE_API_KEY from Secret Manager")
        except Exception as e:
            logger.warning(f"Failed to fetch google-api-key from Secret Manager: {e}")

setup_auth()

# --- CONFIGURATION ---
def get_gemini_model():
    # ... (Same logic: Env -> Secret Manager -> Default) ...
    return os.getenv("FINOPTIAGENTS_LLM", "gemini-2.0-flash")

# Load Manifest & Instructions
manifest = {}
manifest_path = Path(__file__).parent / "manifest.json"
if manifest_path.exists():
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

instruction_str = "You are a helpful agent."
instructions_path = Path(__file__).parent / "instructions.json"
if instructions_path.exists():
    with open(instructions_path, "r") as f:
        instruction_str = json.load(f).get("instruction", instruction_str)

# --- AGENT & APP DEFINITION ---
agent = Agent(
    name=manifest.get("agent_id", "my_agent"),
    model=get_gemini_model(),
    description=manifest.get("description", "My Agent"),
    instruction=instruction_str,
    # tools=[...] # Add Tools Here
)

app = App(
    name=f"finopti_{manifest.get('agent_id', 'agent')}",
    root_agent=agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=3),
        BigQueryAgentAnalyticsPlugin(
            project_id=os.getenv("GCP_PROJECT_ID"),
            dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
            table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
            config=BigQueryLoggerConfig(
                enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true"
            )
        )
    ]
)

# --- EXECUTION LOGIC ---
async def send_message_async(prompt: str, user_email: str = None, project_id: str = None) -> str:
    try:
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"
            
        async with InMemoryRunner(app=app) as runner:
            session_uid = user_email if user_email else "default"
            # Create session with app_name
            await runner.session_service.create_session(
                session_id="default", 
                user_id=session_uid, 
                app_name=app.name
            )
            
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            
            async for event in runner.run_async(
                session_id="default", 
                user_id=session_uid, 
                new_message=message
            ):
                 if hasattr(event, 'content') and event.content:
                     for part in event.content.parts:
                         if part.text: response_text += part.text
            return response_text
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return f"Error: {str(e)}"

def process_request(prompt: str) -> str:
    """Synchronous Entrypoint for main.py"""
    return asyncio.run(send_message_async(prompt))
```

#### 2. `main.py` Structure
[... same as before (Flask wrapper) ...]

#### 3. `requirements.txt`
```txt
google-adk>=1.21.0
google-genai>=0.6.0
flask>=3.0.3
gunicorn>=22.0.0
# ...
```

#### 4. `manifest.json` (Metadata)
```json
{
  "agent_id": "my_agent_name",
  "description": "Short description of what this agent does.",
  "type": "adk-model-powered",
  "tools": ["tool_name_1"]
}
```

#### 5. `instructions.json` (Persona)
```json
{
  "instruction": "You are a specialized agent for X. Your goal is Y."
}
```

#### 6. `verify_agent.py` (Self-Verification)
Every agent MUST include a verification script to test its core functionality via the HTTP endpoint.

```python
import requests
import os
import sys

APISIX_URL = os.getenv("APISIX_URL", "http://localhost:9080")
AGENT_ROUTE = "/agent/my_agent_name/execute"
PROMPT = "Test prompt here"

def verify():
    url = f"{APISIX_URL}{AGENT_ROUTE}"
    print(f"Sending prompt to {url}...")
    try:
        response = requests.post(url, json={"prompt": PROMPT}, timeout=60)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 200 and "\"success\":true" in response.text:
            return True
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if verify():
        sys.exit(0)
    else:
        sys.exit(1)
```

---

## Validation Checklist

Before considering an agent "complete", verify:

**Code & Config:**
- [ ] `agent.py` uses `App` wrapper and `InMemoryRunner`.
- [ ] `manifest.json` and `instructions.json` are present and loaded.
- [ ] Authentication uses Secret Manager fallback.
- [ ] Plugins (`ReflectAndRetry`, `BigQueryAnalytics`) are configured correctly.

**Infrastructure:**
- [ ] Docker Compose has agent service with all ENV vars (`GCP_PROJECT_ID`, `GOOGLE_API_KEY`).
- [ ] Health check pass: `curl /health`.

**Testing:**
- [ ] **MANDATORY**: `verify_agent.py` passes successfully against the running container/APISIX.
- [ ] **Full Suite**: Run `python3 tests/run_suite.py` to verify against other agents.



---

## V. Deployment and Security Integration (MANDATORY)

After coding your agent, you MUST complete these integration steps for it to be reachable and secure.

### 1. Update OPA Policy (Security)
The platform uses Open Policy Agent (OPA) for authorization. You must explicit allow access to your new agent.

**File:** `opa_policy/authz.rego`
```rego
allow if {
    user_role["gcloud_admin"]
    input.target_agent == "your_agent_name"  # e.g. "code_execution"
}
```

### 2. Update Deployment Scripts
**File:** `docker-compose.yml`
Add your service definition:
```yaml
  your_agent_name:
    build:
      context: .
      dockerfile: sub_agents/your_agent_name/Dockerfile
    environment:
      - GCP_PROJECT_ID=${GCP_PROJECT_ID}
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
    ports:
      - "50xx:50xx"
    networks:
      - finopti-net
```
*Note: `deploy-local.sh` automatically picks up changes from `docker-compose.yml`, so no changes needed there unless you have custom build logic.*

### 3. Update Orchestrator Routing
The Orchestrator agent decides which sub-agent handles a request.
**File:** `orchestrator_adk/agent.py`

1.  **Add Keywords:** Update `detect_intent` to recognize your agent's domain.
2.  **Register Endpoint:** Update `agent_endpoints` map in `route_to_agent`.
    ```python
    'your_agent': f"{config.APISIX_URL}/agent/your_agent/execute",
    ```
3.  **Update Prompt:** Update the system instruction in `orchestrator_agent` to make the LLM aware of the new capability.

### 4. Create APISIX Route
**File:** `apisix_conf/init_routes.sh`
Add a new route for your agent:
```bash
# Route X: Your Agent
curl -i -X PUT "${APISIX_ADMIN}/routes/X" ...
    "uri": "/agent/your_agent/*",
    "upstream": { "nodes": { "your_agent_name:50xx": 1 } }
    # ...
```

---

## Summary

**Core Principle:** User traffic flows through APISIX. Agent-to-MCP traffic is direct (Stdio) and asynchronous.

**Implementation Checklist:**
1. Async MCP client (Stdio) with Handshake
2. Dynamic LLM Model Name (Env/Secret Manager)
3. Structured Logging & Exception Handling
4. OPA Policy Update (authz.rego)
5. Docker Compose Service Definition
6. Orchestrator Routing & APISIX Route

