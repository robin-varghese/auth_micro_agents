import os
from typing import List, Dict, Any
from mcp_client import get_mcp_client
from context import _report_progress

async def execute_gcloud_command(args: List[str]) -> Dict[str, Any]:
    """
    Chaos Monkey Tool: Execute gcloud command directly via MCP.
    """
    await _report_progress(f"Executing gcloud {' '.join(args)}...", icon="🛠️")
    try:
        client = await get_mcp_client()
        # Direct execution logs for the UI
        command_str = f"gcloud {' '.join(args)}"
        await _report_progress(f"Starting chaos action: {command_str}", icon="⚡")
        
        output = await client.run_gcloud_command(args)
        
        # Build a rich, explanatory response for the UI
        rich_output = f"### [CHAOS LOG] Direct MCP Execution\n"
        rich_output += f"Target Service: calculator-app\n"
        rich_output += f"Environment: Project: vector-search-poc | Region: us-central1\n"
        rich_output += f"Command: `{command_str}`\n"
        rich_output += f"-" * 20 + "\n"
        
        if output:
            rich_output += f"EXECUTION OUTPUT:\n{output}\n"
        else:
            rich_output += f"STATUS: SUCCESS\n(Note: Command executed cleanly with zero exit code. The infrastructure has been updated.)\n"
            
        rich_output += f"-" * 20 + "\n"
        rich_output += f"TIMESTAMP: {os.popen('date').read().strip()}\n"
            
        return {"success": True, "output": rich_output}
    except Exception as e:
        error_msg = f"### [CHAOS FAILED]\nError: {str(e)}\n"
        return {"success": False, "error": error_msg}
