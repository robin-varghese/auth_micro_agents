"""
Monitoring ADK Agent - Google Cloud Monitoring and Logging Specialist

This agent uses Google ADK to handle GCP monitoring and logging requests.
It uses the `gcloud-mcp` server to access observability tools.
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
from tools import query_logs, list_metrics, query_time_series
# from mcp_client import MonitoringMCPClient (Removed, now managed in tools.py)

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Observability
setup_observability()

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_monitoring_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=AGENT_NAME,
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[query_logs, list_metrics, query_time_series]
    )


# Helper to create app per request
def create_app(model_name: str = None):
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    # Create agent instance
    agent_instance = create_monitoring_agent(model_name)

    return App(
        name="finopti_monitoring_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3)
        ]
    )


async def send_message_async(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default", auth_token: str = None) -> str:
    try:
        # --- CONTEXT SETTING ---
        from context import _auth_token_ctx
        _session_id_ctx.set(session_id)
        _user_email_ctx.set(user_email or "unknown")
        if auth_token:
            _auth_token_ctx.set(auth_token)

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
            if user_email:
                span.set_attribute("user_id", user_email)

        # MCP is now managed per-tool in tools.py
        # Initialize Redis Publisher once
        publisher = None
        if RedisEventPublisher:
            try:
                publisher = RedisEventPublisher("Monitoring Agent", "Observability Specialist")
                _redis_publisher_ctx.set(publisher)
            except Exception as e:
                logger.error(f"Failed to initialize RedisEventPublisher: {e}")

        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"

        # Publish "Processing" event
        if _user_email_ctx.get():
            await _report_progress(f"Processing: {prompt[:50]}...", icon="🔍", display_type="toast")
                
            # Define run_once for fallback logic
            async def _run_once(app_instance):
                response_text = ""
                async with InMemoryRunner(app=app_instance) as runner:
                    uid = user_email or "default"
                    sid = session_id
                    
                    await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_monitoring_agent")
                    message = types.Content(parts=[types.Part(text=prompt)])

                    async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                        # Stream event via Publisher (Internal to ADK - not used here as mcp is tool-based)
                        pass

                        if hasattr(event, 'content') and event.content:
                            for part in event.content.parts:
                                if part.text: response_text += part.text
                return response_text if response_text else "No response generated."

            return await run_with_model_fallback(
                create_app_func=create_app,
                run_func=_run_once,
                context_name="Monitoring Agent"
            )
        finally:
            pass

    except Exception as e:
        return f"Error: {str(e)}"

def send_message(prompt: str, user_email: str = None, project_id: str = None, session_id: str = "default", auth_token: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id, session_id, auth_token))

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(send_message(" ".join(sys.argv[1:])))
    else:
        print("Usage: python agent.py <prompt>")
