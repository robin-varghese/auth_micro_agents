import os
import sys
import logging
from contextvars import ContextVar
from typing import Optional
from pathlib import Path

# Add Redis Common to path
redis_common_path = str(Path(__file__).parent.parent.parent / "redis-sessions" / "common")
if redis_common_path not in sys.path:
    sys.path.append(redis_common_path)

try:
    from redis_publisher import RedisEventPublisher
except ImportError:
    RedisEventPublisher = None

logger = logging.getLogger(__name__)

_redis_publisher_ctx: ContextVar[Optional["RedisEventPublisher"]] = ContextVar("redis_publisher", default=None)
_session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[Optional[str]] = ContextVar("user_email", default=None)
_auth_token_ctx: ContextVar[Optional[str]] = ContextVar("auth_token", default=None)

async def _report_progress(message: str, event_type: str = "STATUS_UPDATE", icon: str = "🛡️"):
    """Helper to send progress to Redis for UI Sync"""
    publisher = _redis_publisher_ctx.get()
    session_id = _session_id_ctx.get()
    user_id = _user_email_ctx.get() or "anonymous"
    
    if publisher and session_id:
        try:
             from opentelemetry import trace
             try:
                 span_ctx = trace.get_current_span().get_span_context()
                 trace_id_hex = format(span_ctx.trace_id, '032x') if span_ctx.trace_id else "unknown"
             except Exception:
                 trace_id_hex = "unknown"

             publisher.publish_event(
                 session_id=session_id,
                 user_id=user_id,
                 trace_id=trace_id_hex,
                 msg_type=event_type,
                 message=message,
                 display_type="console_log",
                 icon=icon
             )
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")
