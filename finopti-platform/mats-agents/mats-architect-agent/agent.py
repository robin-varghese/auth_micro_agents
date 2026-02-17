"""
MATS Architect Agent - RCA Synthesis
"""
import os
import sys
import json
import logging
import asyncio
from typing import Any

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.runners import InMemoryRunner
from google.genai import types
from opentelemetry import trace, propagate
from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues

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
from instructions import AGENT_INSTRUCTIONS, AGENT_DESCRIPTION
from tools import upload_rca_to_gcs, write_object, update_bucket_labels

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Observability
setup_observability()


# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_architect_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name="mats_architect_agent",
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[upload_rca_to_gcs, write_object, update_bucket_labels] 
    )


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def process_request(prompt_or_payload: Any, session_id: str = None, user_email: str = None):
    # Handle Payload - extract prompt first
    prompt = ""
    if isinstance(prompt_or_payload, dict):
        prompt = prompt_or_payload.get("message", "")
    else:
        prompt = str(prompt_or_payload)
        try:
             d = json.loads(prompt)
             if isinstance(d, dict):
                 prompt = d.get("message", prompt)
        except: pass
    
    # --- Trace Context Extraction ---
    trace_context = {}
    if isinstance(prompt_or_payload, dict):
        trace_context = prompt_or_payload.get("headers", {})
    elif isinstance(prompt_or_payload, str):
         try:
             d = json.loads(prompt_or_payload)
             if isinstance(d, dict):
                 trace_context = d.get("headers", {})
         except: pass

    # Extract parent trace context for span linking
    parent_ctx = propagate.extract(trace_context) if trace_context else None
    tracer = trace.get_tracer(__name__)
    
    # Extract session_id and user_email from payload if not already provided
    if not session_id and isinstance(prompt_or_payload, dict):
        session_id = prompt_or_payload.get("session_id")
    if not user_email and isinstance(prompt_or_payload, dict):
        user_email = prompt_or_payload.get("user_email")
    
    # Store user_email in ContextVar for consistency
    if user_email:
        _user_email_ctx.set(user_email)

    # Initialize Redis Publisher
    try:
        if RedisEventPublisher:
            pub = RedisEventPublisher("MATS Architect", "Architect")
            _redis_publisher_ctx.set(pub)
            if session_id:
                _session_id_ctx.set(session_id)
                pub.publish_event(
                    session_id=session_id, user_id=user_email or "architect", trace_id="unknown",
                    msg_type="STATUS_UPDATE", message=f"Architect starting RCA synthesis...",
                    display_type="step_progress", icon="🏗️"
                )
    except: pass
    
    # Create child span linked to orchestrator's root span
    span_context = {"context": parent_ctx} if parent_ctx else {}
    
    with tracer.start_as_current_span(
        "architect_synthesis",
        **span_context,
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
            "agent.name": "mats-architect",
            "agent.type": "synthesis"
        }
    ) as span:
        # Set session.id for Phoenix session grouping
        if session_id and span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            logger.info(f"[{session_id}] Architect: Set session.id on span")

        if config.GOOGLE_API_KEY and not (config.GOOGLE_GENAI_USE_VERTEXAI and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"):
            os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
        else:
            if "GOOGLE_API_KEY" in os.environ:
                del os.environ["GOOGLE_API_KEY"]

        # Force project ID into environment for Vertex AI auto-detection
        if config.GCP_PROJECT_ID:
            os.environ['GOOGLE_CLOUD_PROJECT'] = config.GCP_PROJECT_ID
            os.environ['GCP_PROJECT_ID'] = config.GCP_PROJECT_ID
        

        # Define helpers for fallback
        def _create_app(model_name: str):
            architect_agent_instance = create_architect_agent(model_name)
            
            return App(
                name="mats_architect_app",
                root_agent=architect_agent_instance,
                plugins=[
                    ReflectAndRetryToolPlugin()
                ]
            )
            
        async def _run_once(app_instance):
            response_text = ""
            try:
                async with InMemoryRunner(app=app_instance) as runner:
                    sid = "default"
                    await runner.session_service.create_session(session_id=sid, user_id="user", app_name="mats_architect_app")
                    msg = types.Content(parts=[types.Part(text=prompt)])
                    
                    async for event in runner.run_async(user_id="user", session_id=sid, new_message=msg):
                        if hasattr(event, 'content') and event.content:
                            for part in event.content.parts:
                                if part.text:
                                    response_text += part.text
                                    # Report thought to Redis
                                    pub = _redis_publisher_ctx.get()
                                    sid = _session_id_ctx.get()
                                    if pub and sid:
                                        try:
                                            pub.publish_event(
                                                session_id=sid, user_id=user_email or "architect", trace_id="unknown",
                                                msg_type="THOUGHT", message=part.text[:200],
                                                display_type="markdown", icon="🧠"
                                            )
                                        except: pass
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Runner failed: {err_msg}")
                # Return valid JSON even on error
                error_response = json.dumps({
                    "status": "FAILURE",
                    "confidence": 0.0,
                    "rca_content": f"Architect internal error: {err_msg}",
                    "limitations": ["Agent internal error during synthesis"]
                })
                response_text = error_response
                if "429" in err_msg or "Resource exhausted" in err_msg:
                    raise e
            
             # Check for soft 429 in response text
            if "429 Too Many Requests" in response_text or "Resource exhausted" in response_text:
                 raise RuntimeError(f"soft_429: {response_text}")

            return response_text

        # Execute with fallback logic
        return await run_with_model_fallback(
            create_app_func=_create_app,
            run_func=_run_once,
            context_name="MATS Architect Agent"
        )
