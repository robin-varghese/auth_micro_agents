"""
MATS Investigator Agent - Code Analysis
"""
import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any, List
from contextvars import ContextVar

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
# Add Redis Common to path
sys.path.append('/app/redis_common')
try:
    from redis_publisher import RedisEventPublisher
except ImportError:
    pass

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.adk.runners import InMemoryRunner
from google.genai import types

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name="finoptiagents-MATS",  # Unified project for all MATS agents
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import config
if config.GOOGLE_API_KEY and not (config.GOOGLE_GENAI_USE_VERTEXAI and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"):
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    logger.info("Using API Key for authentication (Vertex AI disabled)")
else:
    if "GOOGLE_API_KEY" in os.environ:
        del os.environ["GOOGLE_API_KEY"]
    logger.info("Using ADC/Service Account for authentication (Vertex AI enabled)")

# -------------------------------------------------------------------------
# PROGRESS HELPER (ASYNC)
# -------------------------------------------------------------------------
_redis_publisher_ctx: ContextVar["RedisEventPublisher"] = ContextVar("redis_publisher", default=None)
_session_id_ctx: ContextVar[str] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[str] = ContextVar("user_email", default=None)

async def _report_progress(message: str, event_type: str = "INFO"):
    """Helper to send progress to Orchestrator"""
    job_id = os.environ.get("MATS_JOB_ID")
    orchestrator_url = os.environ.get("MATS_ORCHESTRATOR_URL", "http://mats-orchestrator:8084")
    
    if not job_id:
        return

    # Redis Publishing
    publisher = _redis_publisher_ctx.get()
    session_id = _session_id_ctx.get()
    
    if publisher and session_id:
        try:
             # Map internal event types
             msg_type_map = {
                 "INFO": "STATUS_UPDATE", "TOOL_USE": "TOOL_CALL", "OBSERVATION": "OBSERVATION", 
                 "ERROR": "ERROR", "THOUGHT": "THOUGHT"
             }
             mapped_type = msg_type_map.get(event_type, "STATUS_UPDATE")
             icons = {"INFO": "ℹ️", "TOOL_USE": "🛠️", "OBSERVATION": "👁️", "ERROR": "❌", "THOUGHT": "🧠"}
             
             publisher.publish_event(
                 session_id=session_id, user_id=_user_email_ctx.get() or "investigator", trace_id="unknown",
                 msg_type=mapped_type, message=message,
                 display_type="markdown" if mapped_type == "THOUGHT" else "console_log",
                 icon=icons.get(event_type, "🤖")
             )
        except: pass

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, 
            lambda: requests.post(
                f"{orchestrator_url}/jobs/{job_id}/events",
                json={
                    "type": event_type,
                    "message": message,
                    "source": "mats-investigator-agent"
                },
                timeout=2
            )
        )
    except Exception as e:
        logger.warning(f"Failed to report progress: {e}")

# -------------------------------------------------------------------------
# ASYNC MCP CLIENT
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
    await _report_progress(f"Reading file: {path} (branch={branch})", "TOOL_USE")
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
        await _report_progress(f"File read failed: {str(e)}", "ERROR")
        return {"error": str(e)}

