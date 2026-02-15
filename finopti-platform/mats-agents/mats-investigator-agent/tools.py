"""
Investigator Agent Tools
"""
import logging
from typing import Dict, Any

from context import _report_progress
from mcp_client import get_github_client

logger = logging.getLogger(__name__)

async def read_file(owner: str, repo: str, path: str, branch: str = "main") -> Dict[str, Any]:
    """Read contents of a file from GitHub"""
    await _report_progress(f"Reading file: {path} (branch={branch})", "TOOL_USE")
    try:
        client = await get_github_client()
        # Note: The underlying MCP might expect different args, adapting to standard GitHub MCP
        return await client.call_tool("read_file", {
            "owner": owner,
            "repo": repo,
            "path": path,
            "ref": branch
        })
    except Exception as e:
        await _report_progress(f"File read failed: {str(e)}", "ERROR")
        return {"error": str(e)}

async def search_code(query: str, owner: str, repo: str) -> Dict[str, Any]:
    """Search for code within a repository"""
    await _report_progress(f"Searching code: '{query}' in {owner}/{repo}", "TOOL_USE")
    try:
        client = await get_github_client()
        return await client.call_tool("search_code", {
            "query": f"{query} repo:{owner}/{repo}"
        })
    except Exception as e:
        await _report_progress(f"Search failed: {str(e)}", "ERROR")
        return {"error": str(e)}
