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
        
        target_agent: One of ['gcloud', 'monitoring', 'github', 'storage', 'db', 
                            'brave', 'filesystem', 'analytics', 'puppeteer', 'sequential', 'cloud-run', 'mats', 'googlesearch', 'code']
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
    db_keywords = ['database', 'sql', 'query', 'table', 'postgres', 'postgresql', 'schema', 'select', 'insert', 'bigquery', 'bq', 'history']
    # Monitoring keywords
    monitoring_keywords = ['cpu', 'memory', 'logs', 'metrics', 'monitor', 'alert', 'usage', 'check',
                           'performance', 'latency', 'error', 'log', 'trace', 'observability']
    # GCloud keywords (fallback for general infra)
    gcloud_keywords = ['vm', 'instance', 'create', 'delete', 'compute', 'gcp', 'cloud', 'provision', 
                        'machine', 'disk', 'network', 'firewall', 'operations', 'project', 'region', 'zone']
    # Cloud Run keywords
    cloud_run_keywords = ['cloud run', 'service', 'revision', 'container', 'serverless', 'deploy', 'traffic', 'image', 'knative', 'job']
    # MATS keywords (Troubleshooting)
    mats_keywords = ['troubleshoot', 'fix', 'debug', 'check what went wrong', 'root cause', 'why is it failing', 'investigate', 'rca', 'diagnosis']
    
    # Brave Search keywords
    brave_keywords = ['search', 'find', 'lookup', 'web', 'internet', 'online', 'google']
    # Filesystem keywords
    filesystem_keywords = ['file', 'directory', 'folder', 'cat', 'ls', 'local file', 'read', 'write']
    # Analytics keywords
    analytics_keywords = ['analytics', 'traffic', 'users', 'sessions', 'pageviews', 'ga4', 'report', 'visitor']
    # Puppeteer keywords
    puppeteer_keywords = ['browser', 'screenshot', 'click', 'navigate', 'visit', 'scrape', 'form', 'webpage']
    # Sequential keywords
    sequential_keywords = ['think', 'reason', 'plan', 'solve', 'analyze', 'complex', 'step by step']
    # Google Search keywords
    googlesearch_keywords = ['search', 'google', 'find', 'lookup', 'web', 'internet', 'scraping']
    # Code Execution keywords
    code_keywords = ['code', 'execute', 'calculate', 'python', 'script', 'math', 'function', 'snippet']

    scores = {
        'github': count_matches(github_keywords),
        'storage': count_matches(storage_keywords),
        'db': count_matches(db_keywords),
        'monitoring': count_matches(monitoring_keywords),
        'cloud-run': count_matches(cloud_run_keywords) * 5,
        'gcloud': count_matches(gcloud_keywords),
        'mats': count_matches(mats_keywords) * 10,
        'brave': count_matches(brave_keywords),
        'filesystem': count_matches(filesystem_keywords),
        'analytics': count_matches(analytics_keywords),
        'puppeteer': count_matches(puppeteer_keywords),
        'sequential': count_matches(sequential_keywords),
        'googlesearch': count_matches(googlesearch_keywords) * 2,
        'code': count_matches(code_keywords)
    }
    
    # Resolve Conflicts
    # 'file' -> Filesystem vs Storage
    if 'bucket' in prompt_lower or 'object' in prompt_lower:
        scores['storage'] += 5
        
    # 'agent operations' -> DB (Analytics)
    if 'agent' in prompt_lower and 'operations' in prompt_lower:
        scores['db'] += 10
        
    # 'search' -> Brave vs DB vs Google Search
    if 'sql' in prompt_lower or 'table' in prompt_lower:
        scores['db'] += 5
    elif 'google' in prompt_lower and 'search' in prompt_lower and not ('google cloud' in prompt_lower or 'gcp' in prompt_lower):
        scores['googlesearch'] += 15
    elif 'brave' in prompt_lower:
        scores['brave'] += 10
        
    # 'code' -> GitHub vs Code Execution
    if 'repo' in prompt_lower or 'push' in prompt_lower or 'pull' in prompt_lower:
        scores['github'] += 5
    elif 'execute' in prompt_lower or 'calculate' in prompt_lower: # Removed generic 'run' to avoid Cloud Run conflict
        scores['code'] += 5
        
    # 'google cloud' -> GCloud (vs Google Search)
    if 'google cloud' in prompt_lower or 'gcp' in prompt_lower:
        scores['gcloud'] += 10
        scores['googlesearch'] -= 5  # Penalize generic search if it's clearly cloud platform
        
    # 'mats' explicit trigger overrides others (for troubleshooting context)
    if 'troubleshoot' in prompt_lower or 'debug' in prompt_lower or 'fix' in prompt_lower:
        scores['mats'] += 15
    
    # Find agent with highest score
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


