from flask import Flask, request, jsonify
import logging
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "code_execution_agent"}), 200

@app.route('/execute', methods=['POST'])
def execute():
    try:
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({"error": "Missing 'prompt' in request body"}), 400
            
        prompt = data['prompt']
        user_email = data.get('user_email', 'unknown')
        
        logger.info(f"Received request from {user_email}: {prompt[:100]}")
        
        # Import here to avoid circular dependencies if any
        from agent import process_request
        
        response = process_request(prompt)
        
        return jsonify({
            "success": True,
            "data": {
                "response": response
            }
        })
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5012))
    app.run(host='0.0.0.0', port=port)
