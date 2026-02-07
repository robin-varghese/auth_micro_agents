
"""
MATS Architect Agent - RCA Synthesis
"""
import os
import sys
import asyncio
import logging
from typing import Any
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import config
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY


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
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return f"Upload requested. Response: {response.json()}"
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

architect_agent = Agent(
    name="mats_architect_agent",
    model=config.FINOPTIAGENTS_LLM,
    description="Principal Software Architect.",
    instruction="""
    You are a Principal Software Architect.
    Your job is to synthesize technical investigations into a formal Root Cause Analysis (RCA) document and recommend robust fixes.
    
    INPUTS: SRE Findings (Logs) + Investigator Findings (Code).
    
    OUTPUT FORMAT (Strictly Follow this Template):
    # Root Cause Analysis: [[Incident Title]]

    ## 1. Executive Summary
    [[One-sentence description of the outage and root cause.]]

    ## 2. Technical Context & Impact
    - **Affected Service**: [[service_name]]
    - **Impact Duration**: [[start_time]] to [[end_time]]
    - **User Impact**: [[describe_user_experience_failures]]

    ## 3. Timeline & Detection
    - **Detection Timestamp**: [[timestamp]]
    - **Detection Method**: [[how_was_it_found]]
    - **Affected Version**: [[version_hash]]
    - **Timeline**:
      - [[time]]: [[event]]
      - [[time]]: [[event]]

    ## 4. Root Cause (Technical Deep Dive)
    [[detailed_explanation_of_the_failure_mechanism]]

    ## 5. Remediation (Short Term)
    - **Action Taken**: [[what_fixed_it]]
    - **Code Fix**:
    ```[[language]]
    [[code_snippet]]
    ```

    ## 6. Prevention (Long Term)
    - **Architectural Change**: [[describe_structural_fix]]
    - **Testing**: [[new_test_case_to_prevent_regression]]
    - **Monitoring**: [[new_alert_rule]]

    ## 7. Agent Confidence Score
    - **Confidence Score**: [[0-100]]%
    - **Reasoning**: [[why_you_chose_this_score]]
    
    CRITICAL INSTRUCTIONS: 
    1. **UPLOAD FIRST**: Use `upload_rca_to_gcs` to save the file.
       - Filename: `MATS-RCA-[[service_name]]-[[timestamp]].md`
       - Bucket: `rca-reports-mats`
       - **DO NOT USE `write_object`**. Use ONLY `upload_rca_to_gcs`.
    
    2. **SHORT SUMMARY ONLY**: After uploading, your final response to the user MUST BE LESS THAN 10 LINES.
       - Output ONLY the "Executive Summary" and the GCS Link.
       - **ABSOLUTELY NO FULL RCA TEXT IN CHAT**. The system will truncate logic if you print the full text.
       - If you print the full RCA, the workflow fails.
    """,
    tools=[upload_rca_to_gcs, write_object, update_bucket_labels] 
)


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def process_request(prompt_or_payload: Any):
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
    
    # Extract session_id from payload for Phoenix session grouping
    session_id = None
    if isinstance(prompt_or_payload, dict):
        session_id = prompt_or_payload.get("session_id")
    
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

        # Ensure API Key is in environment
        if config.GOOGLE_API_KEY:
            os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
        
        bq_plugin = BigQueryAgentAnalyticsPlugin(
            project_id=os.getenv("GCP_PROJECT_ID"),
            dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
            table_id=config.BQ_ANALYTICS_TABLE,
            config=BigQueryLoggerConfig(
                enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
            )
        )

        app_instance = App(
            name="mats_architect_app",
            root_agent=architect_agent,
            plugins=[
                ReflectAndRetryToolPlugin(),
                bq_plugin
            ]
        )

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
        except Exception as e:
            response_text = f"Error: {e}"
        
        return response_text
