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
import requests  # For HTTP MCP client
import logging

from config import config

# MCP Client
class StorageMCPClient:
    """Client for connecting to Storage MCP server via APISIX HTTP"""
    
    def __init__(self):
        self.apisix_url = os.getenv('APISIX_URL', 'http://apisix:9080')
        self.mcp_endpoint = f"{self.apisix_url}/mcp/storage"
    
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    

            
            
    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call Storage MCP tool via APISIX HTTP"""
        payload = {
            "jsonrpc": "2.0",
            "method": f"tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": 1
        }
        
        try:
            response = requests.post(
                self.mcp_endpoint,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            # Extract text content
            if "result" in result and "content" in result["result"]:
                output = []
                for content in result["result"]["content"]:
                    if content.get("type") == "text":
                        output.append(content["text"])
                return "\n".join(output)
            
            return str(result.get("result", result))
            
        except Exception as e:
            raise RuntimeError(f"Storage MCP call failed: {e}") from e

# Global MCP client
_mcp_client = None

# --- TOOLS ---

async def list_buckets() -> Dict[str, Any]:
    """ADK Tool: List GCS buckets"""
    try:
        client = StorageMCPClient()
        output = await client.call_tool("list_buckets", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def list_objects(bucket_name: str, prefix: str = "") -> Dict[str, Any]:
    """ADK Tool: List objects in a bucket"""
    try:
        client = StorageMCPClient()
        output = await client.call_tool("list_objects", {"bucket_name": bucket_name, "prefix": prefix})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def read_object(bucket_name: str, object_name: str) -> Dict[str, Any]:
    """ADK Tool: Read object content"""
    try:
        client = StorageMCPClient()
        output = await client.call_tool("read_object", {"bucket_name": bucket_name, "object_name": object_name})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Create ADK Agent
# Ensure GOOGLE_API_KEY is set for the ADK/GenAI library
if not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = getattr(config, "GOOGLE_API_KEY", "")

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

def send_message(prompt: str, user_email: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email))
