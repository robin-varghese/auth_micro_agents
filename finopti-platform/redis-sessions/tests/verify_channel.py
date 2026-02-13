import requests
import json
import redis
import time
import sys

# Protocol Config
REDIS_GATEWAY_URL = "http://localhost:8001"
REDIS_HOST = "localhost"
REDIS_PORT = 6379

def verify_channel_flow():
    print("--- Starting Verification: Task 1 (Channel & Pub/Sub) ---")
    
    # 1. Init Session (Simulate UI)
    user_id = "test_user"
    session_id = "test_session"
    
    print(f"1. Initializing Session: {session_id}")
    try:
        response = requests.post(f"{REDIS_GATEWAY_URL}/session/init", json={
            "user_id": user_id,
            "session_id": session_id
        })
        response.raise_for_status()
        data = response.json()
        channel_name = data["channel"]
        print(f"   Success! Channel: {channel_name}")
    except Exception as e:
        print(f"   Failed to init session: {e}")
        sys.exit(1)

    # 2. Subscribe (Simulate Listener)
    print(f"2. Subscribing to channel: {channel_name}...")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    pubsub = r.pubsub()
    pubsub.subscribe(channel_name)
    
    # Wait for subscription confirmation
    # The first message is always strict 'subscribe' type
    subscription_msg = pubsub.get_message(timeout=2)
    if subscription_msg and subscription_msg['type'] == 'subscribe':
        print(f"   Subscribed successfully to {subscription_msg['channel']}")
    else:
        print("   Subscription failed or timed out.")

    # 3. Publish Message (Simulated Agent)
    print("3. Publishing test message (Simulating Agent via Gateway /event)...")
    
    # Construct Valid Event
    test_event = {
        "user_id": user_id,
        "session_id": session_id,
        "event": {
            "header": {
                "trace_id": "trace-123",
                "agent_name": "VerifierBot",
                "agent_role": "Tester"
            },
            "type": "STATUS_UPDATE",
            "payload": {
                "message": "Verification Successful",
                "severity": "SUCCESS",
                "progress": 100
            },
            "ui_rendering": {
                "display_type": "alert_success",
                "icon": "✅"
            }
        }
    }
    
    try:
        response = requests.post(f"{REDIS_GATEWAY_URL}/event", json=test_event)
        response.raise_for_status()
        print("   Message published via Gateway.")
    except Exception as e:
        print(f"   Failed to publish: {e}")
        try: print(response.text)
        except: pass
        sys.exit(1)

    # 4. Verify Receipt
    print("4. Waiting for message...")
    time.sleep(1)
    msg = pubsub.get_message(timeout=2)
    
    if msg and msg["type"] == "message":
        print(f"   Received: {msg['data']}")
        received_json = json.loads(msg['data'])
        if received_json["payload"]["message"] == "Verification Successful":
            print("\n✅ VERIFICATION PASSED: Channel created, message routed.")
        else:
            print("\n❌ VERIFICATION FAILED: Content mismatch.")
    else:
        print("\n❌ VERIFICATION FAILED: No message received.")

if __name__ == "__main__":
    verify_channel_flow()
