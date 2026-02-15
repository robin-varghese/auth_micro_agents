"""
Brave Search Agent Tools
"""
import logging
from typing import Dict, Any
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)

async def brave_web_search(query: str, count: int = 10) -> Dict[str, Any]:
    """Perform a web search using Brave."""
    client = await ensure_mcp()
    return await client.call_tool("brave_web_search", {"query": query, "count": count})

async def brave_local_search(query: str, count: int = 5) -> Dict[str, Any]:
    """Perform a local search using Brave."""
    client = await ensure_mcp()
    return await client.call_tool("brave_local_search", {"query": query, "count": count})

async def brave_video_search(query: str, count: int = 10) -> Dict[str, Any]:
    """Perform a video search using Brave."""
    client = await ensure_mcp()
    return await client.call_tool("brave_video_search", {"query": query, "count": count})

async def brave_image_search(query: str, count: int = 10) -> Dict[str, Any]:
    """Perform an image search using Brave."""
    client = await ensure_mcp()
    return await client.call_tool("brave_image_search", {"query": query, "count": count})

async def brave_news_search(query: str, count: int = 10) -> Dict[str, Any]:
    """Perform a news search using Brave."""
    client = await ensure_mcp()
    return await client.call_tool("brave_news_search", {"query": query, "count": count})
