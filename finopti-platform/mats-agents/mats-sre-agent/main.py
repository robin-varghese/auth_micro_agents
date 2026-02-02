
import os
import logging
from flask import Flask, request, jsonify
import asyncio
from agent import process_request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mats-sre-main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mats-sre-agent"}), 200

@app.route('/chat', methods=['POST'])
def chat():
    """
    Endpoint for Orchestrator to trigger investigation.
    Payload: {"message": "Analyze logs for project X..."}
    """
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Message is required"}), 400

    user_message = data['message']
    logger.info(f"Received request: {user_message[:50]}...")

    try:
        # Run the async agent loop
        agent_result = asyncio.run(process_request(user_message))
        
        # agent_result is now a dict: {"response": "...", "execution_trace": [...]}
        # We return it directly as JSON
        return jsonify(agent_result)

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081)
