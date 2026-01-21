import requests
import os
import sys

APISIX_URL = os.getenv("APISIX_URL", "http://localhost:9080")
AGENT_ROUTE = "/agent/googlesearch/execute"
PROMPT = "Who is the CEO of Google?"

def verify():
    url = f"{APISIX_URL}{AGENT_ROUTE}"
    print(f"Sending prompt to {url}: {PROMPT}")
    headers = {}
    token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        print("Using OAuth Token in request.")

    try:
        response = requests.post(url, json={"prompt": PROMPT}, headers=headers, timeout=180)
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
