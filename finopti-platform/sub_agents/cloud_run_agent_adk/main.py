from flask import Flask, request, jsonify
import os
import logging
import sys
from pathlib import Path

# Add parent directory to path to allow importing config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent import send_message

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "cloud_run_agent"}), 200

@app.route('/execute', methods=['POST'])
def chat():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        prompt = data.get('prompt')
        user_email = data.get('user_email')
        
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
            
        logger.info(f"Received request from {user_email}: {prompt}")
        
        response = send_message(prompt, user_email)
        
        return jsonify({
            "response": response,
            "status": "success"
        })
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5006))
    app.run(host='0.0.0.0', port=port)
