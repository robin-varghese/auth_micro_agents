"""
Sequential Thinking ADK Agent

This agent uses Google ADK to facilitate structured sequential thinking.
It integrates with the Sequential Thinking MCP server.
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
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
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
from tools import sequentialthinking
from mcp_client import SequentialMCPClient, _mcp_ctx

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Observability
setup_observability()

# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
def create_sequential_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM

    return Agent(
        name=AGENT_NAME,
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[sequentialthinking]
    )

def create_app(model_name: str = None):
    # Ensure API Key
    if hasattr(config, "GOOGLE_API_KEY") and config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    agent_instance = create_sequential_agent(model_name)

    return App(
        name="finopti_sequential_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=5),
            BigQueryAgentAnalyticsPlugin(
                project_id=config.GCP_PROJECT_ID,
                dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
                table_id=config.BQ_ANALYTICS_TABLE,
                config=BigQueryLoggerConfig(enabled=True)
            )
        ]
    )

async def send_message_async(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default", auth_token: str = None) -> str:
    # --- CONTEXT SETTING ---
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email or "unknown")

    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
        if user_email:
            span.set_attribute("user_id", user_email)

    # Initialize Client
    mcp = SequentialMCPClient()
    token_reset = _mcp_ctx.set(mcp)

    # Initialize Redis Publisher
    publisher = None
    if RedisEventPublisher:
         try:
             publisher = RedisEventPublisher("Sequential Agent", "Reasoning Specialist")
             _redis_publisher_ctx.set(publisher)
         except Exception as e:
             logger.warning(f"Failed to initialize RedisEventPublisher: {e}")

    # Publish "Processing" event
    _report_progress(f"Reasoning about: {prompt[:50]}...", icon="🤔", display_type="toast")
    
    try:
        await mcp.connect()

        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"

        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id
                uid = user_email or "default"
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_sequential_agent")
                message = types.Content(parts=[types.Part(text=prompt)])

                async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                    if publisher:
                        publisher.process_adk_event(event, session_id=sid, user_id=uid)
                    if hasattr(event, 'content') and event.content:
                        for part in event.content.parts:
                            if part.text: response_text += part.text
            return response_text

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="Sequential Thinking Agent"
        )
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default", auth_token: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id, session_id, auth_token))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(send_message(" ".join(sys.argv[1:])))
    else:
        print("Usage: python agent.py <prompt>")
