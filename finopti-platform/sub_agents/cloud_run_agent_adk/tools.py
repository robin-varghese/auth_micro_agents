"""
Cloud Run Agent Tools
"""
import logging
from typing import Dict, Any, List
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)

async def list_services(project_id: str, region: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_services", {"project": project_id, "region": region})

async def get_service(service_name: str, project_id: str, region: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_service", {"service_name": service_name, "project": project_id, "region": region})

async def get_service_log(service_name: str, project_id: str, region: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_service_log", {"service_name": service_name, "project": project_id, "region": region})

async def deploy_file_contents(service_name: str, image: str, project_id: str, region: str, env_vars: Dict[str, str] = {}) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("deploy_file_contents", {
        "service_name": service_name, 
        "image": image, 
        "project": project_id, 
        "region": region,
        "env_vars": env_vars
    })

async def list_projects() -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_projects", {})

async def create_project(project_id: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("create_project", {"project_id": project_id})
