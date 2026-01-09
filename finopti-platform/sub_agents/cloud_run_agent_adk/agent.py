"""
Cloud Run ADK Agent - Serverless Container Specialist

This agent uses Google ADK to handle Cloud Run management requests.
It executes `gcloud run` commands directly via subprocess.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.adk.runners import InMemoryRunner
from google.genai import types
from typing import Dict, Any, List
import asyncio
import json
import logging
import subprocess
import shlex

from config import config

import shutil

# Global flag to track if config is setup
_gcloud_config_setup = False

def setup_gcloud_config():
    """Copy mounted gcloud config to writable temp location to avoid Read-Only errors"""
    global _gcloud_config_setup
    if _gcloud_config_setup:
        return

    src = "/root/.config/gcloud"
    dst = "/tmp/gcloud_config"
    
    if os.path.exists(dst):
        shutil.rmtree(dst)
        
    if os.path.exists(src):
        try:
            logging.info(f"Copying gcloud config from {src} to {dst}")
            shutil.copytree(src, dst, dirs_exist_ok=True)
            _gcloud_config_setup = True
        except Exception as e:
            logging.error(f"Failed to copy gcloud config: {e}")
    else:
        logging.warning(f"GCloud config source {src} not found")

async def run_cloud_run_command(command_args: str) -> Dict[str, Any]:
    """
    ADK tool: Execute gcloud run command directly via CLI
    
    Args:
        command_args: Space-separated arguments for gcloud run (e.g. 'services list')
    
    Returns:
        Dictionary with execution result
    """
    
    # Ensure config requires write access is in a writable place
    setup_gcloud_config()
    
    # Parse string into list
    try:
        args = shlex.split(command_args)
    except Exception:
        args = command_args.split()

    full_cmd = ["gcloud", "run"] + args
    
    # Prepare environment with custom config path
    env = os.environ.copy()
    env["CLOUDSDK_CONFIG"] = "/tmp/gcloud_config"
    # Disable file logging to prevent clutter/errors
    env["CLOUDSDK_CORE_DISABLE_FILE_LOGGING"] = "1" 
    
    try:
        logging.info(f"Executing: {' '.join(full_cmd)}")
        
        # Execute synchronously 
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env
        )
        
        if result.returncode == 0:
            logging.info(f"Command succeeded: {result.stdout[:200]}...")
            return {
                "success": True,
                "output": result.stdout,
                "command": f"gcloud run {command_args}"
            }
        else:
            logging.error(f"Command failed: {result.stderr}")
            return {
                "success": False,
                "error": result.stderr,
                "command": f"gcloud run {command_args}"
            }

    except subprocess.TimeoutExpired:
        logging.error("Command timed out")
        return {
            "success": False,
            "error": "Command timed out after 120s",
            "command": f"gcloud run {command_args}"
        }
    except Exception as e:
        logging.error(f"Execution failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "command": f"gcloud run {command_args}"
        }


# Create ADK Agent
cloud_run_agent = Agent(
    name="cloud_run_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="""
    Google Cloud Run specialist.
    Expert in deploying and managing serverless containers using Cloud Run.
    Can execute gcloud run commands to list services, deploy new revisions, and manage traffic.
    """,
    instruction="""
    You are a Google Cloud Run specialist.
    
    Your responsibilities:
    1. Understand user requests related to Cloud Run services and jobs
    2. Translate natural language to appropriate arguments for the `run_cloud_run_command` tool.
    3. Execute commands safely and return results
    4. Provide clear, helpful responses
    
    Guidelines:
    - Use the `run_cloud_run_command` tool.
    - Pass arguments as a SINGLE STRING (space-separated). Do not use a list.
    - Example: to list services, pass `command_args="services list"`.
    - For deployments: Ask for all necessary details (image, region, allow-unauthenticated) if missing.
    - For destructive actions (delete): Always confirm with the user first.
    
    Common patterns:
    - List Services: `command_args="services list"`
    - Describe Service: `command_args="services describe SERVICE_NAME --region=REGION"`
    - Deploy: `command_args="deploy SERVICE_NAME --image=IMAGE_URL --region=REGION"`
    
    Always be helpful, accurate, and safe.
    """,
    tools=[run_cloud_run_command]
)

# Configure BigQuery Analytics Plugin
bq_config = BigQueryLoggerConfig(
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    batch_size=1,
    max_content_length=100 * 1024,
    shutdown_timeout=10.0
)

bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=config.GCP_PROJECT_ID,
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=bq_config,
    location="US"
)

# Ensure API Key is in environment for GenAI library
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

# Create the App
app = App(
    name="finopti_cloud_run_agent",
    root_agent=cloud_run_agent,
    plugins=[
        ReflectAndRetryToolPlugin(
            max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "3")),
            throw_exception_if_retry_exceeded=os.getenv("REFLECT_RETRY_THROW_ON_FAIL", "true").lower() == "true"
        ),
        bq_plugin
    ]
)

async def send_message_async(prompt: str, user_email: str = None) -> str:
    """
    Send a message to the Cloud Run agent
    
    Args:
        prompt: User's natural language request
        user_email: Optional user email for logging
    
    Returns:
        Agent's response as string
    """
    try:
        # Use InMemoryRunner to execute the app
        async with InMemoryRunner(app=app) as runner:
            sid = "default"
            uid = "default"
            await runner.session_service.create_session(
                session_id=sid, 
                user_id=uid,
                app_name="finopti_cloud_run_agent"
            )
            
            message = types.Content(parts=[types.Part(text=prompt)])
            response_text = ""
            async for event in runner.run_async(
                user_id=uid,
                session_id=sid,
                new_message=message
            ):
                 # Accumulate text content from events
                 if hasattr(event, 'content') and event.content and event.content.parts:
                     for part in event.content.parts:
                         if part.text:
                             response_text += part.text
            
            return response_text if response_text else "No response generated."

    except Exception as e:
        return f"Error processing request: {str(e)}"

def send_message(prompt: str, user_email: str = None) -> str:
    """
    Synchronous wrapper for send_message_async
    
    Args:
        prompt: User's natural language request
        user_email: Optional user email for logging
    
    Returns:
        Agent's response as string
    """
    return asyncio.run(send_message_async(prompt, user_email))


if __name__ == "__main__":
    # Test the agent
    import sys
    
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"Prompt: {prompt}")
        print("=" * 50)
        response = send_message(prompt)
        print(response)
    else:
        print("Usage: python agent.py <prompt>")
        print("Example: python agent.py 'list services'")
