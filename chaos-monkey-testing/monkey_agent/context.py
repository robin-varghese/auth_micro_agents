import os
import sys
import asyncio
import logging
from contextvars import ContextVar
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Context Variables for State Management
_session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[Optional[str]] = ContextVar("user_email", default=None)

async def _report_progress(message: str, event_type: str = "INFO", icon: str = "🐵", display_type: str = "console_log", metadata: Dict[str, Any] = None):
    """Helper to report progress. In this monkey agent, we'll just log it."""
    logger.info(f"[{event_type}] {icon} {message}")
    # In a real ADK app, this would publish to Redis/Orchestrator
    # But for chaos monkey, logging to container stdout is enough for debugging
