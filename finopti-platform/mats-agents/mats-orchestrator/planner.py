"""
MATS Orchestrator - Plan Generation

Enhanced with Cloud Issue Taxonomy and Sequential Thinking integration.
Classifies incidents by GCP service type and generates targeted investigation
plans with service-specific log filters and metrics.
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from config import config

logger = logging.getLogger(__name__)


# ============================================================================
# CLOUD ISSUE TAXONOMY
# Maps issue categories to GCP-specific investigation strategies
# ============================================================================

CLOUD_ISSUE_TAXONOMY = {
    "compute": {
        "keywords": [
            "cloud run", "gce", "vm", "instance", "container", "oom", "crash",
            "cold start", "memory", "cpu", "revision", "scaling", "startup",
            "readiness", "liveness", "probe", "restart", "kill"
        ],
        "sre_strategy": (
            "Check resource.type=cloud_run_revision or gce_instance. "
            "Filter crash loops, OOM kills, readiness/liveness probe failures. "
            "Correlate with deployment timestamps to identify regressions. "
            "Check instance scaling events and cold start latency."
        ),
        "log_filters": [
            'severity>=ERROR',
            'resource.type="cloud_run_revision"',
            'textPayload=~"OOMKilled|CrashLoopBackOff|ContainerKilled"',
            'labels."run.googleapis.com/execution_environment"'
        ],
        "metrics": [
            "run.googleapis.com/container/cpu/utilizations",
            "run.googleapis.com/container/memory/utilizations",
            "run.googleapis.com/container/startup_latencies",
            "run.googleapis.com/container/instance_count"
        ],
        "check_config_changes": True,
        "check_recent_deploys": True
    },
    "database": {
        "keywords": [
            "cloud sql", "alloydb", "spanner", "postgres", "mysql", "timeout",
            "connection", "deadlock", "slow query", "replication", "lag",
            "pool", "max_connections", "lock", "transaction", "sql"
        ],
        "sre_strategy": (
            "Check cloudsql.googleapis.com logs. Look for connection pool exhaustion, "
            "lock wait timeouts, replication lag, and max_connections errors. "
            "Correlate with CPU/memory utilization spikes. Check for long-running "
            "transactions and deadlock cycles. Examine if recent schema changes "
            "or index drops caused query plan regressions."
        ),
        "log_filters": [
            'resource.type="cloudsql_database"',
            'severity>=WARNING',
            'textPayload=~"deadlock|timeout|max_connections|lock wait|replication"',
            'protoPayload.methodName=~"cloudsql"'
        ],
        "metrics": [
            "cloudsql.googleapis.com/database/cpu/utilization",
            "cloudsql.googleapis.com/database/memory/utilization",
            "cloudsql.googleapis.com/database/network/connections",
            "cloudsql.googleapis.com/database/replication/replica_lag",
            "cloudsql.googleapis.com/database/disk/utilization"
        ],
        "check_config_changes": True,
        "check_recent_deploys": False
    },
    "networking": {
        "keywords": [
            "load balancer", "dns", "ssl", "certificate", "502", "503", "504",
            "timeout", "latency", "vpc", "firewall", "ingress", "egress",
            "http", "https", "backend", "health check", "neg", "cdn"
        ],
        "sre_strategy": (
            "Check httpRequest.status in Load Balancer logs. Correlate with "
            "backend health check status transitions. Look for SSL certificate "
            "expiry warnings. Check NEG health status and firewall rule changes. "
            "For 502s, check if backends are healthy. For 504s, check backend "
            "response latencies vs timeout config."
        ),
        "log_filters": [
            'resource.type="http_load_balancer"',
            'httpRequest.status>=500',
            'resource.type="gce_network"',
            'jsonPayload.connection.disposition!="allowed"'
        ],
        "metrics": [
            "loadbalancing.googleapis.com/https/backend_latencies",
            "loadbalancing.googleapis.com/https/request_count",
            "loadbalancing.googleapis.com/https/backend_request_count",
            "loadbalancing.googleapis.com/https/total_latencies"
        ],
        "check_config_changes": True,
        "check_recent_deploys": False
    },
    "iam_auth": {
        "keywords": [
            "permission", "denied", "403", "iam", "role", "service account",
            "oauth", "token", "unauthorized", "access", "policy", "binding",
            "impersonate", "workload identity", "credentials"
        ],
        "sre_strategy": (
            "Check Admin Activity audit logs (protoPayload.methodName). Look for "
            "recent SetIamPolicy changes that may have revoked access. Compare "
            "denied principal against current IAM bindings. Check if service "
            "account keys expired or were rotated. For Workload Identity issues, "
            "verify the KSA-to-GSA binding."
        ),
        "log_filters": [
            'logName:"cloudaudit.googleapis.com"',
            'protoPayload.status.code=7',
            'protoPayload.methodName=~"SetIamPolicy|CreateServiceAccount"',
            'severity>=WARNING'
        ],
        "metrics": [
            "iam.googleapis.com/service_account/authn_events_count"
        ],
        "check_config_changes": True,
        "check_recent_deploys": False
    },
    "deployment": {
        "keywords": [
            "deploy", "build", "cloud build", "rollback", "revision", "canary",
            "traffic split", "artifact registry", "docker", "image", "tag",
            "pipeline", "ci/cd", "failed build"
        ],
        "sre_strategy": (
            "Check Cloud Build logs for build failures. Examine revision traffic "
            "splits to identify if a bad revision is receiving traffic. Correlate "
            "error onset timestamp with deployment timestamps. Look for container "
            "image pull failures and Artifact Registry permission issues."
        ),
        "log_filters": [
            'resource.type="build"',
            'resource.type="cloud_run_revision"',
            'severity>=ERROR',
            'textPayload=~"ImagePullBackOff|ErrImagePull|build failed"'
        ],
        "metrics": [
            "run.googleapis.com/container/instance_count",
            "cloudbuild.googleapis.com/build/count"
        ],
        "check_config_changes": False,
        "check_recent_deploys": True
    },
    "storage": {
        "keywords": [
            "gcs", "bucket", "storage", "upload", "download", "signed url",
            "cors", "object", "blob", "lifecycle", "retention"
        ],
        "sre_strategy": (
            "Check GCS audit logs for access denials. Look for bucket policy "
            "changes (uniform bucket-level access transitions), CORS misconfigurations "
            "for web apps, and lifecycle policy deleting objects unexpectedly. "
            "Check if signed URL generation uses the correct service account."
        ),
        "log_filters": [
            'resource.type="gcs_bucket"',
            'protoPayload.methodName=~"storage.objects"',
            'protoPayload.status.code!=0',
            'severity>=WARNING'
        ],
        "metrics": [
            "storage.googleapis.com/api/request_count",
            "storage.googleapis.com/network/received_bytes_count"
        ],
        "check_config_changes": True,
        "check_recent_deploys": False
    },
    "monitoring_alerting": {
        "keywords": [
            "alert", "uptime", "slo", "sli", "error budget", "notification",
            "incident", "pagerduty", "opsgenie", "monitoring", "metric"
        ],
        "sre_strategy": (
            "Check which alerting policy fired and its condition threshold. "
            "Verify if the underlying metric actually breached SLO or if it's a "
            "false positive due to metric collection gaps. Look at the uptime "
            "check results for the time window."
        ),
        "log_filters": [
            'resource.type="metric"',
            'severity>=ERROR',
            'logName:"monitoring.googleapis.com"'
        ],
        "metrics": [
            "monitoring.googleapis.com/uptime_check/check_passed"
        ],
        "check_config_changes": False,
        "check_recent_deploys": False
    }
}


def classify_issue(user_request: str) -> Tuple[str, Dict[str, Any]]:
    """Classify the user's issue into a cloud issue category.
    
    Uses keyword matching with scoring to determine the most likely
    issue type. Falls back to 'compute' (most common) if no match.
    
    Args:
        user_request: The user's raw problem description
        
    Returns:
        Tuple of (issue_type_key, taxonomy_dict)
    """
    request_lower = user_request.lower()
    scores = {}
    
    for category, taxonomy in CLOUD_ISSUE_TAXONOMY.items():
        score = sum(1 for kw in taxonomy["keywords"] if kw in request_lower)
        if score > 0:
            scores[category] = score
    
    if scores:
        best = max(scores, key=scores.get)
        logger.info(f"Issue classified as '{best}' (score={scores[best]}, all scores={scores})")
        return best, CLOUD_ISSUE_TAXONOMY[best]
    
    # Default: generic compute investigation
    logger.info("No strong classification match. Defaulting to 'compute'.")
    return "compute", CLOUD_ISSUE_TAXONOMY["compute"]


# ============================================================================
# AGENT REGISTRY
# ============================================================================

def load_agent_registry() -> list:
    """Load agent registry from JSON file."""
    registry_path = Path(__file__).parent / "agent_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            return json.load(f)
    return []


# ============================================================================
# PLAN NORMALIZATION & FALLBACK
# ============================================================================

def _normalize_plan(plan, user_request: str, issue_type: str = "unknown") -> Dict[str, Any]:
    """Normalize plan output from LLM (handles list/dict variants).
    
    Small models sometimes return a list instead of a dict.
    This handles all known edge cases.
    """
    if isinstance(plan, dict):
        # Ensure issue_type is present
        if "issue_type" not in plan:
            plan["issue_type"] = issue_type
        return plan
    
    if isinstance(plan, list):
        logger.warning(f"Plan generation returned a list, attempting to wrap: {str(plan)[:100]}...")
        if len(plan) > 0 and isinstance(plan[0], dict):
            if "step_id" in plan[0]:
                return {
                    "plan_id": "auto-generated",
                    "issue_type": issue_type,
                    "reasoning": "Model returned raw list of steps",
                    "steps": plan
                }
            elif "steps" in plan[0]:
                result = plan[0]
                result["issue_type"] = issue_type
                return result
    
    return _fallback_plan(user_request, "Unknown plan format", issue_type)


def _fallback_plan(user_request: str, reason: str = "planning error", issue_type: str = "compute") -> Dict[str, Any]:
    """Generate a safe fallback 3-step plan with cloud context."""
    taxonomy = CLOUD_ISSUE_TAXONOMY.get(issue_type, CLOUD_ISSUE_TAXONOMY["compute"])
    
    return {
        "plan_id": "fallback-001",
        "issue_type": issue_type,
        "reasoning": f"Using default 3-step investigation due to {reason}",
        "steps": [
            {
                "step_id": 1,
                "assigned_lead": "sre",
                "task": f"Analyze logs for: {user_request}. {taxonomy['sre_strategy']}",
                "ui_label": "Investigating Logs & Metrics",
                "expected_output": "Error signatures, timestamps, metric anomalies",
                "suggested_filters": taxonomy["log_filters"]
            },
            {
                "step_id": 2,
                "assigned_lead": "investigator",
                "task": "Analyze code based on SRE findings. Trace the error path and identify the defect.",
                "ui_label": "Analyzing Code",
                "expected_output": "File path, line number, defect type, root cause hypothesis"
            },
            {
                "step_id": 3,
                "assigned_lead": "architect",
                "task": "Generate RCA document with remediation steps",
                "ui_label": "Generating RCA",
                "expected_output": "Complete RCA markdown with fix recommendations"
            }
        ]
    }


# ============================================================================
# SEQUENTIAL THINKING INTEGRATION
# ============================================================================

async def _sequential_decompose(seq_client, user_request: str, issue_type: str, taxonomy: Dict) -> Optional[str]:
    """Use Sequential Thinking MCP to decompose the problem before planning.
    
    The Sequential Thinking tool breaks down the problem into logical
    investigation steps, which then feeds into the LLM plan generator
    for a more structured and thorough plan.
    
    Args:
        seq_client: Connected SequentialThinkingClient
        user_request: User's problem description
        issue_type: Classified issue type
        taxonomy: The matching taxonomy dict
        
    Returns:
        Structured decomposition text, or None if unavailable
    """
    if not seq_client:
        return None
    
    try:
        thought_prompt = (
            f"A user reported a cloud infrastructure issue classified as '{issue_type}'. "
            f"Problem: {user_request}\n\n"
            f"Recommended approach: {taxonomy['sre_strategy']}\n"
            f"Available log filters: {taxonomy['log_filters']}\n"
            f"Key metrics: {taxonomy['metrics']}\n\n"
            f"Decompose this into a structured investigation. Think about:\n"
            f"1. What evidence to collect first (most diagnostic value)\n"
            f"2. What correlations to check (time-based, config-based)\n"
            f"3. What hypotheses to test and in what order\n"
            f"4. What red herrings to watch out for in {issue_type} issues"
        )
        
        result = await seq_client.call_tool(
            "sequentialthinking",
            {
                "thought": thought_prompt,
                "thoughtNumber": 1,
                "totalThoughts": 3,
                "nextThoughtNeeded": True
            }
        )
        
        # Collect the thinking chain
        thoughts = [thought_prompt]
        if result and isinstance(result, dict):
            content = result.get("content", [])
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    thoughts.append(item["text"])
        
        # Continue thinking for 2 more rounds
        for i in range(2, 4):
            try:
                continuation = await seq_client.call_tool(
                    "sequentialthinking",
                    {
                        "thought": f"Continue decomposing. Step {i}: What specific checks should the {'SRE' if i == 2 else 'Investigator'} agent perform?",
                        "thoughtNumber": i,
                        "totalThoughts": 3,
                        "nextThoughtNeeded": i < 3
                    }
                )
                if continuation and isinstance(continuation, dict):
                    content = continuation.get("content", [])
                    for item in content:
                        if isinstance(item, dict) and item.get("text"):
                            thoughts.append(item["text"])
            except Exception as e:
                logger.warning(f"Sequential thinking step {i} failed: {e}")
                break
        
        decomposition = "\n\n".join(thoughts[1:])  # Skip the initial prompt
        logger.info(f"Sequential decomposition produced {len(decomposition)} chars")
        return decomposition if decomposition else None
        
    except Exception as e:
        logger.warning(f"Sequential thinking decomposition failed: {e}. Proceeding without it.")
        return None


# ============================================================================
# PLAN GENERATION (MAIN ENTRY POINT)
# ============================================================================

async def generate_plan(
    user_request: str,
    agent_registry: list,
    seq_client=None
) -> Dict[str, Any]:
    """
    Generate a cloud-targeted investigation plan.
    
    Flow:
    1. Classify the issue using CLOUD_ISSUE_TAXONOMY
    2. (Optional) Use Sequential Thinking for structured decomposition
    3. Generate the plan via LLM with cloud-specific context
    
    Args:
        user_request: User's problem description
        agent_registry: List of available agents/capabilities
        seq_client: Optional SequentialThinkingClient for decomposition
        
    Returns:
        Plan dict with issue_type, reasoning, and steps
    """
    # Step 1: Classify the issue
    issue_type, taxonomy = classify_issue(user_request)
    
    # Step 2: Sequential Thinking decomposition (if available)
    decomposition = await _sequential_decompose(seq_client, user_request, issue_type, taxonomy)
    
    # Step 3: Build the planning prompt
    capabilities_summary = "\n".join([
        f"- {agent.get('name') or agent.get('display_name') or agent.get('agent_id', 'Unknown Agent')}: {agent.get('capabilities', 'N/A')}"
        for agent in agent_registry
    ])
    
    decomposition_section = ""
    if decomposition:
        decomposition_section = f"""
