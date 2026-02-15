"""
Code Execution ADK Agent

This agent uses Google ADK to execute Python code.
It uses the NATIVE BuiltInCodeExecutor provided by ADK (Pattern B).
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from contextvars import ContextVar

# Ensure parent path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.adk.code_executors import BuiltInCodeExecutor
from google.genai import types
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

from config import config

# Plugins
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryLoggerConfig
)
from fixed_bq_plugin import FixedBigQueryPlugin


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
def create_code_agent(model_name: str = None) -> LlmAgent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM

    return LlmAgent(
        name=AGENT_NAME,
        model=model_to_use,
        code_executor=BuiltInCodeExecutor(),
        instruction=AGENT_INSTRUCTIONS,
        description=AGENT_DESCRIPTION
    )

def create_app(model_name: str = None):
    # Ensure API Key
    if hasattr(config, "GOOGLE_API_KEY") and config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    agent_instance = create_code_agent(model_name)

    # Initialize BigQuery Plugin locally
    bq_config = BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    )
    bq_plugin = FixedBigQueryPlugin(
        config=bq_config,
        project_id=config.GCP_PROJECT_ID,
        dataset_id=os.getenv("BIGQUERY_DATASET_ID", "finoptiagents"),
        table_id=os.getenv("BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID", "agent_analytics_log")
    )

    return App(
        name="finopti_code_execution_agent",
        root_agent=agent_instance,
        plugins=[bq_plugin]
    )

async def send_message_async(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    # --- CONTEXT SETTING ---
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email or "unknown")

    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
        if user_email:
            span.set_attribute("user_id", user_email)

    # Initialize Redis Publisher
    publisher = None
    if RedisEventPublisher:
         try:
             publisher = RedisEventPublisher("Code Execution Agent", "Python Specialist")
             _redis_publisher_ctx.set(publisher)
         except Exception as e:
             logger.warning(f"Failed to initialize RedisEventPublisher: {e}")

    # Publish "Processing" event
    _report_progress(f"Executing Python code...", icon="🐍", display_type="toast")
    
    try:
        async def _run_once(app_instance):
            final_response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id
                uid = user_email or "default"
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_code_execution_agent")
                message = types.Content(parts=[types.Part(text=prompt)])

                async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                    if publisher:
                        publisher.process_adk_event(event, session_id=sid, user_id=uid)
                    
                    # Check for executable code parts for logging
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.executable_code:
                                logger.info(f"Agent generated code:\n{part.executable_code.code}")
                            elif part.code_execution_result:
                                logger.info(f"Code output: {part.code_execution_result.output}")

                    if event.is_final_response():
                        if event.content and event.content.parts:
                             for part in event.content.parts:
                                 if part.text:
                                     final_response_text = part.text
            
            return final_response_text if final_response_text else "No response generated."

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="Code Execution Agent"
        )
    finally:
        pass

def send_message(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, session_id))

def process_request(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    """Synchronous wrapper for run_agent."""
    return send_message(prompt, user_email, session_id)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(send_message(" ".join(sys.argv[1:])))
    else:
        print("Usage: python agent.py <prompt>")
