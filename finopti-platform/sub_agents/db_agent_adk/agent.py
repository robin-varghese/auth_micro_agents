"""
Google Database ADK Agent

This agent uses Google ADK to handle Database interactions.
It supports:
1. PostgreSQL (via MCP Toolbox over SSE)
2. BigQuery Agent Analytics (via Native Client)
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from contextlib import AsyncExitStack

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.cloud import bigquery, secretmanager
from google.genai import types
from google.adk.runners import InMemoryRunner

# MCP Imports
from mcp import ClientSession
try:
    from mcp.client.sse import sse_client
except ImportError:
    from mcp.client.sse import sse_client

from config import config
from orchestrator_adk.structured_logging import propagate_request_id

# Configure structured logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------
# UTILITIES
# --------------------------------------------------------------------------------

# (get_gemini_model removed - using config.FINOPTIAGENTS_LLM)

# --------------------------------------------------------------------------------
# MCP CLIENT (PostgreSQL)
# --------------------------------------------------------------------------------

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

from contextvars import ContextVar

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["DBMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    """Retrieve the client for the CURRENT context."""
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client

# --------------------------------------------------------------------------------
# NATIVE TOOLS (BigQuery)
# --------------------------------------------------------------------------------

async def query_agent_analytics(limit: int = 10, days_back: int = 7) -> Dict[str, Any]:
    """
    ADK Tool: Query the Agent Analytics (BigQuery) for recent operations.
    Use this to see what agents have been doing.
    """
    try:
        client = bigquery.Client(project=config.GCP_PROJECT_ID)
        dataset_id = os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics")
        table_id = config.BQ_ANALYTICS_TABLE
        full_table_id = f"{config.GCP_PROJECT_ID}.{dataset_id}.{table_id}"
        
        query = f"""
            SELECT timestamp, event_type, agent, prompt, model
            FROM `{full_table_id}`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days_back} DAY)
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        
        query_job = client.query(query)
        results = []
        for row in query_job:
            results.append(dict(row))
            
        return {"success": True, "output": results}
    except Exception as e:
        logger.error(f"BigQuery query failed: {e}")
        return {"success": False, "error": str(e)}

# --------------------------------------------------------------------------------
# MCP TOOLS (PostgreSQL)
# --------------------------------------------------------------------------------

async def postgres_execute_sql(sql: str) -> Dict[str, Any]:
    """Execute SQL query on PostgreSQL."""
    client = await ensure_mcp()
    try:
        output = await client.call_tool("postgres_execute_sql", {"sql": sql})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def postgres_list_tables() -> Dict[str, Any]:
    """List all PostgreSQL tables available."""
    client = await ensure_mcp()
    try:
        # Note: 'postgres-list-tables' might be 'list-tables' in some setups, but we try specific first
        output = await client.call_tool("postgres_list_tables", {})
        return {"success": True, "output": output}
    except Exception as e:
         # Fallback to generic if specific fails? No, keep it specific as per manifest.
        return {"success": False, "error": str(e)}

async def postgres_list_indexes() -> Dict[str, Any]:
    """List PostgreSQL indexes."""
    client = await ensure_mcp()
    try:
        output = await client.call_tool("postgres_list_indexes", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def postgres_database_overview() -> Dict[str, Any]:
    """Get high-level overview of the PostgreSQL database."""
    client = await ensure_mcp()
    try:
        output = await client.call_tool("postgres_database_overview", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def postgres_list_active_queries() -> Dict[str, Any]:
    """List currently active queries in PostgreSQL."""
    client = await ensure_mcp()
    try:
        output = await client.call_tool("postgres_list_active_queries", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --------------------------------------------------------------------------------
# AGENT SETUP
# --------------------------------------------------------------------------------

# Ensure GOOGLE_API_KEY is set
if not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = getattr(config, "GOOGLE_API_KEY", "")

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
        instruction_str = data.get("instruction", "You are a Database Specialist.")
else:
    instruction_str = "You are a Database Specialist."

db_agent = Agent(
    name=manifest.get("agent_id", "database_specialist"),
    model=config.FINOPTIAGENTS_LLM,
    description=manifest.get("description", "Database specialist."),
    instruction=instruction_str,
    tools=[
        postgres_execute_sql,
        postgres_list_tables,
        postgres_list_indexes,
        postgres_database_overview,
        postgres_list_active_queries,
        query_agent_analytics
    ]
)

# Configure BigQuery Plugin
bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=config.GCP_PROJECT_ID,
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=config.BQ_ANALYTICS_TABLE,
    config=BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
        batch_size=1
    ),
    location="US"
)

app = App(
    name="finopti_db_agent",
    root_agent=db_agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=3),
        bq_plugin
    ]
)

# --------------------------------------------------------------------------------
# MSG HANDLING
# --------------------------------------------------------------------------------

async def send_message_async(prompt: str, user_email: str = None, project_id: str = None) -> str:
    # A. Initialize Client for THIS Scope
    mcp = DBMCPClient()
    token_reset = _mcp_ctx.set(mcp)
    
    try:
        # B. Connect
        await mcp.connect()

        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"
            
        async with InMemoryRunner(app=app) as runner:
            session_uid = user_email if user_email else "default"
            await runner.session_service.create_session(session_id="default", user_id=session_uid, app_name=app.name)
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(session_id="default", user_id=session_uid, new_message=message):
                 if hasattr(event, 'content') and event.content and event.content.parts:
                     for part in event.content.parts:
                         if part.text:
                             response_text += part.text
            return response_text if response_text else "No response generated."
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return f"Error: {str(e)}"
    finally:
        # D. Cleanup
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id))
