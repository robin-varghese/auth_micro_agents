"""
Orchestrator ADK - Observability Setup
"""
import os
import logging

try:
    from phoenix.otel import register
except ImportError:
    register = None
except SyntaxError:
    # Handle the Python 3.11 compatibility issue in old phoenix versions
    register = None

try:
    from openinference.instrumentation.google_adk import GoogleADKInstrumentor
except ImportError:
    GoogleADKInstrumentor = None

logger = logging.getLogger(__name__)

# Global tracer provider reference
tracer_provider = None

def setup_observability():
    """Initialize Phoenix tracing and OpenInference instrumentation."""
    global tracer_provider
    if tracer_provider:
        return

    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    if not endpoint or not register:
        logger.info("Phoenix registration skipped (no endpoint or import error).")
        tracer_provider = None
    else:
        try:
            # Initialize tracing
            tracer_provider = register(
                project_name="finoptiagents-OrchestratorADK",
                endpoint=endpoint,
                set_global_tracer_provider=True
            )
        except Exception as e:
            logger.warning(f"Failed to register Phoenix: {e}")
            tracer_provider = None

    if GoogleADKInstrumentor:
        try:
            GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
        except Exception as e:
            logger.warning(f"Failed to instrument ADK: {e}")
