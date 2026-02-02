
import os
import logging
from flask import Flask, request, jsonify
import asyncio
from agent import run_investigation_async
from job_manager import JobManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mats-orchestrator-main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mats-orchestrator"}), 200

# -------------------------------------------------------------------------
# ASYNC JOB ENDPOINTS (NEW)
# -------------------------------------------------------------------------

@app.route('/jobs', methods=['POST'])
def start_job():
    """
    Start a new async troubleshooting job.
    Returns: {"job_id": "...", "status": "RUNNING"}
    """
    data = request.json or {}
    user_request = data.get('prompt') or data.get('user_request')
    project_id = data.get('project_id')
    repo_url = data.get('repo_url')
    user_email = request.headers.get('X-User-Email', data.get('user_email', 'unknown'))
    
    if not user_request:
        return jsonify({"error": "Prompt/user_request is required"}), 400

    # 1. Create Job ID
    job_id = JobManager.create_job(user_request)
    
    logger.info(f"Starting Job {job_id} for user {user_email}")
    
    # 2. Fire and Forget Async Task
    # Note: In production, use Celery/Redis Queue. Here we use asyncio.create_task helper.
    # Flask with Gunicorn/Uvicorn needs care with async.
    
    # Define the worker function
    async def background_task():
        try:
            result = await run_investigation_async(
                user_request=user_request,
                project_id=project_id,
                repo_url=repo_url,
                user_email=user_email,
                job_id=job_id # Inject Job ID
            )
            JobManager.update_result(job_id, result, "COMPLETED")
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            JobManager.fail_job(job_id, str(e))

    # Hack for running async in Flask (better to use Quart or FastAPI, but sticking to Flask for now)
    # We can use a thread to run the async loop
    import threading
    def run_in_thread():
        asyncio.run(background_task())
        
    threading.Thread(target=run_in_thread).start()

    return jsonify({"job_id": job_id, "status": "RUNNING"}), 202

@app.route('/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Get job status and event log.
    """
    job = JobManager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route('/jobs/<job_id>/events', methods=['POST'])
def post_job_event(job_id):
    """
    Internal endpoint for sub-agents to report progress.
    Payload: {"type": "SRE|INVESTIGATOR", "message": "..."}
    """
    data = request.json or {}
    event_type = data.get('type', 'INFO')
    message = data.get('message', '')
    source = data.get('source', 'unknown')
    
    if not message:
        return jsonify({"error": "Message required"}), 400
        
    JobManager.add_event(job_id, event_type, message, source)
    return jsonify({"status": "ok"})

# -------------------------------------------------------------------------
# LEGACY / SYNC ENDPOINTS (ADAPTERS)
# -------------------------------------------------------------------------

@app.route('/troubleshoot', methods=['POST'])
def troubleshoot():
    """Legacy sync endpoint wrapper"""
    return start_job() # For now, just return async response. Client needs update.

@app.route('/ask', methods=['POST'])
def ask():
    """UI Adapter endpoint - Redirects to Async Job start"""
    return start_job()

@app.route('/chat', methods=['POST'])
def chat():
    """Legacy chat endpoint"""
    return start_job()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting MATS Orchestrator on port {port}")
    app.run(host="0.0.0.0", port=port)
