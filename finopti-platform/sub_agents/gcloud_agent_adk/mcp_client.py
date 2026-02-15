"""
GCloud MCP Client Wrapper
"""
import os
import asyncio
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class GCloudMCPClient:
    """Client for connecting to GCloud MCP server via Docker Stdio"""
    
    def __init__(self):
        self.image = os.getenv('GCLOUD_MCP_DOCKER_IMAGE', 'finopti-gcloud-mcp')
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0
        logger.info(f"GCloudMCPClient initialized for image: {self.image}")
        logger.info(f"GCloudMCPClient command mount path: {self.mount_path}")
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        """Start the MCP server container"""
        
        # Check if running in a container with access to docker socket
        cmd = [
            "docker", "run", 
            "-i", "--rm", 
            "-v", self.mount_path,
            self.image
        ]
        
        logger.info(f"Starting MCP server with command: {' '.join(cmd)}")
        
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # --- MCP Initialization Handshake ---
            # 1. Send 'initialize' request
            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "finopti-gcloud-agent", "version": "1.0"}
                },
                "id": 0
            }
            
            logger.info("Sending MCP initialize request...")
            self.process.stdin.write((json.dumps(init_payload) + "\n").encode())
            await self.process.stdin.drain()
            
            # 2. Wait for initialize response
            while True:
                line = await self.process.stdout.readline()
                if not line:
                     stderr = await self.process.stderr.read()
                     raise RuntimeError(f"MCP server closed during initialization. Stderr: {stderr.decode()}")
                
                try:
                    msg = json.loads(line.decode())
                    if msg.get("id") == 0:
                        if "error" in msg:
                             raise RuntimeError(f"MCP initialization error: {msg['error']}")
                        logger.info("MCP Initialized successfully.")
                        break
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON during init: {line}")
            
            # 3. Send 'notifications/initialized'
            notify_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            self.process.stdin.write((json.dumps(notify_payload) + "\n").encode())
            await self.process.stdin.drain()
            
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            if self.process:
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass
            raise

    async def close(self):
        """Stop the MCP server"""
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                pass
            self.process = None
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        """Call GCloud MCP tool via Stdio"""
        if not self.process:
            raise RuntimeError("MCP client not connected")
            
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self.request_id
        }
        
        json_str = json.dumps(payload) + "\n"
        
        try:
            # Write request
            self.process.stdin.write(json_str.encode())
            await self.process.stdin.drain()
            
            # Read response
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    # EOF
                    stderr = await self.process.stderr.read()
                    raise RuntimeError(f"MCP server closed connection. Stderr: {stderr.decode()}")
                
                try:
                    msg = json.loads(line.decode())
                    if msg.get("id") == self.request_id:
                        if "error" in msg:
                            raise RuntimeError(f"MCP tool error: {msg['error']}")
                        
                        result = msg.get("result", {})
                        if "content" in result:
                            output_text = ""
                            for content in result["content"]:
                                if content.get("type") == "text":
                                    output_text += content["text"]
                            try:
                                return json.loads(output_text)
                            except json.JSONDecodeError:
                                return {"output": output_text}
                        
                        return result
                except json.JSONDecodeError:
                     logger.warning(f"Invalid JSON from MCP server: {line}")
                     
        except Exception as e:
             raise RuntimeError(f"MCP call failed: {e}") from e

    async def run_gcloud_command(self, args: List[str]) -> str:
        """
        Execute a gcloud command via MCP server
        
        Args:
            args: List of gcloud command arguments (without 'gcloud' prefix)
        
        Returns:
            Command output as string
        """
        result = await self.call_tool(
            "run_gcloud_command",
            arguments={"args": args}
        )
        
        if isinstance(result, dict) and "output" in result:
            return result["output"]
        return str(result)


# Global MCP client (will be initialized per-request)
_mcp_client = None

async def get_mcp_client():
    global _mcp_client
    if not _mcp_client:
        _mcp_client = GCloudMCPClient()
        await _mcp_client.connect()
    return _mcp_client

async def close_mcp_client():
    global _mcp_client
    if _mcp_client:
        await _mcp_client.close()
        _mcp_client = None
