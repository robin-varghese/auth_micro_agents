"""
GCloud ADK Agent - Google Cloud Infrastructure Specialist

This agent uses Google ADK to handle GCP infrastructure management requests.
It integrates with the GCloud MCP server for executing gcloud commands.
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
from typing import Dict, Any, List
import asyncio
import json
import requests  # For HTTP MCP client
import logging

from config import config

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name=os.getenv("GCP_PROJECT_ID", "local") + "-gcloud-agent-adk",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# MCP Client for GCloud via Docker Stdio
class GCloudMCPClient:
    """Client for connecting to GCloud MCP server via Docker Stdio"""
    
    def __init__(self):
        self.image = os.getenv('GCLOUD_MCP_DOCKER_IMAGE', 'finopti-gcloud-mcp')
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0
        logging.info(f"GCloudMCPClient initialized for image: {self.image}")
        logging.info(f"GCloudMCPClient command mount path: {self.mount_path}")
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        """Start the MCP server container"""
        
        # Check if running in a container with access to docker socket
        cmd = [
            "docker", "run", 
            "-i", "--rm", 
            "-v", self.mount_path,
            self.image
        ]
        
        logging.info(f"Starting MCP server with command: {' '.join(cmd)}")
        
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # --- MCP Initialization Handshake ---
            # 1. Send 'initialize' request
            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "finopti-gcloud-agent", "version": "1.0"}
                },
                "id": 0
            }
            
            logging.info("Sending MCP initialize request...")
            self.process.stdin.write((json.dumps(init_payload) + "\n").encode())
            await self.process.stdin.drain()
            
            # 2. Wait for initialize response
            while True:
                line = await self.process.stdout.readline()
                if not line:
                     stderr = await self.process.stderr.read()
                     raise RuntimeError(f"MCP server closed during initialization. Stderr: {stderr.decode()}")
                
                try:
                    msg = json.loads(line.decode())
                    if msg.get("id") == 0:
                        if "error" in msg:
                             raise RuntimeError(f"MCP initialization error: {msg['error']}")
                        logging.info("MCP Initialized successfully.")
                        break
                except json.JSONDecodeError:
                    logging.warning(f"Invalid JSON during init: {line}")
            
            # 3. Send 'notifications/initialized'
            notify_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            self.process.stdin.write((json.dumps(notify_payload) + "\n").encode())
            await self.process.stdin.drain()
            
        except Exception as e:
            logging.error(f"Failed to start MCP server: {e}")
            if self.process:
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass
            raise

    async def close(self):
        """Stop the MCP server"""
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                pass
            self.process = None
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Dict[str, Any]:
        """Call GCloud MCP tool via Stdio"""
        if not self.process:
            raise RuntimeError("MCP client not connected")
            
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self.request_id
        }
        
        json_str = json.dumps(payload) + "\n"
        
        try:
            # Write request
            self.process.stdin.write(json_str.encode())
            await self.process.stdin.drain()
            
            # Read response
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    # EOF
                    stderr = await self.process.stderr.read()
                    raise RuntimeError(f"MCP server closed connection. Stderr: {stderr.decode()}")
                
                try:
                    msg = json.loads(line.decode())
                    if msg.get("id") == self.request_id:
                        if "error" in msg:
                            raise RuntimeError(f"MCP tool error: {msg['error']}")
                        
                        result = msg.get("result", {})
                        if "content" in result:
                            output_text = ""
                            for content in result["content"]:
                                if content.get("type") == "text":
                                    output_text += content["text"]
                            try:
                                return json.loads(output_text)
                            except json.JSONDecodeError:
                                return {"output": output_text}
                        
                        return result
                except json.JSONDecodeError:
                     logging.warning(f"Invalid JSON from MCP server: {line}")
                     
        except Exception as e:
             raise RuntimeError(f"MCP call failed: {e}") from e

    async def run_gcloud_command(self, args: List[str]) -> str:
        """
        Execute a gcloud command via MCP server
        
        Args:
            args: List of gcloud command arguments (without 'gcloud' prefix)
        
        Returns:
            Command output as string
        """
        result = await self.call_tool(
            "run_gcloud_command",
            arguments={"args": args}
        )
        
        if isinstance(result, dict) and "output" in result:
            return result["output"]
        return str(result)


# Global MCP client (will be initialized per-request)
_mcp_client = None

async def execute_gcloud_command(args: List[str]) -> Dict[str, Any]:
    """
    ADK tool: Execute gcloud command
    
    Args:
        args: List of gcloud command arguments
    
    Returns:
        Dictionary with execution result
    """
    global _mcp_client
    
    try:
        if not _mcp_client:
            _mcp_client = GCloudMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.run_gcloud_command(args)
        
        return {
            "success": True,
            "output": output,
            "command": f"gcloud {' '.join(args)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": f"gcloud {' '.join(args)}"
        }


# ... (imports remain same, assume they are there or I need to include them if I replace large block)
# I will replace from "Create ADK Agent" section down to "from google.adk.runners import InMemoryRunner" safely.

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
        instruction_str = data.get("instruction", "You are a Google Cloud Platform Specialist.")
else:
    instruction_str = "You are a Google Cloud Platform Specialist."


# Helper function to create agent/app per request
def create_app():
    # Ensure API Key is in environment for GenAI library
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    # Create ADK Agent
    gcloud_agent = Agent(
        name=manifest.get("agent_id", "gcloud_infrastructure_specialist"),
        model=config.FINOPTIAGENTS_LLM,
        description=manifest.get("description", "Google Cloud Platform infrastructure management specialist."),
        instruction=instruction_str,
        tools=[execute_gcloud_command]
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
        table_id=config.BQ_ANALYTICS_TABLE,
        config=bq_config,
        location="US"
    )

    # Create the App
    return App(
        name="finopti_gcloud_agent",
        root_agent=gcloud_agent,
        plugins=[
            ReflectAndRetryToolPlugin(
                max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "3")),
                throw_exception_if_retry_exceeded=os.getenv("REFLECT_RETRY_THROW_ON_FAIL", "true").lower() == "true"
            ),
            bq_plugin
        ]
    )

from google.adk.runners import InMemoryRunner
from google.genai import types

async def send_message_async(prompt: str, user_email: str = None) -> str:
    """
    Send a message to the GCloud agent
    
    Args:
        prompt: User's natural language request
        user_email: Optional user email for logging
    
    Returns:
        Agent's response as string
    """
    try:
        # Initialize MCP client if needed
        global _mcp_client
        if not _mcp_client:
            _mcp_client = GCloudMCPClient()
            await _mcp_client.connect()
        
        # Create App instance for this request (ensures fresh event loop binding for plugins)
        app = create_app()

        # Use InMemoryRunner to execute the app
        async with InMemoryRunner(app=app) as runner:
            sid = "default"
            uid = "default"
            await runner.session_service.create_session(
                session_id=sid, 
                user_id=uid,
                app_name="finopti_gcloud_agent"
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
    finally:
        # Clean up MCP client
        if _mcp_client:
            await _mcp_client.close()
            _mcp_client = None


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
        print("Example: python agent.py 'list all VMs'")
