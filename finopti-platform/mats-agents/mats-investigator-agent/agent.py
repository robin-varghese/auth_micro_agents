"""
MATS Investigator Agent - Code Analysis
"""
import os
import sys
import json
import logging
import time
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
from tools import read_file, search_code

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Observability
setup_observability()

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_investigator_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    logger.info(f"Creating Investigator agent with model: {model_to_use}")
    
    return Agent(
        name="mats_investigator_agent",
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[read_file, search_code] 
    )


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def process_request(prompt_or_payload: Any, session_id: str = None, user_email: str = None, auth_token: str = None):
    request_start = time.monotonic()

    # Ensure API Key state is consistent
    if config.GOOGLE_API_KEY and not (config.GOOGLE_GENAI_USE_VERTEXAI and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"):
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    else:
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
            
    # Force project ID into environment for Vertex AI auto-detection
    if config.GCP_PROJECT_ID:
        os.environ['GOOGLE_CLOUD_PROJECT'] = config.GCP_PROJECT_ID
        os.environ['GCP_PROJECT_ID'] = config.GCP_PROJECT_ID
        
    # Handle Dict or JSON string payload
    prompt = ""
    job_id = None
    orchestrator_url = None
    
    # Parse generic input
    if isinstance(prompt_or_payload, dict):
        prompt = prompt_or_payload.get("message", "")
        job_id = prompt_or_payload.get("job_id")
        orchestrator_url = prompt_or_payload.get("orchestrator_url")
        # Allow payload to override session_id if provided there
        if not session_id:
             session_id = prompt_or_payload.get("session_id")
    else:
         # Try to parse string as json just in case
         input_str = str(prompt_or_payload)
         try:
             data = json.loads(input_str)
             if isinstance(data, dict):
                 prompt = data.get("message", input_str)
                 job_id = data.get("job_id")
                 orchestrator_url = data.get("orchestrator_url")
                 if not session_id:
                    session_id = data.get("session_id")
             else:
                 prompt = input_str
         except (json.JSONDecodeError, TypeError):
             prompt = input_str
             
    # Set Env vars for tools to access context
    if job_id:
        os.environ["MATS_JOB_ID"] = job_id
    if orchestrator_url:
        os.environ["MATS_ORCHESTRATOR_URL"] = orchestrator_url

    # --- Trace Context Extraction ---
    trace_context = {}
    if isinstance(prompt_or_payload, dict):
        trace_context = prompt_or_payload.get("headers", {})
    elif isinstance(prompt_or_payload, str):
         try:
             d = json.loads(prompt_or_payload)
             if isinstance(d, dict):
                 trace_context = d.get("headers", {})
         except (json.JSONDecodeError, TypeError):
             pass

    # Extract parent trace context for span linking
    parent_ctx = propagate.extract(trace_context) if trace_context else None
    tracer = trace.get_tracer(__name__)
    
    # Extract user_email from payload if not already provided
    if not user_email and isinstance(prompt_or_payload, dict):
        user_email = prompt_or_payload.get("user_email")
    
    # Store user_email in ContextVar for _report_progress
    if user_email:
        _user_email_ctx.set(user_email)

    if auth_token:
        try:
            from context import _auth_token_ctx
            _auth_token_ctx.set(auth_token)
        except ImportError:
            logger.warning(f"[{session_id}] Investigator: _auth_token_ctx not available in context module")
        os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = auth_token

    current_user_email = user_email or _user_email_ctx.get() or "unknown"

    logger.info(
        f"[{session_id}] Investigator: process_request started | "
        f"user={current_user_email} | job_id={job_id} | "
        f"prompt_length={len(prompt)} chars | has_auth_token={bool(auth_token)}"
    )

    # Initialize Redis Publisher
    try:
        if RedisEventPublisher:
            pub = RedisEventPublisher("MATS Investigator", "Investigator")
            _redis_publisher_ctx.set(pub)
            if session_id:
                _session_id_ctx.set(session_id)
                pub.publish_event(
                    session_id=session_id, user_id=current_user_email, trace_id="unknown",
                    msg_type="STATUS_UPDATE", message="Investigator starting analysis...",
                    display_type="step_progress", icon="🕵️"
                )
                logger.info(f"[{session_id}] Investigator: Redis publisher initialized and notified")
    except Exception as redis_err:
        logger.warning(
            f"[{session_id}] Investigator: Redis publisher initialization failed — "
            f"progress updates will be unavailable | error={redis_err}",
            exc_info=True
        )
    
    # Create child span linked to orchestrator's root span
    span_context = {"context": parent_ctx} if parent_ctx else {}
    
    with tracer.start_as_current_span(
        "investigator_code_analysis",
        **span_context,
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
            "agent.name": "mats-investigator",
            "agent.type": "code_analysis"
        }
    ) as span:
        # Set session.id for Phoenix session grouping
        if session_id and span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            logger.info(f"[{session_id}] Investigator: Set session.id on OTel span")

        # Define helpers for fallback
        def _create_app(model_name: str):
            logger.info(f"[{session_id}] Investigator: Creating app with model={model_name}")
            investigator_agent_instance = create_investigator_agent(model_name)
            
            return App(
                name="mats_investigator_app",
                root_agent=investigator_agent_instance,
                plugins=[
                    ReflectAndRetryToolPlugin()
                ]
            )
            
        async def _run_once(app_instance):
            response_text = ""
            runner_start = time.monotonic()
            try:
                async with InMemoryRunner(app=app_instance) as runner:
                    sid = session_id or "default"
                    await runner.session_service.create_session(
                        session_id=sid, user_id=current_user_email, app_name="mats_investigator_app"
                    )
                    msg = types.Content(parts=[types.Part(text=prompt)])
                    
                    logger.info(f"[{session_id}] Investigator: InMemoryRunner started, dispatching to LLM")
                    event_count = 0
                    async for event in runner.run_async(user_id=current_user_email, session_id=sid, new_message=msg):
                        event_count += 1
                        if hasattr(event, 'content') and event.content:
                            for part in event.content.parts:
                                if part.text:
                                    response_text += part.text
                                    # Report thought to UI
                                    if job_id:
                                        await _report_progress(part.text[:200], "THOUGHT")

                    elapsed = time.monotonic() - runner_start
                    logger.info(
                        f"[{session_id}] Investigator: LLM run completed | "
                        f"events={event_count} | response_length={len(response_text)} chars | "
                        f"elapsed={elapsed:.1f}s"
                    )

            except Exception as e:
                elapsed = time.monotonic() - runner_start
                err_msg = str(e)
                logger.error(
                    f"[{session_id}] Investigator: InMemoryRunner failed after {elapsed:.1f}s | "
                    f"error_type={type(e).__name__} | error={err_msg}",
                    exc_info=True
                )
                # Return valid JSON even on error so caller can handle gracefully
                error_response = json.dumps({
                    "status": "INSUFFICIENT_DATA",
                    "confidence": 0.0,
                    "hypothesis": f"Investigator internal error ({type(e).__name__}): {err_msg}",
                    "blockers": ["Agent internal error during analysis"]
                })
                response_text = error_response
                if "429" in err_msg or "Resource exhausted" in err_msg:
                    logger.warning(f"[{session_id}] Investigator: Quota exhausted (429), will trigger model fallback")
                    raise e
            
             # Check for soft 429 in response text
            if "429 Too Many Requests" in response_text or "Resource exhausted" in response_text:
                 logger.warning(f"[{session_id}] Investigator: Soft 429 detected in response text, raising for model fallback")
                 raise RuntimeError(f"soft_429: {response_text}")

            return response_text

        # Execute with fallback logic
        result = await run_with_model_fallback(
            create_app_func=_create_app,
            run_func=_run_once,
            context_name="MATS Investigator Agent"
        )

        total_elapsed = time.monotonic() - request_start
        logger.info(
            f"[{session_id}] Investigator: process_request complete | "
            f"total_elapsed={total_elapsed:.1f}s | result_length={len(result) if result else 0} chars"
        )
        return result
