import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class GCloudMCPClient:
    """
    Direct client for the GCloud MCP Server.
    Bypasses the platform's gcloud_agent to avoid internal TypeErrors.
    """
    def __init__(self):
        self.image = os.getenv("GCLOUD_MCP_DOCKER_IMAGE", "finopti-gcloud-mcp")
        self.project_id = os.getenv("GCP_PROJECT_ID", "vector-search-poc")
        # Host side path for gcloud config. On Mac, this is usually /Users/robinkv/.config/gcloud
        self.mount_path = os.getenv("GCLOUD_MOUNT_PATH", "/Users/robinkv/.config/gcloud:/root/.config/gcloud")

    async def run_gcloud_command(self, args: List[str]) -> str:
        """Runs a gcloud command via docker run (matches MCP server logic)"""
        # Split the mount path into host and container parts
        host_path = self.mount_path.split(':')[0]
        
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_path}:/root/.config/gcloud",
            self.image,
            "gcloud"
        ] + args
        
        logger.info(f"Executing: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            err_msg = stderr.decode().strip()
            logger.error(f"GCloud Error: {err_msg}")
            raise Exception(f"GCloud failed: {err_msg}")
            
        return stdout.decode().strip()

_mcp_client: Optional[GCloudMCPClient] = None

async def get_mcp_client():
    global _mcp_client
    if not _mcp_client:
        _mcp_client = GCloudMCPClient()
    return _mcp_client
