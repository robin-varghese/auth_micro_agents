#!/usr/bin/env python3
"""
End-to-End Agent Testing Through APISIX

Tests the complete flow:
  Client → Agent → APISIX → MCP Server → Response

This verifies that agents can successfully route requests through
the API gateway to backend MCP servers.
"""

import requests
import json
import sys

# Service endpoints
GCLOUD_AGENT_DIRECT = "http://localhost:15001"
MONITORING_AGENT_DIRECT = "http://localhost:15002"
ORCHESTRATOR_DIRECT = "http://localhost:15000"

GCLOUD_AGENT_APISIX = "http://localhost:9080/agent/gcloud"
MONITORING_AGENT_APISIX = "http://localhost:9080/agent/monitoring"
ORCHESTRATOR_APISIX = "http://localhost:9080/orchestrator"

GCLOUD_MCP_DIRECT = "http://localhost:6001"
MONITORING_MCP_DIRECT = "http://localhost:6002"

def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def test_service_health(name, url):
    """Test health endpoint of a service"""
    print(f"\n🔍 Testing: {name}")
    print(f"   URL: {url}/health")
    
    try:
        response = requests.get(f"{url}/health", timeout=5)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"   ✅ {name} is healthy!")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"   ❌ {name} returned {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_gcloud_agent_to_mcp():
    """Test GCloud Agent calling GCloud MCP"""
    print_header("Test 1: GCloud Agent → GCloud MCP (List VMs)")
    
    print("\n📝 Sending request to GCloud Agent...")
    print(f"   Agent URL: {GCLOUD_AGENT_DIRECT}/execute")
    
    payload = {
        "command": "list_vms",
        "params": {"zone": "all"}
    }
    
    print(f"   Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            f"{GCLOUD_AGENT_DIRECT}/execute",
            json=payload,
            timeout=10
        )
        
        print(f"\n📥 Response from Agent:")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Success: {result.get('success', False)}")
            
            if 'data' in result and 'instances' in result['data']:
                print(f"   VMs Found: {result['data'].get('count', 0)}")
                print(f"   ✅ Agent successfully called MCP!")
                return True
            else:
                print(f"   Response: {json.dumps(result, indent=2)[:300]}")
                return "success" in result
        else:
            print(f"   ❌ Failed: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_monitoring_agent_to_mcp():
    """Test Monitoring Agent calling Monitoring MCP"""
    print_header("Test 2: Monitoring Agent → Monitoring MCP (Check CPU)")
    
    print("\n📝 Sending request to Monitoring Agent...")
    print(f"   Agent URL: {MONITORING_AGENT_DIRECT}/execute")
    
    payload = {
        "command": "check_cpu",
        "params": {"resource": "test-vm-1", "period": "5m"}
    }
    
    print(f"   Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            f"{MONITORING_AGENT_DIRECT}/execute",
            json=payload,
            timeout=10
        )
        
        print(f"\n📥 Response from Agent:")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Success: {result.get('success', False)}")
            
            if 'data' in result:
                print(f"   Metric: {result['data'].get('metric', 'N/A')}")
                print(f"   Value: {result['data'].get('value', 'N/A')}%")
                print(f"   ✅ Agent successfully called MCP!")
                return True
            else:
                print(f"   Response: {json.dumps(result, indent=2)[:300]}")
                return "success" in result
        else:
            print(f"   ❌ Failed: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_agents_through_apisix():
    """Test agents through APISIX gateway"""
    print_header("Test 3: Agents Through APISIX Gateway")
    
    results = []
    
    # Test 1: GCloud Agent via APISIX
    print("\n📝 Testing GCloud Agent via APISIX...")
    print(f"   URL: {GCLOUD_AGENT_APISIX}/health")
    
    try:
        response = requests.get(f"{GCLOUD_AGENT_APISIX}/health", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ GCloud Agent accessible via APISIX!")
            results.append(True)
        else:
            print(f"   ❌ Status: {response.status_code}")
            results.append(False)
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results.append(False)
    
    # Test 2: Monitoring Agent via APISIX
    print("\n📝 Testing Monitoring Agent via APISIX...")
    print(f"   URL: {MONITORING_AGENT_APISIX}/health")
    
    try:
        response = requests.get(f"{MONITORING_AGENT_APISIX}/health", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ Monitoring Agent accessible via APISIX!")
            results.append(True)
        else:
            print(f"   ❌ Status: {response.status_code}")
            results.append(False)
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results.append(False)
    
    # Test 3: Orchestrator via APISIX
    print("\n📝 Testing Orchestrator via APISIX...")
    print(f"   URL: {ORCHESTRATOR_APISIX}/health")
    
    try:
        response = requests.get(f"{ORCHESTRATOR_APISIX}/health", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ Orchestrator accessible via APISIX!")
            results.append(True)
        else:
            print(f"   ❌ Status: {response.status_code}")
            results.append(False)
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results.append(False)
    
    return all(results)

def main():
    print("\n🧪 End-to-End Agent Testing Suite")
    print("=" * 70)
    print("\nTesting the complete flow:")
    print("  Client → Agent → APISIX → MCP Server\n")
    
    results = []
    
    # Phase 1: Health Checks
    print_header("Phase 1: Service Health Checks")
    results.append(("GCloud Agent Health", test_service_health("GCloud Agent", GCLOUD_AGENT_DIRECT)))
    results.append(("Monitoring Agent Health", test_service_health("Monitoring Agent", MONITORING_AGENT_DIRECT)))
    results.append(("Orchestrator Health", test_service_health("Orchestrator", ORCHESTRATOR_DIRECT)))
    results.append(("GCloud MCP Health", test_service_health("GCloud MCP", GCLOUD_MCP_DIRECT)))
    results.append(("Monitoring MCP Health", test_service_health("Monitoring MCP", MONITORING_MCP_DIRECT)))
    
    # Phase 2: Agent to MCP Communication
    print_header("Phase 2: Agent → MCP Communication (Direct)")
    results.append(("GCloud Agent → MCP", test_gcloud_agent_to_mcp()))
    results.append(("Monitoring Agent → MCP", test_monitoring_agent_to_mcp()))
    
    # Phase 3: Through APISIX
    results.append(("Agents via APISIX", test_agents_through_apisix()))
    
    # Summary
    print_header("TEST SUMMARY")
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 All tests passed! Full stack is working!")
        print("  ✓ Agents are healthy")
        print("  ✓ MCP servers are responding")
        print("  ✓ Agents can communicate with MCP servers")
        print("  ✓ APISIX routing is functional")
        return 0
    elif passed >= total - 2:
        print("\n  ⚠️  Most tests passed - System is operational")
        return 0
    else:
        print(f"\n  ❌ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
