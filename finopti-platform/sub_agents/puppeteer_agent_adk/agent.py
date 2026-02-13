"""
Puppeteer ADK Agent

This agent uses Google ADK to handle Puppeteer Browser Automation.
It integrates with the Puppeteer MCP server.
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any

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
    project_name="finoptiagents-PuppeteerAgent",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PuppeteerMCPClient:
    """Client for connecting to Puppeteer MCP server via Docker Stdio"""
    
    def __init__(self):
        self.image = os.getenv('PUPPETEER_MCP_DOCKER_IMAGE', 'finopti-puppeteer')
        self.process = None
        self.request_id = 0
        
    async def connect(self):
        self.last_filename = None
        cmd = [
            "docker", "run", "-i", "--rm", "--init",
            "-e", "DOCKER_CONTAINER=true",
            self.image
        ]
        
        logger.info(f"Starting Puppeteer MCP: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024  # 10MB buffer
        )
        await self._handshake()

    async def _handshake(self):
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "puppeteer-agent", "version": "1.0"}}
        })
        # Wait for initialize response
        while True:
            response = await self._read_json()
            if response.get("id") == 0:
                break
        
        await self._send_json({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _send_json(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def _read_json(self) -> dict:
        """Read JSON-RPC response, skipping non-JSON lines"""
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise EOFError("MCP server process closed unexpectedly")
            
            line_str = line.decode().strip()
            if not line_str:
                continue
                
            try:
                return json.loads(line_str)
            except json.JSONDecodeError:
                logger.debug(f"MCP non-JSON output: {line_str}")
                continue

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self.request_id
        }
        await self._send_json(payload)
        
        while True:
            msg = await self._read_json()
            if msg.get("id") == self.request_id:
                if "error" in msg: return {"error": msg["error"]}
                result = msg.get("result", {})
                content = result.get("content", [])
                
                text = ""
                image_data = None
                
                for c in content:
                    if c["type"] == "text":
                        text += c["text"]
                    elif c["type"] == "image":
                        # Return the actual base64 data so the tool wrapper can save it
                        image_data = c["data"]
                
                return {"result": text, "image": image_data}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except: pass

from contextvars import ContextVar
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["PuppeteerMCPClient"] = ContextVar("mcp_client", default=None)

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

async def puppeteer_navigate(url: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_navigate", {"url": url})

import base64

async def puppeteer_screenshot(name: str = "screenshot", width: int = 1200, height: int = 800, filename: str = None) -> Dict[str, Any]:
    client = await ensure_mcp()
    result = await client.call_tool("puppeteer_screenshot", {"name": name, "width": width, "height": height})
    
    # Check for image data and save to shared volume
    if result.get("image"):
        try:
            # Default filename if not provided
            if not filename:
                filename = f"{name}.png"
            
            # Ensure filename ends with .png
            if not filename.endswith(".png"):
                filename += ".png"
                
            # Define path in shared volume
            save_path = Path("/projects") / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Decode and write
            image_bytes = base64.b64decode(result["image"])
            with open(save_path, "wb") as f:
                f.write(image_bytes)
                
            logger.info(f"Saved screenshot to {save_path}")
            result["result"] += f"\n\n[System] Screenshot saved to shared volume at: {save_path}"
            
            # Store filename for orchestrator chaining
            client.last_filename = filename
            
            # Clear huge base64 string from result
            result["image"] = "[Saved to file]"
            
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            result["result"] += f"\n\n[System] Failed to save screenshot file: {e}"

    return result

async def puppeteer_click(selector: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_click", {"selector": selector})

async def puppeteer_fill(selector: str, value: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_fill", {"selector": selector, "value": value})

async def puppeteer_evaluate(script: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_evaluate", {"script": script})

async def puppeteer_hover(selector: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_hover", {"selector": selector})

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
        instruction_str = data.get("instruction", "You are a Browser Automation Specialist.")
else:
    instruction_str = "You are a Browser Automation Specialist."

# Ensure API Key is in environment for GenAI library
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY


# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_puppeteer_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=manifest.get("agent_id", "browser_automation_specialist"),
        model=model_to_use,
        description=manifest.get("description", "Browser Automation Specialist."),
        instruction=instruction_str,
        tools=[
            puppeteer_navigate, 
            puppeteer_screenshot, 
            puppeteer_click, 
            puppeteer_fill, 
            puppeteer_evaluate, 
            puppeteer_hover
        ]
    )

def create_app(model_name: str = None):
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    # Create agent instance
    agent_instance = create_puppeteer_agent(model_name)

    return App(
        name="finopti_puppeteer_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3),
            # BigQuery disabled to avoid event loop issues in this agent
            # BigQueryAgentAnalyticsPlugin(...)
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
    mcp = PuppeteerMCPClient()
    token_reset = _mcp_ctx.set(mcp)

    # Initialize Redis Publisher once
    publisher = None
    if RedisEventPublisher:
         try:
             publisher = RedisEventPublisher(
                 agent_name="Puppeteer Agent",
                 agent_role="Automation Specialist"
             )
             _redis_publisher_ctx.set(publisher)
         except: pass

    # Publish "Processing" event via standardized helper
    _report_progress(f"Automating Browser...", icon="🎭", display_type="toast")
    
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
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_puppeteer_agent")
                message = types.Content(parts=[types.Part(text=prompt)])

                async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                     # Stream Events
                     if publisher:
                         publisher.process_adk_event(event, session_id=sid, user_id=uid)

                     if hasattr(event, 'content') and event.content:
                         for part in event.content.parts:
                             if part.text: response_text += part.text
            return response_text

        final_response = await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="Puppeteer Agent"
        )
        
        # APPEND FILENAME FOR ORCHESTRATOR CHAINING
        if mcp.last_filename:
             final_response += f"\n\nFile Name: {mcp.last_filename}"
             
        return final_response
        
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id, session_id))
