# FinOptiAgents Platform - AI Agent Development Instructions

**Version:** 3.0 (STABLE)
**Last Updated:** 2026-01-21
**Purpose:** Mandatory guidelines for AI assistants implementing new agents.
**Status:** GOLD STANDARD - Adherence is required to prevent concurrency crashes.

---

## ⚠️ CRITICAL ARCHITECTURE RULES

### Rule 1: Use `ContextVar` for MCP Clients (NO GLOBAL VARIABLES)
**CRITICAL:** Every HTTP request runs in a new `asyncio` event loop. You **cannot** reuse an MCP client connection across requests or loops. Doing so causes `RuntimeError: active loop mismatch` and hangs.
**Requirement:** Use `contextvars.ContextVar` to store the client for the current request context.

### Rule 2: Robust Configuration (Env Vars + Secrets)
**CRITICAL:** Never hardcode Docker image names or secret keys.
**Requirement:** 
1. Use `os.getenv("SERVICE_MCP_DOCKER_IMAGE", "default-image")` to support local/prod overrides.
2. Use the `config` module to fetch `BQ_ANALYTICS_TABLE` and other secrets.

### Rule 3: Agent Traffic Routes Through APISIX
```
✅ CORRECT:   User → APISIX → Agent
```

### Rule 4: ALL Logs MUST Go to Grafana/Loki
All stdout/stderr from containers is automatically collected by Promtail and sent to Loki. Use structured logging.

---

## Mandatory File Structure for New Agents

```
sub_agents/{agent_name}_adk/
├── agent.py           # Core Logic: Agent + App + Plugins + Auth + CONTEXT ISOLATION
├── main.py            # Entrypoint: Flask HTTP wrapper
├── verify_agent.py    # Self-Verification Script (MANDATORY)
├── Dockerfile         # Container build definition
└── ...
```

### 1. `agent.py` (The Pattern)

This is the **ONLY** acceptable pattern for `agent.py`. Do not deviate.

```python
import os
import sys
import asyncio
import json
import logging
from contextvars import ContextVar  # <--- CRITICAL IMPORT
from pathlib import Path
from typing import Dict, Any

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.genai import types
from config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. CONTEXT ISOLATION ---
# Stores the MCP client for the current request/loop.
# Default=None prevents accidental reuse.
_mcp_ctx: ContextVar["MyMCPClient"] = ContextVar("mcp_client", default=None)

class MyMCPClient:
    def __init__(self):
        # Allow override via ENV for testing/staging
        self.image = os.getenv("MY_MCP_DOCKER_IMAGE", "finopti-my-mcp") 
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0

    async def connect(self):
        cmd = ["docker", "run", "-i", "--rm", "-v", self.mount_path, self.image]
        logger.info(f"Starting MCP: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await self._handshake()

    # ... (Standard _handshake, _send_json, call_tool, close) ...

async def ensure_mcp():
    """Retrieve the client for the CURRENT context."""
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client

# --- 2. TOOL WRAPPERS ---
async def my_tool(arg1: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    # verify tool name matches MCP server spec exactly!
    return await client.call_tool("my_tool", {"arg1": arg1}) 

# --- 3. AGENT SETUP ---
# ... (Standard Agent, App, Plugin setup) ...

# --- 4. EXECUTION LOGIC (Lifecycle Management) ---
async def send_message_async(prompt: str, user_email: str = None) -> str:
    # A. Initialize Client for THIS Scope
    mcp = MyMCPClient()
    token_reset = _mcp_ctx.set(mcp) # Bind to ContextVar
    
    try:
        # B. Connect
        await mcp.connect()
        
        # C. Run Agent
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(
                app_name="finopti_my_agent",
                user_id="default",
                session_id="default"
            )
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(session_id="default", user_id="default", new_message=message):
                 if hasattr(event, 'content') and event.content:
                     for part in event.content.parts:
                         if part.text: response_text += part.text
            return response_text
    finally:
        # D. Cleanup
        await mcp.close()
        _mcp_ctx.reset(token_reset) # Unbind to prevent leaks

def send_message(prompt: str, user_email: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email))
```

### 2. `verify_agent.py` (MANDATORY)

Verification scripts MUST use the valid OAuth token to test accurately.

```python
import requests
import os
import sys

APISIX_URL = os.getenv("APISIX_URL", "http://localhost:9080")
AGENT_ROUTE = "/agent/my_agent/execute"
PROMPT = "Test prompt"

def verify():
    url = f"{APISIX_URL}{AGENT_ROUTE}"
    headers = {}
    
    # Authenticate like the real platform
    token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    try:
        response = requests.post(url, json={"prompt": PROMPT}, headers=headers, timeout=60)
        # ... validation logic ...
```

---

## Troubleshooting & Common Pitfalls

### 1. "Event Loop Mismatch" / 504 Gateway Timeout
- **Symptom**: Agent hangs, returns 504, or logs `RuntimeError: active loop mismatch`.
- **Cause**: Reusing a global MCP client variable across different `asyncio.run()` calls.
- **Fix**: **Use `ContextVar`** as shown in Rule 1. Never store `_mcp` globally.

### 2. "Given Arrow field content_parts is a list..." (BigQuery Error)
- **Symptom**: BigQuery plugin logs errors about schema mismatch.
- **Cause**: The `agent_events` table was created with `NULLABLE` `content_parts` but updated code sends `REPEATED` (List).
- **Fix**: Drop the table. The plugin will recreate it correctly on next run.

### 3. "Image pull backoff" / "Connection lost"
- **Symptom**: Agent starts but fails immediately when called.
- **Cause**: Hardcoded Docker image (e.g., `mcp/server:latest`) does not exist locally.
- **Fix**: Use env var `os.getenv("SERVICE_MCP_DOCKER_IMAGE")` and set it to your local image name (e.g., `finopti-service-mcp`) in `docker-compose.yml`.

### 4. "Parameter mismatch" (LLM Error)
- **Symptom**: LLM says "I tried to call tool X but it failed" or logic error.
- **Cause**: Python tool wrapper kwargs (`project_id`) dont match MCP server spec (`project`).
- **Fix**: Check MCP server code or logs to verify exact argument names. Map them in `agent.py`.

### 5. "Infinite Retry Loop" / 504 Gateway Timeout
- **Symptom**: Agent reflects and retries endlessly until it times out. Logs show "Unknown tool".
- **Cause**: `agent.py` defines a tool (e.g., `list_log_entries`) that **does not exist** on the MCP server (e.g., it's actually named `query_logs`).
- **Fix**: You must verify the tool names exposed by the MCP server. Use a debug script to send `tools/list` JSON-RPC command to the container to see the source of truth.
