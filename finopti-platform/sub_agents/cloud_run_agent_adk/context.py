import os
import sys
import asyncio
import logging
import requests
from contextvars import ContextVar
from typing import Optional
from pathlib import Path

# Add Redis Publisher
try:
    # Ensure current directory is in path (Docker WORKDIR /app)
    if str(Path(__file__).parent) not in sys.path:
        sys.path.append(str(Path(__file__).parent))

    from redis_common.redis_publisher import RedisEventPublisher
except ImportError:
    # Fallback or local dev path if not mounted
    sys.path.append(str(Path(__file__).parent.parent.parent / "redis-sessions" / "common"))
    try:
        from redis_publisher import RedisEventPublisher
    except ImportError:
        RedisEventPublisher = None

logger = logging.getLogger(__name__)

_redis_publisher_ctx: ContextVar[Optional["RedisEventPublisher"]] = ContextVar("redis_publisher", default=None)
_session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
_user_email_ctx: ContextVar[Optional[str]] = ContextVar("user_email", default=None)

async def _report_progress(message: str, event_type: str = "INFO", icon: str = None, display_type: str = None):
    """Helper to send progress to Orchestrator AND Redis"""
    job_id = os.environ.get("MATS_JOB_ID")
    orchestrator_url = os.environ.get("MATS_ORCHESTRATOR_URL", "http://mats-orchestrator:8084")
    
    # Redis Publishing
    publisher = _redis_publisher_ctx.get()
    session_id = _session_id_ctx.get()
    
    if publisher and session_id:
        try:
             # Map internal event types
             msg_type_map = {
                 "INFO": "STATUS_UPDATE", "TOOL_USE": "TOOL_CALL", "OBSERVATION": "OBSERVATION", 
                 "ERROR": "ERROR", "THOUGHT": "THOUGHT"
             }
             mapped_type = msg_type_map.get(event_type, "STATUS_UPDATE")
             
             # Icons
             icons = {
                 "INFO": "ℹ️", "TOOL_USE": "🛠️", "OBSERVATION": "👁️", 
                 "ERROR": "❌", "THOUGHT": "🧠"
             }
             final_icon = icon or icons.get(event_type, "🏃")
             final_display = display_type or ("markdown" if mapped_type == "THOUGHT" else "console_log")
             
             user_id = _user_email_ctx.get() or "cloud_run"
             
             publisher.publish_event(
                 session_id=session_id, user_id=user_id, trace_id="unknown",
                 msg_type=mapped_type, message=message,
                 display_type=final_display,
                 icon=final_icon
             )
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")

    if not job_id:
        return

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, 
            lambda: requests.post(
                f"{orchestrator_url}/jobs/{job_id}/events",
                json={
                    "type": event_type,
                    "message": message,
                    "source": "finopti-cloud-run-agent"
                },
                timeout=2
            )
        )
    except Exception as e:
        logger.warning(f"Failed to report progress: {e}")
