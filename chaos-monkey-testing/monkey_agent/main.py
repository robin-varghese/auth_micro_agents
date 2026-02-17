import os
import logging
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

from scenarios import SCENARIOS
from tools import execute_gcloud_command
from context import _session_id_ctx, _user_email_ctx

app = Flask(__name__)
CORS(app)

# Configuration
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://apisix:9080/orchestrator/ask")
PORT = int(os.getenv("PORT", 5007))
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "vector-search-poc")
REGION = os.getenv("GCP_REGION", "us-central1")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Heuristic mapping for reliable chaos testing - Bypasses Platform Agents
COMMAND_MAP = {
    "1_break": ["run", "services", "delete", "calculator-app", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "1_restore": ["run", "deploy", "calculator-app", "--image", f"us-central1-docker.pkg.dev/{PROJECT_ID}/cloud-run-source-deploy/calculator-app", "--project", PROJECT_ID, "--region", REGION, "--platform", "managed", "--allow-unauthenticated", "--quiet"],
    
    "2_break": ["run", "services", "remove-iam-policy-binding", "calculator-app", "--member", "allUsers", "--role", "roles/run.invoker", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "2_restore": ["run", "services", "add-iam-policy-binding", "calculator-app", "--member", "allUsers", "--role", "roles/run.invoker", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    
    "3_break": ["run", "deploy", "calculator-app", "--image", "gcr.io/google-containers/pause:1.0", "--project", PROJECT_ID, "--region", REGION, "--no-traffic", "--quiet"],
    "3_restore": ["run", "deploy", "calculator-app", "--image", f"us-central1-docker.pkg.dev/{PROJECT_ID}/cloud-run-source-deploy/calculator-app", "--project", PROJECT_ID, "--region", REGION, "--to-latest", "--quiet"],
    
    "4_break": ["run", "services", "update-traffic", "calculator-app", "--to-revisions", "LATEST=0", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "4_restore": ["run", "services", "update-traffic", "calculator-app", "--to-latest", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    
    "5_break": ["run", "services", "update", "calculator-app", "--memory", "64Mi", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "5_restore": ["run", "services", "update", "calculator-app", "--memory", "512Mi", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    
    "6_break": ["run", "services", "update", "calculator-app", "--concurrency", "1", "--max-instances", "1", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "6_restore": ["run", "services", "update", "calculator-app", "--concurrency", "default", "--clear-max-instances", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    
    "7_break": ["run", "services", "update", "calculator-app", "--set-env-vars", "DB_CONNECTION_STRING=invalid_host:5432", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "7_restore": ["run", "services", "update", "calculator-app", "--remove-env-vars", "DB_CONNECTION_STRING", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    
    "8_break": ["run", "services", "update", "calculator-app", "--ingress", "internal", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "8_restore": ["run", "services", "update", "calculator-app", "--ingress", "all", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    
    "9_break": ["run", "services", "update", "calculator-app", "--min-instances", "0", "--max-instances", "1", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "9_restore": ["run", "services", "update", "calculator-app", "--min-instances", "1", "--clear-max-instances", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    
    "10_break": ["run", "services", "delete", "calculator-app", "--project", PROJECT_ID, "--region", REGION, "--quiet"],
    "10_restore": ["run", "deploy", "calculator-app", "--image", f"us-central1-docker.pkg.dev/{PROJECT_ID}/cloud-run-source-deploy/calculator-app", "--project", PROJECT_ID, "--region", REGION, "--platform", "managed", "--allow-unauthenticated", "--quiet"],
}

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "agent": "chaos-monkey-v2", "mcp_enabled": True})

@app.route('/scenarios', methods=['GET'])
def list_scenarios():
    # Convert dictionary to list of dicts with 'id' for the UI
    scenario_list = []
    for sid, data in SCENARIOS.items():
        item = data.copy()
        item['id'] = sid
        scenario_list.append(item)
    
    # Sort by ID to keep consistent order
    scenario_list.sort(key=lambda x: int(x['id']) if x['id'].isdigit() else x['id'])
    return jsonify(scenario_list)

async def _execute_action_logic(scenario_id, action_type):
    # Normalize scenario_id
    sid = str(scenario_id) if scenario_id else "unknown"
    key = f"{sid}_{action_type}"
    
    if key in COMMAND_MAP:
        logger.info(f"Direct MCP Execution: {key}")
        result = await execute_gcloud_command(COMMAND_MAP[key])
        return result
    else:
        # Fallback for dynamic prompts
        scenario = next((s for s in SCENARIOS if s["id"] == sid), None)
        prompt = scenario[f"{action_type}_prompt"] if scenario else f"Action {action_type} for scenario {sid}"
        
        try:
            payload = {
                "prompt": prompt, 
                "session_id": f"chaos-{sid}", 
                "user_email": "robin@cloudroaster.com"
            }
            headers = {
                "X-User-Email": "robin@cloudroaster.com",
                "Content-Type": "application/json"
            }
            logger.info(f"Fallback Orchestrator Execution: {prompt}")
            response = requests.post(ORCHESTRATOR_URL, json=payload, headers=headers, timeout=60)
            orchestrator_data = response.json()
            return {
                "success": orchestrator_data.get("success", True),
                "response": orchestrator_data.get("response", orchestrator_data),
                "orchestrator_response": orchestrator_data # Compatibility
            }
        except Exception as e:
            logger.error(f"Orchestrator fallback failed: {e}")
            return {"error": f"Orchestrator failed: {str(e)}"}

@app.route('/execute', methods=['POST'])
def execute_scenario():
    data = request.json
    # Handle both 'id' and 'scenario_id' for backward compatibility
    scenario_id = data.get('scenario_id') or data.get('id')
    action_type = data.get('action') # 'break' or 'restore'

    # Run the async logic in the loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_execute_action_logic(scenario_id, action_type))
    
    return jsonify(result)

@app.route('/reply', methods=['POST'])
def reply_to_orchestrator():
    """Forwards user replies (diagnosis) to the orchestrator"""
    data = request.json
    scenario_id = data.get('scenario_id') or data.get('id', 'default')
    
    payload = {
        "prompt": data.get('message'),
        "session_id": f"chaos-{scenario_id}",
        "user_email": "robin@cloudroaster.com"
    }
    headers = {
        "X-User-Email": "robin@cloudroaster.com",
        "Content-Type": "application/json"
    }
    
    logger.info(f"Forwarding reply to Orchestrator: {payload['prompt']}")
    try:
        response = requests.post(ORCHESTRATOR_URL, json=payload, headers=headers, timeout=60)
        orchestrator_data = response.json()
        
        # Ensure we return a consistent structure that the UI expects
        return jsonify({
            "success": orchestrator_data.get("success", True),
            "response": orchestrator_data.get("response", orchestrator_data),
            "orchestrator_response": orchestrator_data # For backward compatibility with old UI if cached
        })
    except Exception as e:
        logger.error(f"Reply failed: {e}")
        return jsonify({"error": f"Monkey Agent failed to forward reply: {str(e)}"}), 500

if __name__ == '__main__':
    logger.info(f"Chaos Monkey Agent starting on port {PORT}...")
    logger.info(f"Orchestrator URL: {ORCHESTRATOR_URL}")
    app.run(host='0.0.0.0', port=PORT)
