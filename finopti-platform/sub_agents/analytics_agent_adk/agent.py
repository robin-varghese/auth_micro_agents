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
    project_name=os.getenv("GCP_PROJECT_ID", "local") + "-analytics-agent",
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

ga_agent = Agent(
    name=manifest.get("agent_id", "analytics_specialist"),
    model=config.FINOPTIAGENTS_LLM,
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


def create_app():
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    return App(
        name="finopti_analytics_agent",
        root_agent=ga_agent,
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

async def send_message_async(prompt: str, user_email: str = None, token: str = None) -> str:
    # Initialize client locally for this request
    mcp = AnalyticsMCPClient()
    token_reset = _mcp_ctx.set(mcp)
    
    try:
        if token:
            await mcp.connect(token)
        else:
            return "Error: No OAuth Token provided."
        
        app = create_app()
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session("default", "default", "ga_app")
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

def send_message(prompt: str, user_email: str = None, token: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, token))
