
import os
import time
import logging
from flask import Flask, request, jsonify
import asyncio
from agent import process_request

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mats-architect-main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mats-architect-agent"}), 200

@app.route('/chat', methods=['POST'])
def chat():
    """
    Endpoint for Orchestrator to trigger RCA synthesis.
    Payload: {"message": "All findings...", "session_id": "...", "user_email": "..."}
    """
    request_start = time.monotonic()
    data = request.json

    if not data or 'message' not in data:
        logger.warning("Architect /chat called without 'message' field in payload")
        return jsonify({"error": "Message is required"}), 400

    user_message = data['message']
    session_id = data.get('session_id')
    user_email = data.get('user_email')

    # Extract Auth Token
    auth_token = None
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith("Bearer "):
        auth_token = auth_header.split(" ")[1]

    logger.info(
        f"[{session_id}] Architect /chat: received | "
        f"user={user_email} | message_length={len(user_message)} chars | "
        f"has_auth_token={bool(auth_token)}"
    )

    try:
        response = asyncio.run(
            process_request(user_message, session_id=session_id, user_email=user_email, auth_token=auth_token)
        )
        elapsed = time.monotonic() - request_start
        response_len = len(response) if response else 0
        logger.info(
            f"[{session_id}] Architect /chat: success | "
            f"response_length={response_len} chars | elapsed={elapsed:.1f}s"
        )
        return jsonify({"response": response})
    except Exception as e:
        elapsed = time.monotonic() - request_start
        logger.error(
            f"[{session_id}] Architect /chat: FAILED after {elapsed:.1f}s | "
            f"error_type={type(e).__name__} | error={e}",
            exc_info=True
        )
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8083)
