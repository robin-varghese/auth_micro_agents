"""
Monitoring ADK Agent - Google Cloud Monitoring and Logging Specialist

This agent uses Google ADK to handle GCP monitoring and logging requests.
UPDATED: Uses direct `gcloud` subprocess for `query_logs` to ensure stability for Live Logs.
Retains MCP Client for `query_time_series` (metrics).
"""

import os
import sys
import asyncio
import json
import logging
import subprocess
import shlex
import shutil
import datetime
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.adk.runners import InMemoryRunner
from google.genai import types

from config import config

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# GCLOUD CONFIG HELPER (Fix for Read-Only Filesystem)
# -------------------------------------------------------------------------
_gcloud_config_setup = False

def setup_gcloud_config():
    """Copy mounted gcloud config to writable temp location to avoid Read-Only errors"""
    global _gcloud_config_setup
    if _gcloud_config_setup:
        return

    src = "/root/.config/gcloud"
    dst = "/tmp/gcloud_config"
    
    if os.path.exists(dst):
        shutil.rmtree(dst)
        
    if os.path.exists(src):
        try:
            logger.info(f"Copying gcloud config from {src} to {dst}")
            shutil.copytree(src, dst, dirs_exist_ok=True)
            _gcloud_config_setup = True
        except Exception as e:
            logger.error(f"Failed to copy gcloud config: {e}")
    else:
        logger.warning(f"GCloud config source {src} not found")

# -------------------------------------------------------------------------
# MCP Client for Monitoring (Legacy/Metrics only)
# -------------------------------------------------------------------------
class MonitoringMCPClient:
    """Client for connecting to Monitoring MCP server via Docker Stdio"""
    
    def __init__(self):
        self.image = os.getenv('MONITORING_MCP_DOCKER_IMAGE', 'finopti-monitoring-mcp')
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0
        logging.info(f"MonitoringMCPClient initialized for image: {self.image}")
    
    async def connect(self):
        """Start the MCP server container"""
        cmd = [
            "docker", "run", 
            "-i", "--rm", 
            "-v", self.mount_path,
            self.image
        ]
        
        logging.info(f"Starting MCP server with command: {' '.join(cmd)}")
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
                    "clientInfo": {"name": "finopti-monitoring-agent", "version": "1.0"}
                },
                "id": 0
            }
            
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
                        break
                except json.JSONDecodeError:
                    continue
            
            # 3. Send 'notifications/initialized'
            notify_payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            self.process.stdin.write((json.dumps(notify_payload) + "\n").encode())
            await self.process.stdin.drain()
            
        except Exception as e:
            logging.error(f"Failed to start MCP server: {e}")
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
        """Call Monitoring MCP tool via Stdio"""
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
            self.process.stdin.write(json_str.encode())
            await self.process.stdin.drain()
            
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    raise RuntimeError("MCP server closed connection.")
                
                try:
                    msg = json.loads(line.decode())
                    if msg.get("id") == self.request_id:
                        if "error" in msg:
                            raise RuntimeError(f"MCP tool error: {msg['error']}")
                        return msg.get("result", {})
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            raise RuntimeError(f"Monitoring MCP call failed: {e}") from e

# Global MCP client
_mcp_client = None

async def ensure_client():
    global _mcp_client
    if not _mcp_client:
        _mcp_client = MonitoringMCPClient()
        await _mcp_client.connect()
    return _mcp_client

# -------------------------------------------------------------------------
# ADK TOOLS
# -------------------------------------------------------------------------

