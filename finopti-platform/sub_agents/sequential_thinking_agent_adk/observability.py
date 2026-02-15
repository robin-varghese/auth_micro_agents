import os
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

def setup_observability():
    """Initialize Phoenix tracing and ADK instrumentation."""
    tracer_provider = register(
        project_name="finoptiagents-SequentialAgent",
        endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
        set_global_tracer_provider=True
    )
    GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
