"""
MATS SRE Agent - Triage & Evidence Extraction

This agent uses Google ADK and directly executes `gcloud` commands via subprocess
to query logs, bypassing MCP server complexities.
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

from config import config

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure API Key is in environment
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY


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
# ADK TOOLS
# -------------------------------------------------------------------------
async def read_logs(project_id: str, filter_str: str, hours_ago: int = 1) -> Dict[str, Any]:
    """
    Fetch logs from Cloud Logging using gcloud CLI.
    
    Args:
        project_id: GCP Project ID
        filter_str: Cloud Logging filter (e.g., 'severity=ERROR')
        hours_ago: How far back to search in hours
    """
    setup_gcloud_config()
    
    # Calculate timestamp
    cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(hours=hours_ago)
    time_str = cutoff_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Combine filter
    # Use parentheses to ensure precedence if filter_str has ORs
    full_filter = f'({filter_str}) AND timestamp >= "{time_str}"'
    
    cmd = [
        "gcloud", "logging", "read",
        full_filter,
        f"--project={project_id}",
        "--format=json",
        "--limit=50",
        "--order=desc" # Newest first
    ]
    
    # Prepare environment
    env = os.environ.copy()
    env["CLOUDSDK_CONFIG"] = "/tmp/gcloud_config"
    env["CLOUDSDK_CORE_DISABLE_FILE_LOGGING"] = "1"
    
    logger.info(f"Executing Log Query: {' '.join(cmd)}")
    
    try:
        # Run subprocess (blocking is acceptable here as we are in a thread/process for this request)
        # Using run_in_executor to avoid blocking the loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=60, # 60s timeout for log query
                env=env
            )
        )
        
        if result.returncode == 0:
            try:
                logs = json.loads(result.stdout)
                # Simplify logs to save context window
                simplified_logs = []
                for log in logs:
                    simplified_logs.append({
                        "timestamp": log.get("timestamp"),
                        "severity": log.get("severity"),
                        "textPayload": log.get("textPayload"),
                        "jsonPayload": log.get("jsonPayload"),
                        "resource": log.get("resource"),
                        "insertId": log.get("insertId")
                    })
                return {"logs": simplified_logs, "count": len(simplified_logs)}
            except json.JSONDecodeError:
                return {"error": "Failed to parse gcloud output JSON", "raw_output": result.stdout[:500]}
        else:
            return {"error": f"gcloud failed: {result.stderr}"}

    except Exception as e:
        return {"error": f"Execution exception: {str(e)}"}


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
    table_id=config.BQ_ANALYTICS_TABLE,
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
                            if part.text:
                                response_text += part.text
    except Exception as e:
        response_text = f"Error: {e}"
        logger.error(f"Runner failed: {e}")
    
    # Fallback if empty (e.g. only tool calls but no final text)
    if not response_text:
        response_text = "Analysis completed but no textual summary was generated. Check logs."

    return response_text
