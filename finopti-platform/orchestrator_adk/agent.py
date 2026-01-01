"""
Orchestrator ADK Agent - Central Hub with Intelligent Routing

This is the main orchestrator that uses Google ADK for intelligent request routing.
It maintains OPA authorization integration and routes requests to specialized sub-agents.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from typing import Dict, Any, List, Optional
import asyncio
import requests


from config import config
from structured_logging import propagate_request_id


def detect_intent(prompt: str) -> str:
    """
    Simple keyword-based intent detection.
    In production, this could be enhanced with ADK's capabilities.
    
    Args:
        prompt: User's natural language prompt
        
    Returns:
        target_agent: 'gcloud' or 'monitoring'
    """
    prompt_lower = prompt.lower()
    
    # GCloud keywords
    gcloud_keywords = ['vm', 'instance', 'create', 'delete', 'compute', 'gcp', 'cloud', 'provision', 
                        'machine', 'disk', 'network', 'firewall', 'storage', 'bucket']
    # Monitoring keywords
    monitoring_keywords = ['cpu', 'memory', 'logs', 'metrics', 'monitor', 'alert', 'usage', 'check',
                           'performance', 'latency', 'error', 'log', 'trace', 'observability']
    
    gcloud_score = sum(1 for keyword in gcloud_keywords if keyword in prompt_lower)
    monitoring_score = sum(1 for keyword in monitoring_keywords if keyword in prompt_lower)
    
    if monitoring_score > gcloud_score:
        return 'monitoring'
    else:
        # Default to gcloud if unclear
        return 'gcloud'


def check_opa_authorization(user_email: str, target_agent: str) -> dict:
    """
    Call OPA to check if user is authorized to access the target agent.
    
    Args:
        user_email: User's email address
        target_agent: Target agent ('gcloud' or 'monitoring')
        
    Returns:
        dict with 'allow' (bool) and 'reason' (str)
    """
    try:
        opa_endpoint = f"{config.OPA_URL}/v1/data/finopti/authz"
        payload = {
            "input": {
                "user_email": user_email,
                "target_agent": target_agent
            }
        }
        
        response = requests.post(opa_endpoint, json=payload, timeout=5)
        response.raise_for_status()
        
        result = response.json()
        authz_result = result.get('result', {})
        
        return authz_result
        
    except Exception as e:
        return {
            "allow": False,
            "reason": f"Authorization service error: {str(e)}"
        }


async def route_to_agent(target_agent: str, prompt: str, user_email: str, project_id: str = None) -> Dict[str, Any]:
    """
    ADK tool: Route request to appropriate sub-agent
    
    Args:
        target_agent: 'gcloud' or 'monitoring'
        prompt: User's prompt
        user_email: User's email
        project_id: Optional GCP project ID
    
    Returns:
        Response from sub-agent
    """
    try:
        # Map agent to endpoint
        agent_endpoints = {
            'gcloud': f"{config.APISIX_URL}/agent/gcloud/execute",
            'monitoring': f"{config.APISIX_URL}/agent/monitoring/execute"
        }
        
        if target_agent not in agent_endpoints:
            return {
                "success": False,
                "error": f"Unknown agent: {target_agent}"
            }
        
        endpoint = agent_endpoints[target_agent]
        
        # Prepare payload
        payload = {
            "prompt": prompt,
            "user_email": user_email
        }
        
        if project_id:
            payload["project_id"] = project_id
        
        # Call sub-agent via APISIX
        headers = {"Content-Type": "application/json"}
        headers = propagate_request_id(headers)
        
        response = requests.post(endpoint, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        
        return {
            "success": True,
            "data": response.json(),
            "agent": target_agent
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "agent": target_agent
        }


# Create ADK Orchestrator Agent
orchestrator_agent = Agent(
    name="finopti_orchestrator",
    model=config.FINOPTIAGENTS_LLM,
    description="""
    FinOps orchestration agent that intelligently routes user requests to specialized agents.
    Manages infrastructure and monitoring operations with proper authorization.
    """,
    instruction="""
    You are the  central orchestrator for the FinOptiAgents platform.
    
    Your responsibilities:
    1. Understand user requests related to cloud infrastructure and monitoring
    2. Determine which specialized agent should handle the request
    3. Coordinate with the appropriate agent to fulfill the request
    4. Provide clear, helpful responses to users
    
    Available specialized agents:
    - gcloud: Handles GCP infrastructure (VMs, networks, storage, etc.)
    - monitoring: Handles monitoring, metrics, and logs
    
    Guidelines:
    - For infrastructure operations (create VM, delete disk, etc.) → use gcloud agent
    - For monitoring queries (CPU usage, logs, metrics) → use monitoring agent
    - Be helpful and accurate in your responses
    - Provide context and explanations when appropriate
    
    Authorization is handled separately via OPA before you receive requests.
    """,
    tools=[route_to_agent]
)

# Configure BigQuery Analytics Plugin
bq_config = BigQueryLoggerConfig(
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    batch_size=1,  # Low latency for real-time analysis
    max_content_length=100 * 1024,  # 100KB limit
    shutdown_timeout=10.0
)

bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=config.GCP_PROJECT_ID,
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=bq_config,
    location="US"
)

# Create App# Create the App
app = App(
    name="finopti_orchestrator",
    root_agent=orchestrator_agent,
    plugins=[
        ReflectAndRetryToolPlugin(
            max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "3")),
            throw_exception_if_retry_exceeded=os.getenv("REFLECT_RETRY_THROW_ON_FAIL", "true").lower() == "true"
        ),
        bq_plugin
    ]
)


async def process_request_async(
    prompt: str,
    user_email: str,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a user request through the orchestrator
    
    Args:
        prompt: User's natural language request
        user_email: User's email address
        project_id: Optional GCP project ID
    
    Returns:
        Dictionary with response and metadata
    """
    try:
        # Detect intent
        target_agent = detect_intent(prompt)
        
        # Check authorization via OPA
        authz_result = check_opa_authorization(user_email, target_agent)
        
        if not authz_result.get('allow', False):
            return {
                "error": True,
                "message": f"403 Unauthorized: {authz_result.get('reason', 'Access denied')}",
                "user_email": user_email,
                "target_agent": target_agent,
                "authorized": False
            }
        
        # Route to agent
        agent_response = await route_to_agent(
            target_agent=target_agent,
            prompt=prompt,
            user_email=user_email,
            project_id=project_id or config.GCP_PROJECT_ID
        )
        
        # Add orchestrator metadata
        return {
            "success": agent_response.get('success', False),
            "response": agent_response.get('data', {}),
            "orchestrator": {
                "user_email": user_email,
                "target_agent": target_agent,
                "authorization": authz_result.get('reason', ''),
                "authorized": True
            }
        }
    
    except Exception as e:
        return {
            "error": True,
            "message": f"Orchestrator error: {str(e)}"
        }


def process_request(
    prompt: str,
    user_email: str,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronous wrapper for process_request_async
    
    Args:
        prompt: User's natural language request
        user_email: User's email address
        project_id: Optional GCP project ID
    
    Returns:
        Dictionary with response and metadata
    """
    return asyncio.run(process_request_async(prompt, user_email, project_id))


if __name__ == "__main__":
    # Test the orchestrator
    import sys
    
    if len(sys.argv) > 2:
        user_email = sys.argv[1]
        prompt = " ".join(sys.argv[2:])
        
        print(f"User: {user_email}")
        print(f"Prompt: {prompt}")
        print("=" * 50)
        
        result = process_request(prompt, user_email, config.GCP_PROJECT_ID)
        
        import json
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python agent.py <user_email> <prompt>")
        print("Example: python agent.py admin@example.com 'list all VMs'")
