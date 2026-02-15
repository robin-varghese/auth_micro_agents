"""
Monitoring Agent Tools
"""
import logging
from typing import Dict, Any, List
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)

async def query_logs(project_id: str, filter: str = "", limit: int = 10, minutes_ago: int = 2) -> Dict[str, Any]:
    # HARD CAP: Force max 24 hours (1440m) to allow finding older errors while preventing 30-day queries.
    # Buffer fix (10MB) handles the volume.
    if minutes_ago > 1440:
        logger.warning(f"Capping minutes_ago from {minutes_ago} to 1440 to prevent timeout.")
        minutes_ago = 1440
        
    client = await ensure_mcp()
    # Tool name in MCP is 'query_logs'
    return await client.call_tool("query_logs", {
        "project_id": project_id, 
        "filter": filter, 
        "limit": limit,
        "minutes_ago": minutes_ago
    })

async def list_metrics(project_id: str, filter: str = "") -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_metrics", {"project_id": project_id, "filter": filter})

async def query_time_series(project_id: str, metric_type: str, resource_filter: str = "", minutes_ago: int = 60) -> Dict[str, Any]:
    # HARD CAP: Force max 60 minutes
    if minutes_ago > 60:
         logger.warning(f"Capping minutes_ago from {minutes_ago} to 60.")
         minutes_ago = 60

    client = await ensure_mcp()
    return await client.call_tool("query_time_series", {
        "project_id": project_id, 
        "metric_type": metric_type,
        "resource_filter": resource_filter,
        "minutes_ago": minutes_ago
    })
