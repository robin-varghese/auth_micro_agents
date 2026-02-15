"""
Verification Script for MATS Remediation Agent
"""
import aiohttp
import asyncio
import json
import time

URL = "http://localhost:8085/execute"

# Mock RCA Document
MOCK_RCA = """
# Root Cause Analysis
**Incident:** API Latency Spike
**Root Cause:** Redis Connection Pool Exhaustion
**Evidence:** `redis.exceptions.ConnectionError` in logs.
**Recommended Fix:** Increase connection pool size to 50 in `config.py`.
"""

# Mock Resolution Plan (from Architect)
MOCK_RESOLUTION = """
ACTION: UPDATE_CONFIG
TARGET: redis_config
PARAMETER: max_connections
VALUE: 50
"""

async def verify():
    print(f"Testing Remediation Agent at {URL}...")
    
    payload = {
        "rca_document": MOCK_RCA,
        "resolution_plan": MOCK_RESOLUTION,
        "session_id": f"verify-{int(time.time())}",
        "user_email": "tester@finopti.com"
    }
    
    try:
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.post(URL, json=payload, timeout=600) as resp:
                duration = time.time() - start_time
                print(f"Response Status: {resp.status} (took {duration:.2f}s)")
                
                if resp.status == 200:
                    data = await resp.json()
                    print("✅ SUCCESS: Agent returned valid JSON")
                    print(json.dumps(data, indent=2))
                    
                    # Check for report URL
                    if "report_url" in data:
                         print(f"✅ Report URL generated: {data['report_url']}")
                    else:
                         print("⚠️ Report URL missing (might be mocked response)")
                else:
                    text = await resp.text()
                    print(f"❌ FAILED: {resp.status}")
                    print(text)
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
