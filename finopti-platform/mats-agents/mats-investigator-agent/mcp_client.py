"""
Async MCP Client Wrapper & GitHub Client
"""
import os
import asyncio
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# ASYNC MCP CLIENT
# -------------------------------------------------------------------------
class AsyncMCPClient:
    def __init__(self, image: str, env_vars: Dict[str, str]):
        self.image = image
        self.env_vars = env_vars
        self.process = None
        self.request_id = 0

    async def connect(self, client_name: str):
        # Build docker run command with environment variables
        cmd = ["docker", "run", "-i", "--rm"]
        for k, v in self.env_vars.items():
            cmd.extend(["-e", f"{k}={v}"])
        cmd.append(self.image)
        
        logger.info(f"[{client_name}] Starting MCP: {' '.join(cmd)}")
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Handshake
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": "1.0"}
            })
            
            # Read initialize response
            line = await self.process.stdout.readline()
            if not line:
                stderr = await self.process.stderr.read()
                raise RuntimeError(f"MCP Init Failed. Stderr: {stderr.decode()}")
            
            # Send initialized notification
            await self._send_notification("notifications/initialized", {})
            logger.info(f"[{client_name}] Connected & Initialized")
            
        except Exception as e:
            logger.error(f"[{client_name}] Connection failed: {e}")
            await self.close()
            raise

    async def _send_request(self, method, params):
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0", 
            "method": method, 
            "params": params, 
            "id": self.request_id
        }
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()
        return self.request_id

    async def _send_notification(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        if not self.process:
            raise RuntimeError("MCP client not connected")
            
        req_id = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        try:
            while True:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=300.0)
                if not line:
                    raise RuntimeError("MCP Connection Closed Unexpectedly")
                
                try:
                    msg = json.loads(line.decode())
                    if msg.get("id") == req_id:
                         if "error" in msg:
                             return {"error": msg['error']}
                         
                         res = msg.get("result", {})
                         # Text extraction logic
                         if "content" in res:
                             text = ""
                             for c in res["content"]:
                                 if c["type"] == "text":
                                     text += c["text"]
                             try:
                                 return json.loads(text)
                             except:
                                 return {"output": text}
                         return res
                except json.JSONDecodeError:
                    continue
        except asyncio.TimeoutError:
             return {"error": "Tool execution timed out after 300s"}
        except Exception as e:
             return {"error": f"Client Error: {e}"}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except:
                pass
            self.process = None

# -------------------------------------------------------------------------
# GITHUB CLIENT
# -------------------------------------------------------------------------
_github_client = None

async def get_github_client():
    global _github_client
    if not _github_client:
        image = os.getenv('GITHUB_MCP_DOCKER_IMAGE', 'finopti-github-mcp-server')
        token = os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN')
        if not token:
            logger.warning("No GITHUB_PERSONAL_ACCESS_TOKEN found!")
            
        _github_client = AsyncMCPClient(image, {"GITHUB_PERSONAL_ACCESS_TOKEN": token})
        await _github_client.connect("mats-investigator")
    return _github_client
