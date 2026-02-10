"""
Orchestrator ADK Agent - Central Hub with Intelligent Routing
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
import json

from config import config
from structured_logging import propagate_request_id

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize tracing
tracer_provider = register(
    project_name=os.getenv("GCP_PROJECT_ID", "local") + "-orchestrator-adk",
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"),
    set_global_tracer_provider=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# Global Registry Cache
_AGENT_REGISTRY = None

def load_registry(registry_path: str = "master_agent_registry.json") -> List[Dict[str, Any]]:
    """Load the master agent registry, caching it in memory."""
    global _AGENT_REGISTRY
    if _AGENT_REGISTRY:
        return _AGENT_REGISTRY
        
    try:
        current_dir = Path(__file__).parent
        with open(current_dir / registry_path, 'r') as f:
            _AGENT_REGISTRY = json.load(f)
        return _AGENT_REGISTRY
    except Exception as e:
        # Fallback to empty if missing (should not happen in prod)
        print(f"Error loading registry: {e}")
        return []

def get_agent_by_id(agent_id: str) -> Optional[Dict[str, Any]]:
    registry = load_registry()
    for agent in registry:
        if agent['agent_id'] == agent_id:
            return agent
    return None



def detect_intent(prompt: str) -> str:
    """
    Dynamic intent detection based on Master Agent Registry keywords.
    
    Priority:
    1. Simple CRUD operations → route to appropriate agent (bypass MATS)
    2. Troubleshooting requests → route to MATS
    3. Keyword-based scoring → find best matching agent
    4. Default fallback → gcloud
    """
    import re
    import logging
    
    logger = logging.getLogger(__name__)
    registry = load_registry()
    prompt_lower = prompt.lower()
    
    # 0. Detect simple CRUD operations (highest priority - bypass MATS)
    simple_operations = [
        r'\blist\s+(all|my|the)?\s*',
        r'\bshow\s+(all|my|the)?\s*',
        r'\bget\s+(all|my|the)?\s*',
        r'\bcreate\s+a?\s*',
        r'\bdelete\s+a?\s*',
        r'\bupdate\s+a?\s*',
        r'\bdescribe\s+',
        r'\bfind\s+',
    ]
    
    is_simple_operation = any(re.search(pattern, prompt_lower) for pattern in simple_operations)
    
    # 1. Check for explicit MATS triggers (only if NOT a simple operation)
    if not is_simple_operation:
        # MATS triggers - require clear troubleshooting intent with multi-word phrases
        mats_triggers = [
            "troubleshoot",
            "root cause",
            "rca",
            "why is",
            "why did",
            "why does",
            "what caused",
            "find the bug",
            "find the issue",
            "investigate the failure",
            "investigate the error",
            "investigate the crash",
            "investigate the issue",
            "investigate the problem",
            "fix the issue",
            "fix the bug",
            "fix the problem",
            "diagnose the",
            "debug the"
        ]
        
        # Check for MATS triggers
        for trigger in mats_triggers:
            if trigger in prompt_lower:
                logger.info(f"Routing to MATS: matched trigger '{trigger}'")
                return "mats-orchestrator"
    
    # 2. Score based on keywords in registry
    # We prioritize longer matches and exact word matches
    scores = {}
    
    for agent in registry:
        agent_id = agent['agent_id']
        keywords = agent.get('keywords', [])
        score = 0
        
        for k in keywords:
            k_lower = k.lower()
            # Use word boundary matching for better accuracy
            if len(k_lower) <= 3:
                # Short keywords need exact word match
                if re.search(r'\b' + re.escape(k_lower) + r'\b', prompt_lower):
                    score += 2
            else:
                # Longer keywords can match as substring
                if k_lower in prompt_lower:
                    score += 1
                    # Bonus for multi-word concepts ("cloud run", "google cloud")
                    if ' ' in k_lower:
                        score += 2
                        
        scores[agent_id] = score
    
    # Debug logging if enabled
    if os.getenv("DEBUG_ROUTING", "false").lower() == "true":
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        logger.info(f"Routing scores for '{prompt[:50]}...': {sorted_scores}")
    
    # Find winner - require minimum score
    if scores:
        best_agent_id = max(scores, key=scores.get)
        if scores[best_agent_id] >= 1:  # At least 1 keyword match required
            logger.info(f"Routing to {best_agent_id} (score: {scores[best_agent_id]})")
            return best_agent_id
    
    # Default fallback
    logger.info(f"Routing to default: gcloud_infrastructure_specialist")
    return "gcloud_infrastructure_specialist"


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
    ADK tool: Route request to appropriate sub-agent using Master Registry.
    """
    try:
        agent_def = get_agent_by_id(target_agent)
        endpoint = None
        
        # 1. Special Handling for MATS
        if target_agent == "mats-orchestrator":
             # Direct internal routing to MATS service
             # Note: MATS requires specific payload structure
             endpoint = "http://mats-orchestrator:8084/troubleshoot"
             payload = {
                 "project_id": project_id or config.GCP_PROJECT_ID,
                 "repo_url": "https://github.com/robin-varghese/auth_micro_agents", # Default for this env
                 "user_request": prompt, # Updated from logic
                 "user_email": user_email
             }
             
        # 2. Dynamic Routing for Sub-Agents (APISIX)
        elif agent_def:
             source_path = agent_def.get("_source_path", "")
             # Convention: sub_agents/gcloud_agent_adk -> agent/gcloud/execute
             parts = source_path.split('/')
             if len(parts) > 1 and parts[-1].endswith("_agent_adk"):
                 short_name = parts[-1].replace("_agent_adk", "")
                 endpoint = f"{config.APISIX_URL}/agent/{short_name}/execute"
             else:
                 # Fallback/Edge cases (maybe exact match needed or manual mapping if convention fails)
                 # For now, log warning or fail
                 pass
                 
             payload = {
                "prompt": prompt,
                "user_email": user_email
             }
             if project_id:
                payload["project_id"] = project_id
        
        if not endpoint:
            # Fallback for legacy specific IDs if they exist in APISIX map and registry convention fails
            # (Keeping old map as fallback if registry lookup fails)
            agent_endpoints = {
                'gcloud': f"{config.APISIX_URL}/agent/gcloud/execute",
                # ... (can rely on dynamic logic mostly now)
            }
            return {
                "success": False,
                "error": f"Could not determine endpoint for agent: {target_agent}"
            }
        
        # Call sub-agent via APISIX/Internal with retry logic
        headers = {"Content-Type": "application/json"}
        headers = propagate_request_id(headers)

        
        # --- Propagate Auth Token ---
        if auth_token:
            headers['Authorization'] = auth_token
        # ----------------------------
        
        # Retry configuration
        max_retries = 3
        base_delay = 2  # Base delay in seconds
        timeout = 1800
        
        # Retry loop with exponential backoff
        for attempt in range(max_retries + 1):
            try:
                response =requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
                
                # If we get a 429, extract retry delay and implement backoff
                if response.status_code == 429:
                    if attempt < max_retries:
                        # Try to extract retry delay from error response
                        retry_delay = base_delay * (2 ** attempt)  # Exponential: 2s, 4s, 8s
                        
                        try:
                            error_data = response.json()
                            error_message = error_data.get('error', {}).get('message', '')
                            
                            # Extract "Please retry in X.XXs" from error message
                            import re
                            match = re.search(r'Please retry in ([\d.]+)s', error_message)
                            if match:
                                retry_delay = float(match.group(1))
                                print(f"[Retry {attempt + 1}/{max_retries}] 429 Rate Limit - Waiting {retry_delay:.2f}s as suggested by API...")
                            else:
                                print(f"[Retry {attempt + 1}/{max_retries}] 429 Rate Limit - Using exponential backoff: {retry_delay}s")
                        except:
                            print(f"[Retry {attempt + 1}/{max_retries}] 429 Rate Limit - Using exponential backoff: {retry_delay}s")
                        
                        import time
                        time.sleep(retry_delay)
                        continue  # Retry the request
                    else:
                        # Max retries reached, raise the error
                        response.raise_for_status()
                else:
                    # Success or non-429 error, break out of retry loop
                    break
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    retry_delay = base_delay * (2 ** attempt)
                    print(f"[Retry {attempt + 1}/{max_retries}] Timeout - Retrying in {retry_delay}s...")
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    raise
        
        
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

        # Special handling for MATS async job responses
        if target_agent == "mats-orchestrator" and "job_id" in data:
            import time
            job_id = data["job_id"]
            poll_endpoint = f"http://mats-orchestrator:8084/jobs/{job_id}"
            
            # Poll for completion (max 30 minutes)
            max_polls = 360  # 360 * 5s = 30 minutes
            poll_count = 0
            
            while poll_count < max_polls:
                time.sleep(5)  # Poll every 5 seconds
                poll_count += 1
                
                try:
                    poll_response = requests.get(poll_endpoint, headers=headers, timeout=10)
                    poll_response.raise_for_status()
                    poll_data = poll_response.json()
                    
                    status = poll_data.get("status", "UNKNOWN")
                    
                    if status in ["COMPLETED", "FAILED", "PARTIAL"]:
                        # Job finished - return final result
                        result = poll_data.get("result", {})
                        
                        if status == "COMPLETED":
                            return {
                                "success": True,
                                "data": result,
                                "agent": target_agent
                            }
                        else:
                            error_msg = result.get("error", f"MATS job failed with status: {status}")
                            return {
                                "success": False,
                                "error": error_msg,
                                "agent": target_agent
                            }
                    
                except Exception as poll_error:
                    # Polling error - continue trying
                    logger.warning(f"MATS job polling error: {str(poll_error)}")
                    continue
            
            # Timeout after max polls
            return {
                "success": False,
                "error": f"MATS job timed out after {max_polls * 5} seconds",
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
    
    **MATS Orchestrator** - Use ONLY for complex troubleshooting and root cause analysis:
    - "Why did X fail?" (causality questions)
    - "Debug this error in Y" (specific error investigation)
    - "Find the root cause of the crash" (explicit RCA)
    - "Troubleshoot the deployment failure" (multi-step diagnosis)
    - "What caused the outage?" (incident analysis)
    - "Investigate the failure/error/crash" (specific problem investigation)
    
    **DO NOT use MATS for simple operations**:
    - ❌ "List VMs", "Show buckets", "Get logs" → Use specific agents instead
    - ❌ "Create instance", "Delete bucket" → Use gcloud/storage agents
    - ❌ "What are my resources?" → Use gcloud agent
    - ❌ Generic "investigate" without failure context → Use appropriate agent
    
    **Key Rules:**
    1. "operations in GCP/cloud/project" → **gcloud** (NEVER github)
    2. Mention of "project ID" or "GCP Project" → **gcloud**
    3. "GitHub repos/code" → **github**  
    4. "troubleshoot/debug/fix" complex issues → **mats-orchestrator**
    5. Default for infrastructure → **gcloud**
    
    WARNING: Do NOT route "cloud project" or "project operations" to the github agent. The github agent only handles code repositories on github.com. GCP operations like "list operations" MUST go to gcloud.
    
    Authorization is handled separately via OPA before you receive requests.
    """,
    tools=[route_to_agent]
)

# Helper to create app per request
def create_app():
    # Ensure API Key is in environment for GenAI library
    if config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    # Configure BigQuery Analytics Plugin
    bq_config = BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true"
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
        # Create App per request
        app = create_app()

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
        if not agent_response.get('success', False):
            error_msg = agent_response.get('error', 'Unknown sub-agent error')
            return {
                "error": True,
                "message": f"Agent {target_agent} failed: {error_msg}",
                "orchestrator": {
                    "user_email": user_email,
                    "target_agent": target_agent,
                    "authorized": True
                }
            }

        response_data = agent_response.get('data', {})

        # Extract the actual agent response text if it's nested
        agent_text_response = response_data
        if isinstance(response_data, dict):
            # Try to extract nested response text
            if 'response' in response_data:
                agent_text_response = response_data['response']
                # Handle nested response.response structure
                if isinstance(agent_text_response, dict) and 'response' in agent_text_response:
                    agent_text_response = agent_text_response['response']

        # Return human-readable response with minimal metadata
        final_response = agent_text_response

        # --- AUTOMATIC SCREENSHOT UPLOAD CHAINING ---
        if target_agent == "browser_automation_specialist" and "File Name:" in str(final_response):
            try:
                import re
                filename_match = re.search(r"File Name:\s*([a-zA-Z0-9_.-]+\.png)", str(final_response))
                if filename_match:
                    filename = filename_match.group(1)
                    # Explicitly mention bucket and request links
                    bucket_name = "finoptiagents_puppeteer_screenshots"
                    upload_prompt = f"Upload /projects/{filename} to bucket {bucket_name} as screenshots/{filename}. Please provide a secure HTTPS access URL in your response."
                    print(f"[Orchestrator] Auto-uploading screenshot {filename} to GCS bucket {bucket_name}...")
                    
                    upload_response = await route_to_agent(
                        target_agent="storage_specialist",
                        prompt=upload_prompt,
                        user_email=user_email,
                        project_id=project_id or config.GCP_PROJECT_ID,
                        auth_token=auth_token
                    )
                    
                    if upload_response.get("success"):
                        upload_data = upload_response.get("data", {})
                        # Support both direct text and structured data
                        upload_text = upload_data.get("response", str(upload_data)) if isinstance(upload_data, dict) else str(upload_data)
                        
                        # Structured extraction for the Secure Access Link (Signed URL)
                        links_text = ""
                        if isinstance(upload_data, dict):
                             signed_url = upload_data.get("signed_url")
                             if signed_url:
                                 links_text = f"\n\n**Secure Access Link (Valid for 60m):**\n[View Screenshot]({signed_url})"
                        
                        final_response = f"{final_response}\n\n---\n**GCS Upload Status:**\n{upload_text}{links_text}"
                    else:
                        final_response = f"{final_response}\n\n---\n**GCS Upload Warning:** Failed to auto-upload to GCS: {upload_response.get('error')}"
            except Exception as chain_err:
                print(f"[Orchestrator] Error in screenshot chaining: {chain_err}")
        # --------------------------------------------

        return {
            "success": True,
            "response": final_response,
            "orchestrator": {
                "target_agent": target_agent
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
        
        # Load registry for test
        print(f"Loading registry... {len(load_registry())} agents found.")
        
        # When running locally on host, 'http://opa:8181' (docker DNS) won't resolve.
        # If OPA_URL is the default docker value, override to localhost for testing.
        current_opa = config.OPA_URL
        if "opa:8181" in current_opa or not current_opa:
             print(f"Note: Overriding OPA_URL from '{current_opa}' to 'http://localhost:8181' for local testing.")
             config.OPA_URL = "http://localhost:8181"
            
        result = process_request(prompt, user_email, config.GCP_PROJECT_ID)
        
        import json
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python agent.py <user_email> <prompt>")
        print("Example: python agent.py admin@example.com 'list all VMs'")
