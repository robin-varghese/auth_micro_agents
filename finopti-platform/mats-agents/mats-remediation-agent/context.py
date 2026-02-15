"""
Context Management for MATS Remediation Agent
Matches AI_AGENT_DEVELOPMENT_GUIDE_V2.0.md
"""
import os
import sys
import asyncio
import logging
import requests
from contextvars import ContextVar
from typing import Optional, Dict, Any
from pathlib import Path

# Add Redis Publisher
try:
    if str(Path(__file__).parent.parent.parent / "common") not in sys.path:
        sys.path.append(str(Path(__file__).parent.parent.parent / "common"))
    if str(Path(__file__).parent.parent.parent) not in sys.path:
        sys.path.append(str(Path(__file__).parent.parent.parent))

    from redis_common.redis_publisher import RedisEventPublisher
except ImportError:
    # Fallback import logic...
    RedisEventPublisher = None

logger = logging.getLogger(__name__)

_redis_publisher_ctx: ContextVar[Optional["RedisEventPublisher"]] = ContextVar("redis_publisher", default=None)
_session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[Optional[str]] = ContextVar("user_email", default=None)

async def _report_progress(message: str, event_type: str = "INFO", icon: str = "🤖", metadata: Dict[str, Any] = None):
    """Helper to send progress to Orchestrator AND Redis"""
    # Redis Publishing
    publisher = _redis_publisher_ctx.get()
    session_id = _session_id_ctx.get()
    
    if publisher and session_id:
        try:
             # Map internal event types
             msg_type_map = {
                 "INFO": "STATUS_UPDATE", "TOOL_CALL": "TOOL_CALL", "OBSERVATION": "OBSERVATION", 
                 "ERROR": "ERROR", "THOUGHT": "THOUGHT"
             }
             mapped_type = msg_type_map.get(event_type, "STATUS_UPDATE")
             
             user_id = _user_email_ctx.get() or "unknown_agent"
             
             publisher.publish_event(
                 session_id=session_id, user_id=user_id, trace_id="unknown",
                 msg_type=mapped_type, message=message,
                 display_type="markdown" if mapped_type == "THOUGHT" else "console_log",
                 icon=icon,
                 metadata=metadata
             )
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")
            logger.debug(str(e), exc_info=True)
