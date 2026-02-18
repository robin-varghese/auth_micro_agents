"""
Redis Monitor Tool
==================

A CLI utility for real-time monitoring of Redis Pub/Sub events in the FinOptiAgents platform.
This tool helps debug agent orchestration, session state updates, and inter-agent communication.

Usage Examples
--------------

1. Monitor default agent channels (channel:*):
   $ python3 monitor_redis.py

2. Filter events by a specific Session ID:
   $ python3 monitor_redis.py --session-id session_550e8400-e29b-41d4-a716-446655440000

3. Monitor ALL channels (including system events, heartbeats, logs):
   $ python3 monitor_redis.py --channel all

4. Monitor a custom channel pattern:
   $ python3 monitor_redis.py --channel "system:*"

5. Monitor a specific session:
   $ python3 monitor_redis.py 
   --session-id 519152d5ce3947c08e7edb53e5e2a15e 
   --channel all

Arguments
---------
--session-id <ID>   : Only show events matching this Session ID.
                      Useful for tracing a single user request through multiple agents.
                      
--channel <PATTERN> : Redis channel glob pattern to subscribe to.
                      Default: 'channel:*' (Agent communication channels)
                      'all' = '*' (Everything)

Dependencies
------------
- redis (pip install redis)
- Access to localhost:6379 (via port forwarding or running inside network)
"""

import redis
import json
import datetime
import sys
import argparse

def monitor_redis():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Monitor Redis Pub/Sub events.")
    parser.add_argument("--session-id", 
                      help="Filter events by session ID (e.g., 'session_12345'). If 'all' or not provided, shows all events.")
    parser.add_argument("--channel", 
                      default="channel:*",
                      help="Redis channel pattern to subscribe to (default: 'channel:*'). Use 'all' for '*'.")
    args = parser.parse_args()
    
    session_filter = args.session_id
    if session_filter and session_filter.lower() == "all":
        session_filter = None
        
    channel_pattern = args.channel
    if channel_pattern.lower() == "all":
        channel_pattern = "*"

    print(f"Connecting to Redis at localhost:6379...")
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        p = r.pubsub()
        p.psubscribe(channel_pattern)
        
        print(f"✅ Connected! Listening for events on '{channel_pattern}'...")
        if session_filter:
            print(f"🔍 Filtering for Session ID: {session_filter}")
        else:
            print("👉 Go to the UI (http://localhost:8501) and trigger a prompt now.")
        
        print("   (Events will appear below in real-time)\n")
        
        for message in p.listen():
            if message['type'] == 'pmessage':
                channel = message['channel'].decode('utf-8')
                data_str = message['data'].decode('utf-8')
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                
                try:
                    data = json.loads(data_str)
                    
                    # session_id check - look in top level or in header
                    msg_session_id = data.get("session_id") or data.get("header", {}).get("session_id")
                    
                    # If still not found, try to extract from channel name (session_<uuid>)
                    if not msg_session_id and "session_" in channel:
                        msg_session_id = channel.split("session_")[-1]

                    # Filter logic
                    if session_filter:
                        # If a filter is set, strict matching
                        # We also check if the filter is contained in the channel or session ID
                        if session_filter != msg_session_id and session_filter not in channel:
                            continue
                            
                    print(f"[{timestamp}] 📦 Channel: {channel}")
                    print(json.dumps(data, indent=2))
                    print("-" * 50)
                    
                except json.JSONDecodeError:
                    # If we are filtering, we skip non-JSON or obscure data 
                    # unless we want to debug. But user asked for "only messages in respective..."
                    if not session_filter:
                        print(f"[{timestamp}] 📦 Channel: {channel}")
                        print(f"Raw Data: {data_str}")
                        print("-" * 50)
                except Exception as e:
                    print(f"Error processing message: {e}")
                
    except redis.ConnectionError:
        print("❌ Error: Could not connect to Redis on localhost:6379.")
        print("   Ensure the container is running: 'docker ps | grep redis'")
    except KeyboardInterrupt:
        print("\nStopped monitoring.")
        sys.exit(0)

if __name__ == "__main__":
    monitor_redis()
