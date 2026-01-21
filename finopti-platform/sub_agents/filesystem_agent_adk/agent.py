"""
Filesystem ADK Agent
"""

import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from contextlib import AsyncExitStack

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    logging.error("mcp library not found. Please install it.")
    sys.exit(1)

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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FilesystemMCPClient:
    def __init__(self):
        self.image = os.getenv("FILESYSTEM_MCP_IMAGE", "filesystem")
        self.host_path = os.getenv("FILESYSTEM_ROOT", "/tmp/agent_filesystem")
        
        # Ensure host path exists (if running locally or if mapped volume allows creation)
        try:
             if not os.path.exists(self.host_path):
                os.makedirs(self.host_path, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create host path {self.host_path}: {e}")

        self.session: Optional[ClientSession] = None
        self.exit_stack: Optional[AsyncExitStack] = None

    async def connect(self):
        if self.session:
            return

        logger.info(f"Connecting to Filesystem MCP (Image: {self.image}, Root: {self.host_path})...")
        
        # Define Docker run arguments
        cmd = [
            "docker", "run", "-i", "--rm",
            "-v", f"{self.host_path}:/projects",
            self.image,
            "/projects"
        ]

        server_params = StdioServerParameters(
            command=cmd[0],
            args=cmd[1:],
            env=None
        )

        self.exit_stack = AsyncExitStack()
        
        try:
            # Enter stdio_client context
            read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
            # Enter ClientSession context
            self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            logger.info("Connected to Filesystem MCP Server via mcp library!")
            
            # List tools to verify connection
            tools_list = await self.session.list_tools()
            logger.info(f"Available tools: {[t.name for t in tools_list.tools]}")
            
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
            
            # Formatting result for ADK
            # MCP returns a list of content items (TextContent, ImageContent, etc.)
            output_text = ""
            for content in result.content:
                if content.type == "text":
                    output_text += content.text
                else:
                    output_text += f"[{content.type} content]"
            
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

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["FilesystemMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    """Retrieve the client for the CURRENT context."""
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client

# --- Tool Wrappers ---

async def read_text_file(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_text_file", {"path": path})

async def read_media_file(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_media_file", {"path": path})

async def read_multiple_files(paths: List[str]) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_multiple_files", {"paths": paths})

async def write_file(path: str, content: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("write_file", {"path": path, "content": content})

async def edit_file(path: str, edits: List[Dict[str, str]], dryRun: bool = False) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("edit_file", {"path": path, "edits": edits, "dryRun": dryRun})

async def create_directory(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("create_directory", {"path": path})

async def list_directory(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_directory", {"path": path})

async def list_directory_with_sizes(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_directory_with_sizes", {"path": path})

async def move_file(source: str, destination: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("move_file", {"source": source, "destination": destination})

async def search_files(path: str, pattern: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("search_files", {"path": path, "pattern": pattern})

async def directory_tree(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("directory_tree", {"path": path})

async def get_file_info(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_file_info", {"path": path})

async def list_allowed_directories() -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_allowed_directories", {})

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
        instruction_str = data.get("instruction", "You can read/write files.")
else:
    instruction_str = "You can read/write files."

# Ensure API Key is in environment for GenAI library
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

fs_agent = Agent(
    name=manifest.get("agent_id", "filesystem_specialist"),
    model=config.FINOPTIAGENTS_LLM,
    description=manifest.get("description", "Local Filesystem Specialist."),
    instruction=instruction_str,
    tools=[
        read_text_file,
        read_media_file,
        read_multiple_files,
        write_file,
        edit_file,
        create_directory,
        list_directory,
        list_directory_with_sizes,
        move_file,
        search_files,
        directory_tree,
        get_file_info,
        list_allowed_directories
    ]
)

app = App(
    name="finopti_filesystem_agent",
    root_agent=fs_agent,
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
    # Create new client for this request (and this event loop)
    mcp = FilesystemMCPClient()
    token_reset = _mcp_ctx.set(mcp)
    
    try:
        await mcp.connect()

        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"

        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_filesystem_agent")
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
