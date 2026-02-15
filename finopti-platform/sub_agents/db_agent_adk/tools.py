"""
DB Agent Tools
"""
import os
import logging
from typing import Dict, Any, List
from google.cloud import bigquery
from config import config
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)

async def query_agent_analytics(limit: int = 10, days_back: int = 7) -> Dict[str, Any]:
    """
    ADK Tool: Query the Agent Analytics (BigQuery) for recent operations.
    Use this to see what agents have been doing.
    """
    try:
        client = bigquery.Client(project=config.GCP_PROJECT_ID)
        dataset_id = os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics")
        table_id = config.BQ_ANALYTICS_TABLE
        full_table_id = f"{config.GCP_PROJECT_ID}.{dataset_id}.{table_id}"
        
        query = f"""
            SELECT timestamp, event_type, agent, prompt, model
            FROM `{full_table_id}`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days_back} DAY)
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        
        query_job = client.query(query)
        results = []
        for row in query_job:
            results.append(dict(row))
            
        return {"success": True, "output": results}
    except Exception as e:
        logger.error(f"BigQuery query failed: {e}")
        return {"success": False, "error": str(e)}

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
