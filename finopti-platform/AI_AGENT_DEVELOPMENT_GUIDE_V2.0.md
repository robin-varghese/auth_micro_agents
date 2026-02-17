# FinOptiAgents Platform - AI Agent Development Instructions (V2.0)

**Version:** 2.1 (MODULAR + COMPLETE)
**Last Updated:** 2026-Feb-15
**Purpose:** Mandatory guidelines for AI assistants implementing new agents using the Modular Architecture.
**Status:** GOLD STANDARD - Adherence is required for all *new* agent development.

---

## ⚠️ CRITICAL ARCHITECTURE RULES

### Rule 1: Modular File Structure (The 6-File Standard)
**CRITICAL:** Do NOT put all logic in `agent.py`. You MUST use the standard 6-file module structure to separate concerns.
**Requirement:** Every agent must have:
1. `agent.py` (Wiring & App)
2. `mcp_client.py` (Connectivity - Pattern A only)
3. `tools.py` (Capabilities)
4. `instructions.py` (Prompts)
5. `context.py` (State Isolation)
6. `observability.py` (Tracing)

### Rule 2: Use `ContextVar` for State (NO GLOBAL VARIABLES)
**CRITICAL:** Every HTTP request runs in a new `asyncio` event loop. You **cannot** reuse MCP clients or user sessions across requests.
**Requirement:** Use `contextvars.ContextVar` in `context.py` and `mcp_client.py` to isolate state.

### Rule 3: Robust Configuration
**Requirement:** 
1. Use `config.py` for shared constants (LLM models, tables).
2. Use `os.getenv()` for Docker images and secrets.

### Rule 4: Standardized Observability
**CRITICAL:** Every agent must report traces to Arize Phoenix.
**Requirement:** Use the standard `observability.py` boilerplate to register the provider with a consistent project name (`finoptiagents-{AgentName}`).

### Rule 5: Redis Event Bridge for Live Streaming
**CRITICAL:** Agents must never be "silent." All internal thoughts and tools must be published to Redis.
**Requirement:** Use the `_report_progress` helper in `context.py` to stream events standardized as `STATUS_UPDATE`, `TOOL_CALL`, `THOUGHT`, etc.

### Rule 6: Orchestrator Registration (Master Registry)
**CRITICAL:** New agents are not reachable until registered in the Master Registry.
**Requirement:**
1. Create a `manifest.json` in your agent folder defining your `agent_id`, `keywords`, and `capabilities`.
2. Run the registry generator: `python3 tools/generate_master_registry.py`
3. Verify the agent appears in `orchestrator_adk/master_agent_registry.json`.

---

## Standard Module Structure

Every agent MUST follow this directory structure:

```
sub_agents/{agent_name}_adk/
├── agent.py           # Core Logic: Agent + App + Plugins
├── main.py            # Entrypoint: Flask HTTP wrapper
├── mcp_client.py      # Connectivity: Validates & connects to MCP server (Pattern A only)
├── tools.py           # Capability: Python functions wrapping MCP calls or Native logic
├── instructions.py    # Personality: Loads system prompts from instructions.json
├── context.py         # State: ContextVars for session_id, user_email, redis_publisher
├── observability.py   # Tracing: Phoenix/OTel registration boilerplate
├── Dockerfile         # Build: Container definition
└── requirements.txt   # Python dependencies
```

---

## Core Modules Implementation

### 1. `observability.py` (Boilerplate)
*Copy this exactly, changing only the `project_name`.*

```python
import os
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

def setup_observability():
    """Initialize Phoenix tracing and ADK instrumentation."""
    tracer_provider = register(
        project_name="finoptiagents-MyAgent", # <--- CHANGE THIS
        endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
        set_global_tracer_provider=True
    )
    GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
```

### 2. `context.py` (Boilerplate)
*Handles thread-safe state and Redis streaming.*

