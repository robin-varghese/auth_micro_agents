"""
GitHub ADK Agent - Repository and Code Specialist

This agent uses Google ADK to handle GitHub interactions.
It integrates with the official GitHub MCP server.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Ensure parent path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.adk.runners import InMemoryRunner
from google.genai import types
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

from config import config

# --- Refactored Modules ---
from observability import setup_observability
from context import (
    _redis_publisher_ctx, 
    _session_id_ctx, 
    _user_email_ctx, 
    _report_progress,
    RedisEventPublisher
)
from instructions import AGENT_INSTRUCTIONS, AGENT_DESCRIPTION, AGENT_NAME
from tools import (
    search_repositories, list_repositories, get_file_contents, create_or_update_file,
    push_files, create_issue, list_issues, update_issue, add_issue_comment,
    create_pull_request, list_pull_requests, merge_pull_request, get_pull_request,
    create_branch, list_branches, get_commit, search_code, search_issues
)
# Note: GitHubMCPClient in tools.py handles its own lifecycle per call

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Observability
setup_observability()

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_github_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=AGENT_NAME,
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[
            search_repositories, list_repositories, get_file_contents, create_or_update_file,
            push_files, create_issue, list_issues, update_issue, add_issue_comment,
            create_pull_request, list_pull_requests, merge_pull_request, get_pull_request,
            create_branch, list_branches, get_commit, search_code, search_issues
        ]
    )

def create_app(model_name: str = None) -> App:
    # Ensure Keys
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    if config.GCP_PROJECT_ID:
        os.environ["GOOGLE_CLOUD_PROJECT"] = config.GCP_PROJECT_ID
        os.environ["GCP_PROJECT_ID"] = config.GCP_PROJECT_ID
    
    # [NEW] Force Vertex AI if configured (User Request)
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE" or (hasattr(config, "GOOGLE_GENAI_USE_VERTEXAI") and config.GOOGLE_GENAI_USE_VERTEXAI):
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

    agent = create_github_agent(model_name)

    return App(
        name="finopti_github_agent",
        root_agent=agent,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3),
            BigQueryAgentAnalyticsPlugin(
                project_id=config.GCP_PROJECT_ID,
                dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
                table_id=config.BQ_ANALYTICS_TABLE,
                config=BigQueryLoggerConfig(
                    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true"
                ),
                location="US"
            )
        ]
    )

async def send_message_async(prompt: str, user_email: str = None, session_id: str = "default", auth_token: str = None) -> str:
    """Send message with Model Fallback"""
    try:
        # --- Context Setup ---
        _session_id_ctx.set(session_id)
        _user_email_ctx.set(user_email or "unknown")
        if auth_token:
            # [Rule 7] Sync to environment for tool stability
            os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = auth_token

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            if user_email:
                span.set_attribute("user_id", user_email)

        # Initialize Redis Publisher
        publisher = None
        if RedisEventPublisher:
             try:
                 publisher = RedisEventPublisher(agent_name="GitHub Agent", agent_role="Repository Specialist")
                 _redis_publisher_ctx.set(publisher)
             except: pass

        _report_progress(f"Processing GitHub request: {prompt[:50]}...", icon="🐙", display_type="toast")

        # Define run_once
        async def _run_once(app_instance):
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id 
                uid = user_email or "default"
                
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_github_agent")
                message = types.Content(parts=[types.Part(text=prompt)])
                response_text = ""

                async for event in runner.run_async(user_id=uid, session_id=sid, new_message=message):
                     if publisher:
                         publisher.process_adk_event(event, session_id=sid, user_id=uid)

                     if hasattr(event, 'content') and event.content and event.content.parts:
                          for part in event.content.parts:
                              if part.text: response_text += part.text
                
                return response_text if response_text else "No response generated."

        return await run_with_model_fallback(
            create_app_func=create_app, 
            run_func=_run_once,
            context_name="GitHub Agent"
        )
    except Exception as e:
        return f"Error: {str(e)}"

def send_message(prompt: str, user_email: str = None, session_id: str = "default", auth_token: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, session_id, auth_token))

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(send_message(" ".join(sys.argv[1:])))
    else:
        print("Usage: python agent.py <prompt>")
