import os
import logging
import json
import requests
from typing import Dict, Any, List
from context import _report_progress
from pathlib import Path
import sys

# Add parent to path for config
sys.path.append(str(Path(__file__).parent.parent.parent))
from config import config

logger = logging.getLogger(__name__)

async def check_gcp_permissions(project_id: str, member_email: str) -> Dict[str, Any]:
    """
    Check current IAM policy bindings for the user in a project by calling gcloud_agent.
    """
    await _report_progress(f"Checking IAM permissions for {member_email} in {project_id}...", icon="🔍")
    
    # We call the gcloud_agent to get high-level intent/info
    # [Refactor] Using direct container name to avoid circular APISIX dependency/timeouts
    endpoint = "http://finopti-gcloud-agent:5001/execute"
    # [Refactor] Semantic prompt focusing on the specific user's permissions
    prompt = f"Check the IAM policy for project {project_id} and identify all roles assigned to user {member_email}. Return the specific bindings for this user in JSON format."
    
    try:
        from context import _auth_token_ctx
        token = _auth_token_ctx.get()
        if not token:
            token = os.environ.get("CLOUDSDK_AUTH_ACCESS_TOKEN")
        headers = {
            "X-User-Email": member_email,
            "Content-Type": "application/json"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        from context import _session_id_ctx
        session_id = _session_id_ctx.get()

        response = requests.post(endpoint, json={
            "prompt": prompt,
            "user_email": member_email,
            "project_id": project_id,
            "session_id": session_id
        }, headers=headers, timeout=120)
        
        response.raise_for_status()
        res_data = response.json()
        
        # The gcloud agent returns results in a 'response' field or 'data.response'
        policy_text = res_data.get("response", "")
        
        logger.info(f"Raw policy text from gcloud_agent: {policy_text[:500]}...")
        
        if not policy_text and "data" in res_data:
            policy_text = res_data["data"].get("response", "")
            
        # [NEW] Explicit Error Detection: If gcloud returned an error, report it instead of "no roles"
        if isinstance(policy_text, str) and ("ERROR" in policy_text or "does not currently have an active account" in policy_text):
            logger.error(f"GCloud returned an error in policy check: {policy_text}")
            return {"success": False, "error": f"Cloud Identity check failed: {policy_text}"}

        policy = {}
        if isinstance(policy_text, dict):
            policy = policy_text
        elif policy_text:
            try:
                # Basic cleaning if wrapped in markdown
                clean_text = policy_text
                if "```json" in policy_text:
                    clean_text = policy_text.split("```json")[1].split("```")[0].strip()
                elif "```" in policy_text:
                    clean_text = policy_text.split("```")[1].split("```")[0].strip()
                policy = json.loads(clean_text)
            except Exception as parse_err:
                logger.warning(f"Could not parse IAM policy as JSON: {parse_err}")
                # If it's not JSON but contains text, it might be an error we missed
                if "error" in policy_text.lower() or "denied" in policy_text.lower():
                     return {"success": False, "error": f"Permission check failed: {policy_text}"}
                policy = {}

        # Extract roles for the user
        user_roles = []
        
        # Handle list of bindings or dict with 'bindings' key
        bindings = []
        if isinstance(policy, list):
            bindings = policy
        elif isinstance(policy, dict):
            bindings = policy.get("bindings", [])
            
        for binding in bindings:
            if isinstance(binding, dict):
                members = binding.get("members", [])
                if any(member_email in member for member in members):
                    user_roles.append(binding.get("role"))
        
        # [FIX] Deduplicate and filter None
        user_roles = list(set([r for r in user_roles if r]))
        
        logger.info(f"Extracted roles for {member_email}: {user_roles}")
        
        return {
            "success": True,
            "project_id": project_id,
            "user_email": member_email,
            "roles": user_roles,
            "raw_policy_available": bool(policy)
        }
        
    except Exception as e:
        logger.error(f"IAM check failed: {e}")
        return {"success": False, "error": str(e)}

async def generate_iam_remediation(project_id: str, user_email: str, missing_roles: List[str]) -> str:
    """
    Generate the gcloud command to grant missing roles.
    """
    if not missing_roles:
        return "No remediation needed."
        
    commands = []
    for role in missing_roles:
        commands.append(f"gcloud projects add-iam-policy-binding {project_id} --member='user:{user_email}' --role='{role}'")
    
    return "\n".join(commands)
