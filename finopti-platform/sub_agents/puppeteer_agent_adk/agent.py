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
            stderr=asyncio.subprocess.PIPE
        )
        await self._handshake()

    async def _handshake(self):
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "puppeteer-agent", "version": "1.0"}}
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
                
                text = ""
                image_data = None
                
                for c in content:
                    if c["type"] == "text":
                        text += c["text"]
                    elif c["type"] == "image":
                        image_data = "Image received (base64 hidden)"
                        # TODO: Handle image persistence if needed
                
                return {"result": text, "image": image_data}

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
        _mcp = PuppeteerMCPClient()
        await _mcp.connect()
    return _mcp

# --- Tool Wrappers ---

async def puppeteer_navigate(url: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_navigate", {"url": url})

async def puppeteer_screenshot(name: str = "screenshot", width: int = 1200, height: int = 800) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_screenshot", {"name": name, "width": width, "height": height})

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

agent = Agent(
    name=manifest.get("agent_id", "browser_automation_specialist"),
    model=config.FINOPTIAGENTS_LLM,
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

app = App(
    name="finopti_puppeteer_agent",
    root_agent=agent,
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

        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_puppeteer_agent")
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

