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
    Simple keyword-based intent detection with improved accuracy.
    In production, this could be enhanced with ADK's capabilities.
    
    Args:
        prompt: User's natural language prompt
        
    Returns:
        target_agent: 'gcloud', 'monitoring', 'github', 'storage', 'db', or 'cloud-run'
    """
    prompt_lower = prompt.lower()
    words = set(prompt_lower.split())
    
    # Helper for robust matching
    def count_matches(keywords: List[str]) -> int:
        score = 0
        for k in keywords:
            # For short keywords/acronyms, require exact word match
            if len(k) <= 3:
                if k in words:
                    score += 1
            # For longer phrases, use substring match
            else:
                if k in prompt_lower:
                    score += 1
        return score

    # GitHub keywords
    github_keywords = ['github', 'repo', 'repository', 'git', 'pull request', 'pr', 'issue', 'code', 'commit']
    # Storage keywords
    storage_keywords = ['bucket', 'object', 'blob', 'gcs', 'upload', 'download']
    # DB keywords
    db_keywords = ['database', 'sql', 'query', 'table', 'postgres', 'postgresql', 'schema', 'select', 'insert']
    # Monitoring keywords
    monitoring_keywords = ['cpu', 'memory', 'logs', 'metrics', 'monitor', 'alert', 'usage', 'check',
                           'performance', 'latency', 'error', 'log', 'trace', 'observability']
    # GCloud keywords (fallback for general infra)
    gcloud_keywords = ['vm', 'instance', 'create', 'delete', 'compute', 'gcp', 'cloud', 'provision', 
                        'machine', 'disk', 'network', 'firewall', 'operations', 'project', 'region', 'zone']
    # Cloud Run keywords
    cloud_run_keywords = ['cloud run', 'service', 'revision', 'container', 'serverless', 'deploy', 'traffic', 'image', 'knative', 'job']
    
    scores = {
        'github': count_matches(github_keywords),
        'storage': count_matches(storage_keywords),
        'db': count_matches(db_keywords),
        'monitoring': count_matches(monitoring_keywords),
        'cloud-run': count_matches(cloud_run_keywords),
        'gcloud': count_matches(gcloud_keywords)
    }
    
    # Find agent with highest score
    # Use fallback to 'gcloud' if tie or all zero (but handle tie logic explicitly if needed)
    best_agent = max(scores, key=scores.get)
    
    if scores[best_agent] > 0:
        return best_agent
    else:
        # Default to gcloud if unclear/no keywords match
        return 'gcloud'


def check_opa_authorization(user_email: str, target_agent: str) -> dict:
    """
    Call OPA to check if user is authorized to access the target agent.
    
    Args:
        user_email: User's email address
        target_agent: Target agent name
        
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
        target_agent: Target agent name
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
            'monitoring': f"{config.APISIX_URL}/agent/monitoring/execute",
            'github': f"{config.APISIX_URL}/agent/github/execute",
            'storage': f"{config.APISIX_URL}/agent/storage/execute",
            'storage': f"{config.APISIX_URL}/agent/storage/execute",
            'db': f"{config.APISIX_URL}/agent/db/execute",
            'cloud-run': f"{config.APISIX_URL}/agent/cloud-run" # Note: New agent uses /agent/cloud-run directly or via execute if consistent
        }
        
        # Adjust endpoint for cloud-run if following Flask pattern
        if target_agent == 'cloud-run':
             endpoint = f"{config.APISIX_URL}/agent/cloud-run"
        else:
             endpoint = agent_endpoints[target_agent]
        
        if target_agent not in agent_endpoints and target_agent != 'cloud-run':
            return {
                "success": False,
                "error": f"Unknown agent: {target_agent}"
            }
        
        
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
        
        try:
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors (4xx, 5xx)
            try:
                error_data = response.json()
                return {
                    "success": False,
                    "error": error_data.get("message", str(e)),
                    "agent": target_agent
                }
            except ValueError:
                 return {
                    "success": False,
                    "error": f"Agent request failed: {str(e)}. Response: {response.text[:200]}",
                    "agent": target_agent
                }
        except ValueError:
            # Handle valid 200 OK but invalid JSON
             return {
                "success": False,
                "error": f"Invalid JSON response from agent: {response.text[:200]}",
                "agent": target_agent
            }

        return {
            "success": True,
            "data": data,
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
    Manages infrastructure, monitoring, code, storage, and databases.
    """,
    instruction="""
    You are the central orchestrator for the FinOptiAgents platform.
    
    Your responsibilities:
    1. Understand user requests related to cloud operations.
    2. Determine which specialized agent should handle the request.
    3. Coordinate with the appropriate agent to fulfill the request.
    
    Available specialized agents:
    - **gcloud**: Handles GCP infrastructure, operations, activity, and audit logs.
    - **monitoring**: Handles metrics, logs, and observability queries.
    - **github**: Handles GitHub repositories, issues, and PRs (NOT Google Cloud Source Repos).
    - **storage**: Handles Google Cloud Storage buckets and objects.
    - **storage**: Handles Google Cloud Storage buckets and objects.
    - **db**: Handles SQL database queries (PostgreSQL).
    - **cloud-run**: Handles Cloud Run services, jobs, and deployments.
    
    Routing Logic Guidelines (CRITICAL - Follow Exactly):
    
    **GCloud Agent** - Use for generic GCP-related request (VMs, Networks):
    - GCP operations: "list operations", "cloud operations", "recent changes"
    - Infrastructure: "Create VM", "Delete disk", "List instances", "Show VMs"
    - Cloud activity: "What changed", "Recent deployments", "Audit logs"
    - GCP services: Compute Engine, GKE, Cloud Functions
    - Resource management: "Resize VM", "Stop instance", "Network config"

    **Cloud Run Agent** - Use for Cloud Run / Serverless Containers:
    - "Deploy to Cloud Run", "List Cloud Run services"
    - "Show revisions", "Update traffic split", "Cloud Run jobs"
    - "Serverless deployment"
    
    **GitHub Agent** - Use ONLY for GitHub.com:
    - "List GitHub repos", "Show my repositories on GitHub"
    - "Find code in GitHub", "Show PRs", "Create issue"
    - DO NOT use for Google Cloud Source Repositories
    
    **Storage Agent**:
    - "List buckets", "Upload file to GCS", "Show blobs"
    - "Download from bucket", "Get object metadata"
    
    **Database Agent**:
    - "Query table", "Show schema", "SELECT * FROM"
    - PostgreSQL-specific queries
    
    **Monitoring Agent**:
    - "CPU usage", "Error logs", "Latency metrics"
    - "Show logs from service X", "Memory consumption"
    
    **Key Rules:**
    1. "operations in GCP/cloud/project" → **gcloud** (NEVER github)
    2. Mention of "project ID" or "GCP Project" → **gcloud**
    3. "GitHub repos/code" → **github**  
    4. Default for infrastructure → **gcloud**
    
    WARNING: Do NOT route "cloud project" or "project operations" to the github agent. The github agent only handles code repositories on github.com. GCP operations like "list operations" MUST go to gcloud.
    
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
        
        # Propagate error if present
        response_data = agent_response.get('data', {})
        if not agent_response.get('success', False):
            error_msg = agent_response.get('error', 'Unknown sub-agent error')
            response_data = {"error": error_msg}

        # Add orchestrator metadata
        return {
            "success": agent_response.get('success', False),
            "response": response_data,
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
