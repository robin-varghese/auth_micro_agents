"""
Analytics MCP Client Wrapper
"""
import os
import asyncio
import json
import logging
from typing import Dict, Any, List
from contextvars import ContextVar

logger = logging.getLogger(__name__)

class AnalyticsMCPClient:
    def __init__(self):
        self.image = "finopti-analytics-mcp"
        self.process = None
        self.request_id = 0
        
    async def connect(self, token: str):
        cmd = [
            "docker", "run", "-i", "--rm",
            "-e", f"GOOGLE_ACCESS_TOKEN={token}",
            self.image
        ]
        
        logger.info(f"Starting Analytics MCP: {' '.join(cmd)}")
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
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ga-agent", "version": "1.0"}}
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

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
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
                text = "".join([c["text"] for c in content if c["type"] == "text"])
                return {"result": text}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except: pass

# ContextVar for isolation
_mcp_ctx: ContextVar["AnalyticsMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp(token: str = None):
    client = _mcp_ctx.get()
    if not client:
        client = AnalyticsMCPClient()
        _mcp_ctx.set(client)
    
    if not client.process and token:
        await client.connect(token)
    elif not client.process and not token:
        # If we need a token but don't have one, we can't connect.
        # However, callers might just be checking existence.
        pass
        
    return client
