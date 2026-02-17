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
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.plugins import ReflectAndRetryToolPlugin

# Force Vertex AI if configured
if hasattr(config, "GOOGLE_GENAI_USE_VERTEXAI"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = str(config.GOOGLE_GENAI_USE_VERTEXAI)
if hasattr(config, "GCP_PROJECT_ID"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = config.GCP_PROJECT_ID
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
from routing import route_to_agent, chain_screenshot_upload, list_gcp_projects
from instructions import ORCHESTRATOR_INSTRUCTIONS, ORCHESTRATOR_DESCRIPTION
from context import get_session_context, update_session_context

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
        tools=[route_to_agent, get_session_context, update_session_context, list_gcp_projects]
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

        # --- NEW STATEFUL LOGIC ---
        # 1. Fetch Session Context from Redis
        context = await get_session_context(session_id)
        
        # 2. Detect intent
        target_agent = detect_intent(prompt)
        
        # 3. Check for Troubleshooting Flow Interactivity
        is_troubleshooting = target_agent in ["mats-orchestrator", "mats_orchestrator", "iam_verification_specialist"]
        
        # If we are in a troubleshooting flow, ensure context is gathered
        if is_troubleshooting:
            # Update context with current project_id if provided but missing in Redis
            if project_id and not context.get("project_id"):
                context["project_id"] = project_id
                await update_session_context(session_id, context)
            
            # Check for missing required fields
            required_fields = {
                "project_id": "GCP Project ID",
                "environment": "Environment (Production, Staging, Dev)",
                "application_name": "Application Name"
            }
            missing = [label for field, label in required_fields.items() if not context.get(field)]
            
            # Additional context for code-aware troubleshooting
            github_fields = {
                "repo_url": "GitHub Repository URL",
                "repo_branch": "Branch Name",
                "github_pat": "GitHub Personal Access Token"
            }
            # Only ask for GitHub if they haven't provided it and we are getting deeper
            # For now, let's keep it minimal for the first turn
            
            if missing:
                return {
                    "success": True,
                    "response": f"I'm ready to help with troubleshooting, but I need a few more details first. Could you please provide the following: **{', '.join(missing)}**?",
                    "orchestrator": {
                        "state": "COLLECTING_CONTEXT",
                        "missing": missing
                    }
                }
            
            # 4. Check IAM Permissions Status
            if context.get("iam_status") != "VERIFIED":
                target_agent = "iam_verification_specialist"
                # Refine prompt for IAM agent to be specific
                prompt = f"Verify my current permissions in project {context.get('project_id')}. I need to perform troubleshooting for {context.get('application_name')}."
                logger.info(f"Redirecting to {target_agent} because iam_status is {context.get('iam_status')}")

        # --- ROUTING EXECUTION ---
        if target_agent == "finopti_orchestrator":
             # Self-routing: Let the Orchestrator LLM handle the context update or clarification
             async def _run_once(app_instance):
                 async with InMemoryRunner(app=app_instance) as runner:
                     runner.auto_create_session = True
                     sid = session_id or "default"
                     uid = user_email or "unknown"
                     await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_orchestrator")
                     message = types.Content(parts=[types.Part(text=prompt)])
                     response_text = ""
                     async for event in runner.run_async(user_id=uid, session_id=sid, new_message=message):
                         if hasattr(event, 'content') and event.content and event.content.parts:
                             for part in event.content.parts:
                                 if part.text: response_text += part.text
                     return response_text if response_text else "No response generated."

             from common.model_resilience import run_with_model_fallback
             final_response = await run_with_model_fallback(
                 create_app_func=lambda m: create_app(), # Note: App factory should take model
                 run_func=_run_once,
                 context_name="Orchestrator"
             )
             
             return {
                 "success": True,
                 "response": final_response,
                 "orchestrator": {"target_agent": "self"}
             }

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
            project_id=context.get("project_id", project_id or config.GCP_PROJECT_ID),
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
