"""
Sequential Thinking MCP Client Wrapper
"""
import os
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
    os.system("pip install mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

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

# ContextVar for isolation
_mcp_ctx: ContextVar["SequentialMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client
