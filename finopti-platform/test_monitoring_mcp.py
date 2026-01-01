#!/usr/bin/env python3
"""
Test Monitoring MCP Server (JSON-RPC 2.0 Format)

Tests the deployed mock monitoring MCP server using JSON-RPC format.
"""

import requests
import json

MCP_SERVER_URL = "http://localhost:6002"

def test_health():
    """Test health endpoint"""
    print("=" * 60)
    print("Test 1: Health Check")
    print("=" * 60)
    
    response = requests.get(f"{MCP_SERVER_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    print()
    return response.status_code == 200

def test_check_cpu():
    """Test CPU check using JSON-RPC"""
    print("=" * 60)
    print("Test 2: Check CPU Usage (JSON-RPC)")
    print("=" * 60)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "check_cpu",
        "params": {
            "resource": "vm-instance-1",
            "period": "5m"
        },
        "id": 1
    }
    
    print(f"Sending: {json.dumps(payload, indent=2)}")
    response = requests.post(MCP_SERVER_URL, json=payload)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        return "result" in result and result["result"].get("success", False)
    else:
        print(f"Failed: {response.text[:200]}")
        return False

def test_check_memory():
    """Test Memory check using JSON-RPC"""
    print("=" * 60)
    print("Test 3: Check Memory Usage (JSON-RPC)")
    print("=" * 60)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "check_memory",
        "params": {
            "resource": "vm-instance-1",
            "period": "10m"
        },
        "id": 2
    }
    
    print(f"Sending: {json.dumps(payload, indent=2)}")
    response = requests.post(MCP_SERVER_URL, json=payload)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        return "result" in result and result["result"].get("success", False)
    else:
        print(f"Failed: {response.text[:200]}")
        return False

def test_query_logs():
    """Test log query using JSON-RPC"""
    print("=" * 60)
    print("Test 4: Query Logs (JSON-RPC)")
    print("=" * 60)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "query_logs",
        "params": {
            "filter": "severity>=ERROR",
            "limit": 5
        },
        "id": 3
    }
    
    print(f"Sending: {json.dumps(payload, indent=2)}")
    response = requests.post(MCP_SERVER_URL, json=payload)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        return "result" in result and result["result"].get("success", False)
    else:
        print(f"Failed: {response.text[:200]}")
        return False

def test_get_metrics():
    """Test get metrics using JSON-RPC"""
    print("=" * 60)
    print("Test 5: Get Metrics (JSON-RPC)")
    print("=" * 60)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "get_metrics",
        "params": {
            "metric_type": "cpu_utilization"
        },
        "id": 4
    }
    
    print(f"Sending: {json.dumps(payload, indent=2)}")
    response = requests.post(MCP_SERVER_URL, json=payload)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        return "result" in result and result["result"].get("success", False)
    else:
        print(f"Failed: {response.text[:200]}")
        return False

if __name__ == "__main__":
    print("\n🧪 Testing Monitoring MCP Server (Mock - JSON-RPC 2.0)\n")
    print(f"MCP Server: {MCP_SERVER_URL}\n")
    
    results = []
    
    # Run tests
    results.append(("Health Check", test_health()))
    results.append(("Check CPU", test_check_cpu()))
    results.append(("Check Memory", test_check_memory()))
    results.append(("Query Logs", test_query_logs()))
    results.append(("Get Metrics", test_get_metrics()))
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 All tests passed! Monitoring MCP Server is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
    print()
