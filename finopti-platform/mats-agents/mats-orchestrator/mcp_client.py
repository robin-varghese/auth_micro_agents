"""
MATS Orchestrator - Sequential Thinking MCP Client

Extracted from agent.py per REFACTORING_GUIDELINE.md (Step 4).
Manages the subprocess-based connection to the Sequential Thinking MCP server.
"""
import os
import json
import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SequentialThinkingClient:
    """MCP client for Sequential Thinking specialist"""
    
    def __init__(self):
        self.image = os.getenv("SEQUENTIAL_THINKING_MCP_DOCKER_IMAGE", "sequentialthinking")
        self.process = None
        self._request_id = 0

    async def connect(self):
        """Start the Sequential Thinking MCP server"""
        cmd = [
            "docker", "run", "-i", "--rm",
            self.image
        ]
        logger.info(f"Starting Sequential Thinking MCP: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await self._handshake()
        logger.info("Sequential Thinking MCP connected and initialized")

    async def _handshake(self):
        """Perform MCP initialization handshake"""
        self._request_id += 1
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "mats-orchestrator", "version": "1.0"}
            },
            "id": self._request_id
        }
        await self._send_json(init_request)
        response = await self._read_json()
        
        if response and "result" in response:
            logger.info(f"MCP Handshake successful: {response['result'].get('serverInfo', {}).get('name', 'unknown')}")
        else:
            logger.warning(f"MCP Handshake response unexpected: {response}")
        
        # Send initialized notification
        await self._send_json({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

    async def _send_json(self, data: dict):
        """Send JSON-RPC message"""
        message = json.dumps(data) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()

    async def _read_json(self):
        """Read JSON-RPC response, skipping non-JSON lines"""
        while True:
            line = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=30.0
            )
            if not line:
                return None
            text = line.decode().strip()
            if not text:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.debug(f"Skipping non-JSON line: {text[:100]}")
                continue

    async def call_tool(self, tool_name: str, args: dict):
        """Call a tool on the MCP server"""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args
            },
            "id": self._request_id
        }
        await self._send_json(request)
        response = await self._read_json()
        
        if response and "result" in response:
            return response["result"]
        elif response and "error" in response:
            raise RuntimeError(f"MCP tool error: {response['error']}")
        return None

    async def close(self):
        """Close the MCP connection"""
        if self.process:
            try:
                self.process.stdin.close()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except Exception as e:
                logger.warning(f"Error closing MCP: {e}")
                self.process.kill()
