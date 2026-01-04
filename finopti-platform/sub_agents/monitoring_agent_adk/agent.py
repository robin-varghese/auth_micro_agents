"""
Monitoring ADK Agent - Google Cloud Monitoring and Logging Specialist

This agent uses Google ADK to handle GCP monitoring and logging requests.
It integrates with the Monitoring MCP server via Stdio (Docker spawning).
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
import json
import requests  # For HTTP MCP client
import logging

from config import config

# MCP Client for Monitoring
class MonitoringMCPClient:
    """Client for connecting to Monitoring MCP server via APISIX HTTP"""
    
    def __init__(self):
        self.apisix_url = os.getenv('APISIX_URL', 'http://apisix:9080')
        self.mcp_endpoint = f"{self.apisix_url}/mcp/monitoring"
    
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    

    
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        """Call Monitoring MCP tool via APISIX HTTP"""
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
                output_text = ""
                for content in result["result"]["content"]:
                    if content.get("type") == "text":
                        output_text += content["text"]
                try:
                    return json.loads(output_text)
                except json.JSONDecodeError:
                    return {"output": output_text}
            
            return result.get("result", result)
            
        except Exception as e:
            raise RuntimeError(f"Monitoring MCP call failed: {e}") from e


# Global MCP client (will be initialized per-request)
_mcp_client = None

async def ensure_client():
    global _mcp_client
    if not _mcp_client:
        _mcp_client = MonitoringMCPClient()
        await _mcp_client.connect()
    return _mcp_client


async def query_time_series(
    project_id: str,
    metric_type: str,
    resource_filter: str = "",
    minutes_ago: int = 60
) -> Dict[str, Any]:
    """ADK tool: Query time series metrics from Cloud Monitoring"""
    try:
        client = await ensure_client()
        result = await client.call_tool(
            "query_time_series", 
            arguments={
                "project_id": project_id,
                "metric_type": metric_type,
                "resource_filter": resource_filter,
                "minutes_ago": minutes_ago
            }
        )
        return {
            "success": True,
            "data": result,
            "tool": "query_time_series"
        }
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "query_time_series"}


async def query_logs(
    project_id: str,
    filter_str: str = "",
    hours_ago: int = 24,
    limit: int = 100
) -> Dict[str, Any]:
    """ADK tool: Query log entries from Cloud Logging"""
    try:
        client = await ensure_client()
        result = await client.call_tool(
            "query_logs", 
            arguments={
                "project_id": project_id,
                "filter": filter_str or "",
                "hours_ago": hours_ago,
                "limit": limit
            }
        )
        return {
            "success": True,
            "data": result,
            "tool": "query_logs"
        }
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "query_logs"}


async def list_metrics(
    project_id: str,
    filter_str: str = ""
) -> Dict[str, Any]:
    """ADK tool: List available metric descriptors"""
    try:
        client = await ensure_client()
        result = await client.call_tool(
            "list_metrics", 
            arguments={
                "project_id": project_id,
                "filter": filter_str or ""
            }
        )
        return {
            "success": True,
            "data": result,
            "tool": "list_metrics"
        }
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "list_metrics"}


# Create ADK Agent
monitoring_agent = Agent(
    name="cloud_monitoring_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="""
    Google Cloud monitoring and logging specialist.
    Expert in querying metrics, logs, and monitoring data from GCP Cloud Monitoring and Cloud Logging.
    Can retrieve CPU usage, memory metrics, log entries, and analyze system health.
    """,
    instruction="""
    You are a Google Cloud Platform (GCP) monitoring and observability specialist.
    
    Your responsibilities:
    1. Understand user requests related to monitoring, logging, and observability
    2. Query appropriate metrics and logs from Cloud Monitoring and Cloud Logging
    3. Analyze and present monitoring data clearly
    4. Provide insights and recommendations based on monitoring data
    
    Available tools:
    - query_time_series: Get time-series metrics (CPU, memory, disk, network)
    - query_logs: Search and retrieve log entries
    - list_metrics: Discover available metrics
    
    Common patterns:
    - CPU usage: metric_type='compute.googleapis.com/instance/cpu/utilization'
    - Memory usage: metric_type='compute.googleapis.com/instance/memory/usage'
    - Query error logs: filter='severity>=ERROR'
    - Recent logs: Use hours_ago parameter
    
    Guidelines:
    - For monitoring queries: Use appropriate metric types and filters
    - For log queries: Craft effective filter expressions
    - For analysis: Summarize findings clearly
    - Always include project_id when available
    
    Be helpful, accurate, and insightful in your analysis.
    """,
    tools=[query_time_series, query_logs, list_metrics]
)

# Configure BigQuery Analytics Plugin
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

# Ensure API Key is in environment for GenAI library
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

# Create the App
app = App(
    name="finopti_monitoring_agent",
    root_agent=monitoring_agent,
    plugins=[
        ReflectAndRetryToolPlugin(
            max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "2")),
            throw_exception_if_retry_exceeded=os.getenv("REFLECT_RETRY_THROW_ON_FAIL", "true").lower() == "true"
        ),
        bq_plugin
    ]
)


from google.adk.runners import InMemoryRunner
from google.genai import types

async def send_message_async(prompt: str, user_email: str = None, project_id: str = None) -> str:
    """Send a message to the Monitoring agent"""
    try:
        # Enhance prompt with project_id if provided
        if project_id:
            enhanced_prompt = f"[Project: {project_id}] {prompt}"
        else:
            enhanced_prompt = prompt
        
        # Initialize MCP client if needed
        await ensure_client()
        
        # Use InMemoryRunner to execute the app
        async with InMemoryRunner(app=app) as runner:
            sid = "default"
            uid = "default"
            await runner.session_service.create_session(
                session_id=sid, 
                user_id=uid,
                app_name="finopti_monitoring_agent"
            )
            
            message = types.Content(parts=[types.Part(text=enhanced_prompt)])
            response_text = ""
            async for event in runner.run_async(
                user_id=uid,
                session_id=sid,
                new_message=message
            ):
                 # Accumulate text content from events
                 if hasattr(event, 'content') and event.content and event.content.parts:
                     for part in event.content.parts:
                         if part.text:
                             response_text += part.text
            
            return response_text if response_text else "No response generated."

    except Exception as e:
        return f"Error processing request: {str(e)}"
    finally:
        # Clean up MCP client
        global _mcp_client
        if _mcp_client:
            await _mcp_client.close()
            _mcp_client = None


def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    """Synchronous wrapper for send_message_async"""
    return asyncio.run(send_message_async(prompt, user_email, project_id))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"Prompt: {prompt}")
        print("=" * 50)
        response = send_message(prompt, project_id=config.GCP_PROJECT_ID)
        print(response)
    else:
        print("Usage: python agent.py <prompt>")
