#!/usr/bin/env python3
"""
Orchestrator Agent Test

Tests the Orchestrator's ability to:
1. Receive requests via APISIX
2. Detect intent from natural language
3. Route to appropriate sub-agent
4. Sub-agent calls MCP via APISIX
5. Return consolidated response

Flow: Client → APISIX → Orchestrator → APISIX → Agent → APISIX → MCP → Response
"""

import requests
import json
import time

# Endpoints
ORCHESTRATOR_DIRECT = "http://localhost:15000"
ORCHESTRATOR_APISIX = "http://localhost:9080/orchestrator"
APISIX_GATEWAY = "http://localhost:9080"

def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def test_orchestrator_health():
    """Test Orchestrator health via APISIX"""
    print_section("Test 1: Orchestrator Health Check")
    
    print("\n📍 Testing via APISIX Gateway")
    print(f"   URL: {ORCHESTRATOR_APISIX}/health")
    
    response = requests.get(f"{ORCHESTRATOR_APISIX}/health", timeout=5)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    return response.status_code == 200

def test_orchestrator_gcloud_routing():
    """Test Orchestrator routing GCloud request"""
    print_section("Test 2: Orchestrator Routes GCloud Request")
    
    print("\n📝 Flow: Client → APISIX → Orchestrator → GCloud Agent → MCP")
    
    payload = {
        "prompt": "list all my virtual machines",
        "user_email": "admin@cloudroaster.com"
    }
    
    print(f"\n1️⃣  Client sends to Orchestrator (via APISIX):")
    print(f"   URL: {ORCHESTRATOR_APISIX}/ask")
    print(f"   Prompt: '{payload['prompt']}'")
    
    # Add required headers
    headers = {
        "Content-Type": "application/json",
        "X-User-Email": payload["user_email"]
    }
    
    try:
        response = requests.post(
            f"{ORCHESTRATOR_APISIX}/ask",
            json=payload,
            headers=headers,
            timeout=15
        )
        
        print(f"\n2️⃣  Orchestrator Response:")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Agent Routed To: {result.get('agent', 'N/A')}")
            print(f"   User: {result.get('user_email', 'N/A')}")
            
            # Check if we got MCP response
            if 'response' in result:
                agent_response = result['response']
                print(f"\n3️⃣  Agent Response:")
                print(f"   {json.dumps(agent_response, indent=2)[:300]}...")
                
                # Verify it went through the full chain
                if 'result' in agent_response:
                    print(f"\n✅ SUCCESS: Full routing chain verified!")
                    print(f"   Client → APISIX → Orchestrator → Agent → MCP → Client")
                    return True
            
            print(f"\n   Full Response: {json.dumps(result, indent=2)}")
            return result.get('agent') == 'gcloud'
        else:
            print(f"   Error: {response.text[:300]}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_orchestrator_monitoring_routing():
    """Test Orchestrator routing Monitoring request"""
    print_section("Test 3: Orchestrator Routes Monitoring Request")
    
    print("\n📝 Flow: Client → APISIX → Orchestrator → Monitoring Agent → MCP")
    
    payload = {
        "prompt": "check the cpu usage of my servers",
        "user_email": "monitoring@cloudroaster.com"
    }
    
    print(f"\n1️⃣  Client sends to Orchestrator (via APISIX):")
    print(f"   URL: {ORCHESTRATOR_APISIX}/ask")
    print(f"   Prompt: '{payload['prompt']}'")
    
    headers = {
        "Content-Type": "application/json",
        "X-User-Email": payload["user_email"]
    }
    
    try:
        response = requests.post(
            f"{ORCHESTRATOR_APISIX}/ask",
            json=payload,
            headers=headers,
            timeout=15
        )
        
        print(f"\n2️⃣  Orchestrator Response:")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Agent Routed To: {result.get('agent', 'N/A')}")
            print(f"   User: {result.get('user_email', 'N/A')}")
            
            if 'response' in result:
                agent_response = result['response']
                print(f"\n3️⃣  Agent Response:")
                print(f"   {json.dumps(agent_response, indent=2)[:300]}...")
                
                if 'result' in agent_response:
                    print(f"\n✅ SUCCESS: Full routing chain verified!")
                    print(f"   Client → APISIX → Orchestrator → Agent → MCP → Client")
                    return True
            
            print(f"\n   Full Response: {json.dumps(result, indent=2)}")
            return result.get('agent') == 'monitoring'
        else:
            print(f"   Error: {response.text[:300]}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_direct_vs_apisix():
    """Compare direct vs APISIX access"""
    print_section("Test 4: Direct vs APISIX Access Comparison")
    
    payload = {
        "prompt": "list vms",
        "user_email": "test@cloudroaster.com"
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-User-Email": payload["user_email"]
    }
    
    # Direct access
    print("\n📍 Test 4a: Direct Access")
    print(f"   URL: {ORCHESTRATOR_DIRECT}/ask")
    try:
        response = requests.post(f"{ORCHESTRATOR_DIRECT}/ask", json=payload, headers=headers, timeout=10)
        direct_result = response.status_code == 200
        print(f"   Status: {response.status_code} - {'✅' if direct_result else '❌'}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        direct_result = False
    
    # Via APISIX
    print("\n📍 Test 4b: Via APISIX Gateway")
    print(f"   URL: {ORCHESTRATOR_APISIX}/ask")
    try:
        response = requests.post(f"{ORCHESTRATOR_APISIX}/ask", json=payload, headers=headers, timeout=10)
        apisix_result = response.status_code == 200
        print(f"   Status: {response.status_code} - {'✅' if apisix_result else '❌'}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        apisix_result = False
    
    return direct_result and apisix_result

def main():
    print("\n" + "=" * 70)
    print("🎯 Orchestrator Agent - Routing Test")
    print("=" * 70)
    print("\nVerifying:")
    print("  ✓ Orchestrator accessible via APISIX")
    print("  ✓ Intent detection working")
    print("  ✓ Routing to correct sub-agents")
    print("  ✓ Full request chain: Client → APISIX → Orch → Agent → MCP")
    
    results = []
    
    # Run tests
    results.append(("Orchestrator Health", test_orchestrator_health()))
    time.sleep(1)
    
    results.append(("GCloud Routing", test_orchestrator_gcloud_routing()))
    time.sleep(1)
    
    results.append(("Monitoring Routing", test_orchestrator_monitoring_routing()))
    time.sleep(1)
    
    results.append(("Direct vs APISIX", test_direct_vs_apisix()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 Orchestrator routing fully operational!")
        print("\n📊 Verified Flows:")
        print("  ✓ Client → APISIX → Orchestrator")
        print("  ✓ Orchestrator → Intent Detection")
        print("  ✓ Orchestrator → GCloud Agent → MCP")
        print("  ✓ Orchestrator → Monitoring Agent → MCP")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
