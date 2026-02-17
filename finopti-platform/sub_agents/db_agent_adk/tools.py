"""
DB Agent Tools
"""
import os
import logging
from typing import Dict, Any, List
from config import config
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)


async def postgres_execute_sql(sql: str) -> Dict[str, Any]:
    """Execute SQL query on PostgreSQL."""
    client = await ensure_mcp()
    try:
        output = await client.call_tool("postgres_execute_sql", {"sql": sql})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def postgres_list_tables() -> Dict[str, Any]:
    """List all PostgreSQL tables available."""
    client = await ensure_mcp()
    try:
        # Note: 'postgres-list-tables' might be 'list-tables' in some setups, but we try specific first
        output = await client.call_tool("postgres_list_tables", {})
        return {"success": True, "output": output}
    except Exception as e:
         # Fallback to generic if specific fails? No, keep it specific as per manifest.
        return {"success": False, "error": str(e)}

async def postgres_list_indexes() -> Dict[str, Any]:
    """List PostgreSQL indexes."""
    client = await ensure_mcp()
    try:
        output = await client.call_tool("postgres_list_indexes", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def postgres_database_overview() -> Dict[str, Any]:
    """Get high-level overview of the PostgreSQL database."""
    client = await ensure_mcp()
    try:
        output = await client.call_tool("postgres_database_overview", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def postgres_list_active_queries() -> Dict[str, Any]:
    """List currently active queries in PostgreSQL."""
    client = await ensure_mcp()
    try:
        output = await client.call_tool("postgres_list_active_queries", {})
        return {"success": True, "output": output}
    except Exception as e:
        return {"success": False, "error": str(e)}
