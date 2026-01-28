import json
import logging
from functools import wraps
from typing import Any, Dict, Optional
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

def trace_span(name: str, kind: str = "INTERNAL"):
    """
    Decorator to wrap a function in an OpenTelemetry span with OpenInference conventions.
    
    Args:
        name: Name of the span
        kind: OpenInference span kind (CHAIN, AGENT, TOOL, etc.)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = trace.get_tracer("mats_orchestrator")
            
            with tracer.start_as_current_span(name) as span:
                # Set Standard OpenInference Attributes
                span.set_attribute("openinference.span.kind", kind)
                
                # Intelligent Input Capture
                # Prioritize explicit task descriptions or user requests
                input_val = (
                    kwargs.get('user_request') or 
                    kwargs.get('task_description') or 
                    kwargs.get('message') or
                    str(args)
                )
                span.set_attribute("input.value", str(input_val))
                span.set_attribute("input.mime_type", "text/plain")
                
                # Check for session context if available in args (convention-based)
                # This assumes session_id might be passed as an argument
                session_id = kwargs.get('session_id')
                if session_id:
                    span.set_attribute("session.id", session_id)
                
                try:
                    # Execute the function
                    result = await func(*args, **kwargs)
                    
                    # Capture Output
                    if isinstance(result, (dict, list)):
                        try:
                            json_str = json.dumps(result)
                            span.set_attribute("output.value", json_str)
                            span.set_attribute("output.mime_type", "application/json")
                        except (TypeError, OverflowError):
                            span.set_attribute("output.value", str(result))
                    else:
                        span.set_attribute("output.value", str(result))
                        
                    span.set_status(Status(StatusCode.OK))
                    return result
                    
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR))
                    # Capture error as output for visibility
                    error_output = {"error": str(e), "type": type(e).__name__}
                    span.set_attribute("output.value", json.dumps(error_output))
                    raise
                    
        return wrapper
    return decorator
