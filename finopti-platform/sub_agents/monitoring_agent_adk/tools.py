"""
Monitoring Agent Tools
"""
import logging
from typing import Dict, Any, List
from context import _auth_token_ctx
from mcp_client import MonitoringMCPClient

logger = logging.getLogger(__name__)

async def query_logs(project_id: str, filter: str = "", limit: int = 10, minutes_ago: int = 2) -> Dict[str, Any]:
    # HARD CAP: Force max 7 days (10080m) to allow finding older errors while preventing 30-day queries.
    # Buffer fix (10MB) handles the volume.
    if minutes_ago > 10080:
        logger.warning(f"Capping minutes_ago from {minutes_ago} to 10080 to prevent timeout.")
        minutes_ago = 10080
        
    auth_token = _auth_token_ctx.get()
    if not auth_token:
        import os
        auth_token = os.environ.get("CLOUDSDK_AUTH_ACCESS_TOKEN")
    try:
        async with MonitoringMCPClient(auth_token=auth_token) as client:
            result = await client.call_tool("query_logs", {
                "project_id": project_id, 
                "filter": filter, 
                "limit": limit,
                "minutes_ago": minutes_ago
            })
            
            # [NEW] Report Log Observation for the "Eye" icon in UI
            from context import _report_progress
            import json
            
            # Check for output or standard JSON result
            log_data = result.get("output", str(result))
            # limit for UI display
            summary = log_data[:2000] + "..." if len(log_data) > 2000 else log_data
            
            await _report_progress(
                f"Real Log Extracts from {project_id}:\n\n{summary}",
                event_type="OBSERVATION"
            )
            
            return result
    except Exception as e:
        logger.error(f"Query Logs failed: {e}")
        return {"error": str(e)}

async def list_metrics(project_id: str, filter: str = "") -> Dict[str, Any]:
    auth_token = _auth_token_ctx.get()
    if not auth_token:
        import os
        auth_token = os.environ.get("CLOUDSDK_AUTH_ACCESS_TOKEN")
    try:
        async with MonitoringMCPClient(auth_token=auth_token) as client:
            return await client.call_tool("list_metrics", {"project_id": project_id, "filter": filter})
    except Exception as e:
        logger.error(f"List Metrics failed: {e}")
        return {"error": str(e)}

async def query_time_series(project_id: str, metric_filter: str, resource_filter: str = "", minutes_ago: int = 60) -> Dict[str, Any]:
    # HARD CAP: Force max 60 minutes
    if minutes_ago > 60:
         logger.warning(f"Capping minutes_ago from {minutes_ago} to 60.")
         minutes_ago = 60

    auth_token = _auth_token_ctx.get()
    try:
        async with MonitoringMCPClient(auth_token=auth_token) as client:
            return await client.call_tool("query_time_series", {
                "project_id": project_id, 
                "metric_filter": metric_filter,
                "resource_filter": resource_filter,
                "minutes_ago": minutes_ago
            })
    except Exception as e:
        logger.error(f"Query Time Series failed: {e}")
        return {"error": str(e)}
