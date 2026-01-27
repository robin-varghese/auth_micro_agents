"""
MATS Orchestrator - Retry Logic

Implements exponential backoff retry wrapper for agent calls.
"""
import asyncio
import logging
from typing import Callable, Any, TypeVar, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Retry configuration
MAX_RETRIES = 3
BACKOFF_SEQUENCE = [1, 2, 4]  # seconds


class RetryableError(Exception):
    """Errors that should trigger a retry"""
    pass


class NonRetryableError(Exception):
    """Errors that should NOT trigger a retry"""
    pass


def is_retryable_http_error(status_code: int) -> bool:
    """Determine if HTTP status code is retryable"""
    # Retry on 5xx errors (server errors)
    if 500 <= status_code < 600:
        return True
    
    # Do NOT retry on 4xx errors (client errors)
    if 400 <= status_code < 500:
        return False
    
    # Retry on other errors (timeouts, etc)
    return True


async def retry_async(
    func: Callable[..., T],
    *args,
    max_attempts: int = MAX_RETRIES,
    backoff: list = None,
    session_id: str = "unknown",
    agent_name: str = "unknown",
    **kwargs
) -> T:
    """
    Retry an async function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_attempts: Maximum number of attempts (default 3)
        backoff: Backoff sequence in seconds (default [1, 2, 4])
        session_id: Investigation session ID for logging
        agent_name: Agent being called for logging
        
    Returns:
        Result of successful function call
        
    Raises:
        The last exception if all retries exhausted
    """
    if backoff is None:
        backoff = BACKOFF_SEQUENCE
    
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(
                f"[{session_id}] Calling {agent_name} (attempt {attempt}/{max_attempts})"
            )
            result = await func(*args, **kwargs)
            
            if attempt > 1:
                logger.info(
                    f"[{session_id}] {agent_name} succeeded after {attempt} attempts"
                )
            
            return result
            
        except NonRetryableError as e:
            logger.error(
                f"[{session_id}] {agent_name} failed with non-retryable error: {e}"
            )
            raise
            
        except Exception as e:
            last_exception = e
            
            if attempt < max_attempts:
                wait_time = backoff[min(attempt - 1, len(backoff) - 1)]
                logger.warning(
                    f"[{session_id}] {agent_name} attempt {attempt} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    f"[{session_id}] {agent_name} failed after {max_attempts} attempts"
                )
    
    # All retries exhausted
    raise last_exception


def with_retry(max_attempts: int = MAX_RETRIES):
    """
    Decorator for async functions to add retry logic.
    
    Usage:
        @with_retry(max_attempts=3)
        async def call_agent(url: str):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                *args,
                max_attempts=max_attempts,
                **kwargs
            )
        return wrapper
    return decorator


class RetryContext:
    """Context manager for tracking retry state"""
    
    def __init__(self, session_id: str, agent_name: str):
        self.session_id = session_id
        self.agent_name = agent_name
        self.attempts = 0
        self.last_error = None
        
    def record_attempt(self, error: Optional[Exception] = None):
        """Record an attempt"""
        self.attempts += 1
        if error:
            self.last_error = error
            
    def should_retry(self, max_attempts: int = MAX_RETRIES) -> bool:
        """Check if we should retry"""
        return self.attempts < max_attempts
        
    def get_backoff_time(self) -> float:
        """Get backoff time for current attempt"""
        index = min(self.attempts - 1, len(BACKOFF_SEQUENCE) - 1)
        return BACKOFF_SEQUENCE[index]
