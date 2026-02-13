"""
MATS SRE Agent - Triage & Evidence Extraction

This agent uses Google ADK and directly executes `gcloud` commands via subprocess
to query logs, bypassing MCP server complexities.
"""
import os
import sys
import asyncio
import json
import logging
import subprocess
import shlex
import shutil
import datetime
from pathlib import Path
from typing import Dict, Any, List
from contextvars import ContextVar

import requests

# Add parent directory to path for shared imports if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
# Add Redis Common to path
sys.path.append('/app/redis_common')
try:
    from redis_publisher import RedisEventPublisher
except ImportError:
    pass

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

from config import config

# Initialize Phoenix tracing
tracer_provider = register(
    project_name="finoptiagents-MATS",  # Unified project for all MATS agents
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure API Key is in environment ONLY if not using Vertex AI
# Vertex AI requires ADC/OAuth tokens. API keys can cause 401 conflicts.
if config.GOOGLE_API_KEY and not (config.GOOGLE_GENAI_USE_VERTEXAI and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"):
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    logger.info("Using API Key for authentication (Vertex AI disabled)")
else:
    # Ensure it's NOT in env to force ADC for Vertex
    if "GOOGLE_API_KEY" in os.environ:
        del os.environ["GOOGLE_API_KEY"]
    logger.info("Using ADC/Service Account for authentication (Vertex AI enabled)")


# -------------------------------------------------------------------------
# GCLOUD CONFIG HELPER (Fix for Read-Only Filesystem)
# -------------------------------------------------------------------------
_gcloud_config_setup = False

def setup_gcloud_config():
    """Copy mounted gcloud config to writable temp location to avoid Read-Only errors"""
    global _gcloud_config_setup
    if _gcloud_config_setup:
        return

    src = "/root/.config/gcloud"
    dst = "/tmp/gcloud_config"
    
    if os.path.exists(dst):
        try:
            shutil.rmtree(dst)
        except Exception as e:
            logger.warning(f"Could not clear temp gcloud dir: {e}")
        
    if os.path.exists(src):
        try:
            logger.info(f"Copying gcloud config from {src} to {dst}")
            # ignore_dangling_symlinks=True to avoid crashing on broken symlinks (common in some docker volume mounts)
            shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns('*.lock'), dirs_exist_ok=True, ignore_dangling_symlinks=True)
            _gcloud_config_setup = True
        except Exception as e:
            logger.error(f"Failed to copy gcloud config: {e}")
            # Mark as setup anyway to prevent infinite retry loops in tool calls
            _gcloud_config_setup = True
    else:
        logger.warning(f"GCloud config source {src} not found. Proceeding without copying.")
        _gcloud_config_setup = True

# -------------------------------------------------------------------------
# PROGRESS HELPER (ASYNC)
# -------------------------------------------------------------------------
_redis_publisher_ctx: ContextVar["RedisEventPublisher"] = ContextVar("redis_publisher", default=None)
_session_id_ctx: ContextVar[str] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[str] = ContextVar("user_email", default=None)

async def _report_progress(message: str, event_type: str = "INFO"):
    """Helper to send progress to Orchestrator AND Redis"""
    job_id = os.environ.get("MATS_JOB_ID")
    orchestrator_url = os.environ.get("MATS_ORCHESTRATOR_URL", "http://mats-orchestrator:8084")
    
    # Redis Publishing
    publisher = _redis_publisher_ctx.get()
    session_id = _session_id_ctx.get()
    
    if publisher and session_id:
        try:
             # Map internal event types to Schema types
             # SRE uses: INFO, TOOL_USE, OBSERVATION, ERROR, THOUGHT
             msg_type_map = {
                 "INFO": "STATUS_UPDATE",
                 "TOOL_USE": "TOOL_CALL",
                 "OBSERVATION": "OBSERVATION", # Custom or INFO? Schema has output?
                 "ERROR": "ERROR",
                 "THOUGHT": "THOUGHT"
             }
             mapped_type = msg_type_map.get(event_type, "STATUS_UPDATE")
             
             # Icons
             icons = {
                 "INFO": "ℹ️", "TOOL_USE": "🛠️", "OBSERVATION": "👁️", 
                 "ERROR": "❌", "THOUGHT": "🧠"
             }
             
             publisher.publish_event(
                 session_id=session_id,
                 user_id=_user_email_ctx.get() or "sre_agent", # internal
                 trace_id="unknown", # TODO: Extract from context if possible
                 msg_type=mapped_type,
                 message=message,
                 display_type="markdown" if mapped_type == "THOUGHT" else "console_log",
                 icon=icons.get(event_type, "🤖")
             )
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")

    if not job_id:
        return

    try:
        # We need to run sync requests in executor to avoid blocking the loop
        # or use aiohttp. For now, simple run_in_executor with requests
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, 
            lambda: requests.post(
                f"{orchestrator_url}/jobs/{job_id}/events",
                json={
                    "type": event_type,
                    "message": message,
                    "source": "mats-sre-agent"
                },
                timeout=2
            )
        )
    except Exception as e:
        logger.warning(f"Failed to report progress: {e}")

