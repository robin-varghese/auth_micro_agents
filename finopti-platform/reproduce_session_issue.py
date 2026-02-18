
import requests
import json
import uuid
import time
import os

# Configuration
ORCHESTRATOR_URL = "http://localhost:8084"
GCLOUD_AGENT_URL = "http://localhost:5001"
MONITORING_AGENT_URL = "http://localhost:5002"
session_id = str(uuid.uuid4())
user_email = "robin@cloudroaster.com"

def verify_agent_propagation(agent_name, url):
    print(f"\n[Test] Verifying OAuth Token Propagation to {agent_name} Agent...")
    print(f"Session ID: {session_id}")
    
    # Mock OAuth Token
    token = "ya29.a0Ax...MockToken"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": str(uuid.uuid4())
    }
    
    payload = {
        "prompt": "list metrics" if agent_name == "Monitoring" else "list my compute instances",
        "user_email": user_email,
        "session_id": session_id,
        "project_id": "vector-search-poc"
    }
    
    try:
        print(f"Sending request to {url}/execute with Authorization header...")
        response = requests.post(f"{url}/execute", json=payload, headers=headers, timeout=20)
        
        if response.status_code == 200:
            print(f"✅ {agent_name} Agent accepted request with Auth Token")
            resp_json = response.json()
            print(f"Response: {str(resp_json.get('response'))[:100]}...")
        else:
            print(f"❌ {agent_name} Agent failed: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Request failed for {agent_name}: {e}")

if __name__ == "__main__":
    verify_agent_propagation("GCloud", GCLOUD_AGENT_URL)
    verify_agent_propagation("Monitoring", MONITORING_AGENT_URL)
