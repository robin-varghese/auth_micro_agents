"""
Filesystem Agent Tools
"""
import logging
from typing import Dict, Any, List
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)

async def read_text_file(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_text_file", {"path": path})

async def read_media_file(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_media_file", {"path": path})

async def read_multiple_files(paths: List[str]) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_multiple_files", {"paths": paths})

async def write_file(path: str, content: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("write_file", {"path": path, "content": content})

async def edit_file(path: str, edits: List[Dict[str, str]], dryRun: bool = False) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("edit_file", {"path": path, "edits": edits, "dryRun": dryRun})

async def create_directory(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("create_directory", {"path": path})

async def list_directory(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_directory", {"path": path})

async def list_directory_with_sizes(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_directory_with_sizes", {"path": path})

async def move_file(source: str, destination: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("move_file", {"source": source, "destination": destination})

async def search_files(path: str, pattern: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("search_files", {"path": path, "pattern": pattern})

async def directory_tree(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("directory_tree", {"path": path})

async def get_file_info(path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_file_info", {"path": path})

async def list_allowed_directories() -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_allowed_directories", {})
