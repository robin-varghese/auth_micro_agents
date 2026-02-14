"""
MATS Orchestrator - Plan Generation

Extracted from agent.py per REFACTORING_GUIDELINE.md (Step 3).
Contains the investigation plan generation logic with model fallback
and the agent registry loader.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from config import config

logger = logging.getLogger(__name__)


def load_agent_registry() -> list:
    """Load agent registry from JSON file."""
    registry_path = Path(__file__).parent / "agent_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            return json.load(f)
    return []


def _normalize_plan(plan, user_request: str) -> Dict[str, Any]:
    """Normalize plan output from LLM (handles list/dict variants).
    
    Small models sometimes return a list instead of a dict.
    This handles all known edge cases.
    """
    if isinstance(plan, dict):
        return plan  # Already correct format
    
    if isinstance(plan, list):
        logger.warning(f"Plan generation returned a list, attempting to wrap: {str(plan)[:100]}...")
        if len(plan) > 0 and isinstance(plan[0], dict):
            # Case 1: List of steps
            if "step_id" in plan[0]:
                return {
                    "plan_id": "auto-generated",
                    "reasoning": "Model returned raw list of steps",
                    "steps": plan
                }
            # Case 2: List containing the plan object
            elif "steps" in plan[0]:
                return plan[0]
            else:
                return {
                    "plan_id": "fallback-list",
                    "reasoning": "Model returned unrecognized list format",
                    "steps": [
                        {"step_id": 1, "assigned_lead": "sre", "task": f"Analyze logs: {user_request}", "ui_label": "Investigating"}
                    ]
                }
        else:
            return {
                "plan_id": "fallback-empty",
                "reasoning": "Model returned empty/invalid list",
                "steps": [
                    {"step_id": 1, "assigned_lead": "sre", "task": f"Analyze logs: {user_request}", "ui_label": "Investigating"}
                ]
            }
    
    # Unknown type
    return _fallback_plan(user_request, "Unknown plan format")


def _fallback_plan(user_request: str, reason: str = "planning error") -> Dict[str, Any]:
    """Generate a safe fallback 3-step plan."""
    return {
        "plan_id": "fallback-001",
        "reasoning": f"Using default 3-step investigation due to {reason}",
        "steps": [
            {"step_id": 1, "assigned_lead": "sre", "task": f"Analyze logs for: {user_request}", "ui_label": "Investigating Logs"},
            {"step_id": 2, "assigned_lead": "investigator", "task": "Analyze code", "ui_label": "Analyzing Code"},
            {"step_id": 3, "assigned_lead": "architect", "task": "Generate RCA", "ui_label": "Generating RCA"}
        ]
    }


async def generate_plan(user_request: str, agent_registry: list) -> Dict[str, Any]:
    """
    Generate investigation plan using LLM directly (Bypassing MCP tool to avoid schema errors).
    
    Args:
        user_request: User's problem description
        agent_registry: List of available agents/capabilities
        
    Returns:
        Plan with reasoning and steps
    """
    # Format agent registry for context
    capabilities_summary = "\n".join([
        f"- {agent['name']}: {agent.get('capabilities', 'N/A')}"
        for agent in agent_registry
    ])
    
    prompt = f"""
    You are a Principal SRE Investigator planning a troubleshooting session.
    
    USER REQUEST: {user_request}
    
    AVAILABLE CAPABILITIES:
    {capabilities_summary}
    
    Create a step-by-step investigation plan. Your plan should:
    1. Start with log/metric triage (SRE)
    2. Move to code analysis (Investigator)
    3. End with RCA synthesis (Architect)
    
    Think through the approach carefully and output a JSON plan with:
    - plan_id
    - reasoning (why this approach)
    - steps (array of {{step_id, assigned_lead, task, ui_label}})
    """
    
    try:
        from google import genai
        # Re-verify API key availability for this client
        api_key = None
        if config.GOOGLE_API_KEY and not (config.GOOGLE_GENAI_USE_VERTEXAI and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"):
            api_key = config.GOOGLE_API_KEY
            
        client = genai.Client(api_key=api_key)
        
        logger.info(f"Generating plan. Primary model: {config.FINOPTIAGENTS_LLM}")
        
        response = None
        last_error = None
        
        # Use fallback list or default to single model if list missing
        model_list = getattr(config, "FINOPTIAGENTS_MODEL_LIST", [config.FINOPTIAGENTS_LLM])
        
        for model_name in model_list:
            try:
                logger.info(f"Attempting plan generation with model: {model_name}")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                logger.info(f"Plan generation successful with model: {model_name}")
                break  # Success
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "Resource exhausted" in err_msg or "Too Many Requests" in err_msg:
                    logger.warning(f"Model {model_name} quota exhausted. Switching to next model...")
                    last_error = e
                    continue
                else:
                    logger.warning(f"Model {model_name} failed with error: {e}. Retrying with next...")
                    last_error = e
                    continue
        
        if not response:
            raise last_error or RuntimeError("All models failed plan generation")
        
        if not response.parsed:
            # Fallback parsing if needed
            plan = json.loads(response.text)
        else:
            plan = response.parsed
        
        return _normalize_plan(plan, user_request)
        
    except Exception as e:
        logger.error(f"Plan generation failed: {e}")
        return _fallback_plan(user_request)
