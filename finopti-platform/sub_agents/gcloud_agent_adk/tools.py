"""
GCloud Agent Tools
"""
import logging
from typing import Dict, Any, List

from mcp_client import get_mcp_client

logger = logging.getLogger(__name__)

async def execute_gcloud_command(args: List[str]) -> Dict[str, Any]:
    """
    ADK tool: Execute gcloud command
    
    Args:
        args: List of gcloud command arguments (e.g. ['compute', 'instances', 'list'])
    
    Returns:
        Dictionary with execution result
    """
    try:
        client = await get_mcp_client()
        result_text = await client.run_gcloud_command(args)
        logger.info(f"GCloud Command executed: gcloud {' '.join(args)}")
        logger.info(f"GCloud Output: {result_text[:500]}")
        
        return {
            "success": True,
            "output": result_text,
            "command": f"gcloud {' '.join(args)}"
        }
    except Exception as e:
        logger.error(f"GCloud execution failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "command": f"gcloud {' '.join(args)}"
        }