async def query_logs(
    project_id: str,
    filter_str: str = "",
    hours_ago: int = 24,
    limit: int = 100
) -> Dict[str, Any]:
    """ADK tool: Query log entries from Cloud Logging using LOCAL GCLOUD CLI (Subprocess)"""
    
    # Use subprocess for logs to support real-time fetching reliably
    setup_gcloud_config()
    
    # Calculate timestamp
    cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(hours=hours_ago)
    time_str = cutoff_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    full_filter = f'({filter_str}) AND timestamp >= "{time_str}"' if filter_str else f'timestamp >= "{time_str}"'
    
    cmd = [
        "gcloud", "logging", "read",
        full_filter,
        f"--project={project_id}",
        "--format=json",
        f"--limit={limit}",
        "--order=desc" 
    ]
    
    env = os.environ.copy()
    env["CLOUDSDK_CONFIG"] = "/tmp/gcloud_config"
    env["CLOUDSDK_CORE_DISABLE_FILE_LOGGING"] = "1"
    
    logger.info(f"Executing Log Query via Subprocess: {' '.join(cmd)}")
    
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=60, 
                env=env
            )
        )
        
        if result.returncode == 0:
            try:
                logs = json.loads(result.stdout)
                # Map to schema expected by consumers
                mapped_logs = []
                for log in logs:
                    mapped_logs.append({
                        "text_payload": log.get("textPayload"),
                        "json_payload": log.get("jsonPayload"),
                        "severity": log.get("severity"),
                        "timestamp": log.get("timestamp"),
                        "resource": log.get("resource")
                    })
                return {
                    "success": True,
                    "data": {"log_entries": mapped_logs}, # Match MCP result structure roughly
                    "tool": "query_logs"
                }
            except json.JSONDecodeError:
                return {"success": False, "error": "Failed to parse JSON output"}
        else:
             return {"success": False, "error": f"gcloud failed: {result.stderr}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def query_time_series(
    project_id: str,
    metric_type: str,
    resource_filter: str = "",
    minutes_ago: int = 60
) -> Dict[str, Any]:
    """ADK tool: Query time series metrics (Uses MCP Client)"""
    try:
        client = await ensure_client()
        result = await client.call_tool(
            "query_time_series", 
            arguments={
                "project_id": project_id,
                "metric_type": metric_type,
                "resource_filter": resource_filter,
                "minutes_ago": minutes_ago
            }
        )
        return {"success": True, "data": result, "tool": "query_time_series"}
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "query_time_series"}


async def list_metrics(
    project_id: str,
    filter_str: str = ""
) -> Dict[str, Any]:
    """ADK tool: List available metric descriptors (Uses MCP Client)"""
    try:
        client = await ensure_client()
        result = await client.call_tool(
            "list_metrics", 
            arguments={
                "project_id": project_id,
                "filter": filter_str or ""
            }
        )
        return {"success": True, "data": result, "tool": "list_metrics"}
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "list_metrics"}


# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
# Helper: Dynamic Model Loading
def get_gemini_model(default_model: str = "gemini-1.5-flash-001") -> str:
    """
    Fetch Gemini model name from Env Var -> Secret -> Default.
    """
    model = os.getenv("FINOPTIAGENTS_LLM")
    if model:
        return model
    
    # Try Secret Manager via config if available
    try:
        model = getattr(config, "FINOPTIAGENTS_LLM", None)
        if model:
            return model
    except Exception:
        pass
        
    return default_model

monitoring_agent = Agent(
    name="cloud_monitoring_specialist",
    model=get_gemini_model(),
    description="Google Cloud monitoring and logging specialist.",
    instruction="""
    You are a Google Cloud Platform (GCP) monitoring and observability specialist.
    
    Your responsibilities:
    1. Query appropriate metrics and logs.
    2. Analyze and present monitoring data clearly.
    
    Tools:
    - query_time_series: Get metrics.
    - query_logs: Search logs.
    - list_metrics: Discover metrics.
    """,
    tools=[query_time_series, query_logs, list_metrics]
)

bq_config = BigQueryLoggerConfig(
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
)

bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=config.GCP_PROJECT_ID,
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=bq_config,
    location="US"
)

if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

app = App(
    name="finopti_monitoring_agent",
    root_agent=monitoring_agent,
    plugins=[
        ReflectAndRetryToolPlugin(),
        bq_plugin
    ]
)

# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def send_message_async(prompt: str, user_email: str = None, project_id: str = None) -> str:
    """Send a message to the Monitoring agent"""
    try:
        enhanced_prompt = f"[Project: {project_id}] {prompt}" if project_id else prompt
        
        # Don't ensure MCP client here globally if we only want logs
        # But keeping it for backward compat if metrics are asked
        
        async with InMemoryRunner(app=app) as runner:
            sid = "default"
            uid = "default"
            await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_monitoring_agent")
            
            message = types.Content(parts=[types.Part(text=enhanced_prompt)])
            response_text = ""
            async for event in runner.run_async(user_id=uid, session_id=sid, new_message=message):
                 if hasattr(event, 'content') and event.content:
                     for part in event.content.parts:
                         if part.text:
                             response_text += part.text
            
            return response_text if response_text else "No response generated."

    except Exception as e:
        return f"Error processing request: {str(e)}"

def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id))

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(send_message(prompt, project_id=config.GCP_PROJECT_ID))
