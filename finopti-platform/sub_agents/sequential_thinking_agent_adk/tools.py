"""
Sequential Thinking Agent Tools
"""
import logging
from typing import Dict, Any
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)

async def sequentialthinking(thought: str, nextThoughtNeeded: bool = False, thoughtNumber: int = 0, totalThoughts: int = 0, isRevision: bool = False) -> Dict[str, Any]:
    """
    Facilitates high-quality reasoning through a structured, sequential thinking process.
    
    Args:
        thought: The thinking step content.
        nextThoughtNeeded: Whether another thinking step is needed.
        thoughtNumber: The current step number.
        totalThoughts: Estimated total steps.
        isRevision: Whether this functionality revises a previous thought.
    """
    client = await ensure_mcp()
    return await client.call_tool("sequentialthinking", {
        "thought": thought,
        "nextThoughtNeeded": nextThoughtNeeded,
        "thoughtNumber": thoughtNumber,
        "totalThoughts": totalThoughts,
        "isRevision": isRevision
    })
