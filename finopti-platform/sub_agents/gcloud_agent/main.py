"""
GCloud Agent - Sub-Agent for Google Cloud Infrastructure Tasks

This agent handles GCP infrastructure operations by communicating
with the GCloud MCP Server via APISIX.

Request Flow:
1. Receive request from Orchestrator via APISIX
2. Parse the prompt to determine specific action
3. Call GCloud MCP Server via APISIX
4. Return formatted response
"""

from flask import Flask, request, jsonify
import requests
import logging
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
APISIX_URL = os.getenv('APISIX_URL', 'http://apisix:9080')
MCP_ENDPOINT = f"{APISIX_URL}/mcp/gcloud"

def call_mcp_server(action: str, params: dict) -> dict:
    """
    Call the GCloud MCP Server via APISIX.
    
    Args:
        action: The action to perform (e.g., 'create_vm', 'delete_vm', 'list_vms')
        params: Parameters for the action
        
    Returns:
        Response from MCP server
    """
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": action,
            "params": params,
            "id": 1
        }
        
        logger.info(f"Calling GCloud MCP: action={action}, params={params}")
        response = requests.post(MCP_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"MCP response: {result}")
        return result
        
    except requests.RequestException as e:
        logger.error(f"Error calling GCloud MCP: {e}")
        return {
            "error": True,
            "message": f"Error communicating with GCloud MCP: {str(e)}"
        }

def parse_gcloud_action(prompt: str) -> tuple:
    """
    Parse the prompt to determine GCloud action.
    Simple keyword matching for prototype.
    
    Args:
        prompt: User's prompt
        
    Returns:
        (action, params) tuple
    """
    prompt_lower = prompt.lower()
    
    if 'create' in prompt_lower and 'vm' in prompt_lower:
        return 'create_vm', {'instance_name': 'demo-instance', 'zone': 'us-central1-a'}
    elif 'delete' in prompt_lower and 'vm' in prompt_lower:
        return 'delete_vm', {'instance_name': 'demo-instance', 'zone': 'us-central1-a'}
    elif 'list' in prompt_lower:
        return 'list_vms', {'zone': 'us-central1-a'}
    else:
        # Default action
        return 'list_vms', {'zone': 'us-central1-a'}

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "gcloud_agent"}), 200

@app.route('/execute', methods=['POST'])
def execute():
    """
    Execute GCloud operations.
    
    Expected body:
        {
            "prompt": "User's request",
            "user_email": "User's email"
        }
        
    Returns:
        Result from GCloud MCP Server
    """
    try:
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({
                "error": True,
                "message": "Missing 'prompt' in request body"
            }), 400
        
        prompt = data['prompt']
        user_email = data.get('user_email', 'unknown')
        
        logger.info(f"Received GCloud request from {user_email}: {prompt}")
        
        # Parse action from prompt
        action, params = parse_gcloud_action(prompt)
        logger.info(f"Parsed action: {action} with params: {params}")
        
        # Call MCP server
        mcp_response = call_mcp_server(action, params)
        
        # Format response
        response = {
            "agent": "gcloud",
            "action": action,
            "prompt": prompt,
            "user_email": user_email,
            "result": mcp_response.get('result', mcp_response)
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error in /execute endpoint: {e}", exc_info=True)
        return jsonify({
            "error": True,
            "message": f"Internal server error: {str(e)}"
        }), 500

if __name__ == '__main__':
    logger.info("Starting GCloud Agent on port 5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
