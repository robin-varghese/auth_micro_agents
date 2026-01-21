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

# Agent Definition
# Uses exact Tool definition from google-genai
search_tool = types.Tool(google_search=types.GoogleSearch())

agent = Agent(
    name=manifest.get("agent_id", "google_search_specialist"),
    model=config.FINOPTIAGENTS_LLM,
    description=manifest.get("description", "Google Search Specialist."),
    instruction=instruction_str,
    # tools=[search_tool]
)

# App Definition
app = App(
    name="finopti_googlesearch_agent",
    root_agent=agent,
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
            
        async with InMemoryRunner(app=app) as runner:
            # Use dynamic user_id if provided
            session_uid = user_email if user_email else "default"
            await runner.session_service.create_session(session_id="default", user_id=session_uid, app_name=app.name)
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(session_id="default", user_id=session_uid, new_message=message):
                 if hasattr(event, 'content') and event.content:
                     for part in event.content.parts:
                         if part.text: response_text += part.text
            return response_text
    except Exception as e:
        return f"Error: {str(e)}"

def send_message(prompt: str, user_email: str = None, project_id: str = None) -> str:
    # return asyncio.run(send_message_async(prompt, user_email, project_id))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(send_message_async(prompt, user_email, project_id))
    finally:
        loop.close()

def process_request(prompt: str) -> str:
    """Synchronous wrapper for main.py."""
    return send_message(prompt)
