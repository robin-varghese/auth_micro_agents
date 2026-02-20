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

### Rule 6: Orchestrator Registration & Master Registry
**CRITICAL:** New agents are not reachable until registered in the Master Registry. The registry relies on consistent naming to avoid `KeyError` crashes in the Orchestrator.
**Requirement:**
1. Create a `manifest.json` in your agent folder defining your `agent_id`, `name`, `display_name`, `keywords`, and `capabilities`.
2. **Naming Standard**: You MUST include both `name` and `display_name`. They should be identical for consistency.
3. Run the registry generator: `python3 tools/generate_master_registry.py` (which normalizes and aggregates these).
4. Verify the agent appears in `mats-agents/mats-orchestrator/agent_registry.json`.

### Rule 7: Authentication & Authorization (AuthN/AuthZ)
**CRITICAL:** All agents are protected by APISix and OPA. Credentials MUST be propagated end-to-end to enable tool execution (e.g., GCloud calls).
**Requirement:**
1. Agents must extract `user_email`, `session_id`, and the `Authorization` (Bearer) token from incoming requests.
2. The `Authorization` header contains the user's active OIDC/OAuth token.
3. **Environment Fallback (CRITICAL)**: Because `ContextVar` can be lost in complex async tool chains or sub-processes, you MUST also sync the credentials to the process environment:
   - `os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = auth_token`
   - `os.environ["CLOUDSDK_CORE_ACCOUNT"] = user_email`
4. This token MUST be propagated to internal tools and MCP clients (Pattern A) to authenticate against GCP.
5. Access is controlled via `opa_policy/authz.rego`. Ensure your `agent_id` is mapped to the correct roles in OPA.

### Rule 12: Single-Chain Context Inheritance (Inheritance Rule)
**CRITICAL:** Agents must never lose the "Trace Thread." When an agent calls another service or tool, it must pass the current context.
**Requirement:**
1. **Pass the Session ID**: Every internal `requests.post` or tool-to-tool call MUST include the `session_id`.
2. **Pass the Auth Token**: Never assume the downstream agent has its own credentials. Always pass the Bearer token in the `Authorization` header.
3. **Investigation State**: If an agent updates a shared state (e.g., Redis), it must use the inherited `session_id` to ensure observability.

### Rule 8: Model Fallback & Resilience
**CRITICAL:** Production agents must handle LLM quota exhaustion (429) gracefully.
**Requirement:**
1. Do NOT hardcode LLM models in `agent.py`. Use `config.FINOPTIAGENTS_LLM`.
2. Wrap the `InMemoryRunner` logic in `run_with_model_fallback` from `common.model_resilience`.
3. The fallback list is centrally managed in `config.FINOPTIAGENTS_MODEL_LIST`.

### Rule 9: Secret Manager First
**CRITICAL:** No secrets (API keys, tokens) in environment variables or code.
**Requirement:**
1. Add new secrets to Google Secret Manager in the `vector-search-poc` project.
2. Use lowercase with hyphens (e.g., `google-api-key`).
3. Fetch them in `config/__init__.py` using the `_fetch_config` helper.

### Rule 10: Vertex AI as LLM Standard
**CRITICAL:** All agents MUST use Vertex AI for LLM interactions. The Google AI (Gemini) API key is NOT supported in production.
**Requirement:**
1. Set `GOOGLE_GENAI_USE_VERTEXAI = "TRUE"` in `config/__init__.py` or via environment variable.
2. In `agent.py`, ensure these variables are exported BEFORE initializing any ADK components:
   ```python
   if hasattr(config, "GOOGLE_GENAI_USE_VERTEXAI"):
       os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = str(config.GOOGLE_GENAI_USE_VERTEXAI)
   if hasattr(config, "GCP_PROJECT_ID"):
       os.environ["GOOGLE_CLOUD_PROJECT"] = config.GCP_PROJECT_ID
   ```
   ```
3. Local verification (`verify_agent_internal.py`) MUST also force Vertex AI.

### Rule 11: Manifest Schema Consistency
**Requirement:** Every `manifest.json` must follow this schema:
```json
{
    "agent_id": "unique_lowercase_id",
    "name": "Human Readable Name",
    "display_name": "Human Readable Name",
    "description": "Short summary of agent purpose",
    "capabilities": ["Capability 1", "Capability 2"],
    "keywords": ["keyword1", "keyword2"]
}
```
**Critical:** `name` and `display_name` are both REQUIRED to support different legacy and modern orchestrator components.

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

### 1. `observability.py` (Resilient Boilerplate)
*Ensures the agent boots even if Phoenix or OTel is unavailable.*

```python
import os
import logging

try:
    from phoenix.otel import register
except (ImportError, SyntaxError):
    register = None

try:
    from openinference.instrumentation.google_adk import GoogleADKInstrumentor
except ImportError:
    GoogleADKInstrumentor = None

logger = logging.getLogger(__name__)

def setup_observability():
    """Initialize Phoenix tracing and ADK instrumentation safely."""
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    tracer_provider = None
    
    if endpoint and register:
        try:
            tracer_provider = register(
                project_name=f"finoptiagents-{os.getenv('AGENT_ID', 'GenericAgent')}",
                endpoint=endpoint,
                set_global_tracer_provider=True
            )
        except Exception as e:
            logger.warning(f"Failed to register Phoenix: {e}")

    if GoogleADKInstrumentor:
        try:
            GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
        except Exception as e:
            logger.warning(f"Failed to instrument ADK: {e}")
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
_auth_token_ctx: ContextVar[Optional[str]] = ContextVar("auth_token", default=None)

