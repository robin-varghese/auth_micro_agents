import os
import sys
import asyncio
import logging
from pathlib import Path
from contextvars import ContextVar

# Add project root to path for config
sys.path.append(str(Path(__file__).parent.parent.parent))
from config import config

# Set project-wide Vertex AI preference
if hasattr(config, "GOOGLE_GENAI_USE_VERTEXAI"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = str(config.GOOGLE_GENAI_USE_VERTEXAI)
if hasattr(config, "GCP_PROJECT_ID"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = config.GCP_PROJECT_ID

# ADK Imports
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types
from opentelemetry import trace

# Module Imports
from observability import setup_observability
from context import (
    _redis_publisher_ctx, 
    _session_id_ctx, 
    _user_email_ctx, 
    _auth_token_ctx,
    _report_progress,
    RedisEventPublisher
)
from instructions import AGENT_INSTRUCTIONS, AGENT_NAME, AGENT_DESCRIPTION
from tools import check_gcp_permissions, generate_iam_remediation

# 1. Setup Observability
setup_observability()

logger = logging.getLogger(__name__)

# 2. Define Agent
def create_iam_agent(model_name=None):
    return Agent(
        name=AGENT_NAME,
        model=model_name or config.FINOPTIAGENTS_LLM,
        instruction=AGENT_INSTRUCTIONS,
        tools=[check_gcp_permissions, generate_iam_remediation]
    )

# 3. Define App
def create_app(model_name=None):
    return App(
        name="iam_verification_specialist",
        root_agent=create_iam_agent(model_name),
        plugins=[]
    )

# 4. Request Handler
async def process_request(prompt: str, user_email: str = None, session_id: str = "default", project_id: str = None, auth_token: str = None):
    # Context Propagation
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email)
    if auth_token:
        _auth_token_ctx.set(auth_token)
    
    # Setup Redis Publisher if available
    pub = None
    if RedisEventPublisher and session_id:
        try:
            pub = RedisEventPublisher("IAMAgent", "Security Auditor")
            _redis_publisher_ctx.set(pub)
        except Exception as e:
            logger.warning(f"Could not init Redis publisher: {e}")

    await _report_progress(f"Received request: {prompt[:50]}...", icon="🛡️")

    # Define the run function for fallback logic
    async def _run_once(app_instance):
        async with InMemoryRunner(app=app_instance) as runner:
            runner.auto_create_session = True
            sid = session_id or "default"
            uid = user_email or "unknown"
            
            # Ensure session is created in ADK
            await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="iam_verification_specialist")
            
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""

            async for event in runner.run_async(user_id=uid, session_id=sid, new_message=message):
                if pub:
                    # Optional: process ADK event for Redis if publisher supports it
                    # pub.process_adk_event(event, session_id=sid, user_id=uid)
                    pass

                if hasattr(event, 'content') and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
            
            return response_text if response_text else "No response generated."

    from common.model_resilience import run_with_model_fallback
    return await run_with_model_fallback(
        create_app_func=create_app,
        run_func=_run_once,
        context_name="IAM Agent"
    )
