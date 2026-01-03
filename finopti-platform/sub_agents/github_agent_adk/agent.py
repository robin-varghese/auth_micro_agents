"""
GitHub ADK Agent - Repository and Code Specialist

This agent uses Google ADK to handle GitHub interactions.
It integrates with the GitHub MCP server for executing git operations.
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

# MCP Client for GitHub
class GitHubMCPClient:
    """Client for connecting to GitHub MCP server via Docker stdio"""
    
    def __init__(self):
        self.docker_image = config.GITHUB_MCP_DOCKER_IMAGE
        self.session = None
        self.exit_stack = None
        # GitHub token must be passed to the container
        self.github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
        if not self.github_token:
            # Try to fetch from config/secret manager if enabled
            # Note: config.py doesn't have GITHUB_TOKEN directly exposed in the class, 
            # we might need to add it or just rely on env injection in docker-compose
            pass
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        """Connect to GitHub MCP server"""
        if self.session:
            return
            
        # Ensure we have the token
        token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
        
        server_params = StdioServerParameters(
            command="docker",
            args=[
                "run",
                "-i",
                "--rm",
                "--network", "host",
                "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={token}",
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
            raise RuntimeError(f"Failed to connect to GitHub MCP server: {e}")
    
    async def close(self):
        """Close connection"""
        if self.exit_stack:
            await self.exit_stack.aclose()
            self.exit_stack = None
            self.session = None
    
    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Generic tool caller"""
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

async def search_repositories(query: str) -> Dict[str, Any]:
    """ADK Tool: Search GitHub repositories"""
    global _mcp_client
    try:
        if not _mcp_client:
            _mcp_client = GitHubMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.call_tool("search_repositories", {"query": query})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def read_file(owner: str, repo: str, path: str) -> Dict[str, Any]:
    """ADK Tool: Read file content from GitHub"""
    global _mcp_client
    try:
        if not _mcp_client:
            _mcp_client = GitHubMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.call_tool("read_file", {"owner": owner, "repo": repo, "path": path})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Create ADK Agent
github_agent = Agent(
    name="github_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="GitHub repository and code specialist. Can search repos and read code.",
    instruction="""
    You are a GitHub specialist.
    Your capabilities:
    1. Search for repositories based on queries.
    2. Read file contents from specific repositories.
    
    When asked to find code or examples, use search_repositories.
    When asked about specific file content, use read_file.
    """,
    tools=[search_repositories, read_file]
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
    name="finopti_github_agent",
    root_agent=github_agent,
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
            _mcp_client = GitHubMCPClient()
            await _mcp_client.connect()
        
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_github_agent")
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
