"""
Google Search ADK Agent

This agent uses Google GenAI's Google Search capabilities.
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.genai import types
from config import config

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name=os.getenv("GCP_PROJECT_ID", "local") + "-googlesearch-agent",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_auth():
    """Ensure GOOGLE_API_KEY is set."""
    if os.getenv("GOOGLE_API_KEY"):
        return

    project_id = os.getenv("GCP_PROJECT_ID")
    if project_id:
        try:
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            secret_name = "google-api-key"
            name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            api_key = response.payload.data.decode("UTF-8")
            os.environ["GOOGLE_API_KEY"] = api_key
            logger.info("Loaded GOOGLE_API_KEY from Secret Manager")
        except Exception as e:
            logger.warning(f"Failed to fetch google-api-key from Secret Manager: {e}")

# Setup Auth
setup_auth()

# Load Manifest
manifest_path = Path(__file__).parent / "manifest.json"
manifest = {}
if manifest_path.exists():
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

# Load Instructions
instructions_path = Path(__file__).parent / "instructions.json"
if instructions_path.exists():
    with open(instructions_path, "r") as f:
        data = json.load(f)
        instruction_str = data.get("instruction", "You are a Google Search Specialist.")
else:
    instruction_str = "You are a Google Search Specialist."


from google.adk.tools import google_search

# -------------------------------------------------------------------------
# IMPORT COMMON UTILS
# -------------------------------------------------------------------------
from common.model_resilience import run_with_model_fallback

# Agent Definition
# Uses ADK's native GoogleSearchTool
def create_googlesearch_agent(model_name: str = None) -> Agent:
    model_to_use = model_name or config.FINOPTIAGENTS_LLM
    
    return Agent(
        name=manifest.get("agent_id", "google_search_specialist"),
        model=model_to_use,
        description=manifest.get("description", "Google Search Specialist."),
        instruction=instruction_str,
        tools=[google_search]
    )

# App Definition

def create_app(model_name: str = None):
    # Ensure API Key is in environment
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    
    # Create agent instance
    agent_instance = create_googlesearch_agent(model_name)

    return App(
        name="finopti_googlesearch_agent",
        root_agent=agent_instance,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=3),
            BigQueryAgentAnalyticsPlugin(
                project_id=config.GCP_PROJECT_ID,
                dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
                table_id=config.BQ_ANALYTICS_TABLE,
                config=BigQueryLoggerConfig(enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true")
            )
        ]
    )

async def send_message_async(prompt: str, user_email: str = None, project_id: str = None) -> str:
    try:
        # Prepend project context if provided
        if project_id:
            prompt = f"Project ID: {project_id}\n{prompt}"
            
        # Define run_once for fallback logic
        async def _run_once(app_instance):
            response_text = ""
            async with InMemoryRunner(app=app_instance) as runner:
                # Use dynamic user_id if provided
                session_uid = user_email if user_email else "default"
                await runner.session_service.create_session(session_id="default", user_id=session_uid, app_name=app_instance.name)
                message = types.Content(parts=[types.Part(text=prompt)])
                
                async for event in runner.run_async(session_id="default", user_id=session_uid, new_message=message):
                     # logging.info(f"Event received: {event}")
                     if hasattr(event, 'content') and event.content:
                         if event.content.parts:
                            for part in event.content.parts:
                                if part.text: 
                                    response_text += part.text
            
            if not response_text:
                return "Analysis completed but no textual summary was generated. Debug: Tool executed but no final text response."
            
            return response_text

        return await run_with_model_fallback(
            create_app_func=create_app,
            run_func=_run_once,
            context_name="Google Search Agent"
        )
    except Exception as e:
        return f"Error: {str(e)}"

def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    return asyncio.run(send_message_async(prompt, user_email, project_id))

def process_request(prompt: str) -> str:
    """Synchronous wrapper for main.py."""
    return send_message(prompt)
