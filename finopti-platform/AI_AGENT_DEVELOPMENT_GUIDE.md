# FinOptiAgents Platform - AI Agent Development Instructions

**Version:** 4.0 (STABLE)
**Last Updated:** 2026-Feb-07
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

### Rule 5: ALL Traces MUST Go to Arize Phoenix with Session Tracking
**CRITICAL:** Every agent must report execution traces to Phoenix for debugging AND implement session tracking for trace grouping.

**Requirements:**
1. Use `phoenix.otel.register` and `GoogleADKInstrumentor` in `agent.py`
2. **NEVER HARDCODE** the endpoint. Use `os.getenv("PHOENIX_COLLECTOR_ENDPOINT")`
3. **ALWAYS use the SAME project name** across related agents (e.g., "finoptiagents-MATS" for all MATS agents)
4. **ALWAYS set `session.id` attribute** on spans for session grouping in Phoenix
5. **ALWAYS extract and propagate `session_id`** from payloads or headers
6. Ensure `arize-phoenix`, `openinference-instrumentation-google-adk`, and `openinference-semconv` are in `requirements.txt`

**Session Tracking Benefits:**
- Groups multiple traces under one logical user session
- Enables end-to-end debugging across agent boundaries
- Provides complete visibility of multi-agent workflows
- Allows session-level performance analysis

See [Section 7: Observability Implementation](#7-observability-implementation-phoenix-session-tracking) for complete implementation guide.

### Rule 6: Asyncio Event Loop Safety (NO GLOBAL APP)
**CRITICAL:** The `App` and its `Plugins` (especially `BigQueryAgentAnalyticsPlugin`) create async primitives (locks, queues) bound to the event loop active at instantiation.
**Requirement:**
1. **NEVER** instantiate `App` or `Plugins` globally.
2. Define a `create_app()` function that builds them.
3. Call `create_app()` **inside** your request handler (`send_message_async`).
4. Use `asyncio.run()` for the entry point to ensure graceful loop cleanup.

---

## Mandatory File Structure for New Agents

```
sub_agents/{agent_name}_adk/
├── agent.py           # Core Logic: Agent + App + Plugins + Auth + CONTEXT ISOLATION + OBSERVABILITY
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

# Observability Imports
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry import trace, propagate
from openinference.semconv.trace import SpanAttributes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 0. OBSERVABILITY SETUP ---
# Initialize tracing using ADK instrumentation
# CRITICAL: Use CONSISTENT project name across related agents!
tracer_provider = register(
    project_name="finoptiagents-YourSystem",  # e.g., "finoptiagents-MATS" for all MATS agents
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

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

# --- 4. EXECUTION LOGIC (Lifecycle Management + Session Tracking) ---
async def process_request_async(
    prompt_or_payload: Any,
    user_email: str = None
) -> str:
    """
    Process request with session tracking support.
    
    Args:
        prompt_or_payload: Can be string (simple) or dict (with session_id + headers)
        user_email: User email for logging
    """
    # A. Extract session_id from payload for Phoenix session grouping
    session_id = None
    trace_context = {}
    
    if isinstance(prompt_or_payload, dict):
        session_id = prompt_or_payload.get("session_id")
        trace_context = prompt_or_payload.get("headers", {})
        prompt = prompt_or_payload.get("message") or prompt_or_payload.get("prompt")
    else:
        prompt = prompt_or_payload
    
    # B. Extract parent trace context for span linking
    parent_ctx = propagate.extract(trace_context) if trace_context else None
    tracer = trace.get_tracer(__name__)
    
    # C. Create span with session.id attribute
    with tracer.start_as_current_span(
        "my_agent_operation",
        context=parent_ctx,
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: "CHAIN",
            "agent.name": "my-agent",
            "agent.type": "specialist"
        }
    ) as span:
        # D. Set session.id for Phoenix session grouping
        if session_id and span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            logger.info(f"[{session_id}] MyAgent: Set session.id on span")
        
        # E. Initialize MCP Client for THIS Scope
        mcp = MyMCPClient()
        token_reset = _mcp_ctx.set(mcp)  # Bind to ContextVar
        
        try:
            # F. Connect
            await mcp.connect()
            
            # G. Run Agent
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
                            if part.text: 
                                response_text += part.text
                return response_text
        finally:
            # H. Cleanup
            await mcp.close()
            _mcp_ctx.reset(token_reset)  # Unbind to prevent leaks

def process_request(prompt_or_payload: Any, user_email: str = None) -> str:
    return asyncio.run(process_request_async(prompt_or_payload, user_email))
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

## 7. Observability Implementation (Phoenix Session Tracking)

### 7.1 Overview

Phoenix session tracking enables grouping of multiple distributed traces under a single logical user session. This is critical for:
- Debugging multi-agent workflows
- Understanding end-to-end request flow
- Performance analysis across agent boundaries
- User behavior tracking

### 7.2 Core Concepts

**Session vs Trace:**
- **Session**: Logical grouping of related traces, persistent across multiple requests
- **Trace**: Single distributed transaction, one per agent invocation

**Session Flow:**
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

### 7.3 Implementation Patterns

#### Pattern A: Agent Receiving Delegated Work

For agents called by orchestrator or other agents:

```python
async def process_request(prompt_or_payload: Any) -> Dict[str, Any]:
    # 1. Extract session_id from payload
    session_id = None
    trace_context = {}
    
    if isinstance(prompt_or_payload, dict):
        session_id = prompt_or_payload.get("session_id")
        trace_context = prompt_or_payload.get("headers", {})
    
    # 2. Extract parent trace context
    from opentelemetry import propagate, trace
    from openinference.semconv.trace import SpanAttributes
    
    parent_ctx = propagate.extract(trace_context) if trace_context else None
    tracer = trace.get_tracer(__name__)
    
    # 3. Create span with parent context
    with tracer.start_as_current_span(
        "agent_operation",
        context=parent_ctx,  # Links to parent span
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: "CHAIN",
            "agent.name": "my-agent"
        }
    ) as span:
        # 4. Set session.id attribute (CRITICAL for grouping)
        if session_id and span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            logger.info(f"[{session_id}] MyAgent: Set session.id on span")
        
        # 5. Agent logic here
        result = await do_work()
        return result
