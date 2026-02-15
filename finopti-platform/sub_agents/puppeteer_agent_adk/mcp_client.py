"""
Puppeteer MCP Client Wrapper
"""
import os
import asyncio
import json
import logging
from typing import Dict, Any
from contextvars import ContextVar

logger = logging.getLogger(__name__)

class PuppeteerMCPClient:
    """Client for connecting to Puppeteer MCP server via Docker Stdio"""
    
    def __init__(self):
        self.image = os.getenv('PUPPETEER_MCP_DOCKER_IMAGE', 'finopti-puppeteer')
        self.process = None
        self.request_id = 0
        self.last_filename = None
        
    async def connect(self):
        self.last_filename = None
        cmd = [
            "docker", "run", "-i", "--rm", "--init",
            "-e", "DOCKER_CONTAINER=true",
            self.image
        ]
        
        logger.info(f"Starting Puppeteer MCP: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024  # 10MB buffer
        )
        await self._handshake()

    async def _handshake(self):
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "puppeteer-agent", "version": "1.0"}}
        })
        # Wait for initialize response
        while True:
            response = await self._read_json()
            if response.get("id") == 0:
                break
        
        await self._send_json({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _send_json(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def _read_json(self) -> dict:
        """Read JSON-RPC response, skipping non-JSON lines"""
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise EOFError("MCP server process closed unexpectedly")
            
            line_str = line.decode().strip()
            if not line_str:
                continue
                
            try:
                return json.loads(line_str)
            except json.JSONDecodeError:
                logger.debug(f"MCP non-JSON output: {line_str}")
                continue

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self.request_id
        }
        await self._send_json(payload)
        
        while True:
            msg = await self._read_json()
            if msg.get("id") == self.request_id:
                if "error" in msg: return {"error": msg["error"]}
                result = msg.get("result", {})
                content = result.get("content", [])
                
                text = ""
                image_data = None
                
                for c in content:
                    if c["type"] == "text":
                        text += c["text"]
                    elif c["type"] == "image":
                        # Return the actual base64 data so the tool wrapper can save it
                        image_data = c["data"]
                
                return {"result": text, "image": image_data}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except: pass

# ContextVar for isolation
_mcp_ctx: ContextVar["PuppeteerMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client
