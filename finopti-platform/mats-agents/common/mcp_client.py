
import requests
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class HttpMcpClient:
    """
    Simple HTTP JSON-RPC Client for MCP Servers.
    Assumes the server accepts POST requests with JSON-RPC body.
    """
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        # Endpoint convention for some MCP servers, or just root if it handles all
        self.rpc_endpoint = f"{self.base_url}/jsonrpc" 
        # Fallback if specific endpoint not known, might be just base
        self.rpc_endpoint_fallback = self.base_url 

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        }
        
        # Inject Trace Context if available
        # Note: We depend on common.observability, but to avoid circular imports
        # we can inject explicitly or assuming headers passed in args?
        # For now, let's just rely on the session service calling this.
        # But wait, implementation plan said "Inject traceparent".
        # We need to capture current context here.
        
        try:
            from common.observability import FinOptiObservability
            trace_ctx = {}
            FinOptiObservability.inject_trace_to_headers(trace_ctx)
            if "traceparent" in trace_ctx:
                 # Check if params already has _meta, if not create it
                 if "_meta" not in payload["params"]:
                     payload["params"]["_meta"] = {}
                 payload["params"]["_meta"]["traceparent"] = trace_ctx["traceparent"]
        except ImportError:
            pass # Observability not set up or circular dependency
            
        try:
            # Try main endpoint (adjust based on actual tool)
            response = requests.post(self.rpc_endpoint, json=payload, timeout=10)
            
            if response.status_code == 404:
                 # Try fallback
                 response = requests.post(self.rpc_endpoint_fallback, json=payload, timeout=10)

            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                logger.error(f"MCP Error calling {tool_name}: {data['error']}")
                return None
            
            result = data.get("result", {})
            # Return result content (text)
            content = result.get("content", [])
            for item in content:
                if item.get("type") == "text":
                    return item.get("text")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to call MCP tool {tool_name}: {e}")
            return None

class RedisMcpClient(HttpMcpClient):
    """Specialized client for the DB Toolbox"""
    def __init__(self):
        # Service name from docker-compose
        url = os.getenv("DB_MCP_TOOLBOX_URL", "http://finopti-db-mcp-toolbox:5000")
        super().__init__(url)
