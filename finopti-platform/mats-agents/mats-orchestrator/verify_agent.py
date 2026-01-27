"""
MATS Orchestrator - Verification Script

Tests the orchestrator via APISIX following AI_AGENT_DEVELOPMENT_GUIDE.md standards.
"""
import requests
import os
import sys

APISIX_URL = os.getenv("APISIX_URL", "http://localhost:9080")
AGENT_ROUTE = "/agent/mats/troubleshoot"

TEST_REQUEST = {
    "user_request": "My Cloud Run service 'test-service' in project 'test-project' is crashing with database errors",
    "project_id": "test-project",
    "repo_url": "https://github.com/test-org/test-repo"
}


def verify():
    """Verify orchestrator functionality"""
    url = f"{APISIX_URL}{AGENT_ROUTE}"
    headers = {}
    
    # Authenticate like the real platform
    token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    print(f"Testing MATS Orchestrator at: {url}")
    print(f"Request: {TEST_REQUEST}")
    
    try:
        response = requests.post(
            url,
            json=TEST_REQUEST,
            headers=headers,
            timeout=300  # 5 minutes for full investigation
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✓ Orchestrator responded successfully")
            print(f"Status: {result.get('status')}")
            print(f"Session ID: {result.get('session_id')}")
            print(f"Confidence: {result.get('confidence')}")
            print(f"RCA URL: {result.get('rca_url')}")
            
            # Validation
            required_fields = ['status', 'session_id']
            missing = [f for f in required_fields if f not in result]
            
            if missing:
                print(f"✗ Missing required fields: {missing}")
                return False
                
            print("✓ All required fields present")
            print(f"Warnings: {result.get('warnings', [])}")
            print(f"Recommendations: {result.get('recommendations', [])}")
            
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("✗ Request timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False


if __name__ == "__main__":
    success = verify()
    sys.exit(0 if success else 1)
