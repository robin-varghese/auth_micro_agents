"""
Analytics ADK Agent
"""

import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any, List
from pathlib import Path
from contextvars import ContextVar

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Add Redis Publisher
try:
    if str(Path(__file__).parent) not in sys.path:
        sys.path.append(str(Path(__file__).parent))

    from redis_common.redis_publisher import RedisEventPublisher
except ImportError as e:
    sys.path.append(str(Path(__file__).parent.parent.parent / "redis-sessions" / "common"))
    try:
        from redis_publisher import RedisEventPublisher
    except ImportError:
        RedisEventPublisher = None

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

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name="finoptiagents-AnalyticsAgent",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

class AnalyticsMCPClient:
    def __init__(self):
        self.image = "finopti-analytics-mcp"
        self.process = None
        self.request_id = 0
        
    async def connect(self, token: str):
        cmd = [
            "docker", "run", "-i", "--rm",
            "-e", f"GOOGLE_ACCESS_TOKEN={token}",
            self.image
        ]
        
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await self._handshake()

    async def _handshake(self):
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ga-agent", "version": "1.0"}}
        })
        while True:
            line = await self.process.stdout.readline()
            if not line: break
            msg = json.loads(line)
            if msg.get("id") == 0: break
        await self._send_json({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _send_json(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self.request_id
        }
        await self._send_json(payload)
        while True:
            line = await self.process.stdout.readline()
            if not line: raise RuntimeError("MCP closed")
            msg = json.loads(line)
            if msg.get("id") == self.request_id:
                if "error" in msg: return {"error": msg["error"]}
                result = msg.get("result", {})
                content = result.get("content", [])
                text = "".join([c["text"] for c in content if c["type"] == "text"])
                return {"result": text}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except: pass

# ContextVar for isolation
_mcp_ctx: ContextVar["AnalyticsMCPClient"] = ContextVar("mcp_client", default=None)

# --- CONTEXT ISOLATION & PROGRESS (Rule 1 & 6) ---
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

_session_id_ctx: ContextVar[str] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[str] = ContextVar("user_email", default=None)
_redis_publisher_ctx: ContextVar = ContextVar("redis_publisher", default=None)

def _report_progress(message, event_type="STATUS_UPDATE", icon="🤖", display_type="markdown", metadata=None):
    """Standardized progress reporting using context-bound session/user."""
    pub = _redis_publisher_ctx.get()
    sid = _session_id_ctx.get()
    uid = _user_email_ctx.get() or "unknown"
    if pub and sid:
        try:
            span_ctx = trace.get_current_span().get_span_context()
            trace_id_hex = format(span_ctx.trace_id, '032x') if span_ctx.trace_id else "unknown"
        except Exception:
            trace_id_hex = "unknown"
        pub.publish_event(
            session_id=sid, user_id=uid, trace_id=trace_id_hex,
            msg_type=event_type, message=message, display_type=display_type,
            icon=icon, metadata=metadata
        )

async def ensure_mcp(token: str = None):
    client = _mcp_ctx.get()
    if not client:
        client = AnalyticsMCPClient()
        _mcp_ctx.set(client)
    
    if not client.process and token:
        await client.connect(token)
    return client

# Wrapper to use context instead of global
async def run_report(property_id: str, dimensions: List[str] = [], metrics: List[str] = []) -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("run_report", {
        "property_id": property_id,
        "dimensions": dimensions,
        "metrics": metrics
    })

async def run_realtime_report(property_id: str, dimensions: List[str] = [], metrics: List[str] = []) -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("run_realtime_report", {
        "property_id": property_id,
        "dimensions": dimensions,
        "metrics": metrics
    })

async def get_account_summaries() -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("get_account_summaries", {})

async def get_property_details(property_id: str) -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("get_property_details", {"property_id": property_id})

async def get_custom_dimensions_and_metrics(property_id: str) -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("get_custom_dimensions_and_metrics", {"property_id": property_id})

# Load Manifest
manifest_path = Path(__file__).parent / "manifest.json"
manifest = {}
if manifest_path.exists():
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

# Load Instructions
instructions_path = Path(__file__).parent / "instructions.json"
if instructions_path.exists():
    with open(instructions_path, "r") as f:
        data = json.load(f)
        instruction_str = data.get("instruction", "Analyze web traffic using available tools.")
else:
    instruction_str = "Analyze web traffic using available tools."


# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
def create_analytics_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=manifest.get("agent_id", "analytics_specialist"),
        model=model_to_use,
        description=manifest.get("description", "Google Analytics 4 Specialist."),
        instruction=instruction_str,
        tools=[
            run_report, 
            run_realtime_report, 
            get_account_summaries, 
            get_property_details, 
            get_custom_dimensions_and_metrics
        ]
    )



def create_app(model_name: str = None):
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    
    # Create agent instance
    agent_instance = create_analytics_agent(model_name)

    return App(
        name="finopti_analytics_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3),
            BigQueryAgentAnalyticsPlugin(
                project_id=config.GCP_PROJECT_ID,
                dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
                table_id=config.BQ_ANALYTICS_TABLE,
                config=BigQueryLoggerConfig(enabled=True)
            )
        ]
    )

async def send_message_async(prompt: str, user_email: str = None, token: str = None, session_id: str = "default") -> str:
    # --- CONTEXT SETTING (Rule 1 & 6) ---
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email or "unknown")

    # Trace attribute setting (Rule 5)
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
        if user_email:
            span.set_attribute("user_id", user_email)

    # Initialize client locally for this request
    mcp = AnalyticsMCPClient()
    token_reset = _mcp_ctx.set(mcp)

    # Initialize Redis Publisher once
    publisher = None
    if RedisEventPublisher:
         try:
             publisher = RedisEventPublisher(
                 agent_name="Analytics Agent",
                 agent_role="Data Specialist"
             )
             _redis_publisher_ctx.set(publisher)
         except: pass
    
    try:
        if token:
            await mcp.connect(token)
        else:
            return "Error: No OAuth Token provided."

        # Publish "Processing" event via standardized helper
        _report_progress(f"Analyzing data...", icon="📈", display_type="toast")

        # Define run_once for fallback logic
        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id
                uid = user_email or "default"
                
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_analytics_agent")
                message = types.Content(parts=[types.Part(text=prompt)])

                async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                    # Stream Events
                    if publisher:
                        publisher.process_adk_event(event, session_id=sid, user_id=uid)
                    
                    if hasattr(event, 'content') and event.content:
                        for part in event.content.parts:
                            if part.text: response_text += part.text
            return response_text

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="Analytics Agent"
        )
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, token: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, token, session_id))
