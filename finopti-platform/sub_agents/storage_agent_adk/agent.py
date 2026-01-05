"""
Google Storage ADK Agent

This agent uses Google ADK to handle Cloud Storage interactions.
It integrates with the Google Storage MCP server.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from typing import Dict, Any, List
import asyncio
import json
import requests  # For HTTP MCP client
import logging

from config import config

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# MCP Client for Storage via Docker Stdio
class StorageMCPClient:
    """Client for connecting to Storage MCP server via Docker Stdio"""
    
    def __init__(self):
        self.image = os.getenv('STORAGE_MCP_DOCKER_IMAGE', 'finopti-storage-mcp')
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0
        logger.info(f"StorageMCPClient initialized for image: {self.image}")
        logger.info(f"StorageMCPClient command mount path: {self.mount_path}")
    
    
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
                    "clientInfo": {"name": "finopti-storage-agent", "version": "1.0"}
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
            
            
    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call Storage MCP tool via Stdio"""
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
                            output = []
                            for content in result["content"]:
                                if content.get("type") == "text":
                                    output.append(content["text"])
                            return "\n".join(output)
                        
                        return str(result.get("result", result))
                except json.JSONDecodeError:
                     logger.warning(f"Invalid JSON from MCP server: {line}")
            
        except Exception as e:
            raise RuntimeError(f"Storage MCP call failed: {e}") from e

# Global MCP client
_mcp_client = None

async def ensure_client():
    global _mcp_client
    if not _mcp_client:
        _mcp_client = StorageMCPClient()
        await _mcp_client.connect()
    return _mcp_client

# --- TOOLS ---

async def list_buckets() -> Dict[str, Any]:
    """ADK Tool: List GCS buckets"""
    try:
        client = await ensure_client()
        output = await client.call_tool("list_buckets", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def list_objects(bucket_name: str, prefix: str = "") -> Dict[str, Any]:
    """ADK Tool: List objects in a bucket"""
    try:
        client = await ensure_client()
        output = await client.call_tool("list_objects", {"bucket_name": bucket_name, "prefix": prefix})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def read_object(bucket_name: str, object_name: str) -> Dict[str, Any]:
    """ADK Tool: Read object content"""
    try:
        client = await ensure_client()
        output = await client.call_tool("read_object", {"bucket_name": bucket_name, "object_name": object_name})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Create ADK Agent
# Ensure GOOGLE_API_KEY is set for the ADK/GenAI library
if not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = getattr(config, "GOOGLE_API_KEY", "")

storage_agent = Agent(
    name="storage_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="Google Cloud Storage specialist. Can list buckets and manage objects.",
    instruction="""
    You are a Google Cloud Storage specialist.
    Your capabilities:
    1. List buckets in the project.
    2. List objects within buckets.
    3. Read contents of objects.
    
    Always ensure you have the correct bucket name before listing objects.
    """,
    tools=[list_buckets, list_objects, read_object]
)

# Configure BigQuery Plugin
bq_config = BigQueryLoggerConfig(
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    batch_size=1,
    max_content_length=100 * 1024,
    shutdown_timeout=10.0
)

bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=config.GCP_PROJECT_ID,
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=bq_config,
    location="US"
)

# Create App
app = App(
    name="finopti_storage_agent",
    root_agent=storage_agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=3),
        bq_plugin
    ]
)

from google.adk.runners import InMemoryRunner
from google.genai import types

async def send_message_async(prompt: str, user_email: str = None) -> str:
    try:
        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(session_id="default", user_id="default", app_name="finopti_storage_agent")
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(user_id="default", session_id="default", new_message=message):
                 if hasattr(event, 'content') and event.content and event.content.parts:
                     for part in event.content.parts:
                         if part.text:
                             response_text += part.text
            return response_text if response_text else "No response."
    except Exception as e:
        return f"Error: {str(e)}"

def send_message(prompt: str, user_email: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email))
