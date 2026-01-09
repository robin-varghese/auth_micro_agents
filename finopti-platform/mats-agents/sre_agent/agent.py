
"""
MATS SRE Agent - Triage & Evidence Extraction
"""
import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any, List

# Add parent directory to path for shared imports if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.adk.runners import InMemoryRunner
from google.genai import types

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import config
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY


# -------------------------------------------------------------------------
# ASYNC MCP CLIENT BASE
# -------------------------------------------------------------------------
class AsyncMCPClient:
    def __init__(self, image: str, mount_path: str):
        self.image = image
        self.mount_path = mount_path
        self.process = None
        self.request_id = 0

    async def connect(self, client_name: str):
        """Start container and perform handshake"""
        cmd = [
            "docker", "run", 
            "-i", "--rm", 
            "-v", self.mount_path,
            self.image
        ]
        
        logger.info(f"[{client_name}] Starting MCP: {' '.join(cmd)}")
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Handshake
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": "1.0"}
            })
            
            # Read initialize response
            line = await self.process.stdout.readline()
            if not line:
                stderr = await self.process.stderr.read()
                raise RuntimeError(f"MCP Init Failed. Stderr: {stderr.decode()}")
            
            # Send initialized notification
            await self._send_notification("notifications/initialized", {})
            logger.info(f"[{client_name}] Connected & Initialized")
            
        except Exception as e:
            logger.error(f"[{client_name}] Connection failed: {e}")
            await self.close()
            raise

    async def _send_request(self, method, params):
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0", 
            "method": method, 
            "params": params, 
            "id": self.request_id
        }
        json_str = json.dumps(payload) + "\n"
        self.process.stdin.write(json_str.encode())
        await self.process.stdin.drain()
        return self.request_id

    async def _send_notification(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        json_str = json.dumps(payload) + "\n"
        self.process.stdin.write(json_str.encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        if not self.process:
            raise RuntimeError("MCP client not connected")
            
        req_id = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        try:
            while True:
                # Add timeout for tool execution
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=300.0)
                if not line:
                    raise RuntimeError("MCP Connection Closed Unexpectedly")
                
                try:
                    msg = json.loads(line.decode())
                    if msg.get("id") == req_id:
                         if "error" in msg:
                             return {"error": f"Tool Error: {msg['error']}"}
                         
                         res = msg.get("result", {})
                         # Extract text content
                         if "content" in res:
                             text = ""
                             for c in res["content"]:
                                 if c["type"] == "text":
                                     text += c["text"]
                             # Try parsing inner JSON if possible, else return text
                             try:
                                 return json.loads(text)
                             except:
                                 return {"output": text}
                         return res
                except json.JSONDecodeError:
                    continue
        except asyncio.TimeoutError:
             return {"error": "Tool execution timed out after 300s"}
        except Exception as e:
             return {"error": f"Client Error: {e}"}

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except:
                pass
            self.process = None

# -------------------------------------------------------------------------
# GLOBAL CLIENTS
# -------------------------------------------------------------------------
_gcloud_client = None
_monitoring_client = None

async def get_gcloud_client():
    global _gcloud_client
    if not _gcloud_client:
        mount = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        image = os.getenv('GCLOUD_MCP_DOCKER_IMAGE', 'finopti-gcloud-mcp')
        _gcloud_client = AsyncMCPClient(image, mount)
        await _gcloud_client.connect("mats-sre-gcloud")
    return _gcloud_client

async def get_monitoring_client():
    global _monitoring_client
    if not _monitoring_client:
        mount = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        image = os.getenv('MONITORING_MCP_DOCKER_IMAGE', 'finopti-monitoring-mcp')
        _monitoring_client = AsyncMCPClient(image, mount)
        await _monitoring_client.connect("mats-sre-monitoring")
    return _monitoring_client

# -------------------------------------------------------------------------
# ADK TOOLS
# -------------------------------------------------------------------------
async def read_logs(project_id: str, filter_str: str, hours_ago: int = 1) -> Dict[str, Any]:
    """Fetch logs from Cloud Logging. Filter example: 'severity=ERROR'"""
    try:
        client = await get_monitoring_client()
        return await client.call_tool("query_logs", {
            "project_id": project_id,
            "filter": filter_str,
            "hours_ago": hours_ago,
            "limit": 50 
        })
    except Exception as e:
        return {"error": str(e)}

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
sre_agent = Agent(
    name="mats_sre_agent",
    model=config.FINOPTIAGENTS_LLM,
    description="Senior SRE responsible for triaging production incidents.",
    instruction="""
    You are a Senior Site Reliability Engineer (SRE).
    Your goal is to extract factual evidence from Google Cloud logs to pinpoint the "Smoking Gun."
    
    OPERATIONAL RULES:
    1. FILTER: Always filter logs by `severity="ERROR"` first.
    2. VERSIONING: Scan logs for 'git_commit_sha', 'image_tag' or 'version'. THIS IS CRITICAL.
    3. FACTUAL: Identify the exact Timestamp, Request ID, and Stack Trace.
    4. NO HALLUCINATION: If logs are empty, say "No logs found".
    
    OUTPUT JSON FORMAT:
    {
        "incident_timestamp": "...",
        "service_name": "...",
        "version_sha": "...",
        "error_signature": "...",
        "stack_trace_snippet": "..."
    }
    """,
    tools=[read_logs] 
)

# Plugins
bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    )
)

app_instance = App(
    name="mats_sre_agent_app",
    root_agent=sre_agent,
    plugins=[
        ReflectAndRetryToolPlugin(),
        bq_plugin
    ]
)

# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def process_request(prompt: str):
    response_text = ""
    try:
        async with InMemoryRunner(app=app_instance) as runner:
            sid = "default"
            await runner.session_service.create_session(session_id=sid, user_id="user", app_name="mats_sre_agent_app")
            msg = types.Content(parts=[types.Part(text=prompt)])
            
            async for event in runner.run_async(user_id="user", session_id=sid, new_message=msg):
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                            response_text += part.text
    except Exception as e:
        response_text = f"Error: {e}"
    
    return response_text
