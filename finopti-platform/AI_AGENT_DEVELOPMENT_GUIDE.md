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

# Configure logging behavior
bq_config = BigQueryLoggerConfig(
    # DISABLE if causing shutdown hangs (e.g. storage/github agents)
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    batch_size=1,  # Flush after each event (real-time tracking)
    max_content_length=100 * 1024,  # Max 100KB per event
    shutdown_timeout=10.0  # Wait 10s for pending writes on shutdown
)
```

[... rest of BQ plugin config same as before ...]

### Plugin 2: Reflect and Retry Tool Plugin

[... same as before ...]

---

## Mandatory File Structure for New Agents

```
sub_agents/{agent_name}_adk/
├── agent.py           # ADK agent + Async MCP client + logs
├── main.py            # Flask HTTP wrapper + structured logging
├── requirements.txt   # Dependencies
├── Dockerfile         # Container build + log config
└── README.md          # Agent documentation
```

### Required Components in Each File

#### 1. `agent.py` Structure (Async MCP Client Pattern)
```python
import os
import sys
import asyncio
import json
import logging
from google.adk.agents import Agent
from google.adk.apps import App

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# MCP CLIENT - ASYNCIO STDIO
# ═══════════════════════════════════════════════════════════
class ServiceMCPClient:
    """Async client for connecting to MCP server via Docker Stdio"""
    
    def __init__(self, token: str = None):
        self.image = os.getenv('MCP_DOCKER_IMAGE', 'docker-image-name')
        self.token = token
        self.process = None
        self.request_id = 0

    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        """Start container and perform handshake"""
        cmd = ["docker", "run", "-i", "--rm", 
               "-e", f"TOKEN={self.token}", 
               self.image]
        
        # Async subprocess creation
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # MCP Handshake
        await self._send_handshake()

    async def _send_handshake(self):
        # 1. Initialize
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "agent", "version": "1.0"}
        })
        # Wait for response (simplified)
        await self.process.stdout.readline()
        
        # 2. Initialized
        await self._send_notification("notifications/initialized", {})

    async def _send_notification(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        # Implementation using await self.process.stdout.readline()
        pass

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                pass
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

#### 4. `Dockerfile`
[... same as before ...]

---

## Validation Checklist

Before considering an agent "complete", verify:

**Code Quality:**
- [ ] Agent uses Google ADK (`google.adk.agents.Agent`)
- [ ] MCP client uses **Asyncio Stdio** (NOT HTTP)
- [ ] MCP Handshake (`initialize`) is implemented
- [ ] Extensive logging in all functions
- [ ] BQ Analytics configured (or disabled if necessary)

**Infrastructure:**
- [ ] Docker Compose has agent service
- [ ] Environment variables (Images, Credentials) are set
- [ ] Volume mounts are correct (e.g. `~/.config/gcloud`)

**Testing:**
- [ ] Health check passes: `curl /agent/{service}/health`
- [ ] Agent executes prompt correctly: `curl -X POST ...`

---

## Summary

**Core Principle:** User traffic flows through APISIX. Agent-to-MCP traffic is direct (Stdio) and asynchronous.

**Implementation Checklist:**
1. Async MCP client (Stdio)
2. MCP Handshake
3. Extensive logging (stdout)
4. Test scripts
5. README updates
