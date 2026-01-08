"""
Cloud Run ADK Agent - Serverless Container Specialist

This agent uses Google ADK to handle Cloud Run management requests.
It integrates with the Cloud Run MCP server for executing gcloud run commands.
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
import logging

from config import config

# MCP Client for Cloud Run via Docker Stdio
class CloudRunMCPClient:
    """Client for connecting to Cloud Run MCP server via Docker Stdio"""
    
    def __init__(self):
        self.image = os.getenv('CLOUD_RUN_MCP_DOCKER_IMAGE', 'finopti-cloud-run-mcp')
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0
        logging.info(f"CloudRunMCPClient initialized for image: {self.image}")
        logging.info(f"CloudRunMCPClient command mount path: {self.mount_path}")
    
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
                    "clientInfo": {"name": "finopti-cloud-run-agent", "version": "1.0"}
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
        """Call Cloud Run MCP tool via Stdio"""
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

    async def run_cloud_run_command(self, args: List[str]) -> str:
        """
        Execute a gcloud run command via MCP server
        
        Args:
            args: List of gcloud command arguments (without 'gcloud' prefix)
        
        Returns:
            Command output as string
        """
        result = await self.call_tool(
            "run_cloud_run_command",
            arguments={"args": args}
        )
        
        if isinstance(result, dict) and "output" in result:
            return result["output"]
        return str(result)


# Global MCP client (will be initialized per-request)
_mcp_client = None

async def execute_cloud_run_command(args: List[str]) -> Dict[str, Any]:
    """
    ADK tool: Execute gcloud run command
    
    Args:
        args: List of gcloud run command arguments (e.g. ['services', 'list'])
    
    Returns:
        Dictionary with execution result
    """
    global _mcp_client
    
    try:
        if not _mcp_client:
            _mcp_client = CloudRunMCPClient()
            await _mcp_client.connect()
        
        output = await _mcp_client.run_cloud_run_command(args)
        
        return {
            "success": True,
            "output": output,
            "command": f"gcloud run {' '.join(args)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": f"gcloud run {' '.join(args)}"
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
    2. Translate natural language to appropriate `gcloud run` commands
    3. Execute commands safely and return results
    4. Provide clear, helpful responses
    
    Guidelines:
    - Assume `gcloud run` prefix is handled by the tool. Pass arguments starting after `run`.
      Example: to list services, pass `['services', 'list']`.
    - For deployments: Ask for all necessary details (image, region, allow-unauthenticated) if missing.
    - For destructive actions (delete): Always confirm with the user first.
    
    Common patterns:
    - List Services: arguments=['services', 'list']
    - Describe Service: arguments=['services', 'describe', 'SERVICE_NAME', '--region=REGION']
    - Deploy: arguments=['deploy', 'SERVICE_NAME', '--image=IMAGE_URL', '--region=REGION']
    
    Always be helpful, accurate, and safe.
    """,
    tools=[execute_cloud_run_command]
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


from google.adk.runners import InMemoryRunner
from google.genai import types

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
        # Initialize MCP client if needed
        global _mcp_client
        if not _mcp_client:
            _mcp_client = CloudRunMCPClient()
            await _mcp_client.connect()
        
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
        print("Example: python agent.py 'list services'")
