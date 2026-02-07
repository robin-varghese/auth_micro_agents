
import requests
import json
import sys

def test_rca_upload():
    url = "http://localhost:9080/agent/storage/execute"
    filename = "TEST-RCA-MANUAL.md"
    bucket_name = "rca-reports-mats"
    content = "# Test RCA\n\nThis is a manual verification test for the RCA upload flow."
    
    prompt = (
        f"Please ensure the GCS bucket '{bucket_name}' exists (create it in location US if it doesn't). "
        f"Then, upload the following content as object '{filename}' to that bucket:\n\n{content}"
    )
    
    payload = {
        "prompt": prompt,
        "user_email": "manual-test@system.local" 
    }
    
    print(f"Sending request to {url}...")
    try:
        response = requests.post(url, json=payload, timeout=120)
        print(f"Status Code: {response.status_code}")
        print(f"Response Text: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Request accepted.")
            try:
                data = response.json()
                print(f"JSON Response: {json.dumps(data, indent=2)}")
            except:
                pass
        else:
            print("FAILURE: Request failed.")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    test_rca_upload()
