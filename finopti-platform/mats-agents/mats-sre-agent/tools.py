"""
SRE Agent Tools
"""
import os
import json
import logging
import subprocess
import shutil
import datetime
import asyncio
from typing import Dict, Any

from context import _report_progress

logger = logging.getLogger(__name__)

async def read_logs(project_id: str, filter_str: str, hours_ago: int = 48) -> Dict[str, Any]:
    """
    Fetch logs by delegating to the Monitoring Agent via APISIX.
    
    Args:
        project_id: GCP Project ID
        filter_str: Cloud Logging filter (e.g., 'severity=ERROR')
        hours_ago: How far back to search in hours
    """
    from config import config
    import requests
    import asyncio
    
    # Enforce Environment Project ID to prevent hallucinations
    env_project_id = os.environ.get("GCP_PROJECT_ID")
    override_warning = ""
    if env_project_id and env_project_id != project_id:
        logger.warning(f"Agent attempted to query project '{project_id}' but is restricted to '{env_project_id}'. Overriding.")
        override_warning = f" [WARNING: Project '{project_id}' does not exist or is restricted. Query was executed against '{env_project_id}' instead.]"
        project_id = env_project_id

    await _report_progress(f"Delegating log query for {project_id} to Monitoring Agent...\nFilter: {filter_str}\nHours Ago: {hours_ago}", "TOOL_USE")
    
    url = f"{config.APISIX_URL}/agent/monitoring/execute"
    
    # Construct robust prompt for Monitoring Agent
    # We explicitly ask for JSON format if possible, but handle text.
    prompt = (
        f"Please query logs for project '{project_id}'.\n"
        f"Filter: {filter_str}\n"
        f"Time Range: Last {hours_ago} hours.\n"
        f"Instruction: Return a detailed summary of the logs found, including severity, timestamp, and textPayload. "
        f"If specific errors are found, list them explicitly."
    )
    
    payload = {
        "prompt": prompt,
        "user_email": "mats-sre@system.local",
        "project_id": project_id
    }
    
    headers = {}
    
    # Inject Trace Headers
    try:
        from common.observability import FinOptiObservability
        FinOptiObservability.inject_trace_to_headers(headers)
    except ImportError:
        pass

    # Inject Auth Token
    try:
        from context import _auth_token_ctx
        token = _auth_token_ctx.get()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    except ImportError:
        pass
        
    payload["headers"] = headers
        
    logger.info(f"Calling Monitoring Agent at {url}")
    
    try:
        loop = asyncio.get_running_loop()
        
        def _call_svc():
            resp = requests.post(url, json=payload, headers=headers, timeout=120) # 2 min timeout for monitoring agent
            return resp
            
        response = await loop.run_in_executor(None, _call_svc)
        
        if response.status_code != 200:
            return {"error": f"Monitoring Agent failed: {response.status_code} - {response.text}"}
            
        data = response.json()
        
        # monitoring agent returns {"response": "..."} usually
        agent_response = data.get("response", str(data))
        
        return {
            "summary": agent_response, 
            "note": "Logs fetched via Monitoring Agent." + override_warning,
            "raw_data": data
        }

    except Exception as e:
        logger.error(f"Failed to call Monitoring Agent: {e}")
        await _report_progress(f"Monitoring Agent call failed: {e}", "ERROR")
        return {"error": f"Delegation failed: {str(e)}"}
