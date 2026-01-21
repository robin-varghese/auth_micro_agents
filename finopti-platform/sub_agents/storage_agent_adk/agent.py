"""
Google Storage ADK Agent

This agent uses Google ADK to handle Cloud Storage interactions.
It integrates with the Google Storage MCP server (gcloud-mcp).
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.genai import types
from config import config

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

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

from contextvars import ContextVar

# ContextVar to store the MCP client for the current request
_mcp_ctx: ContextVar["StorageMCPClient"] = ContextVar("mcp_client", default=None)

async def ensure_mcp():
    """Retrieve the client for the CURRENT context."""
    client = _mcp_ctx.get()
    if not client:
        raise RuntimeError("MCP Client not initialized for this context")
    return client

# --- Tool Wrappers ---
async def list_objects(bucket_name: str, prefix: str = "") -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_objects", {"bucket_name": bucket_name, "prefix": prefix})

async def read_object_metadata(bucket_name: str, object_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_object_metadata", {"bucket_name": bucket_name, "object_name": object_name})

async def read_object_content(bucket_name: str, object_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_object_content", {"bucket_name": bucket_name, "object_name": object_name})

async def delete_object(bucket_name: str, object_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("delete_object", {"bucket_name": bucket_name, "object_name": object_name})

async def write_object(bucket_name: str, object_name: str, content: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("write_object", {"bucket_name": bucket_name, "object_name": object_name, "content": content})

async def update_object_metadata(bucket_name: str, object_name: str, metadata: dict) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("update_object_metadata", {"bucket_name": bucket_name, "object_name": object_name, "metadata": metadata})

async def copy_object(source_bucket: str, source_object: str, dest_bucket: str, dest_object: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("copy_object", {"source_bucket": source_bucket, "source_object": source_object, "dest_bucket": dest_bucket, "dest_object": dest_object})

async def move_object(source_bucket: str, source_object: str, dest_bucket: str, dest_object: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("move_object", {"source_bucket": source_bucket, "source_object": source_object, "dest_bucket": dest_bucket, "dest_object": dest_object})

async def upload_object(bucket_name: str, object_name: str, file_path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("upload_object", {"bucket_name": bucket_name, "object_name": object_name, "file_path": file_path})

async def download_object(bucket_name: str, object_name: str, file_path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("download_object", {"bucket_name": bucket_name, "object_name": object_name, "file_path": file_path})

async def list_buckets() -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_buckets", {})

async def create_bucket(bucket_name: str, location: str = "US") -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("create_bucket", {"bucket_name": bucket_name, "location": location})

async def delete_bucket(bucket_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("delete_bucket", {"bucket_name": bucket_name})

async def get_bucket_metadata(bucket_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_bucket_metadata", {"bucket_name": bucket_name})

async def update_bucket_labels(bucket_name: str, labels: dict) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("update_bucket_labels", {"bucket_name": bucket_name, "labels": labels})

async def get_bucket_location(bucket_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_bucket_location", {"bucket_name": bucket_name})

async def view_iam_policy(bucket_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("view_iam_policy", {"bucket_name": bucket_name})

async def check_iam_permissions(bucket_name: str, permissions: List[str]) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("check_iam_permissions", {"bucket_name": bucket_name, "permissions": permissions})

async def get_metadata_table_schema(config_name: str, project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_metadata_table_schema", {"config_name": config_name, "project": project})

async def execute_insights_query(query: str, project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("execute_insights_query", {"query": query, "project": project})

async def list_insights_configs(project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_insights_configs", {"project": project})

# Load Manifest
manifest_path = Path(__file__).parent / "manifest.json"
manifest = {}
if manifest_path.exists():
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

# Load Instructions
instructions_path = Path(__file__).parent / "instructions.json"
if instructions_path.exists():
    with open(instructions_path, "r") as f:
        data = json.load(f)
        instruction_str = data.get("instruction", "You are a Storage Specialist.")
else:
    instruction_str = "You are a Storage Specialist."

# Ensure API Key is in environment for GenAI library
if hasattr(config, "GOOGLE_API_KEY") and config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

agent = Agent(
    name=manifest.get("agent_id", "storage_specialist"),
    model=config.FINOPTIAGENTS_LLM,
    description=manifest.get("description", "Storage Specialist."),
    instruction=instruction_str,
    tools=[
        list_objects, read_object_metadata, read_object_content, delete_object, 
        write_object, update_object_metadata, copy_object, move_object, 
        upload_object, download_object, list_buckets, create_bucket, 
        delete_bucket, get_bucket_metadata, update_bucket_labels, 
        get_bucket_location, view_iam_policy, check_iam_permissions, 
        get_metadata_table_schema, execute_insights_query, list_insights_configs
    ]
)

app = App(
    name="finopti_storage_agent",
    root_agent=agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=3),
        BigQueryAgentAnalyticsPlugin(
            project_id=config.GCP_PROJECT_ID,
            dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
            table_id=config.BQ_ANALYTICS_TABLE,
            config=BigQueryLoggerConfig(enabled=True)
        )
    ]
)

async def send_message_async(prompt: str, user_email: str = None) -> str:
    # Create new client for this request (and this event loop)
    mcp = StorageMCPClient()
    token_reset = _mcp_ctx.set(mcp)
    
    try:
        await mcp.connect()

        async with InMemoryRunner(app=app) as runner:
            await runner.session_service.create_session(
                session_id="default",
                user_id="default",
                app_name="finopti_storage_agent"
            )
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(session_id="default", user_id="default", new_message=message):
                 if hasattr(event, 'content') and event.content:
                     for part in event.content.parts:
                         if part.text: response_text += part.text
            return response_text
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email))
