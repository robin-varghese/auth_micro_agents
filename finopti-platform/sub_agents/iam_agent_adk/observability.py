import os
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

import logging
logger = logging.getLogger(__name__)

def setup_observability():
    """Initialize Phoenix tracing and ADK instrumentation."""
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    if not endpoint:
        logger.info("PHOENIX_COLLECTOR_ENDPOINT not set. Skipping Phoenix registration.")
        tracer_provider = None
    else:
        try:
            tracer_provider = register(
                project_name="finoptiagents-iam-verification",
                endpoint=endpoint,
                set_global_tracer_provider=True
            )
        except Exception as e:
            logger.warning(f"Failed to register Phoenix: {e}")
            tracer_provider = None
            
    try:
        GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
    except Exception as e:
        logger.warning(f"Failed to instrument ADK: {e}")
