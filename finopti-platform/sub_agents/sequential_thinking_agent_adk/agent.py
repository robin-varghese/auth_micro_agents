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

_mcp = None
async def ensure_mcp():
    global _mcp
    if not _mcp:
        _mcp = SequentialMCPClient()
        await _mcp.connect()
    return _mcp

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

agent = Agent(
    name=manifest.get("agent_id", "sequential_thinking_specialist"),
    model=config.FINOPTIAGENTS_LLM,
    description=manifest.get("description", "Advanced reasoning specialist."),
    instruction=instruction_str,
    tools=[sequentialthinking]
)

app = App(
    name="finopti_sequential_agent",
    root_agent=agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=5),
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
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_sequential_agent")
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(session_id="default", user_id="default", new_message=message):
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text: response_text += part.text
            return response_text
    finally:
        # Keep connection open for reuse ideally, but close strictly if needed.
        # pass
         if _mcp: await _mcp.close(); _mcp = None

def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id))
