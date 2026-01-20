import requests
import os
import sys

APISIX_URL = os.getenv("APISIX_URL", "http://localhost:9080")
AGENT_ROUTE = "/agent/analytics/execute"
PROMPT = "Show me the top 5 most used agents based on analytics data"

def verify():
    url = f"{APISIX_URL}{AGENT_ROUTE}"
    print(f"Sending prompt to {url}: {PROMPT}")
    try:
        response = requests.post(url, json={"prompt": PROMPT}, timeout=60)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200 and response.text:
            return True
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if verify():
        sys.exit(0)
    else:
        sys.exit(1)
