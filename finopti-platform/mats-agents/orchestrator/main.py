
import os
import logging
import asyncio
import requests
import google.auth
from google.auth.transport.requests import Request
from flask import Flask, request, jsonify
from permission_check import check_gcp_credentials
from workflow import run_troubleshooting_workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mats-orchestrator-main")

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mats-orchestrator"}), 200

@app.route('/projects', methods=['GET'])
def list_projects():
    """
    List accessible GCP projects via REST API.
    """
    valid, msg, _ = check_gcp_credentials()
    if not valid:
         return jsonify({"error": msg}), 401
         
    try:
        credentials, _ = google.auth.default()
        if not credentials.valid:
            credentials.refresh(Request())

        resp = requests.get(
            "https://cloudresourcemanager.googleapis.com/v1/projects",
            headers={"Authorization": f"Bearer {credentials.token}"}
        )
        if resp.status_code != 200:
             return jsonify({"error": f"GCP API Error: {resp.text}"}), resp.status_code
             
        data = resp.json()
        projects = []
        if 'projects' in data:
            for p in data['projects']:
                projects.append({"project_id": p.get('projectId'), "name": p.get('name')})
        
        return jsonify({"projects": projects})
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/troubleshoot', methods=['POST'])
def troubleshoot():
    """
    Trigger the troubleshooting workflow.
    """
    data = request.json
    required = ['project_id', 'repo_url', 'error_description']
    if not all(k in data for k in required):
        return jsonify({"error": f"Missing required fields: {required}"}), 400
        
    # Check permissions first
    valid, msg, _ = check_gcp_credentials()
    if not valid:
         return jsonify({"error": msg}), 401

    # Extract Repo Details
    repo_url = data['repo_url']
    try:
        parts = repo_url.rstrip('/').split('/')
        if 'github.com' in parts:
            idx = parts.index('github.com')
            owner = parts[idx+1]
            repo = parts[idx+2]
            if repo.endswith('.git'):
                repo = repo[:-4]
        else:
             if len(parts) >= 2:
                 owner = parts[-2]
                 repo = parts[-1]
             else:
                 raise ValueError("Invalid Format")
    except Exception:
        return jsonify({"error": "Invalid GitHub URL format. Expected github.com/owner/repo"}), 400

    project_id = data['project_id']
    branch = data.get('branch', 'main')
    desc = data['error_description']
    
    logger.info(f"Starting troubleshooting for {project_id} | {owner}/{repo}")

    try:
        result = asyncio.run(run_troubleshooting_workflow(
            project_id, owner, repo, branch, desc
        ))
        return jsonify(result)
    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8084)
