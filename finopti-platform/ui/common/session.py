
import json
import logging
from typing import Optional, Dict, Any, List

from google.adk.sessions import SessionService, Session
# Note: This assumes the Agent uses a standard MCP Client interface.
# Since ADK doesn't enforce a strict MCP Client class, we define a Protocol or expect duck typing.

logger = logging.getLogger(__name__)

class McpRedisSessionService(SessionService):
    """
    Custom ADK Session Service that delegates persistence to an MCP Server (via 'redis' tools).
    It does NOT connect to Redis directly.
    """
    
    def __init__(self, mcp_client: Any, session_ttl_seconds: int = 3600):
        """
        Args:
            mcp_client: An instantiated MCP Client capable of .call_tool()
            session_ttl_seconds: TTL for session keys in Redis (default 1 hour)
        """
        self.mcp = mcp_client
        self.ttl = session_ttl_seconds
        self.get_tool_name = "redis_get"
        self.set_tool_name = "redis_set"

    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        Retrieve session from Redis via MCP.
        """
        try:
            # 1. Call MCP Tool
            # The 'redis_get' tool is expected to return the value string or None
            # Tool signature: redis_get(key: str) -> str | None
            result = await self.mcp.call_tool(
                self.get_tool_name, 
                {"key": f"session:{session_id}"}
            )
            
            if not result:
                return None
                
            # MCP tools might wrap output, e.g. {"content": [...]}. 
            # We assume the tool returns the raw string value or a dict we can parse.
            # Adjust based on your specific Redis MCP implementation.
            
            # If result is a specialized MCP tool result object, extract text
            if hasattr(result, 'content') and isinstance(result.content, list):
                 # MCP SDK standard response
                 text_content = next((c.text for c in result.content if c.type == 'text'), None)
                 if text_content:
                     session_data = json.loads(text_content)
                 else:
                     return None
            elif isinstance(result, str):
                 session_data = json.loads(result)
            elif isinstance(result, dict):
                 session_data = result
            else:
                 logger.warning(f"Unexpected return type from redis_get: {type(result)}")
                 return None

            return Session.from_dict(session_data)
        
        except Exception as e:
            logger.error(f"Failed to load session {session_id} from MCP: {e}")
            return None

    async def save_session(self, session: Session):
        """
        Save session to Redis via MCP.
        """
        try:
            session_json = json.dumps(session.to_dict())
            
            # Tool signature: redis_set(key: str, value: str)
            # Note: Your implementation plan mentioned 'expire' arg. 
            # Ensure your db-mcp-toolbox supports it, otherwise ignore.
            args = {
                "key": f"session:{session.id}", 
                "value": session_json
            }
            # Optional: Add TTL if supported by tool
            # args["ex"] = self.ttl 
            
            await self.mcp.call_tool(self.set_tool_name, args)
            logger.debug(f"Saved session {session.id} via MCP")
            
        except Exception as e:
            logger.error(f"Failed to save session {session.id} via MCP: {e}")

    async def create_session(self, session_id: str, user_id: str = "default_user", app_name: str = "default_app", **kwargs) -> Session:
        """Create and save a new session"""
        session = Session(
            id=session_id,
            user_id=user_id,
            app_name=app_name,
            **kwargs
        )
        await self.save_session(session)
        return session
    
    async def delete_session(self, session_id: str):
        # Optional: Implement redis_del if needed
        pass
