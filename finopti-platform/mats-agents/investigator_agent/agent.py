
"""
MATS Investigator Agent - Code Analysis
"""
import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any, List

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import config
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY


# -------------------------------------------------------------------------
# ASYNC MCP CLIENT (Re-using pattern)
# -------------------------------------------------------------------------
class AsyncMCPClient:
    def __init__(self, image: str, env_vars: Dict[str, str]):
        self.image = image
        self.env_vars = env_vars
        self.process = None
        self.request_id = 0

    async def connect(self, client_name: str):
        # Build docker run command with environment variables
        cmd = ["docker", "run", "-i", "--rm"]
        for k, v in self.env_vars.items():
            cmd.extend(["-e", f"{k}={v}"])
        cmd.append(self.image)
        
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
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()
        return self.request_id

    async def _send_notification(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
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
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=300.0)
                if not line:
                    raise RuntimeError("MCP Connection Closed Unexpectedly")
                
                try:
                    msg = json.loads(line.decode())
                    if msg.get("id") == req_id:
                         if "error" in msg:
                             return {"error": msg['error']}
                         
                         res = msg.get("result", {})
                         # Text extraction logic
                         if "content" in res:
                             text = ""
                             for c in res["content"]:
                                 if c["type"] == "text":
                                     text += c["text"]
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
# GITHUB CLIENT
# -------------------------------------------------------------------------
_github_client = None

async def get_github_client():
    global _github_client
    if not _github_client:
        image = os.getenv('GITHUB_MCP_DOCKER_IMAGE', 'finopti-github-mcp-server')
        token = os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN')
        if not token:
            logger.warning("No GITHUB_PERSONAL_ACCESS_TOKEN found!")
            
        _github_client = AsyncMCPClient(image, {"GITHUB_PERSONAL_ACCESS_TOKEN": token})
        await _github_client.connect("mats-investigator")
    return _github_client

# -------------------------------------------------------------------------
# ADK TOOLS
# -------------------------------------------------------------------------
async def read_file(owner: str, repo: str, path: str, branch: str = "main") -> Dict[str, Any]:
    """Read contents of a file from GitHub"""
    try:
        client = await get_github_client()
        # Note: The underlying MCP might expect different args, adapting to standard GitHub MCP
        return await client.call_tool("read_file", {
            "owner": owner,
            "repo": repo,
            "path": path,
            "ref": branch
        })
    except Exception as e:
        return {"error": str(e)}

async def search_code(query: str, owner: str, repo: str) -> Dict[str, Any]:
    """Search for code within a repository"""
    try:
        client = await get_github_client()
        return await client.call_tool("search_code", {
            "query": f"{query} repo:{owner}/{repo}"
        })
    except Exception as e:
        return {"error": str(e)}

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
investigator_agent = Agent(
    name="mats_investigator_agent",
    model=config.FINOPTIAGENTS_LLM,
    description="Code Investigator.",
    instruction="""
    You are a Senior Backend Developer (Investigator).
    Your goal is to use the SRE's findings to locate the bug in the code.
    
    OPERATIONAL RULES:
    1. TARGETING: Use the 'version_sha' from SRE used. If missing, use 'main'.
    2. MAPPING: Map the Stack Trace provided by SRE directly to line numbers.
    3. SIMULATION: "Mental Sandbox" execution. Trace the path of valid/invalid data.
    
    OUTPUT FORMAT:
    1. File Path & Line Number of root cause.
    2. Logic Flaw Description.
    3. Evidence (Values of variables, etc).
    """,
    tools=[read_file, search_code] 
)

bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=config.BQ_ANALYTICS_TABLE,
    config=BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    )
)

app_instance = App(
    name="mats_investigator_app",
    root_agent=investigator_agent,
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
            await runner.session_service.create_session(session_id=sid, user_id="user", app_name="mats_investigator_app")
            msg = types.Content(parts=[types.Part(text=prompt)])
            
            async for event in runner.run_async(user_id="user", session_id=sid, new_message=msg):
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
    except Exception as e:
        response_text = f"Error: {e}"
    
    return response_text
