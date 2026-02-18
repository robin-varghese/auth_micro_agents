"""
GitHub MCP Client Wrapper
"""
import os
import asyncio
import json
import logging
from typing import Dict, Any, List

from config import config

logger = logging.getLogger(__name__)

class GitHubMCPClient:
    """Client for connecting to GitHub MCP server via Docker Stdio"""
    
    def __init__(self, token: str = None):
        self.image = os.getenv('GITHUB_MCP_DOCKER_IMAGE', 'ghcr.io/github/github-mcp-server:latest')
        self.github_token = token or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN") or getattr(config, "GITHUB_PERSONAL_ACCESS_TOKEN", "")
        self.process = None
        self.request_id = 0

    async def connect(self):
        if not self.github_token:
            logger.warning("No GITHUB_PERSONAL_ACCESS_TOKEN. Tools may fail.")

        cmd = [
            "docker", "run", "-i", "--rm", 
            "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={self.github_token}",
            "-e", "GITHUB_TOOLSETS=all",  # Enable ALL toolsets
            self.image
        ]
        
        logger.info(f"Starting GitHub MCP: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=10 * 1024 * 1024  # Increase buffer limit to 10MB
        )
        await self._handshake()

    async def _handshake(self):
        await self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "github-agent", "version": "1.0"}}
        })
        while True:
            line = await self.process.stdout.readline()
            if not line: break
            
            line_str = line.decode().strip()
            if not line_str.startswith("{"):
                logger.debug(f"MCP LOG: {line_str}")
                continue

            try:
                msg = json.loads(line)
                if msg.get("id") == 0: break
            except json.JSONDecodeError:
                continue

        await self._send_json({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _send_json(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        if not self.github_token:
             raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN is required. Please ask the user for their GitHub PAT.")

        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self.request_id
        }
        await self._send_json(payload)
        
        while True:
            try:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=60)
            except asyncio.TimeoutError:
                raise RuntimeError(f"Tool call {tool_name} timed out")
                
            if not line: raise RuntimeError("MCP closed")
            
            line_str = line.decode().strip()
            if not line_str.startswith("{"):
                logger.debug(f"MCP LOG: {line_str}")
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if msg.get("id") == self.request_id:
                if "error" in msg: return {"error": msg["error"]}
                result = msg.get("result", {})
                content = result.get("content", [])
                output_text = ""
                for c in content:
                    if c["type"] == "text": output_text += c["text"]
                
                try: 
                    return json.loads(output_text)
                except:
                    # Return text directly if not JSON
                    return output_text

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except: pass

    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
