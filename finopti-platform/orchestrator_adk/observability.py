"""
Orchestrator ADK - Observability Setup
"""
import os
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Global tracer provider reference
tracer_provider = None

def setup_observability():
    """Initialize Phoenix tracing and OpenInference instrumentation."""
    global tracer_provider
    if tracer_provider:
        return

    # Initialize tracing
    tracer_provider = register(
        project_name="finoptiagents-OrchestratorADK",
        endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
        set_global_tracer_provider=True
    )
    GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
