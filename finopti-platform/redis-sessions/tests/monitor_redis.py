import redis
import json
import datetime
import sys
def monitor_redis():
    print(f"Connecting to Redis at localhost:6379...")
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        p = r.pubsub()
        p.psubscribe('channel:*')
        
        print("✅ Connected! Listening for events on 'channel:*'...")
        print("👉 Go to the UI (http://localhost:8501) and trigger a prompt now.")
        print("   (Events will appear below in real-time)\n")
        
        for message in p.listen():
            if message['type'] == 'pmessage':
                channel = message['channel'].decode('utf-8')
                data_str = message['data'].decode('utf-8')
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                
                print(f"[{timestamp}] 📦 Channel: {channel}")
                try:
                    data = json.loads(data_str)
                    print(json.dumps(data, indent=2))
                except:
                    print(f"Raw Data: {data_str}")
                print("-" * 50)
                
    except redis.ConnectionError:
        print("❌ Error: Could not connect to Redis on localhost:6379.")
        print("   Ensure the container is running: 'docker ps | grep redis'")
    except KeyboardInterrupt:
        print("\nStopped monitoring.")
        sys.exit(0)
if __name__ == "__main__":
    monitor_redis()
