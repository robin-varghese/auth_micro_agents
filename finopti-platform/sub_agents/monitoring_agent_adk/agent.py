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

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MonitoringMCPClient:
    """Client for connecting to Monitoring MCP server via Docker Stdio"""
    
    def __init__(self):
        # Use gcloud-mcp image as it contains observability tools
        self.image = os.getenv('GCLOUD_MCP_DOCKER_IMAGE', 'finopti-gcloud-mcp')
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
        await self._send_json(payload)
        while True:
            line = await self.process.stdout.readline()
            if not line: raise RuntimeError("MCP closed")
            msg = json.loads(line)
            if msg.get("id") == self.request_id:
                if "error" in msg: return {"error": msg["error"]}
                result = msg.get("result", {})
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
                await self.process.wait()
            except: pass

_mcp = None
async def ensure_mcp():
    global _mcp
    if not _mcp:
        _mcp = MonitoringMCPClient()
        await _mcp.connect()
    return _mcp

# --- Tool Wrappers ---

async def list_log_entries(project: str, filter: str = "", limit: int = 10) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_log_entries", {"project": project, "filter": filter, "limit": limit})

async def list_log_names(project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_log_names", {"project": project})

async def list_buckets(project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_buckets", {"project": project})

async def list_views(project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_views", {"project": project})

async def list_sinks(project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_sinks", {"project": project})

async def list_log_scopes(project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_log_scopes", {"project": project})

async def list_metric_descriptors(name: str, filter: str = "") -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_metric_descriptors", {"name": name, "filter": filter})

async def list_time_series(name: str, filter: str, interval: dict, view: str = "FULL") -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_time_series", {"name": name, "filter": filter, "interval": interval, "view": view})

async def list_alert_policies(name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_alert_policies", {"name": name})

async def list_traces(project_id: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_traces", {"project_id": project_id})

async def get_trace(project_id: str, trace_id: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_trace", {"project_id": project_id, "trace_id": trace_id})

async def list_group_stats(project_id: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_group_stats", {"project_id": project_id})

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
        list_log_entries, list_log_names, list_buckets, list_views, list_sinks, 
        list_log_scopes, list_metric_descriptors, list_time_series, 
        list_alert_policies, list_traces, get_trace, list_group_stats
    ]
)

app = App(
    name="finopti_monitoring_agent",
    root_agent=agent,
    plugins=[
        ReflectAndRetryToolPlugin(),
        BigQueryAgentAnalyticsPlugin(
            project_id=config.GCP_PROJECT_ID,
            dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
            table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
            config=BigQueryLoggerConfig(enabled=True)
        )
    ]
)

async def send_message_async(prompt: str, user_email: str = None, project_id: str = None) -> str:
    global _mcp
    try:
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
        if _mcp: await _mcp.close(); _mcp = None

def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id))

