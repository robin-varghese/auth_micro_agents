"""
Orchestrator ADK Agent - Central Hub with Intelligent Routing
"""

import os
import sys
import asyncio
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from opentelemetry import trace
from opentelemetry.semconv.trace import SpanAttributes

from config import config

# --- Refactored Modules ---
from observability import setup_observability
from context import (
    _session_id_ctx, 
    _user_email_ctx, 
    _redis_publisher_ctx, 
    _report_progress,
    RedisEventPublisher
)
from registry import load_registry
from intent import detect_intent
from auth import check_opa_authorization
from routing import route_to_agent, chain_screenshot_upload
from instructions import ORCHESTRATOR_INSTRUCTIONS, ORCHESTRATOR_DESCRIPTION

logger = logging.getLogger(__name__)

# Initialize tracing
setup_observability()


# --- App Factory ---
def create_app():
    """Factory to create loop-safe App and Agent instances."""
    # Ensure API Key is in environment for GenAI library
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    # Create Orchestrator Agent (Rule 8: Move locally)
    orchestrator_agent = Agent(
        name="finopti_orchestrator",
        model=config.FINOPTIAGENTS_LLM,
        description=ORCHESTRATOR_DESCRIPTION,
        instruction=ORCHESTRATOR_INSTRUCTIONS,
        tools=[route_to_agent]
    )

    # Configure BigQuery Analytics Plugin
    bq_config = BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true"
    )

    bq_plugin = BigQueryAgentAnalyticsPlugin(
        project_id=config.GCP_PROJECT_ID,
        dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
        table_id=config.BQ_ANALYTICS_TABLE,
        config=bq_config,
        location="US"
    )

    # Create the App
    return App(
        name="finopti_orchestrator",
        root_agent=orchestrator_agent,
        plugins=[
            ReflectAndRetryToolPlugin(
                max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "3")),
                throw_exception_if_retry_exceeded=os.getenv("REFLECT_RETRY_THROW_ON_FAIL", "true").lower() == "true"
            ),
            bq_plugin
        ]
    )


async def process_request_async(
    prompt: str,
    user_email: str,
    project_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a user request through the orchestrator
    
    Args:
        prompt: User's natural language request
        user_email: User's email address
        project_id: Optional GCP project ID
        auth_token: Optional OAuth token
        session_id: Optional ADK Session ID
    
    Returns:
        Dictionary with response and metadata
    """
    try:
        # --- CONTEXT SETTING ---
        _session_id_ctx.set(session_id)
        _user_email_ctx.set(user_email or "unknown")

        # Trace attribute setting
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
            if user_email:
                span.set_attribute("user_id", user_email)

        # Create App per request
        app = create_app()

        # Detect intent
        target_agent = detect_intent(prompt)
        
        # Check authorization via OPA
        authz_result = check_opa_authorization(user_email, target_agent)
        
        if not authz_result.get('allow', False):
            return {
                "error": True,
                "message": f"403 Unauthorized: {authz_result.get('reason', 'Access denied')}",
                "user_email": user_email,
                "target_agent": target_agent,
                "authorized": False
            }
        
        # Route to agent
        agent_response = await route_to_agent(
            target_agent=target_agent,
            prompt=prompt,
            user_email=user_email,
            project_id=project_id or config.GCP_PROJECT_ID,
            auth_token=auth_token,
            session_id=session_id
        )
        
        # Publish routing event
        if RedisEventPublisher and session_id:
            try:
                pub = RedisEventPublisher("Orchestrator", "System Coordinator")
                _redis_publisher_ctx.set(pub)
                await _report_progress(f"Routing request to {target_agent}...", event_type="STATUS_UPDATE", icon="🔀", display_type="step_progress")
            except Exception: pass
        
        # Propagate error if present
        if not agent_response.get('success', False):
            error_msg = agent_response.get('error', 'Unknown sub-agent error')
            return {
                "error": True,
                "message": f"Agent {target_agent} failed: {error_msg}",
                "orchestrator": {
                    "user_email": user_email,
                    "target_agent": target_agent,
                    "authorized": True
                }
            }

        # Handle Screenshot Chaining
        if target_agent == "browser_automation_specialist":
            agent_response = await chain_screenshot_upload(
                agent_response,
                user_email=user_email,
                project_id=project_id or config.GCP_PROJECT_ID,
                auth_token=auth_token,
                session_id=session_id
            )

        # Extract final text
        response_data = agent_response.get('data', {})
        final_response = response_data
        if isinstance(response_data, dict):
            if 'response' in response_data:
                final_response = response_data['response']
                if isinstance(final_response, dict) and 'response' in final_response:
                    final_response = final_response['response']

        return {
            "success": True,
            "response": final_response,
            "orchestrator": {
                "target_agent": target_agent
            }
        }
    
    except Exception as e:
        logger.error(f"Orchestrator error: {str(e)}", exc_info=True)
        return {
            "error": True,
            "message": f"Orchestrator error: {str(e)}"
        }


def process_request(
    prompt: str,
    user_email: str,
    project_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronous wrapper for process_request_async
    """
    return asyncio.run(process_request_async(prompt, user_email, project_id, auth_token, session_id))


if __name__ == "__main__":
    # Test the orchestrator
    import sys
    
    if len(sys.argv) > 2:
        user_email = sys.argv[1]
        prompt = " ".join(sys.argv[2:])
        
        print(f"User: {user_email}")
        print(f"Prompt: {prompt}")
        print("=" * 50)
        
        # Load registry for test
        print(f"Loading registry... {len(load_registry())} agents found.")
        
        # When running locally on host, override OPA_URL if needed
        # (This logic is simplified for the test block)
        
        print("Running process_request...")
        result = process_request(prompt, user_email)
        print("Result:")
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python agent.py <email> <prompt>")
