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
        import subprocess
        
        # Check if running in a container with access to docker socket
        # The command: docker run -i --rm -v <mount> <image>
        # Note: -i is crucial for stdin. -t is NOT used to avoid TTY control chars.
        cmd = [
            "docker", "run", 
            "-i", "--rm", 
            "-v", self.mount_path,
            self.image
        ]
        
        logging.info(f"Starting MCP server with command: {' '.join(cmd)}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )
            
        except Exception as e:
            logging.error(f"Failed to start MCP server: {e}")
            raise

    async def close(self):
        """Stop the MCP server"""
        if self.process:
            self.process.terminate()
            self.process.wait()
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
            self.process.stdin.write(json_str)
            self.process.stdin.flush()
            
            # Read response
            while True:
                line = self.process.stdout.readline()
                if not line:
                    # EOF
                    stderr = self.process.stderr.read()
                    raise RuntimeError(f"MCP server closed connection. Stderr: {stderr}")
                
                try:
                    msg = json.loads(line)
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


# Create ADK Agent
gcloud_agent = Agent(
    name="gcloud_infrastructure_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="""
    Google Cloud Platform infrastructure management specialist.
    Expert in managing VMs, networks, storage, and other GCP resources using gcloud CLI.
    Can execute gcloud commands to list, create, modify, and delete cloud resources.
    """,
    instruction="""
    You are a Google Cloud Platform (GCP) infrastructure specialist with deep expertise in gcloud CLI.
    
    Your responsibilities:
    1. Understand user requests related to GCP infrastructure
    2. Translate natural language to appropriate gcloud commands
    3. Execute commands safely and return results
    4. Provide clear, helpful responses
    
    Guidelines:
    - For listing operations: Use appropriate --format flags for readable output
    - For modifications: Confirm the operation before executing if it's destructive
    - For VM operations: Remember that changing machine types requires stopping the instance first
    - For cost optimization: Suggest recommendations when appropriate
    
    Common patterns:
    - List VMs: gcloud compute instances list
    - Create VM: gcloud compute instances create <name> --zone=<zone> --machine-type=<type>
    - Delete VM: gcloud compute instances delete <name> --zone=<zone>
    - Stop/Start VM: gcloud compute instances stop/start <name> --zone=<zone>
    - Change machine type: (stop VM first, then set-machine-type, then start)
    
    Always be helpful, accurate, and safe in your operations.
    """,
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
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=bq_config,
    location="US"
)

# Ensure API Key is in environment for GenAI library
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

# Create the App
app = App(
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
