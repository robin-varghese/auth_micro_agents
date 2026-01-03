#!/usr/bin/env python3
"""
Test New MCP Agents via APISIX

This script verifies that the new GitHub, Storage, and Database agents are:
1. Reachable via APISIX (port 9080).
2. Healthy.
3. Capable of processing basic requests.
"""

import requests
import json
import time

APISIX_URL = "http://localhost:9080"

AGENTS = {
    "github": {
        "health": "/agent/github/health",
        "execute": "/agent/github/execute",
        "test_prompt": "Search for repositories related to 'mcp-server'"
    },
    "storage": {
        "health": "/agent/storage/health",
        "execute": "/agent/storage/execute",
        "test_prompt": "List all buckets in the project"
    },
    "db": {
        "health": "/agent/db/health",
        "execute": "/agent/db/execute",
        "test_prompt": "List all tables in the database"
    }
}

def test_agent_health(agent_name, endpoint):
    """Test agent health endpoint via APISIX"""
    url = f"{APISIX_URL}{endpoint}"
    print(f"Checking {agent_name} health at {url}...")
    try:
        response = requests.get(url, timeout=5)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Health Check Passed")
            return True
        else:
            print(f"❌ Health Check Failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

def test_agent_execution(agent_name, endpoint, prompt):
    """Test agent execution endpoint via APISIX"""
    url = f"{APISIX_URL}{endpoint}"
    print(f"Testing {agent_name} execution at {url}...")
    payload = {
        "prompt": prompt,
        "user_email": "admin@cloudroaster.com" # Authorized user
    }
    
    try:
        print(f"Sending prompt: '{prompt}'")
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            if data.get("success", False):
                print("✅ Execution Passed")
                return True
            else:
                print("❌ Execution Failed (Logic Error)")
                return False
        else:
            print(f"❌ Execution Failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Connection/Timeout Error: {e}")
        return False

if __name__ == "__main__":
    print("\n🚀 Testing New MCP Agents via APISIX\n")
    
    results = []
    
    for agent, config in AGENTS.items():
        print(f"\n--- Testing Agent: {agent.upper()} ---")
        
        # 1. Health Check
        health_passed = test_agent_health(agent, config["health"])
        results.append((f"{agent}_health", health_passed))
        
        if health_passed:
            # 2. Execution Test
            # Note: This might require valid credentials/mocking to fully succeed,
            # but we at least verify the agent receives and processes the request.
            exec_passed = test_agent_execution(agent, config["execute"], config["test_prompt"])
            results.append((f"{agent}_execution", exec_passed))
        else:
            print(f"Skipping execution test for {agent} due to health failure.")
            results.append((f"{agent}_execution", False))
            
    print("\n" + "="*40)
    print("TEST SUMMARY")
    print("="*40)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
        
    print("\nNote: Failures might be expected if containers are not running or credentials are missing.")
