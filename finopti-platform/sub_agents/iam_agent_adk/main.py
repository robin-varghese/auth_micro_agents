import os
import logging
import json
from flask import Flask, request, jsonify
import asyncio
from agent import process_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iam_agent_main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "agent": "iam_verification_specialist"}), 200

@app.route('/execute', methods=['POST'])
def execute():
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"error": "Prompt is required"}), 400

    prompt = data['prompt']
    session_id = data.get('session_id')
    user_email = data.get('user_email')
    project_id = data.get('project_id')
    
    try:
        # Run async process in a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(process_request(
                prompt, 
                user_email=user_email, 
                session_id=session_id,
                project_id=project_id
            ))
            return jsonify({
                "success": True,
                "response": result
            })
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"IAM Agent Error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
