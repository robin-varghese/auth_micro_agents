"""
Cloud Run ADK Agent - Serverless Container Specialist
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
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
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
from tools import list_services, get_service, get_service_log, deploy_file_contents, list_projects, create_project
from mcp_client import CloudRunMCPClient, _mcp_ctx

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
def create_cloud_run_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=AGENT_NAME,
        model=model_to_use,
        description=AGENT_DESCRIPTION,
        instruction=AGENT_INSTRUCTIONS,
        tools=[
            list_services,
            get_service,
            get_service_log,
            list_projects,
            create_project,
            deploy_file_contents
        ]
    )

def create_bq_plugin():
    bq_config = BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    )
    
    return BigQueryAgentAnalyticsPlugin(
        project_id=config.GCP_PROJECT_ID,
        dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
        table_id=config.BQ_ANALYTICS_TABLE,
        config=bq_config
    )

def create_app(model_name: str = None):
    # Ensure API Key
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    
    agent_instance = create_cloud_run_agent(model_name)

    return App(
        name="finopti_cloud_run_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3),
            create_bq_plugin()
        ]
    )

# Limit concurrency
_concurrency_sem = asyncio.Semaphore(5)

async def send_message_async(prompt: str, user_email: str = None, session_id: str = "default", auth_token: str = None) -> str:
    async with _concurrency_sem:
        # --- CONTEXT SETTING ---
        _session_id_ctx.set(session_id)
        _user_email_ctx.set(user_email or "unknown")
        if auth_token:
            # [Rule 7] Sync to environment for tool stability
            os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"] = auth_token

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
            if user_email:
                span.set_attribute("user_id", user_email)

        # MCP Client
        mcp = CloudRunMCPClient()
        token_reset = _mcp_ctx.set(mcp)

        # Redis Publisher
        publisher = None
        if RedisEventPublisher:
            try:
                publisher = RedisEventPublisher("Cloud Run Agent", "Serverless Specialist")
                _redis_publisher_ctx.set(publisher)
            except: pass

        _report_progress(f"Managing Cloud Run...", icon="🏃", display_type="toast")
        
        try:
            await mcp.connect()
            
            async def _run_once(app_instance):
                bq_plugin = None
                for p in app_instance.plugins:
                    if isinstance(p, BigQueryAgentAnalyticsPlugin):
                        bq_plugin = p
                        break
                
                try:
                    async with InMemoryRunner(app=app_instance) as runner:
                        sid = session_id
                        uid = user_email or "default"
                        await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_cloud_run_agent")
                        message = types.Content(parts=[types.Part(text=prompt)])

                        response_text = ""
                        async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                            if publisher:
                                publisher.process_adk_event(event, session_id=sid, user_id=uid)
                            if hasattr(event, 'content') and event.content:
                                for part in event.content.parts:
                                    if part.text: response_text += part.text
                        return response_text
                finally:
                    # Clean up BQ Plugin
                    if bq_plugin:
                        try:
                            if hasattr(bq_plugin, 'client') and hasattr(bq_plugin.client, 'close'):
                                bq_plugin.client.close()
                            elif hasattr(bq_plugin, '_client') and hasattr(bq_plugin._client, 'close'):
                                bq_plugin._client.close()
                        except: pass

            return await run_with_model_fallback(
                create_app_func=create_app,
                run_func=_run_once,
                context_name="Cloud Run Agent"
            )
        finally:
            await mcp.close()
            _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None, session_id: str = "default", auth_token: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, session_id, auth_token))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(send_message(" ".join(sys.argv[1:])))
    else:
        print("Usage: python agent.py <prompt>")
