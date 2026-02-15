"""
MATS Orchestrator - Operational Routing

Extracted from agent.py per REFACTORING_GUIDELINE.md (Step 2).
Handles detection and delegation of simple operational requests (e.g. "list VMs")
that bypass the full investigation workflow.
"""
import re
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Import delegation URL constants
try:
    from delegation import delegate_to_operational_agent, GCLOUD_AGENT_URL
except ImportError:
    GCLOUD_AGENT_URL = None
    delegate_to_operational_agent = None
    logger.warning("delegation module not available for routing")


# --- OPERATIONAL ROUTE PATTERNS ---
# Format: (regex_pattern, agent_url_key, agent_name)
# Using URL keys resolved at match time so imports work correctly
OPERATIONAL_ROUTES = [
    # GCloud Patterns
    (r'\blist\s+(all|my|the)?\s*(vms?|instances?|buckets?|services?|projects?|resources?)', 'gcloud', "GCloud Agent"),
    (r'\bshow\s+(all|my|the)?\s*(vms?|instances?|buckets?|services?|projects?|resources?)', 'gcloud', "GCloud Agent"),
    (r'\bget\s+(all|my|the)?\s*(vms?|instances?|buckets?|services?|projects?|resources?)', 'gcloud', "GCloud Agent"),
    (r'\bcreate\s+a?\s*(vm|instance|bucket|service|resource)', 'gcloud', "GCloud Agent"),
    (r'\bdelete\s+a?\s*(vm|instance|bucket|service|resource)', 'gcloud', "GCloud Agent"),
    (r'\bdescribe\s+(the|my|a)?\s*(vm|instance|bucket|service|resource)', 'gcloud', "GCloud Agent"),
    # Generic GCloud Intent
    (r'\bgcloud\s+', 'gcloud', "GCloud Agent"),
    # Remediation Intents
    (r'\b(fix|remediate|solve|solution|apply fix)\b.*', 'remediation', "Remediation Agent"),
]

# URL resolution map
_URL_MAP = {
    'gcloud': lambda: GCLOUD_AGENT_URL,
    'remediation': lambda: "http://mats-remediation-agent:8085",
}


def match_operational_route(user_request: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check if a user request matches an operational (non-investigation) pattern.
    
    Args:
        user_request: The raw user request text
        
    Returns:
        Tuple of (matched: bool, agent_url: str or None, agent_name: str or None)
    """
    request_lower = user_request.lower()
    
    for pattern, url_key, name in OPERATIONAL_ROUTES:
        if re.search(pattern, request_lower):
            # Resolve URL at match time
            url_resolver = _URL_MAP.get(url_key)
            agent_url = url_resolver() if url_resolver else None
            
            if agent_url:
                logger.info(f"Request matched operational route: {name} (Pattern: {pattern})")
                return True, agent_url, name
            else:
                logger.warning(f"Route matched {name} but URL not available for key '{url_key}'")
    
    return False, None, None


async def handle_operational_request(
    user_request: str,
    agent_url: str,
    agent_name: str,
    session_id: str,
    user_email: str = None,
    job_id: str = None,
    report_progress=None,
) -> Dict[str, Any]:
    """Execute an operational request by delegating to the matched agent.
    
    Args:
        user_request: The user's request text
        agent_url: URL of the target agent
        agent_name: Human-readable agent name
        session_id: Current session ID
        user_email: User's email
        job_id: Optional job ID for tracking
        report_progress: Optional async progress callback
        
    Returns:
        Standardized response dict
    """
    if report_progress:
        await report_progress(
            f"Routing request to **{agent_name}**...",
            event_type="THOUGHT", icon="🧠"
        )
    
    try:
        op_result = await delegate_to_operational_agent(
            task_description=user_request,
            agent_url=agent_url,
            agent_name=agent_name,
            session_id=session_id,
            user_email=user_email
        )
        
        # Format Response
        response_text = ""
        if op_result.get("success"):
            response_text = op_result.get("response", "Command executed successfully.")
            if report_progress:
                await report_progress(response_text, event_type="ARTIFACT", icon="✅")
        else:
            response_text = f"⚠️ Error executing command: {op_result.get('message', 'Unknown error')}"
            if report_progress:
                await report_progress(response_text, event_type="ERROR", icon="❌", display_type="alert")
        
        # Update job tracking if available
        if job_id:
            try:
                from job_manager import JobManager
                JobManager.update_job(job_id, {"status": "COMPLETED", "result": op_result})
            except ImportError:
                pass
        
        return {
            "status": "SUCCESS",
            "orchestrator": {"target_agent": agent_name},
            "response": response_text,
            "data": op_result
        }
        
    except Exception as e:
        logger.error(f"[{session_id}] Operational delegation failed: {e}")
        if report_progress:
            await report_progress(
                f"Failed to execute command: {e}",
                event_type="ERROR", icon="❌", display_type="alert"
            )
        return {
            "status": "FAILURE",
            "error": str(e)
        }
