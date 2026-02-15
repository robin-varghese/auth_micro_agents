"""
Storage MCP Client Wrapper
"""
import os
import asyncio
import json
import logging
from typing import Dict, Any, List
from contextvars import ContextVar

logger = logging.getLogger(__name__)

class StorageMCPClient:
    """Client for connecting to Storage MCP server via Docker Stdio"""
    
    def __init__(self):
        self.image = os.getenv('STORAGE_MCP_DOCKER_IMAGE', 'finopti-storage-mcp')
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0
    
    async def connect(self):
        cmd = [
            "docker", "run", "-i", "--rm", 
            "-v", self.mount_path,
            self.image
        ]
        logging.info(f"Starting Storage MCP: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await self._handshake()

    async def _handshake(self):
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "storage-agent", "version": "1.0"}}
        })
        while True:
            line = await self.process.stdout.readline()
            if not line: break
            msg = json.loads(line)
            if msg.get("id") == 0: break
        await self._send_json({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _send_json(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self.request_id
        }
        await self._send_json(payload)
        
        while True:
            line = await self.process.stdout.readline()
            if not line: raise RuntimeError("MCP closed")
            msg = json.loads(line)
            if msg.get("id") == self.request_id:
                if "error" in msg: return {"error": msg["error"]}
                result = msg.get("result", {})
                content = result.get("content", [])
                output_text = ""
                for c in content:
                    if c["type"] == "text": output_text += c["text"]
                # Try parsing JSON output if possible
                try: 
                    return json.loads(output_text)
                except:
                    return {"output": output_text}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except: pass

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["StorageMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    """Retrieve the client for the CURRENT context."""
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client
