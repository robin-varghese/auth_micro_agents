"""
Orchestrator ADK - Context and Progress Reporting
"""
import sys
import logging
from pathlib import Path
from contextvars import ContextVar
from opentelemetry import trace
import requests
from config import config

logger = logging.getLogger(__name__)

# --- Redis Publisher Setup ---
sys.path.append("/app/redis_common")
try:
    from redis_publisher import RedisEventPublisher
except ImportError:
    # Fallback if not mounted yet/running locally without path
    try:
        sys.path.append(str(Path(__file__).parent.parent.parent / "redis-sessions" / "common"))
        from redis_publisher import RedisEventPublisher
    except ImportError as e2:
        logger.warning(f"RedisEventPublisher not found. Streaming disabled. Error: {e2}")
        RedisEventPublisher = None

# --- Context Variables ---
_session_id_ctx: ContextVar[str] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[str] = ContextVar("user_email", default=None)
_redis_publisher_ctx: ContextVar["RedisEventPublisher"] = ContextVar("redis_publisher", default=None)

async def _report_progress(
    message: str, 
    event_type: str = "STATUS_UPDATE", 
    icon: str = "🤖", 
    display_type: str = "markdown", 
    metadata: dict = None
):
    """Standardized progress reporting using context-bound session/user."""
    pub = _redis_publisher_ctx.get()
    sid = _session_id_ctx.get()
    uid = _user_email_ctx.get() or "unknown"
    
    if pub and sid:
        # Extract trace_id from current span for link back
        try:
            span_ctx = trace.get_current_span().get_span_context()
            trace_id_hex = format(span_ctx.trace_id, '032x') if span_ctx.trace_id else "unknown"
        except Exception:
            trace_id_hex = "unknown"

        pub.publish_event(
            session_id=sid,
            user_id=uid,
            trace_id=trace_id_hex,
            msg_type=event_type,
            message=message,
            display_type=display_type,
            icon=icon,
            metadata=metadata
        )

async def get_session_context(session_id: str) -> dict:
    """Fetch structured context from Redis Gateway."""
    if not session_id:
        return {}
    
    url = f"{config.REDIS_GATEWAY_URL}/session/{session_id}/context"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch session context: {e}")
        return {}

async def update_session_context(session_id: str, context: dict):
    """Update structured context in Redis Gateway."""
    if not session_id:
        return
    
    logger.info(f"Attempting to update session context for {session_id}. Payload: {context}")
    url = f"{config.REDIS_GATEWAY_URL}/session/{session_id}/context"
    try:
        response = requests.post(url, json=context, timeout=5)
        response.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to update session context: {e}")
