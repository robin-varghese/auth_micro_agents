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
from google.adk. runners import InMemoryRunner

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

def get_gemini_model(project_id: str) -> str:
    """Fetch Gemini model name dynamically."""
    env_model = os.getenv("FINOPTIAGENTS_LLM")
    if env_model: return env_model
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/finoptiagents-llm/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.warning(f"Could not fetch LLM model from Secret Manager: {e}")
    return "gemini-2.0-flash-exp"

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
            # Do not raise here to allow Native tools to function even if MCP fails
            # raise RuntimeError(f"Failed to connect to DB MCP Toolbox at {sse_url}: {e}")
    
    async def close(self):
        if self.exit_stack:
            await self.exit_stack.aclose()
            self.exit_stack = None
            self.session = None
            
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        if not self.session:
            raise RuntimeError("MCP not connected (Postgres tools unavailable)")
        
        result = await self.session.call_tool(tool_name, arguments=arguments)
        
        output = []
        for content in result.content:
            if content.type == "text":
                output.append(content.text)
        return "\n".join(output)

_mcp_client = None

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
        table_id = os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2")
        full_table_id = f"{config.GCP_PROJECT_ID}.{dataset_id}.{table_id}"
        
        query = f"""
            SELECT timestamp, event_type, agent_name, prompt, model
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

async def execute_postgres_query(query: str) -> Dict[str, Any]:
    """ADK Tool: Execute SQL query on PostgreSQL (via MCP)"""
    global _mcp_client
    try:
        if not _mcp_client: _mcp_client = DBMCPClient(); await _mcp_client.connect()
        output = await _mcp_client.call_tool("query_database", {"query": query}) # Mapped to generic 'query_database'
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def list_postgres_tables() -> Dict[str, Any]:
    """ADK Tool: List all PostgreSQL tables"""
    global _mcp_client
    try:
        if not _mcp_client: _mcp_client = DBMCPClient(); await _mcp_client.connect()
        output = await _mcp_client.call_tool("list_tables", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --------------------------------------------------------------------------------
# AGENT SETUP
# --------------------------------------------------------------------------------

# Ensure GOOGLE_API_KEY is set
if not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = getattr(config, "GOOGLE_API_KEY", "")

db_agent = Agent(
    name="database_specialist",
    model=get_gemini_model(config.GCP_PROJECT_ID),
    description="Database specialist for PostgreSQL and Agent Analytics (BigQuery).",
    instruction="""
    You are a Database Specialist.
    
    1. For "operations", "history", "logs", or "agent analytics":
       - Use `query_agent_analytics`.
       - This queries BigQuery for recent agent activity.
       
    2. For PostgreSQL database tasks (tables, schemas, generic SQL):
       - Use `list_postgres_tables` or `execute_postgres_query`.
       - Always inspect tables first if unsure.
    """,
    tools=[list_postgres_tables, execute_postgres_query, query_agent_analytics]
)

# Configure BigQuery Plugin
bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=config.GCP_PROJECT_ID,
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
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

async def send_message_async(prompt: str, user_email: str = None) -> str:
    try:
        global _mcp_client
        # Lazy init MCP
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
            return response_text if response_text else "No response generated."
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return f"Error: {str(e)}"
    finally:
        # Don't close MCP here if we want reuse, but current architecture is stateless-ish per request
        if _mcp_client:
            await _mcp_client.close()
            _mcp_client = None

def send_message(prompt: str, user_email: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email))
