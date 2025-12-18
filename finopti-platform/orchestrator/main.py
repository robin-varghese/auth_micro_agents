"""
FinOptiAgents Orchestrator Service

This service acts as the central hub in the Hub-and-Spoke architecture.
It receives user requests, determines intent, validates permissions via OPA,
and routes to the appropriate sub-agent.

Request Flow:
1. Receive POST /ask from UI via APISIX
2. Extract X-User-Email header
3. Parse prompt to determine target agent (intent detection)
4. Call OPA for authorization check
5. If authorized: Forward to sub-agent via APISIX
6. If denied: Return 403 error
7. Return response to UI
"""

from flask import Flask, request, jsonify
import requests
import os
from structured_logging import (
    StructuredLogger,
    set_request_id,
    get_request_id,
    propagate_request_id,
    add_request_id_to_response
)

app = Flask(__name__)

# Configure structured logging
logger = StructuredLogger('orchestrator', level='INFO')

# Add request ID to all responses
app.after_request(add_request_id_to_response)

# Configuration
OPA_URL = os.getenv('OPA_URL', 'http://opa:8181')
APISIX_URL = os.getenv('APISIX_URL', 'http://apisix:9080')

def detect_intent(prompt: str) -> str:
    """
    Simple keyword-based intent detection.
    In production, this would use NLP/LLM for better understanding.
    
    Args:
        prompt: User's natural language prompt
        
    Returns:
        target_agent: 'gcloud' or 'monitoring'
    """
    prompt_lower = prompt.lower()
    
    # GCloud keywords
    gcloud_keywords = ['vm', 'instance', 'create', 'delete', 'compute', 'gcp', 'cloud', 'provision']
    # Monitoring keywords
    monitoring_keywords = ['cpu', 'memory', 'logs', 'metrics', 'monitor', 'alert', 'usage', 'check']
    
    gcloud_score = sum(1 for keyword in gcloud_keywords if keyword in prompt_lower)
    monitoring_score = sum(1 for keyword in monitoring_keywords if keyword in prompt_lower)
    
    if gcloud_score > monitoring_score:
        return 'gcloud'
    elif monitoring_score > gcloud_score:
        return 'monitoring'
    else:
        # Default to gcloud if unclear
        return 'gcloud'

def check_authorization(user_email: str, target_agent: str) -> dict:
    """
    Call OPA to check if user is authorized to access the target agent.
    
    Args:
        user_email: User's email address
        target_agent: Target agent ('gcloud' or 'monitoring')
        
    Returns:
        dict with 'allow' (bool) and 'reason' (str)
    """
    try:
        opa_endpoint = f"{OPA_URL}/v1/data/finopti/authz"
        payload = {
            "input": {
                "user_email": user_email,
                "target_agent": target_agent
            }
        }
        
        # Propagate request ID
        headers = propagate_request_id({"Content-Type": "application/json"})
        
        logger.info(
            "Checking authorization with OPA",
            user_email=user_email,
            target_agent=target_agent
        )
        response = requests.post(opa_endpoint, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        
        result = response.json()
        authz_result = result.get('result', {})
        
        logger.info(
            "Authorization check completed",
            user_email=user_email,
            target_agent=target_agent,
            allowed=authz_result.get('allow', False)
        )
        return authz_result
        
    except requests.RequestException as e:
        logger.error(
            "Error calling OPA authorization service",
            user_email=user_email,
            target_agent=target_agent,
            error=str(e)
        )
        return {
            "allow": False,
            "reason": f"Authorization service error: {str(e)}"
        }

def forward_to_agent(target_agent: str, prompt: str, user_email: str) -> dict:
    """
    Forward the request to the appropriate sub-agent via APISIX.
    
    Args:
        target_agent: 'gcloud' or 'monitoring'
        prompt: User's prompt
        user_email: User's email
        
    Returns:
        Response from the sub-agent
    """
    try:
        agent_endpoint = f"{APISIX_URL}/agent/{target_agent}"
        payload = {
            "prompt": prompt,
            "user_email": user_email
        }
        
        # Propagate request ID
        headers = propagate_request_id({"Content-Type": "application/json"})
        
        logger.info(
            f"Forwarding request to {target_agent} agent",
            target_agent=target_agent,
            user_email=user_email
        )
        response = requests.post(agent_endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        return response.json()
        
    except requests.RequestException as e:
        logger.error(
            f"Error calling {target_agent} agent",
            target_agent=target_agent,
            user_email=user_email,
            error=str(e)
        )
        return {
            "error": True,
            "message": f"Error communicating with {target_agent} agent: {str(e)}"
        }

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "orchestrator"}), 200

@app.route('/ask', methods=['POST'])
def ask():
    """
    Main endpoint for receiving user requests.
    
    Expected headers:
        X-User-Email: User's email address (set by APISIX/UI)
        
    Expected body:
        {
            "prompt": "User's natural language request"
        }
        
    Returns:
        Success: Agent's response
        Failure: 403 if unauthorized, 400 if bad request, 500 if error
    """
    try:
        # Set request ID (get from header or generate new)
        request_id = set_request_id(request.headers.get('X-Request-ID'))
        
        # Extract user email from header
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            logger.warning(
                "Request missing X-User-Email header",
                path=request.path
            )
            return jsonify({
                "error": True,
                "message": "Missing X-User-Email header"
            }), 400
        
        # Extract prompt from body
        data = request.get_json()
        if not data or 'prompt' not in data:
            logger.warning(
                "Request missing prompt in body",
                user_email=user_email
            )
            return jsonify({
                "error": True,
                "message": "Missing 'prompt' in request body"
            }), 400
        
        prompt = data['prompt']
        logger.info(
            "Received user request",
            user_email=user_email,
            prompt=prompt[:100]  # Truncate long prompts
        )
        
        # Detect intent to determine target agent
        target_agent = detect_intent(prompt)
        logger.info(
            "Intent detected",
            target_agent=target_agent,
            user_email=user_email
        )
        
        # Check authorization via OPA
        authz_result = check_authorization(user_email, target_agent)
        
        if not authz_result.get('allow', False):
            reason = authz_result.get('reason', 'Access denied')
            logger.warning(
                "Authorization denied",
                user_email=user_email,
                target_agent=target_agent,
                reason=reason
            )
            return jsonify({
                "error": True,
                "message": f"403 Unauthorized: {reason}",
                "user_email": user_email,
                "target_agent": target_agent
            }), 403
        
        # Authorization successful, forward to sub-agent
        logger.info(
            "Authorization granted",
            user_email=user_email,
            target_agent=target_agent
        )
        agent_response = forward_to_agent(target_agent, prompt, user_email)
        
        # Add orchestrator metadata to response
        agent_response['orchestrator'] = {
            'user_email': user_email,
            'target_agent': target_agent,
            'authorization': authz_result.get('reason', '')
        }
        
        return jsonify(agent_response), 200
        
    except Exception as e:
        logger.error(
            "Unexpected error in /ask endpoint",
            error=str(e),
            exc_info=True
        )
        return jsonify({
            "error": True,
            "message": f"Internal server error: {str(e)}"
        }), 500

if __name__ == '__main__':
    logger.info("Starting Orchestrator Service on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
