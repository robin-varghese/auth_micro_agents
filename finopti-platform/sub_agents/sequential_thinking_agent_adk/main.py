"""
Sequential Thinking ADK Agent - Flask HTTP Wrapper
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from flask import Flask, request, jsonify
from agent import send_message
from config import config

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
    logger = StructuredLogger('sequential_agent_adk', level=config.LOG_LEVEL)
    app.after_request(add_request_id_to_response)
else:
    logger = logging.getLogger(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "sequential_thinking_agent_adk"
    }), 200

@app.route('/execute', methods=['POST'])
def execute():
    try:
        if STRUCTURED_LOGGING_AVAILABLE:
            set_request_id(request.headers.get('X-Request-ID'))
        
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({"error": True, "message": "Missing 'prompt'"}), 400
        
        prompt = data['prompt']
        user_email = data.get('user_email', 'unknown')
        
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.info("Received execution request", user_email=user_email)
        
        response_text = send_message(prompt, user_email)
        
        return jsonify({
            "success": True,
            "response": response_text,
            "agent": "sequential_adk"
        }), 200
    
    except Exception as e:
        if STRUCTURED_LOGGING_AVAILABLE:
            logger.error("Error processing request", error=str(e), exc_info=True)
        return jsonify({"error": True, "message": str(e)}), 500

if __name__ == '__main__':
    if not config.validate():
        sys.exit(1)
    
    app.run(host='0.0.0.0', port=5010, debug=config.DEV_MODE)
