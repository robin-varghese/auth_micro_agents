"""
Main Entrypoint for MATS Remediation Agent
Matches AI_AGENT_DEVELOPMENT_GUIDE_V2.0.md
"""
import os
import logging
from flask import Flask, request, jsonify
import asyncio
from agent import process_remediation_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mats-remediation-main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mats-remediation-agent"}), 200

@app.route('/execute', methods=['POST'])
def execute():
    data = request.json
    if not data:
        return jsonify({"error": "JSON payload required"}), 400

    # Extract inputs
    rca = data.get('rca_document')
    resolution = data.get('resolution_plan')
    session_id = data.get('session_id')
    user_email = data.get('user_email')
    
    # Extract auth_token from header
    auth_token = request.headers.get('Authorization')
    
    if not rca or not resolution:
        return jsonify({"error": "rca_document and resolution_plan are required"}), 400

    logger.info(f"Received remediation request. Session: {session_id}, User: {user_email}")

    try:
        # Run agent logic
        result = asyncio.run(process_remediation_async(
            rca_document=rca,
            resolution_plan=resolution,
            session_id=session_id,
            user_email=user_email,
            auth_token=auth_token
        ))
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8085))
    app.run(host="0.0.0.0", port=port)
