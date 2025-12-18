"""
Monitoring Agent - Sub-Agent for Observability and Monitoring Tasks

This agent handles monitoring, logging, and observability operations
by communicating with the Monitoring MCP Server via APISIX.

Request Flow:
1. Receive request from Orchestrator via APISIX
2. Parse the prompt to determine specific monitoring query
3. Call Monitoring MCP Server via APISIX
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
MCP_ENDPOINT = f"{APISIX_URL}/mcp/monitoring"

def call_mcp_server(action: str, params: dict) -> dict:
    """
    Call the Monitoring MCP Server via APISIX.
    
    Args:
        action: The action to perform (e.g., 'check_cpu', 'query_logs', 'get_metrics')
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
        
        logger.info(f"Calling Monitoring MCP: action={action}, params={params}")
        response = requests.post(MCP_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"MCP response: {result}")
        return result
        
    except requests.RequestException as e:
        logger.error(f"Error calling Monitoring MCP: {e}")
        return {
            "error": True,
            "message": f"Error communicating with Monitoring MCP: {str(e)}"
        }

def parse_monitoring_action(prompt: str) -> tuple:
    """
    Parse the prompt to determine monitoring action.
    Simple keyword matching for prototype.
    
    Args:
        prompt: User's prompt
        
    Returns:
        (action, params) tuple
    """
    prompt_lower = prompt.lower()
    
    if 'cpu' in prompt_lower:
        return 'check_cpu', {'resource': 'compute', 'period': '5m'}
    elif 'memory' in prompt_lower:
        return 'check_memory', {'resource': 'compute', 'period': '5m'}
    elif 'log' in prompt_lower:
        return 'query_logs', {'filter': 'severity>=ERROR', 'limit': 10}
    elif 'metric' in prompt_lower:
        return 'get_metrics', {'metric_type': 'cpu_utilization'}
    else:
        # Default action
        return 'check_cpu', {'resource': 'compute', 'period': '5m'}

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "monitoring_agent"}), 200

@app.route('/execute', methods=['POST'])
def execute():
    """
    Execute Monitoring operations.
    
    Expected body:
        {
            "prompt": "User's request",
            "user_email": "User's email"
        }
        
    Returns:
        Result from Monitoring MCP Server
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
        
        logger.info(f"Received Monitoring request from {user_email}: {prompt}")
        
        # Parse action from prompt
        action, params = parse_monitoring_action(prompt)
        logger.info(f"Parsed action: {action} with params: {params}")
        
        # Call MCP server
        mcp_response = call_mcp_server(action, params)
        
        # Format response
        response = {
            "agent": "monitoring",
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
    logger.info("Starting Monitoring Agent on port 5002")
    app.run(host='0.0.0.0', port=5002, debug=False)
