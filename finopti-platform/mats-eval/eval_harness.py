
import asyncio
import aiohttp
import yaml
import logging
import json
import argparse
from typing import Dict, Any, List
import sys
import os

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mats-eval-harness")

# Configuration
CHAOS_MONKEY_URL = os.getenv("CHAOS_MONKEY_URL", "http://localhost:5007")
MATS_ORCHESTRATOR_URL = os.getenv("MATS_ORCHESTRATOR_URL", "http://localhost:8084") # Start this service if not running
PROJECT_ID = "vector-search-poc"
APP_NAME = "calculator-app"
USER_EMAIL = "robin@cloudroaster.com"

def load_ground_truth(path: str = "ground_truth.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)

async def trigger_chaos(session, scenario_id: int, action: str):
    """Call Monkey Agent to Break or Restore"""
    url = f"{CHAOS_MONKEY_URL}/execute"
    payload = {
        "id": str(scenario_id),
        "action": action, 
        "user_email": USER_EMAIL
    }
    async with session.post(url, json=payload) as resp:
        if resp.status != 200:
            text = await resp.text()
            logger.error(f"Chaos {action} failed for Scenario {scenario_id}: {text}")
            return False
        logger.info(f"Chaos {action} successful for Scenario {scenario_id}")
        return True

async def query_mats(session, prompt: str):
    """Ask MATS to troubleshoot"""
    # Assuming MATS Orchestrator exposes a similar /ask or /chat endpoint.
    # Adjust URL/Payload based on actual MATS implementation.
    # Based on workflow.py, MATS orchestrator runs on port 8084 (mapped to 5000 in main platform)
    # But usually we talk to Main Orchestrator via APISIX. 
    # For DIRECT MATS usage (mats-orchestrator), let's assume direct access or via Main.
    
    # We will use the Main Orchestrator (port 5000 / APISIX 9080) which routes to MATS agents? 
    # OR talk to MATS Orchestrator directly. 
    # Let's assume we talk to the Main Platform Orchestrator which routes to SRE agent?
    # Wait, the user prompt is "check what went wrong with cloud run service..."
    # This usually hits the Main Orchestrator, which loops SRE->Investigator.
    
    url = f"http://localhost:9080/orchestrator/ask" # Through APISIX
    payload = {
        "prompt": prompt,
        "user_email": USER_EMAIL
    }
    
    headers = {"Content-Type": "application/json", "X-User-Email": USER_EMAIL}
    
    try:
        async with session.post(url, json=payload, headers=headers, timeout=300) as resp:
             if resp.status != 200:
                 logger.error(f"MATS Request failed: {resp.status}")
                 return None
             return await resp.json()
    except Exception as e:
        logger.error(f"MATS Connection failed: {e}")
        return None

def score_response(response: Dict, scenario: Dict) -> Dict:
    """Evaluate the response against ground truth"""
    if not response:
        return {"score": 0, "reason": "No response from MATS", "passed": False}
    
    # Extract the text content from the response
    # The response structure might vary. Let's assume it has 'response' key text or 'data'.
    text_output = str(response) 
    
    score = 0
    matches = []
    
    # Keyword Check
    expected_keywords = scenario.get("expected_keywords", [])
    for kw in expected_keywords:
        if kw.lower() in text_output.lower():
            score += 1
            matches.append(kw)
    
    # Normalize score (0.0 to 1.0)
    final_score = min(score / max(len(expected_keywords), 1), 1.0)
    
    return {
        "score": final_score,
        "matches": matches,
        "passed": final_score > 0.5 # Threshold
    }

async def run_scenario(session, scenario_id: int, config: Dict):
    logger.info(f"\n--- Starting Evaluation for Scenario {scenario_id}: {config['name']} ---")
    
    # 1. Break
    if not await trigger_chaos(session, scenario_id, "break"):
        return
    
    # 2. Wait for propagation
    logger.info("Waiting 30s for fault propagation...")
    await asyncio.sleep(30)
    
    # 3. Troubleshoot
    prompt = f"The service {APP_NAME} in project {PROJECT_ID} is not working. Can you check logs and code to find the root cause?"
    logger.info(f"Asking MATS: {prompt}")
    response = await query_mats(session, prompt)
    
    # 4. Score
    result = score_response(response, config)
    logger.info(f"Evaluation Result: {result}")
    
    # 5. Restore
    await trigger_chaos(session, scenario_id, "restore")
    logger.info(f"--- Scenario {scenario_id} Complete. Passed: {result['passed']} ---\n")
    
    return result

async def main():
    parser = argparse.ArgumentParser(description="MATS Evaluation Harness")
    parser.add_argument("--scenario", type=int, help="Run specific scenario ID")
    args = parser.parse_args()
    
    ground_truth = load_ground_truth("ground_truth.yaml")
    scenarios = ground_truth["scenarios"]
    
    async with aiohttp.ClientSession() as session:
        if args.scenario:
            if args.scenario in scenarios:
                 await run_scenario(session, args.scenario, scenarios[args.scenario])
            elif str(args.scenario) in scenarios:
                await run_scenario(session, args.scenario, scenarios[str(args.scenario)])
            else:
                logger.error(f"Scenario {args.scenario} not found.")
        else:
            # Run all
            for sid, config in scenarios.items():
                await run_scenario(session, int(sid), config)
                await asyncio.sleep(5) # Cooldown

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(current_dir)
    asyncio.run(main())
