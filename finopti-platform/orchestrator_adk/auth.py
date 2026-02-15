"""
Orchestrator ADK - Authorization Logic
"""
import requests
import logging
from config import config

logger = logging.getLogger(__name__)

def check_opa_authorization(user_email: str, target_agent: str) -> dict:
    """
    Call OPA to check if user is authorized to access the target agent.
    
    Args:
        user_email: User's email address
        target_agent: Target agent name
        
    Returns:
        dict with 'allow' (bool) and 'reason' (str)
    """
    try:
        opa_endpoint = f"{config.OPA_URL}/v1/data/finopti/authz"
        payload = {
            "input": {
                "user_email": user_email,
                "target_agent": target_agent
            }
        }
        
        response = requests.post(opa_endpoint, json=payload, timeout=5)
        response.raise_for_status()
        
        result = response.json()
        authz_result = result.get('result', {})
        
        return authz_result
        
    except Exception as e:
        logger.error(f"Authorization check failed: {e}")
        return {
            "allow": False,
            "reason": f"Authorization service error: {str(e)}"
        }
