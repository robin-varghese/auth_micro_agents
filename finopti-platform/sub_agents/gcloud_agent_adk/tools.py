import logging
from typing import Dict, Any, List

from context import _auth_token_ctx
from mcp_client import GCloudMCPClient

logger = logging.getLogger(__name__)

async def execute_gcloud_command(args: List[str]) -> Dict[str, Any]:
    """
    ADK tool: Execute gcloud command
    
    Args:
        args: List of gcloud command arguments (e.g. ['compute', 'instances', 'list'])
    
    Returns:
        Dictionary with execution result
    """
    # Retrieve Auth Token from Context (with environment fallback)
    auth_token = _auth_token_ctx.get()
    if not auth_token:
        import os
        auth_token = os.environ.get("CLOUDSDK_AUTH_ACCESS_TOKEN")
        
    logger.info(f"Retrieved auth_token: {auth_token[:10] if auth_token else 'None'}... (from {'context' if _auth_token_ctx.get() else 'env'})")
    
    from context import _user_email_ctx
    user_email = _user_email_ctx.get()
    
    try:
        # Use Ephemeral Client per request, now with user_account for active account support
        async with GCloudMCPClient(auth_token=auth_token, user_account=user_email) as client:
            result_text = await client.run_gcloud_command(args)
            logger.info(f"GCloud Command executed: gcloud {' '.join(args)}")
            logger.info(f"GCloud Output: {result_text[:500]}")
            
            # [NEW] Report GCloud Observation for the "Eye" icon in UI
            from context import _report_progress
            cmd_str = f"gcloud {' '.join(args)}"
            summary = result_text[:2000] + "..." if len(result_text) > 2000 else result_text
            
            await _report_progress(
                f"Output from command: `{cmd_str}`\n\n{summary}",
                event_type="OBSERVATION"
            )
            
            return {
                "success": True,
                "output": result_text,
                "command": cmd_str
            }
    except Exception as e:
        logger.error(f"GCloud execution failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "command": f"gcloud {' '.join(args)}"
        }
