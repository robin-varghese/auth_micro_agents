
import os
import logging
from flask import Flask, request, jsonify
import asyncio
from agent import run_investigation_async
from job_manager import JobManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mats-orchestrator-main")

# Add file handler
fh = logging.FileHandler('/tmp/debug.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)
logging.getLogger().addHandler(fh) # Root logger

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
    Start a new async troubleshooting job, or resume an existing one if waiting.
    Returns: {"job_id": "...", "status": "RUNNING"}
    """
    data = request.json or {}
    user_request = data.get('prompt') or data.get('user_request')
    project_id = data.get('project_id')
    repo_url = data.get('repo_url')
    user_email = request.headers.get('X-User-Email', data.get('user_email', 'unknown'))
    
    # Extract Trace Context
    trace_context = {}
    if "traceparent" in request.headers:
        trace_context["traceparent"] = request.headers["traceparent"]
    
    # Extract Session ID from headers (UI provides this for Phoenix tracking)
    provided_session_id = request.headers.get('X-Session-ID')
    logger.info(f"Received session ID from UI: {provided_session_id}")
        
    if not user_request:
        return jsonify({"error": "Prompt/user_request is required"}), 400

    # 1. Check for RESUMABLE JOB
    existing_job_id = JobManager.get_active_job_for_user(user_email)
    
    if existing_job_id:
        # Resume existing job
        job_id = existing_job_id
        logger.info(f"Resuming Job {job_id} for user {user_email}")
        JobManager.add_event(job_id, "SYSTEM", f"Resuming job with user input: {user_request[:50]}...", "orchestrator")
        
        # Fire async resume
        async def background_task_resume():
            try:
                result = await run_investigation_async(
                    user_request=user_request, # This is the users REPLY now
                    project_id=project_id,
                    repo_url=repo_url,
                    user_email=user_email,
                    job_id=job_id,
                    resume_job_id=job_id, # Signal to resume
                    trace_context=trace_context,
                    provided_session_id=provided_session_id  # Pass UI session ID
                )
                JobManager.update_result(job_id, result, result.get("status", "COMPLETED"))
            except Exception as e:
                logger.error(f"Job {job_id} failed on resume: {e}", exc_info=True)
                JobManager.fail_job(job_id, str(e))
                
        import threading
        def run_resume_in_thread():
            asyncio.run(background_task_resume())
        threading.Thread(target=run_resume_in_thread).start()
        
        return jsonify({"job_id": job_id, "status": "RESUMED"}), 202

    # 2. Create Job ID (BRAND NEW)
    job_id = JobManager.create_job(user_request, user_email)
    
    logger.info(f"Starting Job {job_id} for user {user_email}")
    
    # 3. Fire and Forget Async Task (NEW)
    async def background_task_new():
        try:
            result = await run_investigation_async(
                user_request=user_request,
                project_id=project_id,
                repo_url=repo_url,
                user_email=user_email,
                job_id=job_id,
                trace_context=trace_context,
                provided_session_id=provided_session_id  # Pass UI session ID
            )
            # Update status based on result (WAITING_FOR_USER vs COMPLETED)
            final_status = result.get("status", "COMPLETED")
            if final_status == "WAITING_FOR_USER":
                JobManager.update_result(job_id, result, "WAITING_FOR_USER")
            else:
                JobManager.update_result(job_id, result, "COMPLETED")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            JobManager.fail_job(job_id, str(e))

    import threading
    def run_new_in_thread():
        asyncio.run(background_task_new())
    threading.Thread(target=run_new_in_thread).start()

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
