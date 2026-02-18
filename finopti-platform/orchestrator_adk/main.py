"""
Orchestrator ADK Agent - Flask HTTP Wrapper

Provides HTTP API endpoint compatible with existing APISIX routing.
Integrates with structured logging and request ID propagation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request, jsonify
import asyncio
import uuid
from agent import process_request_async
from config import config

# Import structured logging
# Import structured logging
try:
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
    logger = StructuredLogger('orchestrator_adk', level=config.LOG_LEVEL)
    app.after_request(add_request_id_to_response)
else:
    logger = logging.getLogger(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "orchestrator_adk",
        "model": config.FINOPTIAGENTS_LLM,
        "opa_url": config.OPA_URL
    }), 200


@app.route('/ask', methods=['POST'])
def ask():
    """
    Main endpoint for receiving user requests.
    
    Expected headers:
        X-User-Email: User's email address (set by APISIX/UI)
        X-Request-ID: Optional request ID for tracing
        
    Expected body:
        {
            "prompt": "User's natural language request",
            "project_id": "gcp-project-id" (optional)
        }
        
    Returns:
        Success: Agent's response
        Failure: 403 if unauthorized, 400 if bad request, 500 if error
    """
    try:
        # Set request ID for tracing
        if STRUCTURED_LOGGING_AVAILABLE:
            request_id = set_request_id(request.headers.get('X-Request-ID'))
        
        # Extract user email from header
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            if STRUCTURED_LOGGING_AVAILABLE:
                logger.warning("Request missing X-User-Email header", path=request.path)
            return jsonify({
                "error": True,
                "message": "Missing X-User-Email header"
            }), 400
        
        # Extract prompt from body
        data = request.get_json()
        if not data or 'prompt' not in data:
            if STRUCTURED_LOGGING_AVAILABLE:
                logger.warning("Request missing prompt in body", user_email=user_email)
            return jsonify({
                "error": True,
                "message": "Missing 'prompt' in request body"
            }), 400
        
        prompt = data['prompt']
        project_id = data.get('project_id', config.GCP_PROJECT_ID)
        
        # Extract Authorization header
        auth_token = request.headers.get('Authorization')
        
        # Extract Session ID (default to trace ID or generated if missing)
        session_id = request.headers.get('X-Session-ID')

        if not session_id:
             session_id = request.headers.get('X-Request-ID')
             

            
             if not session_id:
                 # Generate a clean session ID if missing or rejected
                 session_id = f"gen-{uuid.uuid4().hex[:12]}"

        # Log incoming request
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.info(
                "Received orchestration request",
                user_email=user_email,
                session_id=session_id,
                prompt=prompt[:100] if len(prompt) > 100 else prompt,
                project_id=project_id
            )
        else:
            logger.info(f"Received request from {user_email} (session: {session_id}): {prompt[:100]}")
        
        # Process request
        from agent import process_request
        result = process_request(prompt, user_email, project_id, auth_token, session_id)
        
        # Check if authorization failed
        if result.get('error') and '403' in result.get('message', ''):
            if STRUCTURED_LOGGING_AVAILABLE:
                logger.warning(
                    "Authorization denied",
                    user_email=user_email,
                    reason=result.get('message', '')
                )
            return jsonify(result), 403
        
        # Check for other errors
        if result.get('error'):
            if STRUCTURED_LOGGING_AVAILABLE:
                logger.error(
                    "Request processing failed",
                    user_email=user_email,
                    error=result.get('message', '')
                )
            return jsonify(result), 500
        
        # Success
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.info(
                "Request processed successfully",
                user_email=user_email,
                target_agent=result.get('orchestrator', {}).get('target_agent')
            )
        
        return jsonify(result), 200
    
    except Exception as e:
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.error(
                "Unexpected error in /ask endpoint",
                error=str(e),
                exc_info=True
            )
        else:
            logger.error(f"Error: {str(e)}", exc_info=True)
        
        return jsonify({
            "error": True,
            "message": f"Internal server error: {str(e)}"
        }), 500


@app.route('/info', methods=['GET'])
def info():
    """Get orchestrator information"""
    return jsonify({
        "name": "orchestrator_adk",
        "description": "FinOps orchestration agent with intelligent routing using ADK",
        "model": config.FINOPTIAGENTS_LLM,
        "capabilities": [
            "Intent detection and routing",
            "OPA-based authorization",
            "Request tracing with request IDs",
            "Intelligent agent coordination"
        ],
        "sub_agents": ["gcloud", "monitoring"],
        "opa_url": config.OPA_URL
    }), 200


if __name__ == '__main__':
    # Validate configuration
    if not config.validate():
        print("ERROR: Configuration validation failed!")
        print("Please check your .env file or environment variables")
        sys.exit(1)
    
    if STRUCTURED_LOGGING_AVAILABLE:
        logger.info(
            "Starting Orchestrator ADK Agent",
            port=5000,
            model=config.FINOPTIAGENTS_LLM,
            opa_url=config.OPA_URL
        )
    else:
        logger.info(f"Starting Orchestrator ADK Agent on port 5000")
    
    app.run(host='0.0.0.0', port=5000, debug=config.DEV_MODE)
