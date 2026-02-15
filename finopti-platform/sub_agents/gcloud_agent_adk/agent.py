"""
GCloud ADK Agent - Google Cloud Infrastructure Specialist

This agent uses Google ADK to handle GCP infrastructure management requests.
It integrates with the GCloud MCP server for executing gcloud commands.
"""

import os
import sys
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any

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
from opentelemetry import trace, propagate
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
from tools import execute_gcloud_command
from mcp_client import get_mcp_client, close_mcp_client

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Observability
setup_observability()


# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_gcloud_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=AGENT_NAME,
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[execute_gcloud_command]
    )

def create_app(model_name: str = None) -> App:
    # Ensure API Key
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
        
    gcloud_agent = create_gcloud_agent(model_name)

    # Configure Analytics
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

    return App(
        name="finopti_gcloud_agent",
        root_agent=gcloud_agent,
        plugins=[
            ReflectAndRetryToolPlugin(
                max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "3"))
            ),
            bq_plugin
        ]
    )


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def send_message_async(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    """Send message with Model Fallback"""
    try:
        # --- Context Setup ---
        _session_id_ctx.set(session_id)
        _user_email_ctx.set(user_email or "unknown")

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            if user_email:
                span.set_attribute("user_id", user_email)

        # Initialize MCP Client
        await get_mcp_client()
        
        # Initialize Redis Publisher
        publisher = None
        if RedisEventPublisher:
             try:
                 publisher = RedisEventPublisher(agent_name="GCloud Agent", agent_role="Infrastructure Specialist")
                 _redis_publisher_ctx.set(publisher)
             except: pass
        # Publish "Processing" event
        await _report_progress(f"Processing request: {prompt[:50]}...", icon="⏳", display_type="toast")

        # Define run_once
        async def _run_once(app_instance):
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id 
                uid = user_email or "default"
                
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_gcloud_agent")
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
            context_name="GCloud Agent"
        )

    except Exception as e:
        return f"Error processing request: {str(e)}"
    finally:
        await close_mcp_client()


def send_message(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, session_id))

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(send_message(" ".join(sys.argv[1:])))
    else:
        print("Usage: python agent.py <prompt>")
