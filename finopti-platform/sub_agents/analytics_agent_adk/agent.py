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

_mcp = None
_token_cache = None

# Wrapper to receive token indirectly via global state or context
# ADK Tool handling is stateless, so we rely on the _mcp client being initialized per request
async def run_report(property_id: str, dimensions: List[str] = [], metrics: List[str] = []) -> Dict[str, Any]:
    global _mcp
    if not _mcp: raise RuntimeError("MCP not initialized with token")
    return await _mcp.call_tool("run_report", {
        "property_id": property_id,
        "dimensions": dimensions,
        "metrics": metrics
    })

ga_agent = Agent(
    name="analytics_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="Google Analytics 4 Specialist.",
    instruction="Analyze web traffic using run_report.",
    tools=[run_report]
)

app = App(
    name="finopti_analytics_agent",
    root_agent=ga_agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=3),
        BigQueryAgentAnalyticsPlugin(
            project_id=config.GCP_PROJECT_ID,
            dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
            table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
            config=BigQueryLoggerConfig(enabled=True)
        )
    ]
)

async def send_message_async(prompt: str, user_email: str = None, token: str = None) -> str:
    global _mcp, _token_cache
    _token_cache = token
    # Re-init client per request to be safe with different tokens?
    # For now, yes.
    if _mcp: await _mcp.close()
    _mcp = AnalyticsMCPClient()
    
    try:
        if token:
            await _mcp.connect(token)
        else:
            return "Error: No OAuth Token provided."
            
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session("default", "default", "ga_app")
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async("default", "default", new_message=message):
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text: response_text += part.text
            return response_text
    finally:
        if _mcp: await _mcp.close(); _mcp = None

def send_message(prompt: str, user_email: str = None, token: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, token))
