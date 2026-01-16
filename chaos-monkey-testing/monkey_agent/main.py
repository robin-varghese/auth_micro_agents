import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from scenarios import SCENARIOS

# Configuration
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://apisix:9080/orchestrator/ask")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Logging setup
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("monkey_agent")

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "chaos-monkey-agent"}), 200

@app.route('/scenarios', methods=['GET'])
def list_scenarios():
    """Returns the list of available chaos scenarios with full details."""
    serialized = []
    for id, data in SCENARIOS.items():
        serialized.append({
            "id": id,
            "name": data["name"],
            "description": data["description"],
            "technical_explanation": data.get("technical_explanation", ""),
            "steps": data.get("steps", [])
        })
    return jsonify(serialized)

@app.route('/execute', methods=['POST'])
def execute_scenario():
    """
    Executes a 'break' or 'restore' action for a given scenario.
    Calls the central Orchestrator to perform the actual work.
    """
    data = request.json
    scenario_id = data.get("id")
    action = data.get("action")  # 'break' or 'restore'
    user_email = "robin@cloudroaster.com" # Force authorized user for testing

    if not scenario_id or action not in ['break', 'restore']:
        return jsonify({"error": "Invalid parameters. Need 'id' and 'action' (break/restore)"}), 400

    scenario = SCENARIOS.get(str(scenario_id))
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404

    # Select the prompt
    prompt = scenario["break_prompt"] if action == "break" else scenario["restore_prompt"]
    
    logger.info(f"Executing Scenario {scenario_id} [{action}]: {prompt}")

    try:
        # Call FinOpti Orchestrator
        payload = {
            "prompt": prompt
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-User-Email": user_email,
            "X-Request-ID": f"chaos-{str(scenario_id)}-{action}"
        }
        
        response = requests.post(
            ORCHESTRATOR_URL, 
            json=payload, 
            headers=headers,
            timeout=600
        )
        
        response.raise_for_status()
        orchestrator_data = response.json()

        return jsonify({
            "status": "success",
            "scenario": scenario["name"],
            "action": action,
            "orchestrator_response": orchestrator_data
        })

    except Exception as e:
        logger.error(f"Failed to execute chaos: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 502

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5007))
    app.run(host='0.0.0.0', port=port)