async def search_code(query: str, owner: str, repo: str) -> Dict[str, Any]:
    """Search for code within a repository"""
    await _report_progress(f"Searching code: '{query}' in {owner}/{repo}", "TOOL_USE")
    try:
        client = await get_github_client()
        return await client.call_tool("search_code", {
            "query": f"{query} repo:{owner}/{repo}"
        })
    except Exception as e:
        await _report_progress(f"Search failed: {str(e)}", "ERROR")
        return {"error": str(e)}

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
def create_investigator_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name="mats_investigator_agent",
        model=model_to_use,
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

    AVAILABLE SUB-AGENT CAPABILITIES (For Context Only):
    - GitHub Specialist: search_repositories, list_repositories, get_file_contents, create_or_update_file, push_files, create_issue, list_issues, update_issue, add_issue_comment, create_pull_request, list_pull_requests, merge_pull_request, get_pull_request, create_branch, list_branches, get_commit, search_code, search_issues
    - Code Execution Specialist: execute_python_code, solve_math_problems, process_data, generate_text_programmatically
    - GCloud Specialist: run_gcloud_command
    """,
    tools=[read_file, search_code] 
    )


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def process_request(prompt_or_payload: Any, session_id: str = None, user_email: str = None):
    # Ensure API Key state is consistent
    if config.GOOGLE_API_KEY and not (config.GOOGLE_GENAI_USE_VERTEXAI and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"):
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    else:
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
            
    # Force project ID into environment for Vertex AI auto-detection
    if config.GCP_PROJECT_ID:
        os.environ['GOOGLE_CLOUD_PROJECT'] = config.GCP_PROJECT_ID
        os.environ['GCP_PROJECT_ID'] = config.GCP_PROJECT_ID
        
    # Handle Dict or JSON stirng payload
    prompt = ""
    job_id = None
    orchestrator_url = None
    
    # Parse generic input
    if isinstance(prompt_or_payload, dict):
        prompt = prompt_or_payload.get("message", "")
        job_id = prompt_or_payload.get("job_id")
        orchestrator_url = prompt_or_payload.get("orchestrator_url")
        # Allow payload to override session_id if provided there
        if not session_id:
             session_id = prompt_or_payload.get("session_id")
    else:
         # Try to parse string as json just in case
         input_str = str(prompt_or_payload)
         try:
             data = json.loads(input_str)
             if isinstance(data, dict):
                 prompt = data.get("message", input_str)
                 job_id = data.get("job_id")
                 orchestrator_url = data.get("orchestrator_url")
                 if not session_id:
                    session_id = data.get("session_id")
             else:
                 prompt = input_str
         except:
             prompt = input_str
             
    # Set Env vars for tools to access context
    if job_id:
        os.environ["MATS_JOB_ID"] = job_id
    if orchestrator_url:
        os.environ["MATS_ORCHESTRATOR_URL"] = orchestrator_url

    # --- Trace Context Extraction ---
    trace_context = {}
    if isinstance(prompt_or_payload, dict):
        trace_context = prompt_or_payload.get("headers", {})
    elif isinstance(prompt_or_payload, str):
         try:
             d = json.loads(prompt_or_payload)
             if isinstance(d, dict):
                 trace_context = d.get("headers", {})
         except: pass

    # Extract parent trace context for span linking
    from opentelemetry import propagate, trace
    from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues
    
    parent_ctx = propagate.extract(trace_context) if trace_context else None
    tracer = trace.get_tracer(__name__)
    
    # Extract user_email from payload if not already provided
    if not user_email and isinstance(prompt_or_payload, dict):
        user_email = prompt_or_payload.get("user_email")
    
    # Store user_email in ContextVar for _report_progress
    if user_email:
        _user_email_ctx.set(user_email)

    # Initialize Redis Publisher
    try:
        pub = RedisEventPublisher("MATS Investigator", "Investigator")
        _redis_publisher_ctx.set(pub)
        if session_id:
            _session_id_ctx.set(session_id)
            pub.publish_event(
                session_id=session_id, user_id=user_email or "investigator", trace_id="unknown",
                msg_type="STATUS_UPDATE", message=f"Investigator starting analysis...",
                display_type="step_progress", icon="🕵️"
            )
    except: pass
    
    # Create child span linked to orchestrator's root span
    span_context = {"context": parent_ctx} if parent_ctx else {}
    
    with tracer.start_as_current_span(
        "investigator_code_analysis",
        **span_context,
        attributes={
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
            "agent.name": "mats-investigator",
            "agent.type": "code_analysis"
        }
    ) as span:
        # Set session.id for Phoenix session grouping
        if session_id and span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            logger.info(f"[{session_id}] Investigator: Set session.id on span")
        # Initialize Observability (legacy compatibility)
        try:
            from common.observability import FinOptiObservability
            FinOptiObservability.setup("mats-investigator-agent")
            if trace_context:
                FinOptiObservability.middleware_extract_trace(trace_context)
        except ImportError:
             logger.warning("Common Observability lib missing")


        # Define helpers for fallback
        def _create_app(model_name: str):
            investigator_agent_instance = create_investigator_agent(model_name)
            
            # Recreate plugin per app instance
            bq_plugin = BigQueryAgentAnalyticsPlugin(
                project_id=os.getenv("GCP_PROJECT_ID"),
                dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
                table_id=config.BQ_ANALYTICS_TABLE,
                config=BigQueryLoggerConfig(
                    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
                )
            )
            
            return App(
                name="mats_investigator_app",
                root_agent=investigator_agent_instance,
                plugins=[
                    ReflectAndRetryToolPlugin(),
                    bq_plugin
                ]
            )
            
        async def _run_once(app_instance):
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
                                    # Report thought to UI
                                    if job_id:
                                        await _report_progress(part.text[:200], "THOUGHT")
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Runner failed: {err_msg}")
                # Return valid JSON even on error
                error_response = json.dumps({
                    "status": "INSUFFICIENT_DATA",
                    "confidence": 0.0,
                    "hypothesis": f"Investigator internal error: {err_msg}",
                    "blockers": ["Agent internal error during analysis"]
                })
                response_text = error_response
                if "429" in err_msg or "Resource exhausted" in err_msg:
                    raise e
            
             # Check for soft 429 in response text
            if "429 Too Many Requests" in response_text or "Resource exhausted" in response_text:
                 raise RuntimeError(f"soft_429: {response_text}")

            return response_text

        # Execute with fallback logic
        return await run_with_model_fallback(
            create_app_func=_create_app,
            run_func=_run_once,
            context_name="MATS Investigator Agent"
        )
