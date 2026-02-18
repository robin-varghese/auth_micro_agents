"""
GCloud ADK Agent - Flask HTTP Wrapper

Provides HTTP API endpoint for the GCloud ADK agent.
Integrates with structured logging and request ID propagation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from flask import Flask, request, jsonify
import asyncio
from agent import send_message
from config import config

# Import structured logging from parent orchestrator
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
    logger = StructuredLogger('gcloud_agent_adk', level=config.LOG_LEVEL)
    app.after_request(add_request_id_to_response)
else:
    logger = logging.getLogger(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "gcloud_agent_adk",
        "model": config.FINOPTIAGENTS_LLM
    }), 200


@app.route('/execute', methods=['POST'])
def execute():
    """
    Execute a GCloud operation via ADK agent
    
    Expected JSON body:
    {
        "prompt": "Natural language request",
        "user_email": "user@example.com" (optional)
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
        session_id = data.get('session_id', 'default') # Extract session_id
        
        from context import _auth_token_ctx
        
        # Extract Auth Token
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            _auth_token_ctx.set(token)
            if STRUCTURED_LOGGING_AVAILABLE:
                logger.info("Captured OAuth token from request headers")
        
        # Log request
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.info(
                "Received execution request",
                user_email=user_email,
                session_id=session_id,
                prompt=prompt[:100] if len(prompt) > 100 else prompt
            )
        else:
            logger.info(f"Received request from {user_email} (session: {session_id}): {prompt[:100]}")
        
        # Process with ADK agent
        token = _auth_token_ctx.get()
        response_text = send_message(prompt, user_email, session_id=session_id, auth_token=token)
        
        # Check if response_text contains an error message from ADK agent.py catch block
        is_error = "Error processing request:" in str(response_text)
        
        # Log status
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.info(
                "Request processed",
                user_email=user_email,
                success=not is_error,
                response_length=len(str(response_text))
            )
        else:
            logger.info(f"Request processed for {user_email}. Success: {not is_error}")
        
        return jsonify({
            "success": not is_error,
            "error": is_error,
            "response": response_text,
            "message": response_text if is_error else None,
            "agent": "gcloud_adk",
            "model": config.FINOPTIAGENTS_LLM
        }), 200 if not is_error else 500
    
    except Exception as e:
        # Log error
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.error(
                "Error processing request",
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
        "name": "gcloud_agent_adk",
        "description": "Google Cloud Platform infrastructure management specialist using ADK",
        "model": config.FINOPTIAGENTS_LLM,
        "capabilities": [
            "VM management (list, create, delete, start, stop)",
            "Machine type changes",
            "Network operations",
            "Storage management",
            "Cost optimization recommendations"
        ],
        "mcp_server": config.GCLOUD_MCP_DOCKER_IMAGE
    }), 200


if __name__ == '__main__':
    # Validate configuration
    if not config.validate():
        print("ERROR: Configuration validation failed!")
        print("Please check your .env file or environment variables")
        sys.exit(1)
    
    if STRUCTURED_LOGGING_AVAILABLE:
        logger.info(
            "Starting GCloud ADK Agent",
            port=5001,
            model=config.FINOPTIAGENTS_LLM,
            mcp_image=config.GCLOUD_MCP_DOCKER_IMAGE
        )
    else:
        logger.info(f"Starting GCloud ADK Agent on port 5001")
    
    app.run(host='0.0.0.0', port=5001, debug=config.DEV_MODE)
