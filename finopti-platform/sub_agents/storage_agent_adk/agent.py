"""
Google Storage ADK Agent

This agent uses Google ADK to handle Cloud Storage interactions.
It integrates with the Google Storage MCP server (gcloud-mcp).
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
    list_objects, read_object_metadata, read_object_content, delete_object, 
    write_object, update_object_metadata, copy_object, move_object, 
    upload_object, download_object, list_buckets, create_bucket, 
    delete_bucket, get_bucket_metadata, update_bucket_labels, 
    get_bucket_location, view_iam_policy, check_iam_permissions, 
    get_metadata_table_schema, execute_insights_query, list_insights_configs,
    upload_file_from_local
)
from mcp_client import StorageMCPClient, _mcp_ctx

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
def create_storage_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=AGENT_NAME,
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[
            list_objects, read_object_metadata, read_object_content, delete_object, 
            write_object, update_object_metadata, copy_object, move_object, 
            upload_object, download_object, list_buckets, create_bucket, 
            delete_bucket, get_bucket_metadata, update_bucket_labels, 
            get_bucket_location, view_iam_policy, check_iam_permissions, 
            get_metadata_table_schema, execute_insights_query, list_insights_configs,
            upload_file_from_local
        ]
    )

def create_app(model_name: str = None):
    # Ensure API Key
    if hasattr(config, "GOOGLE_API_KEY") and config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    
    agent_instance = create_storage_agent(model_name)
    
    return App(
        name="finopti_storage_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3)
        ]
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

    # Initialize Client
    mcp = StorageMCPClient()
    token_reset = _mcp_ctx.set(mcp)

    # Initialize Redis Publisher
    publisher = None
    if RedisEventPublisher:
        try:
            publisher = RedisEventPublisher("Storage Agent", "Cloud Storage Specialist")
            _redis_publisher_ctx.set(publisher)
        except Exception as e:
            logger.error(f"Failed to initialize RedisEventPublisher: {e}")
    
    # Publish processing status
    await _report_progress(f"Processing storage request: {prompt[:50]}...", icon="📦", display_type="toast")
    
    try:
        await mcp.connect()

        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id
                uid = user_email or "default"
                await runner.session_service.create_session(
                    session_id=sid,
                    user_id=uid,
                    app_name="finopti_storage_agent"
                )
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
            context_name="Storage Agent"
        )
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, session_id))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(send_message(" ".join(sys.argv[1:])))
    else:
        print("Usage: python agent.py <prompt>")
