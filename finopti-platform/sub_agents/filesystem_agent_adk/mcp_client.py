"""
Filesystem MCP Client Wrapper
"""
import os
import sys
import logging
import asyncio
from typing import Dict, Any, Optional
from contextlib import AsyncExitStack
from contextvars import ContextVar

# Try importing mcp library
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    logging.error("mcp library not found. Please install it.")
    sys.exit(1)

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
            read, write = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
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
            # Note: We use the mcp library's session.call_tool which handles JSON
            result = await self.session.call_tool(tool_name, arguments=arguments)
            
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
            try:
                await self.exit_stack.aclose()
            except Exception as e:
                logger.warning(f"Error during exit_stack close: {e}")
        self.session = None
        self.exit_stack = None

# ContextVar for isolation
_mcp_ctx: ContextVar["FilesystemMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client
