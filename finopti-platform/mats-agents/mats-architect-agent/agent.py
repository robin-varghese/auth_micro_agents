
"""
MATS Architect Agent - RCA Synthesis
"""
import os
import sys
import asyncio
import logging
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.adk.runners import InMemoryRunner
from google.genai import types

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name=os.getenv("GCP_PROJECT_ID", "local") + "-mats-architect",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import config
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY


# -------------------------------------------------------------------------
# AGENT DEFINITION
# -------------------------------------------------------------------------
architect_agent = Agent(
    name="mats_architect_agent",
    model=config.FINOPTIAGENTS_LLM,
    description="Principal Software Architect.",
    instruction="""
    You are a Principal Software Architect.
    Your job is to synthesize technical investigations into a formal Root Cause Analysis (RCA) document and recommend robust fixes.
    
    INPUTS:SRE Findings (Logs) + Investigator Findings (Code).
    
    OUTPUT FORMAT (Markdown):
    1. **Executive Summary**: One sentence description.
    2. **Timeline & Detection**: Timestamp and metric context.
    3. **Root Cause**: Deep technical explanation.
    4. **Resolution**: The recommended code fix (CODE BLOCK).
    5. **Prevention Plan**: Test cases or architectural changes.
    
    Prefer architectural fixes over quick patches.
    """,
    tools=[] # No tools, purely cognitive
)


# -------------------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------------------
async def process_request(prompt: str):
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    
    bq_plugin = BigQueryAgentAnalyticsPlugin(
        project_id=os.getenv("GCP_PROJECT_ID"),
        dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
        table_id=config.BQ_ANALYTICS_TABLE,
        config=BigQueryLoggerConfig(
            enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
        )
    )

    app_instance = App(
        name="mats_architect_app",
        root_agent=architect_agent,
        plugins=[
            ReflectAndRetryToolPlugin(),
            bq_plugin
        ]
    )

    response_text = ""
    try:
        async with InMemoryRunner(app=app_instance) as runner:
            sid = "default"
            await runner.session_service.create_session(session_id=sid, user_id="user", app_name="mats_architect_app")
            msg = types.Content(parts=[types.Part(text=prompt)])
            
            async for event in runner.run_async(user_id="user", session_id=sid, new_message=msg):
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
    except Exception as e:
        response_text = f"Error: {e}"
    
    return response_text
