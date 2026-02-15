"""
Analytics Agent Tools
"""
import logging
from typing import Dict, Any, List
from mcp_client import _mcp_ctx

logger = logging.getLogger(__name__)

async def run_report(property_id: str, dimensions: List[str] = [], metrics: List[str] = []) -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("run_report", {
        "property_id": property_id,
        "dimensions": dimensions,
        "metrics": metrics
    })

async def run_realtime_report(property_id: str, dimensions: List[str] = [], metrics: List[str] = []) -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("run_realtime_report", {
        "property_id": property_id,
        "dimensions": dimensions,
        "metrics": metrics
    })

async def get_account_summaries() -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("get_account_summaries", {})

async def get_property_details(property_id: str) -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("get_property_details", {"property_id": property_id})

async def get_custom_dimensions_and_metrics(property_id: str) -> Dict[str, Any]:
    client = _mcp_ctx.get()
    if not client: raise RuntimeError("MCP not initialized for this context")
    return await client.call_tool("get_custom_dimensions_and_metrics", {"property_id": property_id})
