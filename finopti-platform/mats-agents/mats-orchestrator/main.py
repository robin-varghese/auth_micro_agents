
import os
import logging
from flask import Flask, request, jsonify
import asyncio
from agent import run_investigation_async

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mats-orchestrator-main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mats-orchestrator"}), 200

@app.route('/troubleshoot', methods=['POST'])
def troubleshoot():
    """
    Main troubleshooting endpoint.
    Payload: {
        "user_request": "description",
        "project_id": "gcp-project",
        "repo_url": "https://github.com/org/repo",
        "user_email": "optional"
    }
    """
    data = request.json
    if not data:
        return jsonify({"error": "JSON payload required"}), 400
    
    user_request = data.get('user_request')
    project_id = data.get('project_id')
    repo_url = data.get('repo_url')
    user_email = data.get('user_email', 'unknown')
    
    if not all([user_request, project_id, repo_url]):
        return jsonify({"error": "Missing required fields: user_request, project_id, repo_url"}), 400
    
    logger.info(f"Troubleshoot request: {user_request[:100]}")
    
    try:
        # Run the async investigation
        result = asyncio.run(run_investigation_async(
            user_request=user_request,
            project_id=project_id,
            repo_url=repo_url,
            user_email=user_email
        ))
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error processing troubleshoot request: {e}", exc_info=True)
        return jsonify({"error": str(e), "status": "FAILURE"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    """
    Chat endpoint for conversational troubleshooting.
    Payload: {"message": "...", "project_id": "...", "repo_url": "..."}
    """
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Message is required"}), 400
    
    message = data['message']
    project_id = data.get('project_id', '')
    repo_url = data.get('repo_url', '')
    
    logger.info(f"Chat request: {message[:50]}...")
    
    try:
        result = asyncio.run(run_investigation_async(
            user_request=message,
            project_id=project_id,
            repo_url=repo_url
        ))
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