async def route_to_agent(target_agent: str, prompt: str, user_email: str, project_id: str = None, auth_token: str = None) -> Dict[str, Any]:
    """
    ADK tool: Route request to appropriate sub-agent
    
    Args:
        target_agent: Target agent name
        prompt: User's prompt
        user_email: User's email
        project_id: Optional GCP project ID
        auth_token: Optional OAuth token for Auth-dependent agents (Analytics)
    
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
            'db': f"{config.APISIX_URL}/agent/db/execute",
            'cloud-run': f"{config.APISIX_URL}/agent/cloud-run/execute",
            'mats': "http://mats-orchestrator:8084/chat",
            'brave': f"{config.APISIX_URL}/agent/brave/execute",
            'filesystem': f"{config.APISIX_URL}/agent/filesystem/execute",
            'analytics': f"{config.APISIX_URL}/agent/analytics/execute",
            'puppeteer': f"{config.APISIX_URL}/agent/puppeteer/execute",
            'sequential': f"{config.APISIX_URL}/agent/sequential/execute",
            'googlesearch': f"{config.APISIX_URL}/agent/googlesearch/execute",
            'code': f"{config.APISIX_URL}/agent/code/execute"
        }
        
        # Adjust endpoint logic if needed (e.g. cloud-run special case is now standardized above)
        if target_agent == 'mats':
             endpoint = agent_endpoints['mats']
        else:
             endpoint = agent_endpoints.get(target_agent)
        
        if not endpoint:
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
            
        if target_agent == 'mats':
             # Direct internal routing to MATS service
             # Note: MATS requires specific payload structure
             endpoint = "http://mats-orchestrator:8084/troubleshoot"
             payload = {
                 "project_id": project_id or config.GCP_PROJECT_ID,
                 "repo_url": "https://github.com/robin-varghese/auth_micro_agents", # Default for this env
                 "error_description": prompt,
                 "branch": "main"
             }
        
        # Call sub-agent via APISIX
        headers = {"Content-Type": "application/json"}
        headers = propagate_request_id(headers)
        
        # --- Propagate Auth Token ---
        if auth_token:
            headers['Authorization'] = auth_token
        # ----------------------------
        
        # Increase timeout for all agents to support long-running operations (e.g. Broken Deployment)
        timeout = 600
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        
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
    - **brave**: Web search using Brave Search (privacy-focused).
    - **filesystem**: Local file system operations (list, read, write).
    - **analytics**: Google Analytics queries (traffic, users).
    - **puppeteer**: Browser automation and screenshots.
    - **sequential**: Deep reasoning for complex multi-step problems.
    - **googlesearch**: Google Search (official) for internet queries.
    - **code**: Execute Python code for calculations and data processing.
    
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

    **Web Search Agents**:
    - **brave**: "search brave for X", "find X online" (Privacy focus)
    - **googlesearch**: "google X", "search internet for X" (General focus)
    - Use these for external knowledge, current events, or documentation.

    **Filesystem Agent**:
    - "List files in directory", "Read file X", "Cat file Y"
    
    **Analytics Agent**:
    - "Show website traffic", "User count for last week"
    
    **Puppeteer Agent**:
    - "Take screenshot of google.com", "Browser automation"
    
    **Sequential Agent**:
    - "Think step by step", "Plan a complex solution"
    
    **Code Execution Agent**:
    - "Calculate fibonacci", "Run python script", "Solve math problem"
    
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
    table_id=config.BQ_ANALYTICS_TABLE,
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
    project_id: Optional[str] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a user request through the orchestrator
    
    Args:
        prompt: User's natural language request
        user_email: User's email address
        project_id: Optional GCP project ID
        auth_token: Optional OAuth token
    
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
            project_id=project_id or config.GCP_PROJECT_ID,
            auth_token=auth_token
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
    project_id: Optional[str] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronous wrapper for process_request_async
    
    Args:
        prompt: User's natural language request
        user_email: User's email address
        project_id: Optional GCP project ID
        auth_token: Optional OAuth token
    
    Returns:
        Dictionary with response and metadata
    """
    return asyncio.run(process_request_async(prompt, user_email, project_id, auth_token))


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
