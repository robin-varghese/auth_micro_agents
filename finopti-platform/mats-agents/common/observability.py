
import os
import logging
from typing import Optional, Dict

from opentelemetry import trace, propagate
from openinference.instrumentation.google_adk import AdkInstrumentor

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FinOptiObservability:
    """
    Centralized Observability Setup for FinOpti Agents.
    Wraps standard OpenInference and OTel setup.
    """
    
    _instrumented = False
    
    @classmethod
    def setup(cls, service_name: str):
        """
        Initialize Observability for this service.
        Should be called at agent startup.
        """
        if cls._instrumented:
            return

        logger.info(f"Initializing Observability for service: {service_name}")
        
        # 1. Initialize ADK Instrumentation
        # This automatically captures agent execution steps (Chains)
        AdkInstrumentor().instrument()
        
        # 2. (Optional) Custom OTel Global Config if needed
        # trace.set_tracer_provider(...) - handled by OpenInference auto-config usually
        
        cls._instrumented = True

    @staticmethod
    def middleware_extract_trace(headers: Dict[str, str]):
        """
        Middleware logic to extract traceparent from incoming headers
        and set the current OTel context.
        """
        if not headers:
            return
            
        try:
            # Extract 'traceparent' and other context from headers
            context = propagate.extract(headers)
            
            # Attach to current execution context 
            # Note: In async frameworks (like Starlette/FastAPI), this context 
            # needs to be carefully managed. For ADK synchronous/threaded logic,
            # attach_context returns a token to detach later.
            token = trace.context.attach(context)
            return token
        except Exception as e:
            logger.warning(f"Failed to extract trace context: {e}")
            return None

    @staticmethod
    def inject_trace_to_headers(headers: Dict[str, str] = None) -> Dict[str, str]:
        """
        Inject current trace context into headers for downstream calls.
        """
        if headers is None:
            headers = {}
        
        propagate.inject(headers)
        return headers

    @staticmethod
    def get_current_trace_id() -> Optional[str]:
        """Get current Trace ID as hex string"""
        span = trace.get_current_span()
        if span.get_span_context().is_valid:
            return format(span.get_span_context().trace_id, "032x")
        return None
