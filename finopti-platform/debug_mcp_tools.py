import asyncio
import json
import os

async def list_tools():
    image = "finopti-monitoring-mcp"
    cmd = ["docker", "run", "-i", "--rm", image]
    
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
        print(f"Received: {msg}")
        if msg.get("id") == 0: break
    
    # List Tools
    print("Sending tools/list...")
    list_payload = {
        "jsonrpc": "2.0", "method": "tools/list", "id": 1, "params": {}
    }
    process.stdin.write((json.dumps(list_payload) + "\n").encode())
    await process.stdin.drain()

    while True:
        line = await process.stdout.readline()
        if not line: break
        msg = json.loads(line)
        print(f"Received Tools: {msg}")
        if msg.get("id") == 1: 
            result = msg.get("result", {})
            tools = result.get("tools", [])
            print("\n=== AVAILABLE TOOLS ===")
            for t in tools:
                print(f"- {t['name']}")
            break

    process.terminate()

if __name__ == "__main__":
    asyncio.run(list_tools())
