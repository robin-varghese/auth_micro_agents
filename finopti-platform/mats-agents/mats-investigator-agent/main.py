
import os
import logging
from flask import Flask, request, jsonify
import asyncio
from agent import process_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mats-investigator-main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mats-investigator-agent"}), 200

@app.route('/chat', methods=['POST'])
def chat():
    """
    Endpoint for Orchestrator to trigger investigation.
    Payload: {"message": "...SRE context + Repo Spec..."}
    """
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Message is required"}), 400

    user_message = data['message']
    session_id = data.get('session_id')  # Extract session_id
    user_email = data.get('user_email')  # Extract user_email for Redis channel
    logger.info(f"Received request: {len(user_message)} chars. Session: {session_id}, User: {user_email}")

    try:
        response = asyncio.run(process_request(user_message, session_id=session_id, user_email=user_email))
        return jsonify({"response": response})
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082)
