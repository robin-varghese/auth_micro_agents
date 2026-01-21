
import asyncio
import json
import os
import subprocess

async def call_tool():
    image = "finopti-analytics-mcp"
    
    # Get token using gcloud
    print("Fetching access token...")
    try:
        # Use application-default print-access-token to get the ADC token with correct scopes
        token = subprocess.check_output([
            "gcloud", "auth", "application-default", "print-access-token"
        ]).decode().strip()
    except Exception as e:
        print(f"Failed to get token: {e}")
        return

    cmd = [
        "docker", "run", "-i", "--rm", 
        "-e", f"GOOGLE_ACCESS_TOKEN={token}",
        image
    ]
    
    print(f"Spawning {image}...")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Handshake
    print("Sending initialize...")
    init_payload = {
        "jsonrpc": "2.0", "method": "initialize", "id": 0,
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "debug", "version": "1.0"}}
    }
    process.stdin.write((json.dumps(init_payload) + "\n").encode())
    await process.stdin.drain()

    while True:
        line = await process.stdout.readline()
        if not line: break
        msg = json.loads(line)
        if msg.get("id") == 0: break
    
    # Call Tool
    print("Sending tools/call get_account_summaries...")
    call_payload = {
        "jsonrpc": "2.0", "method": "tools/call", "id": 1, 
        "params": {
            "name": "get_account_summaries",
            "arguments": {}
        }
    }
    process.stdin.write((json.dumps(call_payload) + "\n").encode())
    await process.stdin.drain()

    while True:
        line = await process.stdout.readline()
        if not line: break
        msg = json.loads(line)
        if msg.get("id") == 1: 
            print(f"Tool Result: {msg}")
            break
        else:
            print(f"Received other: {msg}")

    process.terminate()
    stdout_data, stderr_data = await process.communicate()
    
    if stderr_data:
        print(f"\n[STDERR Output]:\n{stderr_data.decode()}")

if __name__ == "__main__":
    asyncio.run(call_tool())
