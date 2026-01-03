#!/usr/bin/env python3
"""
Test GCloud MCP Server (JSON-RPC 2.0 Format)

Tests the deployed mock gcloud MCP server using JSON-RPC format.
"""

import requests
import json

MCP_SERVER_URL = "http://localhost:6001"

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

def test_list_vms():
    """Test list VMs using JSON-RPC"""
    print("=" * 60)
    print("Test 2: List VMs (JSON-RPC)")
    print("=" * 60)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "list_vms",
        "params": {"zone": "all"},
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

def test_create_vm():
    """Test create VM using JSON-RPC"""
    print("=" * 60)
    print("Test 3: Create VM (JSON-RPC)")
    print("=" * 60)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "create_vm",
        "params": {
            "instance_name": "test-vm-001",
            "zone": "us-central1-a",
            "machine_type": "e2-micro"
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

def test_delete_vm():
    """Test delete VM using JSON-RPC"""
    print("=" * 60)
    print("Test 4: Delete VM (JSON-RPC)")
    print("=" * 60)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "delete_vm",
        "params": {
            "instance_name": "test-vm-001",
            "zone": "us-central1-a"
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

if __name__ == "__main__":
    print("\n🧪 Testing GCloud MCP Server (Mock - JSON-RPC 2.0)\n")
    print(f"MCP Server: {MCP_SERVER_URL}\n")
    
    results = []
    
    # Run tests
    results.append(("Health Check", test_health()))
    results.append(("List VMs", test_list_vms()))
    results.append(("Create VM", test_create_vm()))
    results.append(("Delete VM", test_delete_vm()))
    
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
        print("\n🎉 All tests passed! GCloud MCP Server is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
    print()