```

#### Pattern B: Agent Delegating to Other Agents

For agents that call other agents (orchestrators):

```python
async def delegate_to_sub_agent(
    prompt: str,
    session_id: str,
    **kwargs
) -> Dict[str, Any]:
    # 1. Inject trace context for propagation
    from opentelemetry import propagate
    
    trace_headers = {}
    propagate.inject(trace_headers)
    
    # 2. Build payload with session_id and headers
    payload = {
        "message": prompt,
        "session_id": session_id,  # ← CRITICAL: Pass session_id explicitly
        "headers": trace_headers    # ← CRITICAL: Pass trace context
    }
    
    # 3. Call sub-agent
    response = await http_post(sub_agent_url, payload)
    return response
```

#### Pattern C: Top-Level Entry Point (UI/API)

For entry points receiving requests from UI or external APIs:

```python
async def handle_request(
    user_request: str,
    provided_session_id: str = None
) -> Dict[str, Any]:
    # 1. Use provided session_id or generate new one
    session_id = provided_session_id or str(uuid.uuid4())
    
    # 2. Set session.id on current span
    from opentelemetry import trace
    from openinference.semconv.trace import SpanAttributes
    
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute(SpanAttributes.SESSION_ID, session_id)
        logger.info(f"Set session.id={session_id} on current span")
    
    # 3. Process request and delegate with session_id
    result = await process_with_delegation(user_request, session_id)
    return result
```

### 7.4 Project Name Consistency

**CRITICAL:** All agents in the same system MUST use the same Phoenix project name.

```python
# ❌ WRONG - Different project names
# Agent 1:
register(project_name="my-orchestrator")

# Agent 2:
register(project_name="my-sub-agent")

# ✅ CORRECT - Same project name
# All agents:
register(project_name="finoptiagents-MySystem")
```

**Naming Convention:**
- Main platform agents: `"finoptiagents-MATS"` (for MATS system)
- Sub-agents: Same as their parent system
- Test agents: `"{project_id}-test-agent"`

### 7.5 Required Dependencies

Add to `requirements.txt`:

```
arize-phoenix>=4.0.0
openinference-instrumentation-google-adk>=0. 1.0
openinference-semconv>=0.1.0
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
```

### 7.6 Verification Checklist

When implementing a new agent, verify:

- [ ] Phoenix registration uses correct project name (matches system)
- [ ] `session_id` is extracted from payload (if delegated agent)
- [ ] `session.id` attribute is set on main span
- [ ] Trace context is extracted from headers (for parent-child linking)
- [ ] Trace context is propagated when delegating (if orchestrator)
- [ ] `session_id` is passed in payload when delegating (if orchestrator)
- [ ] All spans show in Phoenix under correct project
- [ ] Sessions tab shows grouped traces
- [ ] Span hierarchy shows parent-child relationships

### 7.7 Testing Session Tracking

**Manual Test:**
1. Make request through UI
2. Note session_id from UI
3. Check agent logs: `docker-compose logs my-agent | grep "session.id"`
4. Expected: `[{session_id}] MyAgent: Set session.id on span`
5. Check Phoenix: http://localhost:6006 → Sessions tab
6. Expected: See session with matching ID containing agent's traces

**Debug Logging:**
```bash
# View Phoenix traces
docker-compose logs phoenix | grep "session"