STRUCTURED PROBLEM DECOMPOSITION (from Sequential Thinking analysis):
{decomposition}

Use this decomposition to inform your plan. Incorporate its insights into the steps.
"""
    
    prompt = f"""You are a Principal SRE planning a cloud incident investigation.

USER REQUEST: {user_request}

CLASSIFIED ISSUE TYPE: {issue_type}
RECOMMENDED SRE STRATEGY: {taxonomy['sre_strategy']}
SUGGESTED LOG FILTERS: {json.dumps(taxonomy['log_filters'], indent=2)}
KEY METRICS TO CHECK: {json.dumps(taxonomy['metrics'], indent=2)}
CHECK CONFIG CHANGES: {taxonomy.get('check_config_changes', False)}
CHECK RECENT DEPLOYS: {taxonomy.get('check_recent_deploys', False)}
{decomposition_section}
AVAILABLE AGENT CAPABILITIES:
{capabilities_summary}

Create a targeted investigation plan. Structure your steps:
1. EVIDENCE COLLECTION: What specific logs/metrics to query (use the filters above as starting points)
2. CORRELATION: What to cross-reference (deploy times, config changes, traffic patterns)
3. HYPOTHESIS TESTING: If logs point to an app-level issue, what to verify in code
4. SYNTHESIS: Generate RCA with remediation steps

