
"""
MATS Architect Agent - RCA Synthesis
"""
import os
import sys
import asyncio
import logging
import json
from typing import Any
from contextvars import ContextVar
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.adk.runners import InMemoryRunner
from google.genai import types

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing - Use same project as orchestrator for session grouping
tracer_provider = register(
    project_name="finoptiagents-MATS",  # MUST match orchestrator for proper session grouping
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
# Add Redis Common to path
sys.path.append('/app/redis_common')
try:
    from redis_publisher import RedisEventPublisher
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import config
if config.GOOGLE_API_KEY and not (config.GOOGLE_GENAI_USE_VERTEXAI and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"):
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    logger.info("Using API Key for authentication (Vertex AI disabled)")
else:
    if "GOOGLE_API_KEY" in os.environ:
        del os.environ["GOOGLE_API_KEY"]
    logger.info("Using ADC/Service Account for authentication (Vertex AI enabled)")


# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
import requests

def upload_rca_to_gcs(filename: str, content: str, bucket_name: str = "rca-reports-mats") -> str:
    """
    Uploads the RCA document to Google Cloud Storage via the Storage Agent.
    
    Args:
        filename: Name of the file (e.g., "rca-2024-01-01.md")
        content: The Markdown content of the RCA.
        bucket_name: Target GCS bucket name (default: "finopti-reports")
        
    Returns:
        The public URL or path of the uploaded file.
    """
    try:
        # Route via APISIX to Storage Agent
        url = f"{config.APISIX_URL}/agent/storage/execute"
        logger.info(f"Initiating RCA Upload to {bucket_name}/{filename} via {url}")

        
        # Robust prompt for Storage Agent
        prompt = (
            f"Please ensure the GCS bucket '{bucket_name}' exists (create it in location US if it doesn't). "
            f"Then, upload the following content as object '{filename}' to that bucket:\n\n{content}"
        )
        
        payload = {
            "prompt": prompt,
            "user_email": "mats-architect@system.local" 
        }

        # Inject Trace Headers
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            payload["headers"] = headers
        except ImportError:
            pass
        
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        
        # Extract response text if nested (ADK pattern)
        if isinstance(data, dict) and "response" in data:
            try:
                # The prompt execution might return a JSON string in 'response'
                inner_data = json.loads(data["response"])
                if isinstance(inner_data, dict) and "signed_url" in inner_data:
                    return f"RCA Uploaded. Secure Link: {inner_data['signed_url']}"
            except:
                pass
            return f"RCA Uploaded. Details: {data['response']}"
            
        return f"Upload requested. Response: {data}"
    except Exception as e:
        return f"Failed to upload RCA: {e}"

def write_object(bucket: str, path: str, content: str) -> str:
    """
    Shim for legacy/hallucinated write_object calls. Redirects to upload_rca_to_gcs.
    """
    logging.warning("LLM called write_object (shim). Redirecting to upload_rca_to_gcs.")
    # Map arguments
    return upload_rca_to_gcs(filename=path, content=content, bucket_name=bucket)

def update_bucket_labels(bucket_name: str, labels: dict) -> str:
    """
    Shim for hallucinated update_bucket_labels calls.
    """
    logging.warning(f"LLM called update_bucket_labels (shim) for {bucket_name}. Ignoring.")
    return "Bucket labels updated (shim)."


# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
def create_architect_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name="mats_architect_agent",
        model=model_to_use,
        description="Principal Software Architect.",
        instruction="""
    Your job is to synthesize technical investigations into a formal Root Cause Analysis (RCA) document following the **RCA-Template-V1**.
    
    INPUTS: SRE Findings (Logs) + Investigator Findings (Code).
    
    ### RCA STRUCTURE (STRICT ADHERENCE REQUIRED):
    
    [Incident ID] - Autonomous Root Cause Analysis
    
    **Metadata (Auto-Generated)**
    - Incident ID: [incident_id]
    - Primary System: [impacted_service_name]
    - Detection Source: Google Cloud Observability
    - Agent Version: MATS-v1.0
    - Status: Pending Human Review
    
    **1. Executive Summary**
    *Directive: Summarize in <150 words. Focus on Primary Trigger and Ultimate Resolution.*
    
    **2. Impact & Scope Analysis**
    *Directive: Identify hard numbers from the investigation (error rates, resources affected).*
    
    **3. Autonomous Troubleshooting Timeline (UTC)**
    *Directive: Reconstruct timeline using ISO 8601. Map alert -> diagnosis -> action.*
    
    **4. Root Cause Analysis (The 5 Whys)**
    *Directive: Use logical chaining. Final Root Cause MUST be systemic (e.g. missing policy, leak).*
    
    **5. Technical Evidence & Logs**
    *Directive: Attach specific log snippets or trace IDs that confirmed the hypothesis.*
    
    **6. Autonomous Mitigation vs. Permanent Fixes**
    *Directive: Differentiate between Agent mitigation and Recommended Permanent Surgery.*
    
    **7. Agent Confidence Score & Reasoning**
    *Directive: Self-assess accuracy. If <80%, flag specific unknowns/assumptions.*
    
    ### CRITICAL INSTRUCTIONS: 
    1. **UPLOAD FIRST**: Use `upload_rca_to_gcs` to save the file.
       - Filename: `MATS-RCA-[[service_name]]-[[timestamp]].md`
       - Bucket: `rca-reports-mats`
    
    2. **JSON OUTPUT REQUIRED**: Your final response must be a JSON object containing:
       - `status`: SUCCESS
       - `confidence`: your score (0.0-1.0)
       - `rca_content`: the full markdown text following Template-V1
       - `rca_url`: the secure link returned by `upload_rca_to_gcs`
       - `limitations`: list
       - `recommendations`: list
    """,
    tools=[upload_rca_to_gcs, write_object, update_bucket_labels] 
    )


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
_redis_publisher_ctx: ContextVar["RedisEventPublisher"] = ContextVar("redis_publisher", default=None)
_session_id_ctx: ContextVar[str] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[str] = ContextVar("user_email", default=None)

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
    from opentelemetry import propagate, trace
    from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues
    
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
        # Initialize Observability (legacy FinOptiObservability still called for compatibility)
        try:
            from common.observability import FinOptiObservability
            FinOptiObservability.setup("mats-architect-agent")
            if trace_context:
                FinOptiObservability.middleware_extract_trace(trace_context)
        except ImportError:
             pass

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
            
            bq_plugin = BigQueryAgentAnalyticsPlugin(
                project_id=os.getenv("GCP_PROJECT_ID"),
                dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
                table_id=config.BQ_ANALYTICS_TABLE,
                config=BigQueryLoggerConfig(
                    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
                )
            )
            
            return App(
                name="mats_architect_app",
                root_agent=architect_agent_instance,
                plugins=[
                    ReflectAndRetryToolPlugin(),
                    bq_plugin
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
