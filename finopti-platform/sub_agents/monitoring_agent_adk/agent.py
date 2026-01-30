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
    project_name=os.getenv("GCP_PROJECT_ID", "local") + "-monitoring-agent-adk",
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

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["MonitoringMCPClient"] = ContextVar("mcp_client", default=None)

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

agent = Agent(
    name=manifest.get("agent_id", "cloud_monitoring_specialist"),
    model=config.FINOPTIAGENTS_LLM,
    description=manifest.get("description", "Monitoring Specialist."),
    instruction=instruction_str,
    tools=[
        query_logs, list_metrics, query_time_series
    ]
)


# Helper to create app per request
def create_app():
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

    return App(
        name="finopti_monitoring_agent",
        root_agent=agent,
        plugins=[
            ReflectAndRetryToolPlugin(),
            bq_plugin
        ]
    )


async def send_message_async(prompt: str, user_email: str = None, project_id: str = None) -> str:
    # Create new client for this request (and this event loop)
    mcp = MonitoringMCPClient()
    token_reset = _mcp_ctx.set(mcp)
    
    try:
        await mcp.connect()
        
        # Create app per request
        app = create_app()

        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"
            
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_monitoring_agent")
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(session_id="default", user_id="default", new_message=message):
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text: response_text += part.text
            return response_text
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id))

