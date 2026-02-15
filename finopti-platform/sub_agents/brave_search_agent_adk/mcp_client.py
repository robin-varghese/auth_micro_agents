"""
Brave Search MCP Client Wrapper
"""
import os
import json
import logging
import asyncio
from typing import Dict, Any
from contextvars import ContextVar
from google.cloud import secretmanager
from config import config

logger = logging.getLogger(__name__)

class BraveMCPClient:
    def __init__(self):
        self.image = "finopti-brave-search"
        self.process = None
        self.request_id = 0
    
    async def _get_api_key(self):
        # Fetch from Secret Manager
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{config.GCP_PROJECT_ID}/secrets/BRAVE_API_KEY/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            logging.error(f"Failed to fetch BRAVE_API_KEY: {e}")
            raise

    async def connect(self):
        if self.process:
            return

        api_key = await self._get_api_key()
        
        cmd = [
            "docker", "run", "-i", "--rm",
            "-e", f"BRAVE_API_KEY={api_key}",
            self.image
        ]
        
        logging.info(f"Starting Brave MCP: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await self._handshake()

    async def _handshake(self):
        # Initialize
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "brave-agent", "version": "1.0"}}
        })
        
        # Wait for response
        while True:
            line = await self.process.stdout.readline()
            if not line: break
            msg = json.loads(line)
            if msg.get("id") == 0: break
            
        # Initialized notification
        await self._send_json({
            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}
        })

    async def _send_json(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        if not self.process:
            await self.connect()

        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
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
                # Extract text content
                content = result.get("content", [])
                text = "".join([c["text"] for c in content if c["type"] == "text"])
                return {"result": text}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except: pass
        self.process = None

# ContextVar for isolation
_mcp_ctx: ContextVar["BraveMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client
