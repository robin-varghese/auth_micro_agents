"""
Monitoring ADK Agent - Flask HTTP Wrapper

Provides HTTP API endpoint for the Monitoring ADK agent.
Integrates with structured logging and request ID propagation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from flask import Flask, request, jsonify
import asyncio
# from agent import send_message_async # Deprecated in main
from config import config

# Import structured logging
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'orchestrator'))
    from structured_logging import (
        StructuredLogger,
        set_request_id,
        get_request_id,
        propagate_request_id,
        add_request_id_to_response
    )
    STRUCTURED_LOGGING_AVAILABLE = True
except ImportError:
    print("Warning: Structured logging not available, using basic logging")
    STRUCTURED_LOGGING_AVAILABLE = False
    import logging
    logging.basicConfig(level=logging.INFO)


app = Flask(__name__)

# Configure logging
if STRUCTURED_LOGGING_AVAILABLE:
    logger = StructuredLogger('monitoring_agent_adk', level=config.LOG_LEVEL)
    app.after_request(add_request_id_to_response)
else:
    logger = logging.getLogger(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "monitoring_agent_adk",
        "model": config.FINOPTIAGENTS_LLM
    }), 200


@app.route('/execute', methods=['POST'])
def execute():
    """
    Execute a Monitoring operation via ADK agent
    
    Expected JSON body:
    {
        "prompt": "Natural language request",
        "user_email": "user@example.com" (optional),
        "project_id": "gcp-project-id" (optional)
    }
    
    Returns:
        JSON response with agent output
    """
    try:
        # Set request ID for tracing
        if STRUCTURED_LOGGING_AVAILABLE:
            set_request_id(request.headers.get('X-Request-ID'))
        
        # Extract request data
        data = request.get_json()
        if not data or 'prompt' not in data:
            if STRUCTURED_LOGGING_AVAILABLE:
                logger.warning("Missing prompt in request body")
            return jsonify({
                "error": True,
                "message": "Missing 'prompt' in request body"
            }), 400
        
        prompt = data['prompt']
        user_email = data.get('user_email', 'unknown')
        project_id = data.get('project_id', config.GCP_PROJECT_ID)
        
        # Log request
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.info(
                "Received monitoring request",
                user_email=user_email,
                prompt=prompt[:100] if len(prompt) > 100 else prompt,
                project_id=project_id
            )
        else:
            logger.info(f"Received request from {user_email}: {prompt[:100]}")
        
        # Process with ADK agent
        from agent import send_message
        response_text = send_message(prompt, user_email, project_id)
        
        # Log success
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.info(
                "Request processed successfully",
                user_email=user_email,
                response_length=len(response_text)
            )
        else:
            logger.info(f"Request processed for {user_email}")
        
        return jsonify({
            "success": True,
            "response": response_text,
            "agent": "monitoring_adk",
            "model": config.FINOPTIAGENTS_LLM
        }), 200
    
    except Exception as e:
        # Log error
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.error(
                "Error processing monitoring request",
                error=str(e),
                exc_info=True
            )
        else:
            logger.error(f"Error: {str(e)}", exc_info=True)
        
        return jsonify({
            "error": True,
            "message": f"Error processing request: {str(e)}"
        }), 500


@app.route('/info', methods=['GET'])
def info():
    """Get agent information"""
    return jsonify({
        "name": "monitoring_agent_adk",
        "description": "Google Cloud monitoring and logging specialist using ADK",
        "model": config.FINOPTIAGENTS_LLM,
        "capabilities": [
            "Query time-series metrics (CPU, memory, disk, network)",
            "Search and retrieve log entries",
            "List available metrics",
            "Analyze system health and performance"
        ],
        "mcp_server_url": config.MONITORING_MCP_URL
    }), 200


if __name__ == '__main__':
    # Validate configuration
    if not config.validate():
        print("ERROR: Configuration validation failed!")
        print("Please check your .env file or environment variables")
        sys.exit(1)
    
    if STRUCTURED_LOGGING_AVAILABLE:
        logger.info(
            "Starting Monitoring ADK Agent",
            port=5002,
            model=config.FINOPTIAGENTS_LLM,
            mcp_url=config.MONITORING_MCP_URL
        )
    else:
        logger.info(f"Starting Monitoring ADK Agent on port 5002")
    
    app.run(host='0.0.0.0', port=5002, debug=config.DEV_MODE)
