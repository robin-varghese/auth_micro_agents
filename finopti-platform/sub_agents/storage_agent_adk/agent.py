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
from datetime import timedelta
from google.cloud import storage

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
    # 1. Write the object via MCP
    res = await client.call_tool("write_object_safe", {"bucket_name": bucket_name, "object_name": object_name, "content": content})
    if "error" in res:
        return res
    
    # 2. Generate Signed URL for immediate access
    try:
        def _get_signed_url():
             storage_client = storage.Client()
             bucket = storage_client.bucket(bucket_name)
             blob = bucket.blob(object_name)
             try:
                 return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
             except:
                 return f"https://storage.cloud.google.com/{bucket_name}/{object_name}"
        
        signed_url = await asyncio.to_thread(_get_signed_url)
        return {
            "result": f"Object '{object_name}' written to bucket '{bucket_name}'.",
            "gcs_uri": f"gs://{bucket_name}/{object_name}",
            "signed_url": signed_url
        }
    except Exception as e:
        return {"result": f"Object written, but signed URL failed: {e}", "gcs_uri": f"gs://{bucket_name}/{object_name}"}

async def update_object_metadata(bucket_name: str, object_name: str, metadata: dict) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("update_object_metadata", {"bucket_name": bucket_name, "object_name": object_name, "metadata": metadata})

async def copy_object(source_bucket: str, source_object: str, dest_bucket: str, dest_object: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("copy_object_safe", {"source_bucket_name": source_bucket, "source_object_name": source_object, "destination_bucket_name": dest_bucket, "destination_object_name": dest_object})

async def move_object(source_bucket: str, source_object: str, dest_bucket: str, dest_object: str) -> Dict[str, Any]:
    # MCP does not support move_object directly. Implementing as copy + delete.
    client = await ensure_mcp()
    copy_res = await client.call_tool("copy_object_safe", {"source_bucket_name": source_bucket, "source_object_name": source_object, "destination_bucket_name": dest_bucket, "destination_object_name": dest_object})
    if "error" in copy_res:
        return copy_res
    return await client.call_tool("delete_object", {"bucket_name": source_bucket, "object_name": source_object})

async def upload_object(bucket_name: str, object_name: str, file_path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("upload_object_safe", {"bucket_name": bucket_name, "object_name": object_name, "file_path": file_path})

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

async def upload_file_from_local(bucket_name: str, source_file_path: str, destination_blob_name: str) -> Dict[str, Any]:
    """Uploads a file from the local filesystem to GCS and returns a Signed URL."""
    try:
        if not os.path.exists(source_file_path):
             return {"error": f"Source file not found: {source_file_path}"}
        
        def _upload_and_sign():
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(source_file_path)
            
            try:
                # Use v4 signing
                return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
            except:
                # Fallback to Console URL (requires login)
                return f"https://storage.cloud.google.com/{bucket_name}/{destination_blob_name}"

        signed_url = await asyncio.to_thread(_upload_and_sign)
        gcs_uri = f"gs://{bucket_name}/{destination_blob_name}"
        
        return {
            "result": f"Successfully uploaded {source_file_path} to {gcs_uri}.",
            "gcs_uri": gcs_uri,
            "signed_url": signed_url
        }
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        return {"error": str(e)}

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


# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_storage_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=manifest.get("agent_id", "storage_specialist"),
        model=model_to_use,
        description=manifest.get("description", "Storage Specialist."),
        instruction=instruction_str,
        tools=[
            list_objects, read_object_metadata, read_object_content, delete_object, 
            write_object, update_object_metadata, copy_object, move_object, 
            upload_object, download_object, list_buckets, create_bucket, 
            delete_bucket, get_bucket_metadata, update_bucket_labels, 
            get_bucket_location, view_iam_policy, check_iam_permissions, 
            get_metadata_table_schema, execute_insights_query, list_insights_configs,
            upload_file_from_local
        ]
    )

def create_app(model_name: str = None):
    # Retrieve or create agent
    agent_instance = create_storage_agent(model_name)
    
    return App(
        name="finopti_storage_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3),
            # BigQueryAgentAnalyticsPlugin(
            #     project_id=config.GCP_PROJECT_ID,
            #     dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
            #     table_id=config.BQ_ANALYTICS_TABLE,
            #     config=BigQueryLoggerConfig(enabled=True)
            # )
        ]
    )


async def send_message_async(prompt: str, user_email: str = None) -> str:
    # Create new client for this request (and this event loop)
    mcp = StorageMCPClient()
    token_reset = _mcp_ctx.set(mcp)
    
    try:
        await mcp.connect()

        # Define run_once for fallback logic
        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                await runner.session_service.create_session(
                    session_id="default",
                    user_id="default",
                    app_name="finopti_storage_agent"
                )
                message = types.Content(parts=[types.Part(text=prompt)])
                
                async for event in runner.run_async(session_id="default", user_id="default", new_message=message):
                     if hasattr(event, 'content') and event.content:
                         for part in event.content.parts:
                             if part.text: response_text += part.text
            return response_text

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="Storage Agent"
        )
    finally:
        await mcp.close()
        _mcp_ctx.reset(token_reset)

def send_message(prompt: str, user_email: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email))