async def _report_progress(message: str, event_type: str = "INFO", icon: str = "🤖"):
    """Helper to send progress to Orchestrator AND Redis for UI Sync"""
    # Redis Publishing (channel:user_{user_id}:session_{session_id})
    publisher = _redis_publisher_ctx.get()
    session_id = _session_id_ctx.get()
    user_id = _user_email_ctx.get() or "anonymous"
    
    if publisher and session_id:
        try:
             # MAPPED_TYPES: STATUS_UPDATE, TOOL_CALL, OBSERVATION, ERROR, THOUGHT, ACTION
             msg_type_map = {
                 "INFO": "STATUS_UPDATE", "TOOL_CALL": "ACTION", "OBSERVATION": "OBSERVATION", 
                 "ERROR": "ERROR", "THOUGHT": "THOUGHT"
             }
             mapped_type = msg_type_map.get(event_type, "STATUS_UPDATE")
             
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

def load_manifest():
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    return {}

AGENT_INSTRUCTIONS = load_instructions()
MANIFEST = load_manifest()
# Standard: Use display_name for the internal agent variable, fallback to agent_id
AGENT_NAME = MANIFEST.get("display_name", MANIFEST.get("agent_id", "my_specialist"))
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
# 1. Load Config FIRST (Critical for environment overrides)
from config import config

# 2. Set Vertex AI preference BEFORE other imports use LLM libs
if hasattr(config, "GOOGLE_GENAI_USE_VERTEXAI"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = str(config.GOOGLE_GENAI_USE_VERTEXAI)
if hasattr(config, "GCP_PROJECT_ID"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = config.GCP_PROJECT_ID

# 3. Rest of the imports
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types
from opentelemetry import trace

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

# 4. Setup Observability
setup_observability()

# 5. Define Agent
def create_my_agent(model_name=None):
    return Agent(
        name=AGENT_NAME,
        model=model_name or config.FINOPTIAGENTS_LLM,
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
async def send_message_async(prompt: str, user_email: str = None, session_id: str = "default", auth_token: str = None):
    try:
        # --- CONTEXT PROPAGATION (Rule 12) ---
        _session_id_ctx.set(session_id)
        _user_email_ctx.set(user_email or "unknown")
        if auth_token:
            _auth_token_ctx.set(auth_token)
            # SYNC TO ENVIRONMENT (Rule 7 Fallback)
            os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = auth_token
            os.environ["CLOUDSDK_CORE_ACCOUNT"] = user_email or "unknown"
            logger.info(f"Synced OAuth token and account ({user_email}) to process environment")

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
    
    # Extract Auth Token from Authorization Header
    auth_header = request.headers.get('Authorization')
    auth_token = None
    if auth_header and auth_header.startswith("Bearer "):
        auth_token = auth_header.split(" ")[1]

    try:
        result = asyncio.run(process_request(prompt, session_id=session_id, user_email=user_email, auth_token=auth_token))
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

### 3. `requirements.txt` (Standard Dependencies)
*Ensure version compatibility to avoid import/syntax errors.*

```text
google-adk>=0.1.0
google-genai>=0.1.0
Flask>=3.0.0
gunicorn>=21.0.0
requests>=2.31.0
arize-phoenix>=4.0.0      # Critical for Python 3.11 compatibility
opentelemetry-sdk>=1.20.0
openinference-instrumentation-google-adk>=0.1.0
```

### 4. `verify_agent_internal.py` (Verification)
*Script to test the agent logic locally without infrastructure.*

```python
import os
import asyncio
from agent import process_request

async def verify():
    # Force Vertex AI for local test
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
    os.environ["USE_SECRET_MANAGER"] = "FALSE"
    
    print("Testing Agent Logic...")
    result = await process_request(
        prompt="Hello",
        session_id="test-session",
        user_email="test@example.com"
    )
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(verify())
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
4.  Sub-Agent Standard Span Attributes:
    - `session.id`: Captured from `_session_id_ctx`.
    - `user.email`: Captured from `_user_email_ctx`.
    - `enduser.id`: For audit trails.

5.  Phoenix UI (groups all traces by session.id)
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
### 4. "Permission Denied" / "No credentialed accounts" in MCP
- **Symptom**: `gcloud` commands fail inside the spawned container, or logs say "No credentialed accounts".
- **Cause**: The active OAuth token is not passed to the container, or the `ContextVar` was lost during an async yield.
- **Fix**: 
  1. Ensure `agent.py` syncs to the environment (Rule 7).
  2. In your tool execution or `mcp_client.py`, check BOTH context and environment:
  ```python
  auth_token = _auth_token_ctx.get() or os.environ.get("CLOUDSDK_AUTH_ACCESS_TOKEN")
  user_email = _user_email_ctx.get() or os.environ.get("CLOUDSDK_CORE_ACCOUNT")
  
  cmd = [
      "docker", "run", "-i", "--rm",
      "-e", f"CLOUDSDK_AUTH_ACCESS_TOKEN={auth_token}",
      "-e", f"CLOUDSDK_CORE_ACCOUNT={user_email}",
      "finopti-gcloud-mcp"
  ]
  ```

---
**End of V2.1 Guide**
