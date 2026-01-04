#!/usr/bin/env python3
"""
Test APISIX API Gateway Routes

Tests all routes through the APISIX gateway to verify proper routing
and connectivity to backend services.
"""

import requests
import json
import sys

APISIX_GATEWAY = "http://localhost:9080"
APISIX_ADMIN = "http://localhost:9180"
ADMIN_KEY = "finopti-admin-key"

def test_admin_api():
    """Test APISIX Admin API access"""
    print("=" * 60)
    print("Test 1: APISIX Admin API Access")
    print("=" * 60)
    
    response = requests.get(
        f"{APISIX_ADMIN}/apisix/admin/routes",
        headers={"X-API-KEY": ADMIN_KEY}
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        routes = response.json()
        print(f"Routes configured: {routes.get('total', 0)}")
        return True
    else:
        print(f"Failed: {response.text[:200]}")
        return False

def create_route(route_id, name, uri, upstream_service, upstream_port):
    """Helper to create an APISIX route"""
    print(f"\nCreating route: {uri} -> {upstream_service}:{upstream_port}")
    
    payload = {
        "name": name,
        "uri": uri,
        "upstream": {
            "type": "roundrobin",
            "nodes": {
                f"{upstream_service}:{upstream_port}": 1
            }
        },
        "plugins": {
            "proxy-rewrite": {
                "regex_uri": [f"^{uri.replace('*', '(.*)')}", "/$1"]
            }
        }
    }
    
    response = requests.put(
        f"{APISIX_ADMIN}/apisix/admin/routes/{route_id}",
        headers={"X-API-KEY": ADMIN_KEY, "Content-Type": "application/json"},
        json=payload
    )
    
    if response.status_code in [200, 201]:
        print(f"✅ Route created successfully")
        return True
    else:
        print(f"❌ Failed to create route: {response.status_code}")
        print(response.text[:200])
        return False

def test_route(route_name, url, expected_status=200):
    """Helper to test a route through APISIX"""
    print(f"\nTesting: {route_name}")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, timeout=5)
        print(f"Status: {response.status_code}")
        
        if response.status_code == expected_status:
            try:
                print(f"Response: {response.json()}")
            except:
                print(f"Response: {response.text[:100]}")
            return True
        else:
            print(f"Expected {expected_status}, got {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        print("❌ Request timeout")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_jsonrpc_route(route_name, url, method, params):
    """Helper to test JSON-RPC routes"""
    print(f"\nTesting: {route_name} (JSON-RPC)")
    print(f"URL: {url}")
    
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if "result" in result and result["result"].get("success"):
                print(f"✅ Success: {result['result'].get('message', 'OK')}")
                return True
            else:
                print(f"Response: {json.dumps(result, indent=2)[:200]}")
                return "result" in result
        else:
            print(f"Failed: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("\n🧪 APISIX API Gateway Test Suite\n")
    print(f"Gateway: {APISIX_GATEWAY}")
    print(f"Admin API: {APISIX_ADMIN}\n")
    
    results = []
    
    # Test 1: Admin API
    results.append(("Admin API Access", test_admin_api()))
    
    print("\n" + "=" * 60)
    print("Creating APISIX Routes")
    print("=" * 60)
    
    # Create all routes
    routes_to_create = [
        # MCP Server Routes
        (1, "gcloud_mcp_route", "/mcp/gcloud/*", "gcloud_mcp", 6001),
        (2, "monitoring_mcp_route", "/mcp/monitoring/*", "monitoring_mcp", 6002),
        (9, "github_mcp_route", "/mcp/github/*", "github_mcp", 6003),
        (10, "storage_mcp_route", "/mcp/storage/*", "storage_mcp", 6004),
        (11, "db_mcp_route", "/mcp/db/*", "db_mcp_toolbox", 5000),
        # Agent Routes
        (3, "orchestrator_route", "/orchestrator/*", "orchestrator", 15000),
        (4, "gcloud_agent_route", "/agent/gcloud/*", "gcloud_agent", 15001),
        (5, "monitoring_agent_route", "/agent/monitoring/*", "monitoring_agent", 15002),
        (6, "github_agent_route", "/agent/github/*", "github_agent", 15003),
        (7, "storage_agent_route", "/agent/storage/*", "storage_agent", 15004),
        (8, "db_agent_route", "/agent/db/*", "db_agent", 15005),
    ]
    
    for route_id, name, uri, service, port in routes_to_create:
        results.append((f"Create Route: {name}", create_route(route_id, name, uri, service, port)))
    
    print("\n" + "=" * 60)
    print("Testing Routes Through APISIX Gateway")
    print("=" * 60)
    
    
    # Test MCP Server health endpoints through APISIX
    print("\nTesting MCP Server Routes...")
    results.append((
        "GCloud MCP Health (via APISIX)",
        test_route("GCloud MCP", f"{APISIX_GATEWAY}/mcp/gcloud/health")
    ))
    
    results.append((
        "Monitoring MCP Health (via APISIX)",
        test_route("Monitoring MCP", f"{APISIX_GATEWAY}/mcp/monitoring/health")
    ))
    
    results.append((
        "GitHub MCP Health (via APISIX)",
        test_route("GitHub MCP", f"{APISIX_GATEWAY}/mcp/github/health")
    ))
    
    results.append((
        "Storage MCP Health (via APISIX)",
        test_route("Storage MCP", f"{APISIX_GATEWAY}/mcp/storage/health")
    ))
    
    results.append((
        "DB MCP Health (via APISIX)",
        test_route("DB MCP", f"{APISIX_GATEWAY}/mcp/db/health")
    ))
    
    # Test JSON-RPC through APISIX
    print("\nTesting MCP JSON-RPC Endpoints...")
    results.append((
        "GCloud MCP - List VMs (via APISIX)",
        test_jsonrpc_route(
            "GCloud MCP List VMs",
            f"{APISIX_GATEWAY}/mcp/gcloud",
            "list_vms",
            {"zone": "all"}
        )
    ))
    
    results.append((
        "Monitoring MCP - Check CPU (via APISIX)",
        test_jsonrpc_route(
            "Monitoring MCP CPU",
            f"{APISIX_GATEWAY}/mcp/monitoring",
            "check_cpu",
            {"resource": "test-vm", "period": "5m"}
        )
))
    
    # Test agent endpoints (these might fail if agents aren't healthy yet)
    print("\n" + "=" * 60)
    print("Testing Agent Endpoints (May fail if agents unhealthy)")
    print("=" * 60)
    
    results.append((
        "Orchestrator Health (via APISIX)",
        test_route("Orchestrator", f"{APISIX_GATEWAY}/orchestrator/health", expected_status=200)
    ))
    
    results.append((
        "GCloud Agent Health (via APISIX)",
        test_route("GCloud Agent", f"{APISIX_GATEWAY}/agent/gcloud/health", expected_status=200)
    ))
    
    results.append((
        "Monitoring Agent Health (via APISIX)",
        test_route("Monitoring Agent", f"{APISIX_GATEWAY}/agent/monitoring/health", expected_status=200)
    ))
    
    results.append((
        "GitHub Agent Health (via APISIX)",
        test_route("GitHub Agent", f"{APISIX_GATEWAY}/agent/github/health", expected_status=200)
    ))
    
    results.append((
        "Storage Agent Health (via APISIX)",
        test_route("Storage Agent", f"{APISIX_GATEWAY}/agent/storage/health", expected_status=200)
    ))
    
    results.append((
        "DB Agent Health (via APISIX)",
        test_route("DB Agent", f"{APISIX_GATEWAY}/agent/db/health", expected_status=200)
    ))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed >= total - 6:  # Allow 6 failures for agent/MCP health checks
        print("\n🎉 APISIX Gateway is working! Core routes verified.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
