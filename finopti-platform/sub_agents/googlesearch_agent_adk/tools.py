"""
Google Search Agent Tools
"""
from typing import Dict, Any

# ADK Native Tool
from google.adk.tools import google_search

async def search(query: str) -> Dict[str, Any]:
    """
    Perform a Google Search.
    
    Args:
        query: The search query.
    """
    # Simply wrap the native ADK tool if needed, 
    # but for now we just export it for consistency.
    return google_search(query)
