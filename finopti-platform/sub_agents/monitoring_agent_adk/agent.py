"""
Monitoring ADK Agent - Google Cloud Monitoring and Logging Specialist

This agent uses Google ADK to handle GCP monitoring and logging requests.
It uses the `gcloud-mcp` server to access observability tools.
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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
    project_name="finoptiagents-MonitoringAgent",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MonitoringMCPClient:
    """Client for connecting to Monitoring MCP server via Docker Stdio"""
    
    def __init__(self):
        # Use monitoring-mcp image
        self.image = os.getenv('MONITORING_MCP_DOCKER_IMAGE', 'finopti-monitoring-mcp')
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0
    
    async def connect(self):
        cmd = [
            "docker", "run", "-i", "--rm", 
            "-v", self.mount_path,
            self.image
        ]
        
        logging.info(f"Starting Monitoring MCP: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # Increase buffer limit to 10MB to avoid LimitOverrunError on large JSON responses
        if self.process.stdout:
            self.process.stdout._limit = 10 * 1024 * 1024 
        
        await self._handshake()

    async def _handshake(self):
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "monitoring-agent", "version": "1.0"}}
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
        logger.info(f"[DEBUG] Calling Tool: {tool_name} with args: {arguments}")
        await self._send_json(payload)
        while True:
            line = await self.process.stdout.readline()
            if not line: raise RuntimeError("MCP closed")
            msg = json.loads(line)
            if msg.get("id") == self.request_id:
                if "error" in msg: 
                    logger.error(f"[DEBUG] Tool Error: {msg['error']}")
                    return {"error": msg["error"]}
                result = msg.get("result", {})
                logger.info(f"[DEBUG] Tool Result: {str(result)[:200]}...") # Truncate for sanity
                content = result.get("content", [])
                output_text = ""
                for c in content:
                    if c["type"] == "text": output_text += c["text"]
                # Try parsing JSON output if possible
                try: 
                    return json.loads(output_text)
                except:
                    return {"output": output_text}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                # Wait for process to exit, with a short timeout
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    logging.warning("MCP process did not exit gracefully, force killing...")
                    try:
                        self.process.kill()
                        await self.process.wait()
                    except: pass
            except Exception as e:
                logging.warning(f"Error closing MCP process: {e}")

from contextvars import ContextVar
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["MonitoringMCPClient"] = ContextVar("mcp_client", default=None)

# --- CONTEXT ISOLATION & PROGRESS (Rule 1 & 6) ---
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

async def ensure_mcp():
    """Retrieve the client for the CURRENT context."""
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client

# --- Tool Wrappers ---

async def query_logs(project_id: str, filter: str = "", limit: int = 10, minutes_ago: int = 2) -> Dict[str, Any]:
    # HARD CAP: Force max 24 hours (1440m) to allow finding older errors while preventing 30-day queries.
    # Buffer fix (10MB) handles the volume.
    if minutes_ago > 1440:
        logger.warning(f"Capping minutes_ago from {minutes_ago} to 1440 to prevent timeout.")
        minutes_ago = 1440
        
    client = await ensure_mcp()
    # Tool name in MCP is 'query_logs'
    return await client.call_tool("query_logs", {
        "project_id": project_id, 
        "filter": filter, 
        "limit": limit,
        "minutes_ago": minutes_ago
    })

async def list_metrics(project_id: str, filter: str = "") -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_metrics", {"project_id": project_id, "filter": filter})

async def query_time_series(project_id: str, metric_type: str, resource_filter: str = "", minutes_ago: int = 60) -> Dict[str, Any]:
    # HARD CAP: Force max 60 minutes
    if minutes_ago > 60:
         logger.warning(f"Capping minutes_ago from {minutes_ago} to 60.")
         minutes_ago = 60

    client = await ensure_mcp()
    return await client.call_tool("query_time_series", {
        "project_id": project_id, 
        "metric_type": metric_type,
        "resource_filter": resource_filter,
        "minutes_ago": minutes_ago
    })

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
        instruction_str = data.get("instruction", "You are a Monitoring Specialist.")
else:
    instruction_str = "You are a Monitoring Specialist."

# Ensure API Key is in environment for GenAI library
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY


# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

# Add Redis Publisher
try:
    if str(Path(__file__).parent) not in sys.path:
        sys.path.append(str(Path(__file__).parent))
    from redis_common.redis_publisher import RedisEventPublisher
except ImportError:
    try:
        from redis_publisher import RedisEventPublisher
    except ImportError:
        RedisEventPublisher = None
        logging.warning("RedisPublisher not found. Events will not be streamed.")

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
def create_monitoring_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM

    return Agent(
        name=manifest.get("agent_id", "cloud_monitoring_specialist"),
        model=model_to_use,
        description=manifest.get("description", "Monitoring Specialist."),
        instruction=instruction_str,
        tools=[
            query_logs, list_metrics, query_time_series
        ]
    )


# Helper to create app per request
def create_app(model_name: str = None):
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    bq_config = BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true"
    )

    bq_plugin = BigQueryAgentAnalyticsPlugin(
        project_id=config.GCP_PROJECT_ID,
        dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
        table_id=config.BQ_ANALYTICS_TABLE,
        config=bq_config
    )
    
    # Create agent instance
    agent_instance = create_monitoring_agent(model_name)

    return App(
        name="finopti_monitoring_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(),
            bq_plugin
        ]
    )


async def send_message_async(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default") -> str:
    # --- CONTEXT SETTING (Rule 1 & 6) ---
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email or "unknown")

    # Trace attribute setting (Rule 5)
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
        if user_email:
            span.set_attribute("user_id", user_email)

    # Create new client for this request (and this event loop)
    mcp = MonitoringMCPClient()
    token_reset = _mcp_ctx.set(mcp)
    
    # Initialize Redis Publisher once
    publisher = None
    if RedisEventPublisher:
        try:
            publisher = RedisEventPublisher("Monitoring Agent", "Observability Specialist")
            _redis_publisher_ctx.set(publisher)
        except Exception as e:
            logging.error(f"Failed to initialize RedisEventPublisher: {e}")

    try:
        await mcp.connect()
        
        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"

        # Publish "Processing" event via standardized helper
        _report_progress(f"Processing: {prompt[:50]}...", icon="🔍", display_type="toast")
            
        # Define run_once for fallback logic
        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                uid = user_email or "default"
                sid = session_id
                
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_monitoring_agent")
                message = types.Content(parts=[types.Part(text=prompt)])

                async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                    # Stream event via Publisher
                    if publisher:
                        publisher.process_adk_event(event, session_id=sid, user_id=uid)

                    if hasattr(event, 'content') and event.content:
                        for part in event.content.parts:
                            if part.text: response_text += part.text
            return response_text

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="Monitoring Agent"
        )
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id, session_id))

