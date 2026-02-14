"""
MATS Orchestrator - Context Isolation & Progress Reporting

Extracted from agent.py per REFACTORING_GUIDELINE.md (Step 5).
Provides ContextVars for request-scoped state and the standardized
_report_progress helper used by all orchestrator modules.

This module has ZERO dependencies on agent logic and can be safely
imported by agent.py, delegation.py, routing.py, etc.
"""
import logging
from contextvars import ContextVar

from opentelemetry import trace

logger = logging.getLogger(__name__)

# --- CONTEXT VARS (Rule 1 & 6) ---
# Stores state for the current request context
_session_id_ctx: ContextVar[str] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[str] = ContextVar("user_email", default=None)
_redis_publisher_ctx: ContextVar = ContextVar("redis_publisher", default=None)
_sequential_thinking_ctx: ContextVar = ContextVar("seq_thinking_client", default=None)


async def _report_progress(
    message: str,
    event_type: str = "STATUS_UPDATE",
    icon: str = "🤖",
    display_type: str = "markdown",
    metadata: dict = None
):
    """Standardized progress reporting using context-bound session/user.
    
    Reads session_id, user_email, and redis_publisher from ContextVars.
    Safe to call even if publisher is not initialized (no-ops gracefully).
    """
    pub = _redis_publisher_ctx.get()
    sid = _session_id_ctx.get()
    uid = _user_email_ctx.get() or "unknown"
    
    if pub and sid:
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
