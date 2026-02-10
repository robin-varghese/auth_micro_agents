"""
Model Resilience Utility
------------------------
Provides retry logic for switching LLM models upon Quota Exhaustion (429).
"""
import logging
import asyncio
from typing import Callable, Any, Awaitable
from config import config

logger = logging.getLogger(__name__)

async def run_with_model_fallback(
    create_app_func: Callable[[str], Any],
    run_func: Callable[[Any], Awaitable[Any]],
    context_name: str = "Agent"
) -> Any:
    """
    Executes an agent run with automatic fallback to alternative models on 429 errors.
    
    Args:
        create_app_func: Function that takes `model_name` (str) and returns an `App`.
        run_func: Async function that takes the `App` and executes the run, returning the result.
                  Must raise exception on failure for retry to work, or return error dict.
        context_name: Name for logging.
        
    Returns:
        The result from the successful run.
        
    Raises:
        Exception: If all models fail.
    """
    
    # Use the configured list, or default if missing
    model_list = getattr(config, "FINOPTIAGENTS_MODEL_LIST", [config.FINOPTIAGENTS_LLM])
    
    last_exception = None
    
    for model_name in model_list:
        try:
            logger.info(f"[{context_name}] Attempting execution with model: {model_name}")
            
            # 1. Create App with specific model
            app = create_app_func(model_name)
            
            # 2. Execute Run
            result = await run_func(app)
            
            # 3. Check for soft-failures (if run_func catches exceptions and returns dict)
            # This depends on agent implementation, but looking for "429" in text response is a heuristic
            if isinstance(result, dict) and "error" in result:
                err_msg = str(result["error"])
                if "429" in err_msg or "Resource exhausted" in err_msg or "Too Many Requests" in err_msg:
                    raise RuntimeError(f"soft_429: {err_msg}")

            if isinstance(result, str):
                if "429 Too Many Requests" in result or "Resource exhausted" in result:
                     raise RuntimeError(f"soft_429: {result}")
            
            # Success!
            logger.info(f"[{context_name}] Success with model: {model_name}")
            return result
            
        except Exception as e:
            err_str = str(e)
            is_quota = "429" in err_str or "Resource exhausted" in err_str or "Too Many Requests" in err_str
            
            if is_quota:
                logger.warning(f"[{context_name}] Quota exhausted for {model_name}. Switching to next model...")
                last_exception = e
                continue # Try next model
            else:
                # If it's not a quota error (e.g., code error), fail immediately? 
                # Or should we try other models just in case model is hallucinating bad tool calls?
                # For safety, let's assume non-quota errors might be model-specific too (e.g. 500s), so we retry.
                logger.warning(f"[{context_name}] Error with {model_name}: {e}. Retrying with next model...")
                last_exception = e
                continue

    # If we get here, all models failed
    logger.error(f"[{context_name}] All models failed. Last error: {last_exception}")
    raise last_exception or RuntimeError("All models failed without specific exception")
