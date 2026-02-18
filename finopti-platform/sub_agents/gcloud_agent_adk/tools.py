"""
GCloud Agent Tools
"""
import logging
from typing import Dict, Any, List

from context import _auth_token_ctx
from mcp_client import GCloudMCPClient

async def execute_gcloud_command(args: List[str]) -> Dict[str, Any]:
    """
    ADK tool: Execute gcloud command
    
    Args:
        args: List of gcloud command arguments (e.g. ['compute', 'instances', 'list'])
    
    Returns:
        Dictionary with execution result
    """
    # Retrieve Auth Token from Context
    auth_token = _auth_token_ctx.get()
    
    try:
        # Use Ephemeral Client per request
        async with GCloudMCPClient(auth_token=auth_token) as client:
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
