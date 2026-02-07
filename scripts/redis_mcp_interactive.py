#!/usr/bin/env python3
"""
Interactive Redis MCP verification script.
Uses the common RedisMcpClient to interact with the Redis Session Store via the DB MCP Toolbox.

Prereq: 
- docker-compose up (db_mcp_toolbox running on port 6005)
"""
import sys
import os
import asyncio
import argparse
import json
import logging

# Add project root to path
# Path to finopti-platform/mats-agents where common/ is located
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../finopti-platform/mats-agents')))

try:
    from common.mcp_client import RedisMcpClient
except ImportError as e:
    print(f"Import Error: {e}")
    # Try alternate path if running from different location
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../finopti-platform')))
    try:
         # If checking from root, maybe common is accessible differently?
         # But the folder common is inside mats-agents.
         pass
    except:
         pass
    # If still failing, define a simple mock or exit
    # print("Could not import RedisMcpClient.")
    # sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("redis_cli")

async def main():
    parser = argparse.ArgumentParser(description="Redis MCP Interactive CLI")
    parser.add_argument("--url", default="http://localhost:6005/mcp", help="DB MCP Toolbox URL")
    args = parser.parse_args()

    print(f"Connecting to Redis MCP at {args.url}...")
    
    # Instantiate Client
    os.environ["DB_MCP_TOOLBOX_URL"] = args.url
    client = RedisMcpClient() # Uses env var

    print("Interactive Mode. Commands: get <key>, set <key> <value>, keys <pattern>, exit")
    
    while True:
        try:
            cmd_input = input("redis-mcp> ").strip()
            if not cmd_input:
                continue
            
            parts = cmd_input.split(" ")
            cmd = parts[0].lower()
            
            if cmd == "exit":
                break
                
            elif cmd == "set":
                if len(parts) < 3:
                    print("Usage: set <key> <value>")
                    continue
                key = parts[1]
                val = " ".join(parts[2:]) # Allow value with spaces
                res = await client.call_tool("redis_set", {"key": key, "value": val})
                print(f"Result: {res}")
                
            elif cmd == "get":
                if len(parts) < 2:
                    print("Usage: get <key>")
                    continue
                key = parts[1]
                res = await client.call_tool("redis_get", {"key": key})
                print(f"Result: {res}")

            elif cmd == "keys":
                # Note: Toolbox might not expose 'keys' tool, usually 'redis_list_keys' or similar
                # Checking tool definitions in toolbox... usually it exposes raw commands or specific tools
                # Assuming redis_get/set. Let's try raw command if available, or just implemented ones.
                # RedisMcpClient only implements redis_get / redis_set wrappers?
                # The generic call_tool can call anything.
                # Let's try 'redis_keys' or 'execute_query' if it's a generic DB tool.
                # The prompt said "Redis backed session... delegating to MCP Redis tools".
                # Standard tools: redis_get, redis_set, redis_delete.
                if len(parts) < 2:
                    pattern = "*"
                else:
                    pattern = parts[1]
                
                # Try generic redis_execute if available, else standard tools
                print("Trying redis_execute...")
                res = await client.call_tool("redis_execute", {"command": "KEYS", "args": [pattern]})
                print(f"Result: {res}")

            else:
                print(f"Unknown command: {cmd}")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