RULES:
- Each step MUST have a specific, actionable task (not "analyze logs" but "query Cloud Run revision logs filtered by severity>=ERROR in the last 2 hours")
- Include the actual GCP log filters in the SRE steps
- If the issue is infrastructure-only (IAM, networking, config), you may skip the code analysis step
- Order steps by diagnostic value (most likely to reveal root cause first)

Output JSON:
{{
    "plan_id": "string",
    "issue_type": "{issue_type}",
    "reasoning": "Why this investigation approach for a {issue_type} issue",
    "steps": [
        {{
            "step_id": 1,
            "assigned_lead": "sre|investigator|architect",
            "task": "Specific, actionable task with actual GCP log filters/commands",
            "ui_label": "Human-readable short label (max 30 chars)",
            "expected_output": "What this step should produce",
            "skip_condition": "When this step can be skipped (optional)"
        }}
    ]
}}"""
    
    try:
        from google import genai
        api_key = None
        if config.GOOGLE_API_KEY and not (config.GOOGLE_GENAI_USE_VERTEXAI and config.GOOGLE_GENAI_USE_VERTEXAI.upper() == "TRUE"):
            api_key = config.GOOGLE_API_KEY
            
        client = genai.Client(api_key=api_key)
        
        logger.info(f"Generating plan for issue_type={issue_type}. Primary model: {config.FINOPTIAGENTS_LLM}")
        
        response = None
        last_error = None
        
        model_list = getattr(config, "FINOPTIAGENTS_MODEL_LIST", [config.FINOPTIAGENTS_LLM])
        
        for model_name in model_list:
            try:
                logger.info(f"Attempting plan generation with model: {model_name}")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                logger.info(f"Plan generation successful with model: {model_name}")
                break
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "Resource exhausted" in err_msg or "Too Many Requests" in err_msg:
                    logger.warning(f"Model {model_name} quota exhausted. Switching to next model...")
                    last_error = e
                    continue
                else:
                    logger.warning(f"Model {model_name} failed with error: {e}. Retrying with next...")
                    last_error = e
                    continue
        
        if not response:
            raise last_error or RuntimeError("All models failed plan generation")
        
        if not response.parsed:
            plan = json.loads(response.text)
        else:
            plan = response.parsed
        
        return _normalize_plan(plan, user_request, issue_type)
        
    except Exception as e:
        logger.error(f"Plan generation failed: {e}")
        return _fallback_plan(user_request, str(e), issue_type)
