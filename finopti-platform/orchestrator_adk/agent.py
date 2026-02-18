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

from google.auth import jwt
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.plugins import ReflectAndRetryToolPlugin

from config import config

# Force Vertex AI if configured
if hasattr(config, "GOOGLE_GENAI_USE_VERTEXAI"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = str(config.GOOGLE_GENAI_USE_VERTEXAI)
if hasattr(config, "GCP_PROJECT_ID"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = config.GCP_PROJECT_ID

from opentelemetry import trace
from opentelemetry.semconv.trace import SpanAttributes

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
def create_app(session_id: Optional[str] = None):
    """Factory to create loop-safe App and Agent instances."""
    # Ensure API Key is in environment for GenAI library
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    # [FIX] Wrapper to prevent LLM from hallucinating session ID (e.g. using email)
    async def save_context_to_session(context: Dict[str, Any]):
        """
        Save/Update key-value context to the current user session.
        Use this to store project_id, environment, application_name, etc.
        """
        if session_id:
            await update_session_context(session_id, context)
        else:
            logger.warning("save_context_to_session called but no session_id bound.")

    # Create Orchestrator Agent (Rule 8: Move locally)
    orchestrator_agent = Agent(
        name="finopti_orchestrator",
        model=config.FINOPTIAGENTS_LLM,
        description=ORCHESTRATOR_DESCRIPTION,
        instruction=ORCHESTRATOR_INSTRUCTIONS,
        tools=[route_to_agent, get_session_context, save_context_to_session, list_gcp_projects]
    )

    # Create the App
    return App(
        name="finopti_orchestrator",
        root_agent=orchestrator_agent,
        plugins=[
            ReflectAndRetryToolPlugin(
                max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "3")),
                throw_exception_if_retry_exceeded=os.getenv("REFLECT_RETRY_THROW_ON_FAIL", "true").lower() == "true"
            )
        ]
    )


async def process_request_async(
    prompt: str,
    user_email: str,
    project_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    # ... (existing trace logic)

    try:
        # --- NEW STATEFUL LOGIC ---
        # 1. Fetch Session Context from Redis
        context = await get_session_context(session_id)
        
        # [NEW] Extract User Details from OAuth Token
        if auth_token and auth_token.startswith("Bearer "):
            try:
                token = auth_token.split(" ")[1]
                # Decode without verification (trusted internal service, verification done at Gateway/UI)
                decoded = jwt.decode(token, verify=False)
                
                # Update context with available fields
                updates = {}
                if "name" in decoded and not context.get("user_name"):
                    updates["user_name"] = decoded["name"]
                if "picture" in decoded and not context.get("user_picture"):
                    updates["user_picture"] = decoded["picture"]
                if "email" in decoded and not context.get("user_email"):
                    updates["user_email"] = decoded["email"]
                    
                if updates:
                    logger.info(f"Enriched context from OAuth token: {list(updates.keys())}")
                    context.update(updates)
                    await update_session_context(session_id, context)
            except Exception as e:
                logger.warning(f"Failed to decode OAuth token for context enrichment: {e}")
        
        # [NEW] Extract User Details from OAuth Token
        if auth_token and auth_token.startswith("Bearer "):
            try:
                token = auth_token.split(" ")[1]
                # Decode without verification (trusted internal service, verification done at Gateway/UI)
                decoded = jwt.decode(token, verify=False)
                
                # Update context with available fields
                updates = {}
                if "name" in decoded and not context.get("user_name"):
                    updates["user_name"] = decoded["name"]
                if "picture" in decoded and not context.get("user_picture"):
                    updates["user_picture"] = decoded["picture"]
                if "email" in decoded and not context.get("user_email"):
                    updates["user_email"] = decoded["email"]
                    
                if updates:
                    logger.info(f"Enriched context from OAuth token: {list(updates.keys())}")
                    context.update(updates)
                    await update_session_context(session_id, context)
            except Exception as e:
                logger.warning(f"Failed to decode OAuth token for context enrichment: {e}")

        # 2. Detect intent
        target_agent = detect_intent(prompt)

        
        # 3. Check for Troubleshooting Flow Interactivity
        is_troubleshooting = target_agent in ["mats-orchestrator", "mats_orchestrator", "iam_verification_specialist"]

        # [FIX] Sticky Routing: If we have troubleshooting context, don't fall back to generic gcloud agent
        has_context = bool(context.get('project_id') or context.get('application_name'))
        if has_context and target_agent == "gcloud_infrastructure_specialist":
            # Check if it's a specific gcloud command (simple heuristic or trust detect_intent's specific match)
            # Since detect_intent returns gcloud as fallback (score 0), we override it here.
            logger.info("Sticky Context: Overriding 'gcloud' default to 'mats-orchestrator'")
            target_agent = "mats-orchestrator"
            is_troubleshooting = True

        # If we are in a troubleshooting flow, ensure context is gathered
        if is_troubleshooting:
            # Update context with current request metadata if missing in Redis
            updates = {}
            if project_id and not context.get("project_id"): 
                updates["project_id"] = project_id
            if user_email and not context.get("user_email"): 
                updates["user_email"] = user_email
            
            if updates:
                context.update(updates)
                await update_session_context(session_id, context)
            
            # Check for missing required fields
            required_fields = {
                "project_id": "GCP Project ID",
                "environment": "Environment (Production, Staging, Dev)",
                "application_name": "Application Name"
            }
            missing = [label for field, label in required_fields.items() if not context.get(field)]
            
            # If fields are missing, DON'T return error immediately.
            # Route to finopti_orchestrator (LLM) to:
            # 1. Parse the *current* prompt (which might contain the missing info)
            # 2. Update context
            # 3. Ask for remaining items
            if missing:
                logger.info(f"Context missing {missing}. Routing to Orchestrator LLM to parse/prompt.")
                target_agent = "finopti_orchestrator"
                # Fall through to 'finopti_orchestrator' block below
            
            else:
                # Context is full. Check IAM Permissions Status
                if context.get("iam_status") != "VERIFIED":
                    target_agent = "iam_verification_specialist"
                    # Refine prompt for IAM agent to be specific
                    prompt = f"Verify permissions for user {user_email} in project {context.get('project_id')}. I need to perform troubleshooting for {context.get('application_name')}."
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
                     
                     # [FIX] Explicitly inject User Email into system context for the LLM
                     full_prompt = prompt
                     if uid and "unknown" not in uid:
                         full_prompt += f"\n\n[System Context] User Email: {uid}"
                     
                     message = types.Content(parts=[types.Part(text=full_prompt)])
                     response_text = ""
                     async for event in runner.run_async(user_id=uid, session_id=sid, new_message=message):
                         if hasattr(event, 'content') and event.content and event.content.parts:
                             for part in event.content.parts:
                                 if part.text: response_text += part.text
                     return response_text if response_text else "No response generated."

             from common.model_resilience import run_with_model_fallback
             final_response = await run_with_model_fallback(
                 create_app_func=lambda m: create_app(session_id=session_id), # Note: App factory should take model
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
