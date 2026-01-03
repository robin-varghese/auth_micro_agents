"""
Google Storage ADK Agent

This agent uses Google ADK to handle Cloud Storage interactions.
It integrates with the Google Storage MCP server.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from typing import Dict, Any, List
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

from config import config

# MCP Client
class StorageMCPClient:
    """Client for connecting to Storage MCP server via Docker stdio"""
    
    def __init__(self):
        self.docker_image = config.STORAGE_MCP_DOCKER_IMAGE
        self.session = None
        self.exit_stack = None
        # Mount authentication
        self.mount_path = os.path.expanduser(config.GCLOUD_MOUNT_PATH)
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        if self.session:
            return
            
        server_params = StdioServerParameters(
            command="docker",
            args=[
                "run",
                "-i",
                "--rm",
                "--network", "host",
                "-v", self.mount_path,
                self.docker_image
            ],
            env=None
        )
        
        self.exit_stack = AsyncExitStack()
        
        try:
            read, write = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self.session.initialize()
        except Exception as e:
            await self.close()
            raise RuntimeError(f"Failed to connect to Storage MCP server: {e}")
    
    async def close(self):
        if self.exit_stack:
            await self.exit_stack.aclose()
            self.exit_stack = None
            self.session = None
            
    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        if not self.session:
            raise RuntimeError("Not connected")
        
        result = await self.session.call_tool(tool_name, arguments=arguments)
        
        output = []
        for content in result.content:
            if content.type == "text":
                output.append(content.text)
        
        return "\n".join(output)

# Global MCP client
_mcp_client = None

# --- TOOLS ---

async def list_buckets() -> Dict[str, Any]:
    """ADK Tool: List GCS buckets"""
    global _mcp_client
    try:
        if not _mcp_client:
            _mcp_client = StorageMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.call_tool("list_buckets", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def list_objects(bucket_name: str, prefix: str = "") -> Dict[str, Any]:
    """ADK Tool: List objects in a bucket"""
    global _mcp_client
    try:
        if not _mcp_client:
            _mcp_client = StorageMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.call_tool("list_objects", {"bucket_name": bucket_name, "prefix": prefix})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def read_object(bucket_name: str, object_name: str) -> Dict[str, Any]:
    """ADK Tool: Read object content"""
    global _mcp_client
    try:
        if not _mcp_client:
            _mcp_client = StorageMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.call_tool("read_object", {"bucket_name": bucket_name, "object_name": object_name})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Create ADK Agent
storage_agent = Agent(
    name="storage_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="Google Cloud Storage specialist. Can list buckets and manage objects.",
    instruction="""
    You are a Google Cloud Storage specialist.
    Your capabilities:
    1. List buckets in the project.
    2. List objects within buckets.
    3. Read contents of objects.
    
    Always ensure you have the correct bucket name before listing objects.
    """,
    tools=[list_buckets, list_objects, read_object]
)

# Configure BigQuery Plugin
bq_config = BigQueryLoggerConfig(
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    batch_size=1,
    max_content_length=100 * 1024,
    shutdown_timeout=10.0
)

bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=config.GCP_PROJECT_ID,
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=bq_config,
    location="US"
)

# Create App
app = App(
    name="finopti_storage_agent",
    root_agent=storage_agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=3),
        bq_plugin
    ]
)

from google.adk.runners import InMemoryRunner
from google.genai import types

async def send_message_async(prompt: str, user_email: str = None) -> str:
    try:
        global _mcp_client
        if not _mcp_client:
            _mcp_client = StorageMCPClient()
            await _mcp_client.connect()
        
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_storage_agent")
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(user_id="default", session_id="default", new_message=message):
                 if hasattr(event, 'content') and event.content and event.content.parts:
                     for part in event.content.parts:
                         if part.text:
                             response_text += part.text
            return response_text if response_text else "No response."
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        if _mcp_client:
            await _mcp_client.close()
            _mcp_client = None

def send_message(prompt: str, user_email: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email))
