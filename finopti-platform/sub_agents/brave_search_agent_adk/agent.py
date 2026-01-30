"""
Brave Search ADK Agent
"""

import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any, List
from pathlib import Path

# Add parent directory to path
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
from google.cloud import secretmanager
from config import config

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name=os.getenv("GCP_PROJECT_ID", "local") + "-brave-agent",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# 1. MCP Client with Secret Manager Integration
class BraveMCPClient:
    def __init__(self):
        self.image = "finopti-brave-search"
        self.process = None
        self.request_id = 0
    
    async def _get_api_key(self):
        # Fetch from Secret Manager
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{config.GCP_PROJECT_ID}/secrets/BRAVE_API_KEY/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            logging.error(f"Failed to fetch BRAVE_API_KEY: {e}")
            raise

    async def connect(self):
        api_key = await self._get_api_key()
        
        cmd = [
            "docker", "run", "-i", "--rm",
            "-e", f"BRAVE_API_KEY={api_key}",
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
        # Initialize
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "brave-agent", "version": "1.0"}}
        })
        
        # Wait for response
        while True:
            line = await self.process.stdout.readline()
            if not line: break
            msg = json.loads(line)
            if msg.get("id") == 0: break
            
        # Initialized notification
        await self._send_json({
            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}
        })

    async def _send_json(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
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
                # Extract text content
                content = result.get("content", [])
                text = "".join([c["text"] for c in content if c["type"] == "text"])
                return {"result": text}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except: pass

# Global Client
_mcp = None

async def brave_web_search(query: str, count: int = 10) -> Dict[str, Any]:
    """Perform a web search using Brave."""
    global _mcp
    if not _mcp:
        _mcp = BraveMCPClient()
        await _mcp.connect()
    return await _mcp.call_tool("brave_web_search", {"query": query, "count": count})

async def brave_local_search(query: str, count: int = 5) -> Dict[str, Any]:
    """Perform a local search using Brave."""
    global _mcp
    if not _mcp:
        _mcp = BraveMCPClient()
        await _mcp.connect()
    return await _mcp.call_tool("brave_local_search", {"query": query, "count": count})

async def brave_video_search(query: str, count: int = 10) -> Dict[str, Any]:
    """Perform a video search using Brave."""
    global _mcp
    if not _mcp:
        _mcp = BraveMCPClient()
        await _mcp.connect()
    return await _mcp.call_tool("brave_video_search", {"query": query, "count": count})

async def brave_image_search(query: str, count: int = 10) -> Dict[str, Any]:
    """Perform an image search using Brave."""
    global _mcp
    if not _mcp:
        _mcp = BraveMCPClient()
        await _mcp.connect()
    return await _mcp.call_tool("brave_image_search", {"query": query, "count": count})

async def brave_news_search(query: str, count: int = 10) -> Dict[str, Any]:
    """Perform a news search using Brave."""
    global _mcp
    if not _mcp:
        _mcp = BraveMCPClient()
        await _mcp.connect()
    return await _mcp.call_tool("brave_news_search", {"query": query, "count": count})

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
        instruction_str = data.get("instruction", "You are a search expert.")
else:
    instruction_str = "You are a search expert."

# Ensure API Key is in environment for GenAI library
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

# 2. ADK Agent
brave_agent = Agent(
    name=manifest.get("agent_id", "brave_search_specialist"),
    model=config.FINOPTIAGENTS_LLM,
    description=manifest.get("description", "Web and Local Search Specialist using Brave Search."),
    instruction=instruction_str,
    tools=[
        brave_web_search, 
        brave_local_search,
        brave_news_search,
        brave_video_search,
        brave_image_search
    ]
)

# 3. App with Plugins

def create_app():
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    return App(
        name="finopti_brave_agent",
        root_agent=brave_agent,
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

async def send_message_async(prompt: str, user_email: str = None, project_id: str = None) -> str:
    global _mcp
    try:
        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"
            
        app = create_app()
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_brave_agent")
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(session_id="default", user_id="default", new_message=message):
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text: response_text += part.text
            return response_text
    finally:
        if _mcp:
            await _mcp.close()
            _mcp = None

def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id))
