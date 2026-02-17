"""
Storage ADK Agent - Flask HTTP Wrapper
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from flask import Flask, request, jsonify
from agent import send_message
from config import config
import os

# Import structured logging
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'orchestrator'))
    from structured_logging import (
        StructuredLogger,
        set_request_id,
        add_request_id_to_response
    )
    STRUCTURED_LOGGING_AVAILABLE = True
except ImportError:
    STRUCTURED_LOGGING_AVAILABLE = False
    import logging
    logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

if STRUCTURED_LOGGING_AVAILABLE:
    logger = StructuredLogger('storage_agent_adk', level=config.LOG_LEVEL)
    app.after_request(add_request_id_to_response)
else:
    logger = logging.getLogger(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "storage_agent_adk"}), 200

@app.route('/execute', methods=['POST'])
def execute():
    try:
        if STRUCTURED_LOGGING_AVAILABLE:
            set_request_id(request.headers.get('X-Request-ID'))
        
        data = request.get_json()
        prompt = data.get('prompt')
        user_email = data.get('user_email', 'unknown')
        session_id = data.get('session_id', 'default')
        
        if not prompt:
            return jsonify({"error": True, "message": "Missing prompt"}), 400
            
        logger.info(f"Processing Storage request for {user_email} (session: {session_id})")
        response = send_message(prompt, user_email, session_id=session_id)
        
        is_error = "Error processing request:" in str(response)
        
        return jsonify({
            "success": not is_error,
            "error": is_error,
            "response": response,
            "message": response if is_error else None,
            "agent": "storage_agent"
        }), 200 if not is_error else 500
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return jsonify({"error": True, "message": str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Storage ADK Agent on port 5004")
    app.run(host='0.0.0.0', port=5004, debug=config.DEV_MODE)
