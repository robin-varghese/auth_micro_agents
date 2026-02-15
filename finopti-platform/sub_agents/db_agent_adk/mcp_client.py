"""
DB MCP Client Wrapper (PostgreSQL via SSE)
"""
import logging
from typing import Any
from contextlib import AsyncExitStack
from mcp import ClientSession
try:
    from mcp.client.sse import sse_client
except ImportError:
    from mcp.client.sse import sse_client

from config import config
from contextvars import ContextVar

logger = logging.getLogger(__name__)

class DBMCPClient:
    """Client for connecting to DB MCP Toolbox via SSE (Shared Configuration)"""
    
    def __init__(self):
        self.base_url = config.DB_MCP_TOOLBOX_URL
        self.session = None
        self.exit_stack = None
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        if self.session: return
        sse_url = f"{self.base_url}/sse"
        logger.info(f"Connecting to DB MCP Toolbox at {sse_url}")
        self.exit_stack = AsyncExitStack()
        try:
            read, write = await self.exit_stack.enter_async_context(sse_client(sse_url))
            self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            logger.info("DB MCP Toolbox connected.")
        except Exception as e:
            await self.close()
            logger.error(f"Failed to connect to DB MCP Toolbox: {e}")
    
    async def close(self):
        if self.exit_stack:
            await self.exit_stack.aclose()
            self.exit_stack = None
            self.session = None
            
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        if not self.session:
            raise RuntimeError("MCP not connected (Postgres tools unavailable)")
        
        toolbox_tool_name = tool_name
        
        # Fallback mappings if needed
        if toolbox_tool_name == "postgres_execute_sql":
             toolbox_tool_name = "query_database"
             if "sql" in arguments:
                 arguments["query"] = arguments.pop("sql")
        elif toolbox_tool_name == "postgres_list_tables":
             toolbox_tool_name = "list_tables"

        logger.info(f"Calling MCP Tool: {toolbox_tool_name}")
        result = await self.session.call_tool(toolbox_tool_name, arguments=arguments)
        
        output = []
        for content in result.content:
            if content.type == "text":
                output.append(content.text)
        return "\n".join(output)

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["DBMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    """Retrieve the client for the CURRENT context."""
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client
