"""
GitHub ADK Agent - Repository and Code Specialist

This agent uses Google ADK to handle GitHub interactions.
It integrates with the official GitHub MCP server.
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Add Redis Publisher
try:
    # Ensure current directory is in path (Docker WORKDIR /app)
    if str(Path(__file__).parent) not in sys.path:
        sys.path.append(str(Path(__file__).parent))

    from redis_common.redis_publisher import RedisEventPublisher
except ImportError as e:
    # Fallback or local dev path if not mounted
    sys.path.append(str(Path(__file__).parent.parent.parent / "redis-sessions" / "common"))
    try:
        from redis_publisher import RedisEventPublisher
    except ImportError as e2:
        RedisEventPublisher = None

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

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name="finoptiagents-GitHubAgent",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# --- CONTEXT ISOLATION & PROGRESS (Rule 1 & 6) ---
from contextvars import ContextVar
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes

_session_id_ctx: ContextVar[str] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[str] = ContextVar("user_email", default=None)
_redis_publisher_ctx: ContextVar = ContextVar("redis_publisher", default=None)

def _report_progress(message, event_type="STATUS_UPDATE", icon="🤖", display_type="markdown", metadata=None):
    """Standardized progress reporting using context-bound session/user."""
    pub = _redis_publisher_ctx.get()
    sid = _session_id_ctx.get()
    uid = _user_email_ctx.get() or "unknown"
    if pub and sid:
        try:
            span_ctx = trace.get_current_span().get_span_context()
            trace_id_hex = format(span_ctx.trace_id, '032x') if span_ctx.trace_id else "unknown"
        except Exception:
            trace_id_hex = "unknown"
        pub.publish_event(
            session_id=sid, user_id=uid, trace_id=trace_id_hex,
            msg_type=event_type, message=message, display_type=display_type,
            icon=icon, metadata=metadata
        )

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
            stderr=asyncio.subprocess.PIPE
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
            msg = json.loads(line)
            if msg.get("id") == 0: break
        await self._send_json({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _send_json(self, payload):
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        if not self.github_token:
             raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN is required. Please ask the user for their GitHub PAT.")

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

# --- Tool Wrappers ---

async def _call_gh_tool(tool_name: str, args: dict, pat: str = None) -> Dict[str, Any]:
    try:
        async with GitHubMCPClient(token=pat) as client:
            return await client.call_tool(tool_name, args)
    except ValueError as ve:
        return {"success": False, "error": str(ve), "action_needed": "ask_user_for_pat"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def search_repositories(query: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("search_repositories", {"query": query}, github_pat)

async def list_repositories(github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("list_repositories", {}, github_pat)

async def get_file_contents(owner: str, repo: str, path: str, branch: str = None, github_pat: str = None) -> Dict[str, Any]:
    args = {"owner": owner, "repo": repo, "path": path}
    if branch: args["branch"] = branch
    return await _call_gh_tool("get_file_contents", args, github_pat)

async def create_or_update_file(owner: str, repo: str, path: str, content: str, message: str, branch: str = None, sha: str = None, github_pat: str = None) -> Dict[str, Any]:
    args = {"owner": owner, "repo": repo, "path": path, "content": content, "message": message}
    if branch: args["branch"] = branch
    if sha: args["sha"] = sha
    return await _call_gh_tool("create_or_update_file", args, github_pat)

async def push_files(owner: str, repo: str, branch: str, files: str, message: str, github_pat: str = None) -> Dict[str, Any]:
    """
    Push files to a branch.
    files: JSON string representing list of files [{'path': '...', 'content': '...'}, ...]
    """
    try:
         if isinstance(files, str):
             files_list = json.loads(files)
         else:
             files_list = files
    except:
         files_list = files # Fallback
         
    return await _call_gh_tool("push_files", {"owner": owner, "repo": repo, "branch": branch, "files": files_list, "message": message}, github_pat)

async def create_issue(owner: str, repo: str, title: str, body: str = None, github_pat: str = None) -> Dict[str, Any]:
    args = {"owner": owner, "repo": repo, "title": title}
    if body: args["body"] = body
    return await _call_gh_tool("create_issue", args, github_pat)

async def list_issues(owner: str, repo: str, state: str = "open", github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("list_issues", {"owner": owner, "repo": repo, "state": state}, github_pat)

async def update_issue(owner: str, repo: str, issue_number: int, title: str = None, body: str = None, state: str = None, github_pat: str = None) -> Dict[str, Any]:
    args = {"owner": owner, "repo": repo, "issue_number": issue_number}
    if title: args["title"] = title
    if body: args["body"] = body
    if state: args["state"] = state
    return await _call_gh_tool("update_issue", args, github_pat)

async def add_issue_comment(owner: str, repo: str, issue_number: int, body: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("add_issue_comment", {"owner": owner, "repo": repo, "issue_number": issue_number, "body": body}, github_pat)

async def create_pull_request(owner: str, repo: str, title: str, head: str, base: str, body: str = None, github_pat: str = None) -> Dict[str, Any]:
    args = {"owner": owner, "repo": repo, "title": title, "head": head, "base": base}
    if body: args["body"] = body
    return await _call_gh_tool("create_pull_request", args, github_pat)

async def list_pull_requests(owner: str, repo: str, state: str = "open", github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("list_pull_requests", {"owner": owner, "repo": repo, "state": state}, github_pat)

async def merge_pull_request(owner: str, repo: str, pull_number: int, merge_method: str = "merge", github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("merge_pull_request", {"owner": owner, "repo": repo, "pull_number": pull_number, "merge_method": merge_method}, github_pat)

async def get_pull_request(owner: str, repo: str, pull_number: int, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("get_pull_request", {"owner": owner, "repo": repo, "pull_number": pull_number}, github_pat)

async def create_branch(owner: str, repo: str, branch: str, from_branch: str = "main", github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("create_branch", {"owner": owner, "repo": repo, "branch": branch, "from_branch": from_branch}, github_pat)

async def list_branches(owner: str, repo: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("list_branches", {"owner": owner, "repo": repo}, github_pat)

async def get_commit(owner: str, repo: str, ref: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("get_commit", {"owner": owner, "repo": repo, "ref": ref}, github_pat)

async def search_code(q: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("search_code", {"q": q}, github_pat)

async def search_issues(q: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("search_issues", {"q": q}, github_pat)

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
        instruction_str = data.get("instruction", "You are a GitHub Specialist.")
else:
    instruction_str = "You are a GitHub Specialist."


# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

def create_github_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=manifest.get("agent_id", "github_specialist"),
        model=model_to_use,
        description=manifest.get("description", "GitHub Specialist."),
        instruction=instruction_str,
        tools=[
            search_repositories, list_repositories, get_file_contents, create_or_update_file,
            push_files, create_issue, list_issues, update_issue, add_issue_comment,
            create_pull_request, list_pull_requests, merge_pull_request, get_pull_request,
            create_branch, list_branches, get_commit, search_code, search_issues
        ]
    )

def create_app(model_name: str = None):
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    if config.GCP_PROJECT_ID:
        os.environ["GOOGLE_CLOUD_PROJECT"] = config.GCP_PROJECT_ID
        os.environ["GCP_PROJECT_ID"] = config.GCP_PROJECT_ID

    agent = create_github_agent(model_name)

    return App(
        name="finopti_github_agent",
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

async def send_message_async(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    try:
        # --- CONTEXT SETTING (Rule 1 & 6) ---
        _session_id_ctx.set(session_id)
        _user_email_ctx.set(user_email or "unknown")

        # Trace attribute setting (Rule 5)
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(SpanAttributes.SESSION_ID, session_id or "unknown")
            if user_email:
                span.set_attribute("user_id", user_email)

        # Initialize Redis Publisher
        publisher = None
        if RedisEventPublisher:
             try:
                 publisher = RedisEventPublisher(
                     agent_name="GitHub Agent",
                     agent_role="Repository Specialist"
                 )
                 _redis_publisher_ctx.set(publisher)
             except: pass

        # Publish "Processing" event via standardized helper
        _report_progress(f"Processing GitHub request: {prompt[:50]}...", icon="🐙", display_type="toast")

        # Define run_once for fallback logic
        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                sid = session_id
                uid = user_email or "default"
                await runner.session_service.create_session(session_id=sid, user_id=uid, app_name="finopti_github_agent")
                message = types.Content(parts=[types.Part(text=prompt)])
                
                async for event in runner.run_async(session_id=sid, user_id=uid, new_message=message):
                     # Stream Events
                     if publisher:
                         publisher.process_adk_event(event, session_id=sid, user_id=uid)
                         
                     if hasattr(event, 'content') and event.content:
                         for part in event.content.parts:
                             if part.text: response_text += part.text
            return response_text

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="GitHub Agent"
        )
    except Exception as e:
        return f"Error: {str(e)}"

def send_message(prompt: str, user_email: str = None, session_id: str = "default") -> str:
    return asyncio.run(send_message_async(prompt, user_email, session_id))