```python
import os
import sys
import asyncio
import logging
import requests
from contextvars import ContextVar
from typing import Optional
from pathlib import Path

# Add Redis Publisher
try:
    if str(Path(__file__).parent) not in sys.path:
        sys.path.append(str(Path(__file__).parent))
    from redis_common.redis_publisher import RedisEventPublisher
except ImportError:
    # Fallback import logic...
    RedisEventPublisher = None

logger = logging.getLogger(__name__)

_redis_publisher_ctx: ContextVar[Optional["RedisEventPublisher"]] = ContextVar("redis_publisher", default=None)
_session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[Optional[str]] = ContextVar("user_email", default=None)

async def _report_progress(message: str, event_type: str = "INFO", icon: str = "🤖"):
    """Helper to send progress to Orchestrator AND Redis"""
    # Redis Publishing
    publisher = _redis_publisher_ctx.get()
    session_id = _session_id_ctx.get()
    
    if publisher and session_id:
        try:
             # Map internal event types
             msg_type_map = {
                 "INFO": "STATUS_UPDATE", "TOOL_CALL": "TOOL_CALL", "OBSERVATION": "OBSERVATION", 
                 "ERROR": "ERROR", "THOUGHT": "THOUGHT"
             }
             mapped_type = msg_type_map.get(event_type, "STATUS_UPDATE")
             
             user_id = _user_email_ctx.get() or "unknown_agent"
             
             publisher.publish_event(
                 session_id=session_id, user_id=user_id, trace_id="unknown",
                 msg_type=mapped_type, message=message,
                 display_type="markdown" if mapped_type == "THOUGHT" else "console_log",
                 icon=icon
             )
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")
```

### 3. `instructions.py`
*Separates prompt text from logic.*

```python
import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "manifest.json"
INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.json"

def load_instructions():
    if INSTRUCTIONS_PATH.exists():
        with open(INSTRUCTIONS_PATH, "r") as f:
            data = json.load(f)
            return data.get("instruction", "You represent the agent.")
    return "You represent the agent."

AGENT_INSTRUCTIONS = load_instructions()
AGENT_NAME = "my_specialist"
```

---

## Agent Patterns

### Pattern A: MCP Wrapper (Standard)
*Used when wrapping an external MCP server (Docker).*

**File: `mcp_client.py`**
- Uses `mcp` library (python setup) or `asyncio.subprocess` to launch/connect to the MCP container.
- Manages `ClientSession` lifecycle.
- Uses `ContextVar` to ensure one client per request.

**File: `tools.py`**
- Defines async python functions.
- Calls `await ensure_mcp()` to get the client.
- Invokes `client.call_tool()`.

### Pattern B: Native Tool
*Used when the tool is just a Python library (e.g., Google Search, Code Execution).*

**File: `mcp_client.py`**
- **NOT REQUIRED.**

**File: `tools.py`**
- Directly imports the Native SDK or ADK tool.
- Wraps it in a simple async function if needed.

---

## The `agent.py` Pattern (Composition)

The `agent.py` file should now be **minimal**, purely wiring the modules together.

```python
import os
import sys
import asyncio
import logging
from pathlib import Path
from contextvars import ContextVar

# Imports
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

# Module Imports
from observability import setup_observability
from context import (
    _redis_publisher_ctx, 
    _session_id_ctx, 
    _user_email_ctx, 
    _report_progress,
    RedisEventPublisher
)
from instructions import AGENT_INSTRUCTIONS, AGENT_NAME
from tools import my_tool_function
# Pattern A only:
from mcp_client import MyMCPClient, _mcp_ctx

# 1. Setup Observability
setup_observability()

# 2. Define Agent
def create_my_agent(model_name=None):
    return Agent(
        name=AGENT_NAME,
        model=model_name or "gemini-2.0-flash",
        instruction=AGENT_INSTRUCTIONS,
        tools=[my_tool_function]
    )

# 3. Define App
def create_app(model_name=None):
    return App(
        name="my_app",
        root_agent=create_my_agent(model_name),
        plugins=[]
    )

# 4. Request Handler
async def send_message_async(prompt: str, user_email: str = None, session_id: str = "default"):
    # Context Propagation
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email)
    
    # Initialize Client (Pattern A) - ContextVar SET
    mcp = MyMCPClient()
    token = _mcp_ctx.set(mcp)
    
    try:
        await mcp.connect()
        await _report_progress("Starting...", icon="🚀")
        
        # Run ADK
        # ... standard InMemoryRunner loop ...
        
    finally:
        await mcp.close()
        _mcp_ctx.reset(token) # ContextVar RESET

def send_message(prompt, user_email=None, session_id="default"):
    return asyncio.run(send_message_async(prompt, user_email, None, session_id))
```

