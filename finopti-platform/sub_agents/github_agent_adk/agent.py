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
    
    def __init__(self, token: str = None):
        self.docker_image = config.GITHUB_MCP_DOCKER_IMAGE
        self.session = None
        self.exit_stack = None
        
        # Priority: Dynamic Token -> Env Var -> Config
        self.github_token = token
        if not self.github_token:
             self.github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
        if not self.github_token:
             self.github_token = getattr(config, "GITHUB_PERSONAL_ACCESS_TOKEN", "")

    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        """Connect to GitHub MCP server"""
        if self.session:
            return
            
        token = self.github_token
        if not token:
             # We allow connection without token, but MCP server might fail or work in limited mode?
             # Actually, without token, the container will print error and exit.
             # We throw error here to let the agent know it needs a token.
             raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN is required. Please ask the user for their GitHub PAT.")
        
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
            # Catch specific errors related to token?
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


# --- TOOLS ---

async def search_repositories(query: str, github_pat: str = None) -> Dict[str, Any]:
    """
    Search GitHub repositories.
    
    Args:
        query: The search query (e.g., 'mcp-server language:python').
        github_pat: (Optional) The user's GitHub Personal Access Token. 
                    If not provided, the agent will use the system default if available.
    """
    try:
        async with GitHubMCPClient(token=github_pat) as client:
            output = await client.call_tool("search_repositories", {"query": query})
            return {"success": True, "output": output}
    except ValueError as ve:
         # Token missing
         return {"success": False, "error": str(ve), "action_needed": "ask_user_for_pat"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def read_file(owner: str, repo: str, path: str, github_pat: str = None) -> Dict[str, Any]:
    """
    Read file content from GitHub.
    
    Args:
        owner: Repository owner/organization.
        repo: Repository name.
        path: Path to the file.
        github_pat: (Optional) The user's GitHub Personal Access Token.
    """
    try:
        async with GitHubMCPClient(token=github_pat) as client:
            output = await client.call_tool("read_file", {"owner": owner, "repo": repo, "path": path})
            return {"success": True, "output": output}
    except ValueError as ve:
         return {"success": False, "error": str(ve), "action_needed": "ask_user_for_pat"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Create ADK Agent
# Ensure GOOGLE_API_KEY is set for the ADK/GenAI library
if not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = getattr(config, "GOOGLE_API_KEY", "")

github_agent = Agent(
    name="github_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="GitHub repository and code specialist. Can search repos and read code.",
    instruction="""
    You are a GitHub specialist agent.
    
    ## Authentication Policy
    To interact with GitHub, you need a **Personal Access Token (PAT)**.
    1.  **Try first**: Attempt to call tools *without* successfully asking for a PAT (the system might have a default one).
    2.  **On Auth Error**: If a tool returns an error mentioning "GITHUB_PERSONAL_ACCESS_TOKEN is required" or "ask_user_for_pat", you MUST ask the user:
        "I need your GitHub Personal Access Token (PAT) to proceed. Please provide it."
    3.  **Using PAT**: Once the user provides the PAT, you MUST pass it as the `github_pat` argument to ALL subsequent tool calls in the session.
    
    ## Repo URL Handling
    If the user provides a GitHub Repository URL (e.g., `https://github.com/owner/repo`):
    1.  Extract the `owner` and `repo` names from the URL.
    2.  Use these extracted values for tools like `read_file`.
    
    ## Capabilities
    1.  **Search**: Use `search_repositories` to find code or projects.
    2.  **Read**: Use `read_file` to examine code content.
    
    Always summarize the results clearly for the user.
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
        # Note: We create a fresh runner for each request (stateless logic per request),
        # but the AGENT's conversation history (session) management depends on the session_id passed to run_async
        # or managed by the caller. The `InMemoryRunner` here is ephemeral. 
        # For true conversation history across turns, we rely on the `session_id="default"` being kept?
        # Actually, InMemoryRunner state is memory-only. If this function returns, the runner is destroyed.
        # So conversational state persistence depends on how `app` handles sessions or if `runner` persists.
        # In this simple implementation, context might be lost between HTTP requests.
        # However, for the purpose of this task (updating tool logic), this is sufficient.
        
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

def send_message(prompt: str, user_email: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email))