# -------------------------------------------------------------------------
# ADK TOOLS
# -------------------------------------------------------------------------
async def read_logs(project_id: str, filter_str: str, hours_ago: int = 1) -> Dict[str, Any]:
    """
    Fetch logs from Cloud Logging using gcloud CLI.
    
    Args:
        project_id: GCP Project ID
        filter_str: Cloud Logging filter (e.g., 'severity=ERROR')
        hours_ago: How far back to search in hours
    """
    setup_gcloud_config()
    
    # Enforce Environment Project ID to prevent hallucinations
    env_project_id = os.environ.get("GCP_PROJECT_ID")
    if env_project_id and env_project_id != project_id:
        logger.warning(f"Agent attempted to query project '{project_id}' but is restricted to '{env_project_id}'. Overriding.")
    override_warning = ""
    if env_project_id and env_project_id != project_id:
        logger.warning(f"Agent attempted to query project '{project_id}' but is restricted to '{env_project_id}'. Overriding.")
        override_warning = f" [WARNING: Project '{project_id}' does not exist or is restricted. Query was executed against '{env_project_id}' instead.]"
        project_id = env_project_id

    await _report_progress(f"Querying Cloud Logging for project {project_id} (filter='{filter_str}')", "TOOL_USE")
    
    # Calculate timestamp
    cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(hours=hours_ago)
    time_str = cutoff_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Combine filter
    # Use parentheses to ensure precedence if filter_str has ORs
    full_filter = f'({filter_str}) AND timestamp >= "{time_str}"'
    
    cmd = [
        "gcloud", "logging", "read",
        full_filter,
        f"--project={project_id}",
        "--format=json",
        "--limit=20",
        "--order=desc" # Newest first
    ]
    
    # Prepare environment
    env = os.environ.copy()
    env["CLOUDSDK_CONFIG"] = "/tmp/gcloud_config"
    env["CLOUDSDK_CORE_DISABLE_FILE_LOGGING"] = "1"
    
    logger.info(f"Executing Log Query: {' '.join(cmd)}")
    
    try:
        # Run subprocess (blocking is acceptable here as we are in a thread/process for this request)
        # Using run_in_executor to avoid blocking the loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=60, # 60s timeout for log query
                env=env
            )
        )
        
        if result.returncode == 0:
            try:
                logs = json.loads(result.stdout)
                # Simplify logs to save context window
                simplified_logs = []
                for log in logs:
                    simplified_logs.append({
                        "timestamp": log.get("timestamp"),
                        "severity": log.get("severity"),
                        "textPayload": log.get("textPayload"),
                        "jsonPayload": log.get("jsonPayload"),
                        "protoPayload": log.get("protoPayload"), # Crucial for Audit Logs (IAM)
                        "resource": log.get("resource"),
                        "insertId": log.get("insertId")
                    })
                
                log_count = len(simplified_logs)
                await _report_progress(f"Found {log_count} relevant logs.", "OBSERVATION")
                await _report_progress(f"Found {log_count} relevant logs.", "OBSERVATION")
                return {"logs": simplified_logs, "count": log_count, "note": override_warning if override_warning else None}
            except json.JSONDecodeError:
                return {"error": "Failed to parse gcloud output JSON", "raw_output": result.stdout[:500]}
        else:
            await _report_progress(f"GCloud command failed: {result.stderr[:100]}", "ERROR")
            return {"error": f"gcloud failed: {result.stderr}"}

    except Exception as e:
        await _report_progress(f"Execution failed: {str(e)}", "ERROR")
        return {"error": f"Execution exception: {str(e)}"}


# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
def create_sre_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name="mats_sre_agent",
        model=model_to_use,
        description="Senior SRE responsible for triaging production incidents.",
        instruction="""
    You are a Senior Site Reliability Engineer (SRE).
    
    OPERATIONAL RULES:
    1. FILTER: Filter logs by `(severity=ERROR OR severity=WARNING)`.
    2. VERSIONING: Scan logs for 'git_commit_sha', 'image_tag' or 'version'.
    3. IAM/AUTH: Check `protoPayload` for 'Permission Denied', '403', or 'IAM' errors.
    4. EXECUTION STRATEGY: 
       - EXECUTE ALL NECESSARY QUERIES AUTONOMOUSLY.
       - DO NOT ASK FOR PERMISSION TO RUN QUERIES.
       - If a query yields 0 logs, assume no issue of that type exists and TRY THE NEXT hypothesis.
       - If you have checked logs, metrics, and IAM and found nothing, return `status="FAILURE"` with `error="Root Cause Not Found"`.
       - RETURN ONLY WHEN YOU HAVE A DEFINITIVE FINDING OR HAVE EXHAUSTED ALL CHECKS.
    
    OUTPUT JSON FORMAT:
    {
        "status": "SUCCESS|WAITING_FOR_APPROVAL|FAILURE", 
        "root_cause_found": true|false,
        "incident_timestamp": "...",
        "service_name": "...",
        "version_sha": "...",
        "error_signature": "...",
        "stack_trace_snippet": "...",
        "pending_steps": ["Step 4...", "Step 5..."]
    }

    AVAILABLE SUB-AGENT CAPABILITIES (For Context Only):
    - Monitoring & Observability Specialist: list_log_entries, list_log_names, list_buckets, list_views, list_sinks, list_log_scopes, list_metric_descriptors, list_time_series, list_alert_policies, list_traces, get_trace, list_group_stats
    - GCloud Specialist: run_gcloud_command
    - Cloud Run Specialist: list_services, get_service, get_service_log, deploy_file_contents, deploy_local_folder, list_projects, create_project
    """,
    tools=[read_logs] 
    )


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def process_request(prompt_or_payload: Any, session_id: str = None, user_email: str = None):
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
    from opentelemetry import propagate, trace
    from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues
    
    parent_ctx = propagate.extract(trace_context) if trace_context else None
    tracer = trace.get_tracer(__name__)
    
    # Extract user_email from payload if not already provided
    if not user_email and isinstance(prompt_or_payload, dict):
        user_email = prompt_or_payload.get("user_email")
    
    # Store user_email in ContextVar for _report_progress
    if user_email:
        _user_email_ctx.set(user_email)
        
    # Initialize Redis Publisher for this context
    try:
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
        # Plugins (BQ Disabled due to stability issues)
        # bq_plugin = BigQueryAgentAnalyticsPlugin(...)


        # Plugins (BQ Disabled due to stability issues)
        # bq_plugin = BigQueryAgentAnalyticsPlugin(...)

        # Define helpers for fallback
        def _create_app(model_name: str):
            sre_agent_instance = create_sre_agent(model_name)
            return App(
                name="mats_sre_agent_app",
                root_agent=sre_agent_instance,
                plugins=[
                    ReflectAndRetryToolPlugin()
                    # bq_plugin
                ]
            )
            
        async def _run_once(app_instance):
            response_text = ""
            execution_trace = []
            try:
                async with InMemoryRunner(app=app_instance) as runner:
                    sid = "default"
                    await runner.session_service.create_session(session_id=sid, user_id="user", app_name="mats_sre_agent_app")
                    msg = types.Content(parts=[types.Part(text=prompt)])
                    
                    async for event in runner.run_async(user_id="user", session_id=sid, new_message=msg):
                        # Capture Trace Events
                        # Note: The structure of 'event' depends on Google ADK version, assuming standard patterns
                        
                        # 1. Thought (Model generating plan) - often mapped to 'model_response' before tool calls
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
                        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
