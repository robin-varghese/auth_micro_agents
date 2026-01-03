"""
Google Database ADK Agent

This agent uses Google ADK to handle Database interactions (PostgreSQL).
It connects to the Google DB MCP Toolbox via SSE (Server-Sent Events).
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
from mcp import ClientSession
# Assuming mcp library has sse support. If standard library differs, this might need adjustment.
# Trying standard import for MCP python sdk sse transport
try:
    from mcp.client.sse import sse_client
except ImportError:
    # Fallback or error handling if sse_client is not directly exposed
    from mcp.client.sse import sse_client

from contextlib import AsyncExitStack

from config import config

# MCP Client
class DBMCPClient:
    """Client for connecting to DB MCP Toolbox via SSE"""
    
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
        if self.session:
            return
        
        # Determine SSE endpoint
        sse_url = f"{self.base_url}/sse"
        
        self.exit_stack = AsyncExitStack()
        
        try:
            read, write = await self.exit_stack.enter_async_context(
                sse_client(sse_url)
            )
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self.session.initialize()
        except Exception as e:
            await self.close()
            raise RuntimeError(f"Failed to connect to DB MCP Toolbox at {sse_url}: {e}")
    
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
# NOTE: Exact tool names depend on tools.yaml in the toolbox. 
# We assume standard SQL tools are exposed.

async def execute_query(query: str) -> Dict[str, Any]:
    """ADK Tool: Execute SQL query"""
    global _mcp_client
    try:
        if not _mcp_client:
            _mcp_client = DBMCPClient()
            await _mcp_client.connect()
        
        # 'execute_query' is a common naming convention for DB tools
        output = await _mcp_client.call_tool("execute_query", {"query": query})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def list_tables() -> Dict[str, Any]:
    """ADK Tool: List all tables"""
    global _mcp_client
    try:
        if not _mcp_client:
            _mcp_client = DBMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.call_tool("list_tables", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def get_table_schema(table_name: str) -> Dict[str, Any]:
    """ADK Tool: Get schema for a table"""
    global _mcp_client
    try:
        if not _mcp_client:
            _mcp_client = DBMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.call_tool("get_table_schema", {"table_name": table_name})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Create ADK Agent
db_agent = Agent(
    name="database_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="PostgreSQL database specialist. Can execute queries and inspect schemas.",
    instruction="""
    You are a Database specialist (PostgreSQL).
    Your capabilities:
    1. List tables in the database.
    2. Inspect table schemas.
    3. Execute SQL queries (SELECT only, unless authorized for modifications).
    
    Always inspect the schema (`get_table_schema`) before writing complex queries.
    """,
    tools=[list_tables, get_table_schema, execute_query]
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
    name="finopti_db_agent",
    root_agent=db_agent,
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
            _mcp_client = DBMCPClient()
            await _mcp_client.connect()
        
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_db_agent")
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
