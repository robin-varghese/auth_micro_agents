"""
MATS Orchestrator - Observability Setup

Extracted from agent.py per REFACTORING_GUIDELINE.md (Step 6).
Centralizes Phoenix tracing, OTel instrumentation, and startup verification.

Call setup_observability() once at module load time in agent.py.
"""
import os
import logging

from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues

logger = logging.getLogger(__name__)

# Module-level state (set by setup_observability)
tracer_provider = None
tracer = None

TRACE_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces")


def setup_observability() -> tuple:
    """Initialize Phoenix tracing, ADK instrumentor, and startup verification.
    
    Returns:
        Tuple of (tracer_provider, tracer) for use by agent.py
    """
    global tracer_provider, tracer
    
    # Register with Phoenix
    tracer_provider = register(
        project_name="finoptiagents-MATS",
        endpoint=TRACE_ENDPOINT,
        set_global_tracer_provider=True
    )
    
    # Force SimpleSpanProcessor for immediate export (debugging)
    # register() adds a BatchSpanProcessor. Adding a SimpleSpanProcessor ensures
    # at least one path flushes immediately.
    http_exporter = OTLPSpanExporter(endpoint=TRACE_ENDPOINT)
    tracer_provider.add_span_processor(SimpleSpanProcessor(http_exporter))
    
    # Instrument ADK
    GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
    
    # Get tracer for creating spans
    tracer = trace.get_tracer(__name__)
    
    # Send startup verification trace
    with tracer.start_as_current_span("agent-startup-check") as span:
        span.set_attribute("status", "startup_ok")
        logger.info("Sent manual startup trace to Phoenix")
    
    return tracer_provider, tracer


def ensure_api_key_env():
    """Ensure API Key is in environment ONLY if not using Vertex AI.
    
    Vertex AI requires ADC/OAuth tokens. API keys can cause 401 conflicts.
    Called from agent.py at module init and inside create_app().
    """
    from config import config
    
    if config.GOOGLE_API_KEY and not (
        config.GOOGLE_GENAI_USE_VERTEXAI 
        and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"
    ):
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
        logger.info("Using API Key for authentication (Vertex AI disabled)")
    else:
        # Ensure it's NOT in env to force ADC for Vertex
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
        logger.info("Using ADC/Service Account for authentication (Vertex AI enabled)")
