import os
import asyncio
import logging
import json
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.adk.code_executors import BuiltInCodeExecutor
from google.genai import types
from google.cloud import secretmanager
# Plugins
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent Configuration
APP_NAME = "code_execution_agent"
USER_ID = "finopti_user"
SESSION_ID = "session_code" 

def get_gemini_model():
    """
    Fetch Gemini Model name from Environment or Secret Manager.
    """
    # 1. Try Environment Variable
    model = os.getenv("FINOPTIAGENTS_LLM")
    if model:
        logger.info(f"Using Gemini Model from Env: {model}")
        return model
    
    # 2. Try Secret Manager
    project_id = os.getenv("GCP_PROJECT_ID")
    if project_id:
        try:
            client = secretmanager.SecretManagerServiceClient()
            secret_name = "finoptiagents-llm"
            name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            model = response.payload.data.decode("UTF-8")
            logger.info(f"Using Gemini Model from Secret Manager: {model}")
            return model
        except Exception as e:
            logger.warning(f"Failed to fetch model from Secret Manager: {e}")
    else:
        logger.warning("GCP_PROJECT_ID not set, skipping Secret Manager check.")

    # 3. Default
    default_model = "gemini-2.0-flash"
    logger.info(f"Using Default Gemini Model: {default_model}")
    return default_model

def setup_auth():
    """Ensure GOOGLE_API_KEY is set."""
    if os.getenv("GOOGLE_API_KEY"):
        return

    project_id = os.getenv("GCP_PROJECT_ID")
    if project_id:
        try:
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

# Initialize BigQuery Plugin
bq_config = BigQueryLoggerConfig(
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
)
bq_plugin = BigQueryAgentAnalyticsPlugin(
    config=bq_config,
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id=os.getenv("BIGQUERY_DATASET_ID", "finoptiagents"),
    table_id=os.getenv("BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID", "agent_analytics_log")
)

# Initialize Model
GEMINI_MODEL = get_gemini_model()

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
        instruction_str = data.get("instruction", "You are a code execution agent.")
else:
    instruction_str = "You are a code execution agent."

code_agent = LlmAgent(
    name=manifest.get("agent_id", "code_execution_agent"),
    model=GEMINI_MODEL,
    code_executor=BuiltInCodeExecutor(),
    instruction=instruction_str,
    description=manifest.get("description", "Executes Python code to perform calculations or data processing.")
)

app = App(
    name=APP_NAME,
    root_agent=code_agent,
    plugins=[bq_plugin]
)

async def run_agent(prompt: str) -> str:
    """Run the agent with the given prompt."""
    try:
        async with InMemoryRunner(app=app) as runner:
             await runner.session_service.create_session(
                app_name=APP_NAME,
                user_id=USER_ID,
                session_id=SESSION_ID
            )
             
             content = types.Content(role='user', parts=[types.Part(text=prompt)])
             final_response_text = ""
             
             # Run the agent
             async for event in runner.run_async(
                user_id=USER_ID,
                session_id=SESSION_ID,
                new_message=content
             ):
                # Check for executable code parts for logging
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.executable_code:
                            logger.info(f"Agent generated code:\n{part.executable_code.code}")
                        elif part.code_execution_result:
                            logger.info(f"Code output: {part.code_execution_result.output}")

                if event.is_final_response():
                    # Extract text from the final response
                    if event.content and event.content.parts:
                         for part in event.content.parts:
                             if part.text:
                                 final_response_text = part.text
        
        return final_response_text if final_response_text else "No response generated by agent."
        
    except Exception as e:
        logger.error(f"Error running agent: {str(e)}", exc_info=True)
        return f"Error running agent: {str(e)}"

def process_request(prompt: str) -> str:
    """Synchronous wrapper for run_agent."""
    return asyncio.run(run_agent(prompt))
