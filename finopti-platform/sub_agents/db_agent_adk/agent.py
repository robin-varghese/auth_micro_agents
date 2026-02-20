"""
Google Database ADK Agent

This agent uses Google ADK to handle Database interactions.
It supports:
1. PostgreSQL (via MCP Toolbox over SSE)
2. BigQuery (via Native Client)
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
    postgres_execute_sql, postgres_list_tables, postgres_list_indexes, 
    postgres_database_overview, postgres_list_active_queries, query_agent_analytics
)
from mcp_client import DBMCPClient, _mcp_ctx

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
def create_db_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=AGENT_NAME,
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[
            postgres_execute_sql,
            postgres_list_tables,
            postgres_list_indexes,
            postgres_database_overview,
            postgres_list_active_queries,
            query_agent_analytics
        ]
    )

def create_app(model_name: str = None):
    # Ensure API Key
    if not os.environ.get("GOOGLE_API_KEY"):
         os.environ["GOOGLE_API_KEY"] = getattr(config, "GOOGLE_API_KEY", "")

    agent_instance = create_db_agent(model_name)
    
    return App(
        name="finopti_db_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3)
        ]
    )

async def send_message_async(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default", auth_token: str = None) -> str:
    # --- CONTEXT SETTING ---
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email or "unknown")
    if auth_token:
        # [Rule 7] Sync to environment for tool stability
        os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = auth_token

    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
        if user_email:
            span.set_attribute("user_id", user_email)

    # Initialize Client
    mcp = DBMCPClient()
    token_reset = _mcp_ctx.set(mcp)

    # Initialize Redis Publisher
    publisher = None
    if RedisEventPublisher:
        try:
            publisher = RedisEventPublisher("DB Agent", "Database Specialist")
            _redis_publisher_ctx.set(publisher)
        except: pass
    
    try:
        await mcp.connect()

        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"

        # Publish "Processing" event
        _report_progress(f"Querying Database...", icon="🗄️", display_type="toast")
        
        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id
                uid = user_email or "default"
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_db_agent")
                message = types.Content(parts=[types.Part(text=prompt)])

                async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                     if publisher:
                         publisher.process_adk_event(event, session_id=sid, user_id=uid)
                     if hasattr(event, 'content') and event.content:
                         for part in event.content.parts:
                             if part.text: response_text += part.text
            return response_text if response_text else "No response generated."

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="DB Agent"
        )
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return f"Error: {str(e)}"
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id, session_id))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(send_message(" ".join(sys.argv[1:])))
    else:
        print("Usage: python agent.py <prompt>")
