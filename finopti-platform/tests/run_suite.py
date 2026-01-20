import os
import sys
import requests
import time
import json
import logging
import concurrent.futures
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("TestRunner")

# Configuration
APISIX_URL = os.getenv("APISIX_URL", "http://localhost:9080")
SUB_AGENTS_DIR = Path(__file__).parent.parent / "sub_agents"

def check_apisix_health():
    """Verify APISIX is reachable."""
    try:
        # Just check the root or a known health endpoint
        # Using /agent/filesystem as a probe since it's lightweight
        resp = requests.get(f"{APISIX_URL}/agent/filesystem/health", timeout=5)
        # Even a 404 means the gateway is running, connection refused implies it's down
        logger.info(f"APISIX Connectivity Check: Status {resp.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        logger.error(f"Cannot connect to APISIX at {APISIX_URL}. Is it running?")
        return False
    except Exception as e:
        logger.warning(f"APISIX check warning: {e}")
        return True # Proceed anyway as it might just be the health route missing

def run_verification_script(script_path):
    """Executes a single verify_agent.py script."""
    agent_name = script_path.parent.name
    logger.info(f"Testing Agent: {agent_name}...")
    
    try:
        # Using os.system or subprocess to run the script in its own environment
        # passing APISIX_URL as env var
        exit_code = os.system(f"APISIX_URL={APISIX_URL} python3 {script_path}")
        
        if exit_code == 0:
            logger.info(f"✅ PASS: {agent_name}")
            return True
        else:
            logger.error(f"❌ FAIL: {agent_name} (Exit Code: {exit_code})")
            return False
    except Exception as e:
        logger.error(f"❌ ERROR: {agent_name} - {str(e)}")
        return False

import subprocess

def get_gcloud_val(command):
    try:
        return subprocess.check_output(command, shell=True).decode().strip()
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to run gcloud command '{command}': {e}")
        return None

def fetch_credentials():
    logger.info("Fetching credentials from gcloud and Secret Manager...")
    
    # 1. Project ID
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        project_id = get_gcloud_val("gcloud config get-value project")
        if project_id:
            os.environ["GCP_PROJECT_ID"] = project_id
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            logger.info(f"Loaded Project ID: {project_id}")
    
    if not project_id:
        logger.error("Could not determine GCP Project ID. Please set GCP_PROJECT_ID.")
        return

    # 2. OAuth Token
    token = get_gcloud_val("gcloud auth print-access-token")
    if token:
        os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"] = token
        logger.info("Loaded Google OAuth Token.")
        
    # 3. Google API Key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        api_key = get_gcloud_val(f"gcloud secrets versions access latest --secret='google-api-key' --project='{project_id}'")
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key
            logger.info("Loaded Google API Key from Secret Manager.")

    # 4. GitHub Token
    gh_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not gh_token:
        gh_token = get_gcloud_val(f"gcloud secrets versions access latest --secret='github-personal-access-token' --project='{project_id}'")
        if gh_token:
            os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = gh_token
            logger.info("Loaded GitHub Token from Secret Manager.")

def main():
    logger.info("Starting FinOpti Platform Test Suite...")
    
    # 0. Setup Credentials
    fetch_credentials()
    
    # 1. Check Gateway
    if not check_apisix_health():
        logger.error("Aborting tests due to Gateway unreachable.")
        sys.exit(1)
        
    # 2. Find Verification Scripts
    verification_scripts = list(SUB_AGENTS_DIR.glob("*/verify_agent.py"))
    
    # Filter out skipped agents
    SKIP_AGENTS = ["brave_search_agent_adk"]
    verification_scripts = [s for s in verification_scripts if s.parent.name not in SKIP_AGENTS]
    
    if not verification_scripts:
        logger.warning("No verification scripts found in sub_agents directories.")
        sys.exit(0)
        
    logger.info(f"Found {len(verification_scripts)} agents to test.")
    
    # 3. Run Tests
    results = {}
    passed = 0
    failed = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_to_agent = {executor.submit(run_verification_script, script): script.parent.name for script in sorted(verification_scripts)}
        for future in concurrent.futures.as_completed(future_to_agent):
            agent = future_to_agent[future]
            try:
                success = future.result()
                results[agent] = success
                if success:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"❌ EXCEPTION: {agent} - {e}")
                results[agent] = False
                failed += 1
            
    # 4. Summary
    logger.info("-" * 40)
    logger.info("TEST SUMMARY")
    logger.info("-" * 40)
    for agent, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status}: {agent}")
        
    logger.info("-" * 40)
    logger.info(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
