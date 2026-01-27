"""
MATS Test Suite Runner

Tests MATS Orchestrator and Team Lead agents (SRE, Investigator, Architect).
Follows the pattern from tests/run_suite.py
"""
import os
import sys
import requests
import time
import json
import logging
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MATSTestRunner")

# Configuration
ORCHESTRATOR_URL = os.getenv("MATS_ORCHESTRATOR_URL", "http://localhost:8084")
APISIX_URL = os.getenv("APISIX_URL", "http://localhost:9080")

# Test scenarios
TEST_SCENARIOS = [
    {
        "name": "Health Check - Orchestrator",
        "type": "health",
        "url": f"{ORCHESTRATOR_URL}/health",
        "expected_status": 200
    },
    {
        "name": "Health Check - SRE Agent",
        "type": "health",
        "url": "http://localhost:8081/health",
        "expected_status": 200
    },
    {
        "name": "Health Check - Investigator Agent",
        "type": "health",
        "url": "http://localhost:8082/health",
        "expected_status": 200
    },
    {
        "name": "Health Check - Architect Agent",
        "type": "health",
        "url": "http://localhost:8083/health",
        "expected_status": 200
    },
    {
        "name": "Direct Troubleshoot Request",
        "type": "troubleshoot",
        "url": f"{ORCHESTRATOR_URL}/troubleshoot",
        "payload": {
            "user_request": "Test troubleshooting request for Cloud Run service",
            "project_id": "test-project",
            "repo_url": "https://github.com/test/repo"
        },
        "expected_fields": ["status", "session_id"],
        "timeout": 300
    },
    {
        "name": "APISIX Route Test",
        "type": "troubleshoot",
        "url": f"{APISIX_URL}/mats/orchestrator/troubleshoot",
        "payload": {
            "user_request": "Debug Cloud Run errors",
            "project_id": "test-project",
            "repo_url": "https://github.com/test/repo"
        },
        "expected_fields": ["status"],
        "timeout": 300,
        "optional": True  # May not be configured yet
    }
]


def run_health_check(scenario):
    """Test health endpoint"""
    logger.info(f"Testing: {scenario['name']}")
    try:
        resp = requests.get(scenario['url'], timeout=5)
        if resp.status_code == scenario['expected_status']:
            logger.info(f"✅ PASS: {scenario['name']} (Status: {resp.status_code})")
            return True
        else:
            logger.error(f"❌ FAIL: {scenario['name']} (Expected {scenario['expected_status']}, got {resp.status_code})")
            return False
    except requests.exceptions.ConnectionError:
        if scenario.get('optional'):
            logger.warning(f"⚠️ SKIP: {scenario['name']} (Service not available - optional)")
            return True
        logger.error(f"❌ FAIL: {scenario['name']} (Connection refused)")
        return False
    except Exception as e:
        logger.error(f"❌ ERROR: {scenario['name']} - {str(e)}")
        return False


def run_troubleshoot_test(scenario):
    """Test troubleshoot endpoint"""
    logger.info(f"Testing: {scenario['name']}")
    try:
        resp = requests.post(
            scenario['url'],
            json=scenario['payload'],
            timeout=scenario.get('timeout', 300),
            headers={"Content-Type": "application/json"}
        )
        
        if resp.status_code != 200:
            if scenario.get('optional'):
                logger.warning(f"⚠️ SKIP: {scenario['name']} (Status {resp.status_code} - optional)")
                return True
            logger.error(f"❌ FAIL: {scenario['name']} (Status: {resp.status_code})")
            logger.error(f"Response: {resp.text[:500]}")
            return False
        
        try:
            result = resp.json()
        except json.JSONDecodeError:
            logger.error(f"❌ FAIL: {scenario['name']} (Invalid JSON response)")
            return False
        
        # Check expected fields
        missing_fields = [f for f in scenario.get('expected_fields', []) if f not in result]
        if missing_fields:
            logger.error(f"❌ FAIL: {scenario['name']} (Missing fields: {missing_fields})")
            logger.error(f"Response: {json.dumps(result, indent=2)[:500]}")
            return False
        
        logger.info(f"✅ PASS: {scenario['name']}")
        logger.info(f"Response snippet: status={result.get('status')}, session_id={result.get('session_id', 'N/A')[:8]}...")
        return True
        
    except requests.exceptions.Timeout:
        logger.error(f"❌ FAIL: {scenario['name']} (Timeout after {scenario.get('timeout')}s)")
        return False
    except requests.exceptions.ConnectionError:
        if scenario.get('optional'):
            logger.warning(f"⚠️ SKIP: {scenario['name']} (Connection refused - optional)")
            return True
        logger.error(f"❌ FAIL: {scenario['name']} (Connection refused)")
        return False
    except Exception as e:
        logger.error(f"❌ ERROR: {scenario['name']} - {str(e)}")
        return False


def run_verification_script(script_path):
    """Run official mats-orchestrator/verify_agent.py"""
    logger.info("Running official verification script...")
    try:
        env = os.environ.copy()
        env["APISIX_URL"] = APISIX_URL
        
        result = subprocess.run(
            ["python3", str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            logger.error(f"❌ FAIL: Official verification script")
            logger.error(f"Stdout: {result.stdout}")
            logger.error(f"Stderr: {result.stderr}")
            return False
        
        logger.info(f"✅ PASS: Official verification script")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"❌ FAIL: Verification script timed out")
        return False
    except Exception as e:
        logger.error(f"❌ ERROR: Verification script - {str(e)}")
        return False


def main():
    logger.info("=" * 60)
    logger.info("MATS Test Suite Runner")
    logger.info("=" * 60)
    logger.info("")
    
    # Check connectivity
    logger.info("Pre-flight checks...")
    try:
        resp = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=5)
        logger.info(f"✅ MATS Orchestrator reachable")
    except Exception as e:
        logger.error(f"❌ Cannot reach MATS Orchestrator at {ORCHESTRATOR_URL}")
        logger.error(f"Error: {e}")
        logger.error("Please ensure MATS services are running (./deploy_mats_local.sh)")
        return 1
    
    logger.info("")
    
    # Run test scenarios
    results = []
    for scenario in TEST_SCENARIOS:
        if scenario['type'] == 'health':
            passed = run_health_check(scenario)
        elif scenario['type'] == 'troubleshoot':
            passed = run_troubleshoot_test(scenario)
        else:
            logger.warning(f"⚠️ Unknown test type: {scenario['type']}")
            passed = False
        
        results.append({
            "name": scenario['name'],
            "passed": passed
        })
        logger.info("")
    
    # Run official verification script if exists
    verify_script = Path(__file__).parent.parent / "mats-agents/mats-orchestrator/verify_agent.py"
    if verify_script.exists():
        passed = run_verification_script(verify_script)
        results.append({
            "name": "Official Verification Script",
            "passed": passed
        })
    else:
        logger.warning(f"⚠️ Official verification script not found at {verify_script}")
    
    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    total = len(results)
    passed = sum(1 for r in results if r['passed'])
    failed = total - passed
    
    for result in results:
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        logger.info(f"{status}: {result['name']}")
    
    logger.info("")
    logger.info(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    logger.info("=" * 60)
    
    if failed == 0:
        logger.info("🎉 All tests passed!")
        return 0
    else:
        logger.error(f"❌ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
