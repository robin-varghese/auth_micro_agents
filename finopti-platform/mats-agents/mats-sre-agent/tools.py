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
        try:
            shutil.rmtree(dst)
        except Exception as e:
            logger.warning(f"Could not clear temp gcloud dir: {e}")
        
    if os.path.exists(src):
        try:
            logger.info(f"Copying gcloud config from {src} to {dst}")
            # ignore_dangling_symlinks=True to avoid crashing on broken symlinks (common in some docker volume mounts)
            shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns('*.lock'), dirs_exist_ok=True, ignore_dangling_symlinks=True)
            _gcloud_config_setup = True
        except Exception as e:
            logger.error(f"Failed to copy gcloud config: {e}")
            # Mark as setup anyway to prevent infinite retry loops in tool calls
            _gcloud_config_setup = True
    else:
        logger.warning(f"GCloud config source {src} not found. Proceeding without copying.")
        _gcloud_config_setup = True

async def read_logs(project_id: str, filter_str: str, hours_ago: int = 1) -> Dict[str, Any]:
    """
    Fetch logs from Cloud Logging using gcloud CLI.
    
    Args:
        project_id: GCP Project ID
        filter_str: Cloud Logging filter (e.g., 'severity=ERROR')
        hours_ago: How far back to search in hours
    """
    setup_gcloud_config()
    
    # Enforce Environment Project ID to prevent hallucinations
    env_project_id = os.environ.get("GCP_PROJECT_ID")
    override_warning = ""
    if env_project_id and env_project_id != project_id:
        logger.warning(f"Agent attempted to query project '{project_id}' but is restricted to '{env_project_id}'. Overriding.")
        override_warning = f" [WARNING: Project '{project_id}' does not exist or is restricted. Query was executed against '{env_project_id}' instead.]"
        project_id = env_project_id

    await _report_progress(f"Querying Cloud Logging for project {project_id} (filter='{filter_str}')", "TOOL_USE")
    
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
        "--limit=20",
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
                        "protoPayload": log.get("protoPayload"), # Crucial for Audit Logs (IAM)
                        "resource": log.get("resource"),
                        "insertId": log.get("insertId")
                    })
                
                log_count = len(simplified_logs)
                await _report_progress(f"Found {log_count} relevant logs.", "OBSERVATION")
                return {"logs": simplified_logs, "count": log_count, "note": override_warning if override_warning else None}
            except json.JSONDecodeError:
                return {"error": "Failed to parse gcloud output JSON", "raw_output": result.stdout[:500]}
        else:
            await _report_progress(f"GCloud command failed: {result.stderr[:100]}", "ERROR")
            return {"error": f"gcloud failed: {result.stderr}"}

    except Exception as e:
        await _report_progress(f"Execution failed: {str(e)}", "ERROR")
        return {"error": f"Execution exception: {str(e)}"}
