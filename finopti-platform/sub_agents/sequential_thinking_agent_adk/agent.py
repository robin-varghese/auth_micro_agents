"""
Sequential Thinking ADK Agent

This agent uses Google ADK to facilitate structured sequential thinking.
It integrates with the Sequential Thinking MCP server.
"""

import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from contextlib import AsyncExitStack

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

# Try importing mcp library
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    logging.error("mcp library not found. Please install it.")
    os.system("pip install mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

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
    project_name="finoptiagents-SequentialAgent",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SequentialMCPClient:
    """Client for connecting to Sequential Thinking MCP server via Docker Stdio using mcp library"""
    
    def __init__(self):
        # Use simple image name if pure MCP server, or passed env
        self.image = os.getenv('SEQUENTIAL_THINKING_MCP_DOCKER_IMAGE', 'sequentialthinking')
        self.session: Optional[ClientSession] = None
        self.exit_stack: Optional[AsyncExitStack] = None
        
    async def connect(self):
        if self.session:
            return

        # Docker run command
        # Note: finopti-sequential-thinking might be the ADK agent, 
        # actual MCP server is usually separate. Assuming 'sequentialthinking' based on previous checks.
        # But 'docker images' showed 'sequentialthinking:latest'.
        cmd = ["docker", "run", "-i", "--rm", self.image]
        
        logger.info(f"Connecting to Sequential MCP: {' '.join(cmd)}")
        
        server_params = StdioServerParameters(
            command=cmd[0],
            args=cmd[1:],
            env=None
        )

        self.exit_stack = AsyncExitStack()
        
        try:
            read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
            self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            logger.info("Connected to Sequential Thinking MCP Server via mcp library!")
            
            # List tools to verify
            tools = await self.session.list_tools()
            logger.info(f"Available tools: {[t.name for t in tools.tools]}")
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP: {e}")
            if self.exit_stack:
                await self.exit_stack.aclose()
            self.session = None
            self.exit_stack = None
            raise

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        if not self.session:
            await self.connect()
            
        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            
            # Format output
            output_text = ""
            for content in result.content:
                if content.type == "text":
                    output_text += content.text
                else:
                    output_text += f"[{content.type} content]"
            
            # Detect JSON string in output (Sequential server often returns raw JSON string)
            # ADK expects clean text or dict? Let's return text.
            return {"result": output_text}
            
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {"error": str(e)}

    async def close(self):
        logger.info("Closing MCP connection...")
        if self.exit_stack:
            await self.exit_stack.aclose()
        self.session = None
        self.exit_stack = None

from contextvars import ContextVar
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["SequentialMCPClient"] = ContextVar("mcp_client", default=None)

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

# --- Tool Request Wrappers ---

async def sequentialthinking(thought: str, nextThoughtNeeded: bool = False, thoughtNumber: int = 0, totalThoughts: int = 0, isRevision: bool = False) -> Dict[str, Any]:
    """
    Facilitates high-quality reasoning through a structured, sequential thinking process.
    
    Args:
        thought: The thinking step content.
        nextThoughtNeeded: Whether another thinking step is needed.
        thoughtNumber: The current step number.
        totalThoughts: Estimated total steps.
        isRevision: Whether this functionality revises a previous thought.
    """
    client = await ensure_mcp()
    return await client.call_tool("sequentialthinking", {
        "thought": thought,
        "nextThoughtNeeded": nextThoughtNeeded,
        "thoughtNumber": thoughtNumber,
        "totalThoughts": totalThoughts,
        "isRevision": isRevision
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
        instruction_str = data.get("instruction", "You are a Sequential Thinking Specialist.")
else:
    instruction_str = "You are a Sequential Thinking Specialist."

# Ensure API Key is in environment for GenAI library
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY


# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_sequential_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM

    return Agent(
        name=manifest.get("agent_id", "sequential_thinking_specialist"),
        model=model_to_use,
        description=manifest.get("description", "Advanced reasoning specialist."),
        instruction=instruction_str,
        tools=[sequentialthinking]
    )


def create_app(model_name: str = None):
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    # Create agent instance
    agent_instance = create_sequential_agent(model_name)

    return App(
        name="finopti_sequential_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=5),
            BigQueryAgentAnalyticsPlugin(
                project_id=config.GCP_PROJECT_ID,
                dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
                table_id=config.BQ_ANALYTICS_TABLE,
                config=BigQueryLoggerConfig(enabled=True)
            )
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
    mcp = SequentialMCPClient()
    token_reset = _mcp_ctx.set(mcp)

    # Initialize Redis Publisher once
    publisher = None
    if RedisEventPublisher:
         try:
             publisher = RedisEventPublisher(
                 agent_name="Sequential Agent",
                 agent_role="Reasoning Specialist"
             )
             _redis_publisher_ctx.set(publisher)
         except: pass

    # Publish "Processing" event via standardized helper
    _report_progress(f"Reasoning about: {prompt[:50]}...", icon="🤔", display_type="toast")
    
    try:
        await mcp.connect()

        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"

        # Define run_once for fallback logic
        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id
                uid = user_email or "default"
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_sequential_agent")
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
            context_name="Sequential Thinking Agent"
        )
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id, session_id))