---

## Required Features Implementation

### 1. `main.py` (Flask Entrypoint)
*Must handle request routing and context extraction.*

```python
import os
import logging
from flask import Flask, request, jsonify
import asyncio
from agent import process_request # or send_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/execute', methods=['POST']) # Or /chat
def execute():
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"error": "Prompt is required"}), 400

    prompt = data['prompt']
    session_id = data.get('session_id')
    user_email = data.get('user_email')
    
    try:
        result = asyncio.run(process_request(prompt, session_id=session_id, user_email=user_email))
        return jsonify({"response": result})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

### 2. `Dockerfile` (Containerization)
*Standard ADK container pattern.*

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y docker.io procps curl && \
    rm -rf /var/lib/apt/lists/*

# Install python deps
COPY sub_agents/my_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy config and common libs
COPY config/ config/
COPY mats-agents/common/ common/
COPY sub_agents/my_agent_adk/ .

# Env vars
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "600", "main:app"]
```

### 3. `verify_agent.py` (Verification)
*Script to test the agent locally.*

```python
import requests
import os

URL = os.getenv("AGENT_URL", "http://localhost:8080/execute")

def verify():
    print(f"Testing {URL}...")
    try:
        resp = requests.post(URL, json={
            "prompt": "Test prompt",
            "session_id": "test-session",
            "user_email": "test@example.com"
        }, timeout=60)
        resp.raise_for_status()
        print(f"Success: {resp.json()}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    verify()
```

---

## Observability Implementation (Phoenix Session Tracking)

### Session Flow
```
User Request (session_id: abc-123)
  ↓
Orchestrator (sets session.id on span)
  ↓
Delegation (passes session_id in payload)
  ↓
Sub-Agent (extracts session_id, sets on span)
  ↓
Phoenix UI (groups all traces by session.id)
```

### Verification Checklist
- [ ] Registered in `orchestrator_adk/master_agent_registry.json`
- [ ] Phoenix registration uses correct project name (matches system)
- [ ] `session_id` is extracted from payload (if delegated agent)
- [ ] `session.id` attribute is set on main span
- [ ] Trace context is extracted from headers (for parent-child linking)
- [ ] Trace context is propagated when delegating (if orchestrator)

---

## Troubleshooting & Common Pitfalls

### 1. "Event Loop Mismatch" / "Event loop is closed"
- **Symptom**: `RuntimeError: active loop mismatch`.
- **Cause**: Reusing a global MCP client across requests or instantiating `App` globally.
- **Fix**: Use `ContextVar` for MCP Client (Rule 2) and `create_app()` inside request handler.

### 2. "Image pull backoff"
- **Symptom**: Agent starts but fails when called.
- **Cause**: Hardcoded Docker image.
- **Fix**: Use env var `os.getenv("SERVICE_MCP_DOCKER_IMAGE")`.

### 3. "Phoenix not showing traces"
- **Symptom**: Agent works but no traces appear.
- **Fix**: Verify `PHOENIX_COLLECTOR_ENDPOINT` is correct and Phoenix container is running.

---
**End of V2.1 Guide**