# View agent session tracking
docker-compose logs my-agent | grep -i session
```

### 7.8 Common Issues

**Issue: Sessions tab empty in Phoenix**
- **Cause**: `session.id` attribute not set on spans
- **Fix**: Ensure `span.set_attribute(SpanAttributes.SESSION_ID, session_id)` is called

**Issue: Traces not grouped**
- **Cause**: Different project names across agents
- **Fix**: Use same `project_name` in all `register()` calls

**Issue: No parent-child relationships**
- **Cause**: Trace context not propagated
- **Fix**: Inject headers with `propagate.inject()` and extract with `propagate.extract()`

### 7.9 Reference Implementation

For complete examples, see:
- **Detailed Guide**: [docs/PHOENIX_SESSION_TRACKING.md](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/docs/PHOENIX_SESSION_TRACKING.md)
- **MATS Orchestrator**: `mats-agents/mats-orchestrator/agent.py`
- **MATS Sub-Agents**: `mats-agents/mats-sre-agent/agent.py`

---

## Troubleshooting & Common Pitfalls

### 1. "Event Loop Mismatch" / "Event loop is closed"
- **Symptom**: `RuntimeError: active loop mismatch`, `RuntimeError: bound to a different event loop`, or `Event loop is closed`.
- **Cause**: 
    1. Reusing a global MCP client across requests.
    2. Instantiating `App` or `Plugins` globally (binding them to the import-time loop).
    3. Using manual `loop.close()` prematurely.
- **Fix**: 
    1. **Use `ContextVar`** for MCP Clients (Rule 1).
    2. **Use `create_app()`** inside the request handler (Rule 6).
    3. Use `asyncio.run()` for lifecycle management.

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
- **Cause**: Python tool wrapper kwargs (`project_id`) don't match MCP server spec (`project`).
- **Fix**: Check MCP server code or logs to verify exact argument names. Map them in `agent.py`.

### 5. "Infinite Retry Loop" / 504 Gateway Timeout
- **Symptom**: Agent reflects and retries endlessly until it times out. Logs show "Unknown tool".
- **Cause**: `agent.py` defines a tool (e.g., `list_log_entries`) that **does not exist** on the MCP server (e.g., it's actually named `query_logs`).
- **Fix**: You must verify the tool names exposed by the MCP server. Use a debug script to send `tools/list` JSON-RPC command to the container to see the source of truth.

### 6. "Phoenix not showing traces"
- **Symptom**: Agent works but no traces appear in Phoenix.
- **Cause**: 
    1. Phoenix endpoint incorrect or not accessible
    2. Phoenix not running
    3. Network issues between agent and Phoenix
- **Fix**:
    1. Verify `PHOENIX_COLLECTOR_ENDPOINT` is set correctly
    2. Check Phoenix is running: `docker-compose ps phoenix`
    3. Test connectivity: `curl http://phoenix:6006/healthz` from agent container

### 7. "Session tracking not working"
- **Symptom**: Traces appear but not grouped by session.
- **Cause**: 
    1. `session.id` attribute not set
    2. Different project names used
    3. Session extractor plugin not loaded
- **Fix**:
    1. Verify `span.set_attribute(SpanAttributes.SESSION_ID, session_id)` is called
    2. Ensure all agents use same project name
    3. Check Phoenix session extractor is configured

---

## Version History

- **v4.0 (2026-02-07)**: Added comprehensive observability implementation section (#7) with Phoenix session tracking patterns, examples, and troubleshooting
- **v3.0 (2026-01-21)**: Added context isolation rules and asyncio safety requirements
- **v2.0 (2026-01-15)**: Initial standardization of agent patterns
- **v1.0 (2026-01-10)**: Initial draft
