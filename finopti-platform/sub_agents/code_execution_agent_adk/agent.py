import os
import asyncio
import logging
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Add Redis Publisher
try:
    if str(Path(__file__).parent) not in sys.path:
        sys.path.append(str(Path(__file__).parent))

    from redis_common.redis_publisher import RedisEventPublisher
except ImportError as e:
    sys.path.append(str(Path(__file__).parent.parent.parent / "redis-sessions" / "common"))
    try:
        from redis_publisher import RedisEventPublisher
    except ImportError:
        RedisEventPublisher = None

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.adk.code_executors import BuiltInCodeExecutor
from google.genai import types
from google.cloud import secretmanager
# Plugins
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryLoggerConfig
)
from fixed_bq_plugin import FixedBigQueryPlugin
from config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name="finoptiagents-CodeExecutionAgent",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# --- CONTEXT ISOLATION & PROGRESS (Rule 1 & 6) ---
from contextvars import ContextVar
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

_session_id_ctx: ContextVar[str] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[str] = ContextVar("user_email", default=None)
_redis_publisher_ctx: ContextVar = ContextVar("redis_publisher", default=None)

def _report_progress(message, event_type="STATUS_UPDATE", icon="🤖", display_type="markdown", metadata=None):
    """Standardized progress reporting using context-bound session/user."""
    pub = _redis_publisher_ctx.get()
    sid = _session_id_ctx.get()
    uid = _user_email_ctx.get() or "unknown"
    if pub and sid:
        try:
            span_ctx = trace.get_current_span().get_span_context()
            trace_id_hex = format(span_ctx.trace_id, '032x') if span_ctx.trace_id else "unknown"
        except Exception:
            trace_id_hex = "unknown"
        pub.publish_event(
            session_id=sid, user_id=uid, trace_id=trace_id_hex,
            msg_type=event_type, message=message, display_type=display_type,
            icon=icon, metadata=metadata
        )

# Agent Configuration
APP_NAME = "code_execution_agent"
USER_ID = "finopti_user"
SESSION_ID = "session_code" 

# Setup Auth
if hasattr(config, "GOOGLE_API_KEY") and config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

# Load Manifest
manifest_path = Path(__file__).parent / "manifest.json"
manifest = {}
if manifest_path.exists():
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

# Load Instructions
instructions_path = Path(__file__).parent / "instructions.json"
if instructions_path.exists():
    with open(instructions_path, "r") as f:
        data = json.load(f)
        instruction_str = data.get("instruction", "You are a code execution agent.")
else:
    instruction_str = "You are a code execution agent."


# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

async def run_agent(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    """Run the agent with the given prompt."""
    # --- CONTEXT SETTING (Rule 1 & 6) ---
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email or "unknown")

    # Trace attribute setting (Rule 5)
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
        if user_email:
            span.set_attribute("user_id", user_email)
    
    def create_app(model_name: str = None):
        model_to_use = model_name or config.FINOPTIAGENTS_LLM
        
        # Re-initialize Agent/App per request to ensure fresh event loop binding
        local_code_agent = LlmAgent(
            name=manifest.get("agent_id", "code_execution_agent"),
            model=model_to_use,
            code_executor=BuiltInCodeExecutor(),
            instruction=instruction_str,
            description=manifest.get("description", "Executes Python code.")
        )
        
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
            name=APP_NAME,
            root_agent=local_code_agent,
            plugins=[bq_plugin]
        )

    # Initialize Redis Publisher once
    publisher = None
    if RedisEventPublisher:
            try:
                publisher = RedisEventPublisher(
                    agent_name="Code Execution Agent",
                    agent_role="Python Specialist"
                )
                _redis_publisher_ctx.set(publisher)
            except: pass

    # Publish "Processing" event via standardized helper
    _report_progress(f"Executing Python code...", icon="🐍", display_type="toast")

    try:
        async def _run_once(app_instance):
            final_response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                 sid = session_id
                 uid = user_email or USER_ID
                 await runner.session_service.create_session(
                    app_name=APP_NAME,
                    user_id=uid,
                    session_id=sid
                )
                 
                 content = types.Content(role='user', parts=[types.Part(text=prompt)])

                 # Run the agent
                 async for event in runner.run_async(
                    user_id=uid,
                    session_id=sid,
                    new_message=content
                 ):
                    # Stream Events
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
                        # Extract text from the final response
                        if event.content and event.content.parts:
                             for part in event.content.parts:
                                 if part.text:
                                     final_response_text = part.text
            
            return final_response_text if final_response_text else "No response generated by agent."

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="Code Execution Agent"
        )
        
    except Exception as e:
        logger.error(f"Error running agent: {str(e)}", exc_info=True)
        return f"Error running agent: {str(e)}"

def process_request(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    """Synchronous wrapper for run_agent."""
    return asyncio.run(run_agent(prompt, user_email, session_id))
