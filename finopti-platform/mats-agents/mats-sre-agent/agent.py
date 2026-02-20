"""
MATS SRE Agent - Triage & Evidence Extraction
"""
import os
import sys
import json
import logging
import asyncio
from typing import Any

import requests
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
from tools import read_logs

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Observability
setup_observability()


# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_sre_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name="mats_sre_agent",
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[read_logs] 
    )


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def process_request(prompt_or_payload: Any, session_id: str = None, user_email: str = None, auth_token: str = None):
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
    project_id = None
    
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
                 project_id = data.get("project_id")
                 if not session_id:
                    session_id = data.get("session_id")
             else:
                 prompt = input_str
         except:
             prompt = input_str
             
    #  Set Env vars for tools to access context
    if job_id:
        os.environ["MATS_JOB_ID"] = job_id
    if orchestrator_url:
        os.environ["MATS_ORCHESTRATOR_URL"] = orchestrator_url
    if project_id:
        os.environ["GCP_PROJECT_ID"] = project_id
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        logger.info(f"Set SRE Project Context: {project_id}")
    
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
            pass
        os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = auth_token
        
    # Initialize Redis Publisher for this context
    try:
        if RedisEventPublisher:
            pub = RedisEventPublisher("MATS SRE", "SRE")
            _redis_publisher_ctx.set(pub)
            if session_id:
                _session_id_ctx.set(session_id)
                pub.publish_event(
                    session_id=session_id,
                    user_id=user_email or "sre",
                    trace_id="unknown",
                    msg_type="STATUS_UPDATE",
                    message=f"SRE starting analysis for: {prompt[:50]}...",
                    display_type="step_progress",
                    icon="🕵️"
                )
    except Exception as e:
        logger.warning(f"Failed to init Redis publisher: {e}")
    
    # Create child span linked to orchestrator's root span
    span_context = {"context": parent_ctx} if parent_ctx else {}
    
    with tracer.start_as_current_span(
        "sre_log_analysis",
        **span_context,
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
            "agent.name": "mats-sre",
            "agent.type": "triage"
        }
    ) as span:
        # Set session.id for Phoenix session grouping
        if session_id and span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            logger.info(f"[{session_id}] SRE: Set session.id on span")

        # Define helpers for fallback
        def _create_app(model_name: str):
            sre_agent_instance = create_sre_agent(model_name)
            return App(
                name="mats_sre_agent_app",
                root_agent=sre_agent_instance,
                plugins=[
                    ReflectAndRetryToolPlugin()
                ]
            )
            
        async def _run_once(app_instance):
            response_text = ""
            execution_trace = []
            try:
                async with InMemoryRunner(app=app_instance) as runner:
                    sid = session_id or "default"
                    current_user_email = user_email or _user_email_ctx.get() or "unknown"
                    await runner.session_service.create_session(session_id=sid, user_id=current_user_email, app_name="mats_sre_agent_app")
                    msg = types.Content(parts=[types.Part(text=prompt)])
                    
                    async for event in runner.run_async(user_id=current_user_email, session_id=sid, new_message=msg):
                        # Capture Trace Events
                        
                        # 1. Thought (Model generating plan)
                        if hasattr(event, 'content') and event.content:
                             for part in event.content.parts:
                                if part.text:
                                    response_text += part.text
                                    execution_trace.append({
                                        "type": "thought",
                                        "content": part.text[:200] + "..." if len(part.text) > 200 else part.text
                                    })
                                    # Also report thought to UI
                                    if job_id:
                                        await _report_progress(part.text[:200], "THOUGHT")
                                    
                        # 2. Tool Calls
                        if hasattr(event, 'tool_calls') and event.tool_calls:
                            for tc in event.tool_calls:
                                 execution_trace.append({
                                     "type": "tool_call",
                                     "tool": tc.function_name,
                                     "args": tc.args,
                                     "content": f"Calling {tc.function_name}"
                                 })
                                 
                        # Break infinite loops
                        execution_trace_count = len([e for e in execution_trace if e.get("type") in ["tool_call", "thought"]])
                        if execution_trace_count > 10:
                            logger.warning(f"Max turns exceeded ({execution_trace_count}). Forcing stop.")
                            response_text += "\\n[SYSTEM] Max execution turns exceeded. Stopping validation."
                            break
    
                        # 3. Tool Outputs
                        if hasattr(event, 'tool_outputs') and event.tool_outputs:
                             for to in event.tool_outputs:
                                 execution_trace.append({
                                     "type": "observation",
                                     "tool": to.function_name,
                                     "content": str(to.text_content)[:500]
                                 })
    
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Runner failed: {err_msg}")
                
                # Construct a JSON-friendly error response so Orchestrator doesn't crash on parsing
                error_json_response = json.dumps({
                    "status": "FAILURE",
                    "confidence": 0.0,
                    "evidence": {
                        "timestamp": "unknown",
                        "error_signature": "System Error",
                        "stack_trace": err_msg
                    },
                    "recommendations": ["Check agent logs for authentication or quota issues."]
                })
                response_text = error_json_response
                execution_trace.append({"type": "error", "content": err_msg})
                
                # Reraise 429 errors to trigger fallback
                if "429" in err_msg or "Resource exhausted" in err_msg:
                    raise e
            
            # check soft errors in response text
            if "429 Too Many Requests" in response_text or "Resource exhausted" in response_text:
                 raise RuntimeError(f"soft_429: {response_text}")

            # Fallback if empty
            if not response_text:
                response_text = "Analysis completed but no textual summary was generated. Check logs."
    
            return {
                "response": response_text,
                "execution_trace": execution_trace
            }

        # Execute with fallback logic
        return await run_with_model_fallback(
            create_app_func=_create_app,
            run_func=_run_once,
            context_name="MATS SRE Agent"
        )
