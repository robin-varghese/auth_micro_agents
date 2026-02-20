"""
MATS Orchestrator - Delegation Tools

HTTP-based delegation to Team Lead agents (SRE, Investigator, Architect).
"""
import asyncio
import aiohttp
import os
import logging
from utils.tracing import trace_span
from typing import Dict, Any
from pydantic import ValidationError

from schemas import SREOutput, InvestigatorOutput, ArchitectOutput
from retry import retry_async, NonRetryableError
from error_codes import ErrorCode, execute_recovery
from planner import CLOUD_ISSUE_TAXONOMY

logger = logging.getLogger(__name__)

# Service URLs from environment
SRE_AGENT_URL = os.getenv("SRE_AGENT_URL", "http://mats-sre-agent:8081")
INVESTIGATOR_AGENT_URL = os.getenv("INVESTIGATOR_AGENT_URL", "http://mats-investigator-agent:8082")
ARCHITECT_AGENT_URL = os.getenv("ARCHITECT_AGENT_URL", "http://mats-architect-agent:8083")
GCLOUD_AGENT_URL = os.getenv("GCLOUD_AGENT_URL", "http://finopti-gcloud-agent:5001")


async def _http_post(url: str, data: Dict[str, Any], headers: Dict[str, str] = None, timeout: int = 900) -> Dict[str, Any]:
    """
    Make HTTP POST request with error handling.
    
    Raises:
        NonRetryableError: For 4xx HTTP errors
        Exception: For 5xx HTTP errors or timeouts
    """
    import time as _time
    full_url = f"{url}/chat"
    call_start = _time.monotonic()
    logger.info(f"_http_post → {full_url} | payload_keys={list(data.keys())} | timeout={timeout}s")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                full_url,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                elapsed = _time.monotonic() - call_start
                if resp.status >= 500:
                    text = await resp.text()
                    logger.error(
                        f"_http_post {full_url}: HTTP {resp.status} server error after {elapsed:.1f}s | "
                        f"body={text[:500]}"
                    )
                    raise Exception(f"HTTP {resp.status}: {text}")

                elif resp.status >= 400:
                    text = await resp.text()
                    logger.warning(
                        f"_http_post {full_url}: HTTP {resp.status} client error after {elapsed:.1f}s | "
                        f"body={text[:500]}"
                    )
                    raise NonRetryableError(f"HTTP {resp.status}: {text}")

                result = await resp.json()
                logger.info(f"_http_post {full_url}: HTTP {resp.status} OK | elapsed={elapsed:.1f}s")
                return result

        except asyncio.TimeoutError:
            elapsed = _time.monotonic() - call_start
            logger.error(
                f"_http_post {full_url}: Timed out after {elapsed:.1f}s (limit={timeout}s)",
                exc_info=True
            )
            raise Exception(f"Request to {url} timed out after {timeout}s")
        except aiohttp.ClientConnectorError as conn_err:
            elapsed = _time.monotonic() - call_start
            logger.error(
                f"_http_post {full_url}: Connection refused/unreachable after {elapsed:.1f}s | "
                f"error={conn_err}",
                exc_info=True
            )
            raise Exception(f"Cannot connect to {url}: {conn_err}")


@trace_span("delegate_sre", kind="AGENT")
async def delegate_to_sre(
    task_description: str,
    project_id: str,
    session_id: str = "unknown",
    job_id: str = None,
    user_email: str = None,
    issue_type: str = "compute"
) -> Dict[str, Any]:
    """
    Delegate task to SRE Agent with cloud-specific context.
    
    Args:
        task_description: What the SRE should investigate
        project_id: GCP project ID
        session_id: Investigation session ID for logging
        job_id: Async Job ID for progress reporting
        user_email: User's email for context
        issue_type: Classified issue type from planner (compute, database, etc.)
        
    Returns:
        SREOutput schema dict
    """
    taxonomy = CLOUD_ISSUE_TAXONOMY.get(issue_type, CLOUD_ISSUE_TAXONOMY["compute"])
    filters_list = "\n".join(f"  - {f}" for f in taxonomy.get("log_filters", []))
    metrics_list = "\n".join(f"  - {m}" for m in taxonomy.get("metrics", []))
    
    prompt = f"""
Project ID: {project_id}
Issue Type: {issue_type}

INVESTIGATION TASK:
{task_description}

RECOMMENDED LOG FILTERS (start with these):
{filters_list}

KEY METRICS TO CHECK:
{metrics_list}

INVESTIGATION PROTOCOL:
1. Run the recommended log filters FIRST to establish the error window
2. Extract the EXACT timestamp of the earliest error occurrence
3. Check if any deployment/config change happened in the 30 min BEFORE that timestamp
4. Collect metric anomalies for the same time window
5. If no errors found with recommended filters, broaden to severity>=WARNING
6. Look for correlating events: IAM changes, scaling events, config updates

CRITICAL: Include the raw log entries (first 3) as evidence. Do not just summarize.

Return your findings in the following JSON format:
{{
    "status": "SUCCESS|PARTIAL|FAILURE",
    "confidence": 0.0-1.0,
    "evidence": {{
        "timestamp": "ISO8601 of earliest error",
        "error_signature": "The exact error message or pattern",
        "stack_trace": "Full stack trace if available",
        "version_sha": "string|null",
        "metric_anomalies": [],
        "raw_log_samples": ["First 3 matching log entries"],
        "correlated_events": ["Any deploy/config/IAM changes near the error window"]
    }},
    "blockers": [],
    "recommendations": []
}}
"""
    
    async def _call():
        import time as _time
        call_start = _time.monotonic()
        logger.info(
            f"[{session_id}] Delegating to SRE → {SRE_AGENT_URL} | "
            f"project={project_id} | issue_type={issue_type} | "
            f"task={task_description[:100]}"
        )
        # Use 300s for SRE as it does heavy lifting
        payload = {"message": prompt, "session_id": session_id, "user_email": user_email}  # Pass session_id and user_email
        if job_id:
            payload["job_id"] = job_id
            payload["orchestrator_url"] = "http://mats-orchestrator:8084" 
        
        # Explicitly pass project_id for context setting
        if project_id:
            payload["project_id"] = project_id
            
        # Inject Trace Headers & Auth
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            try:
                from context import _auth_token_ctx
                token = _auth_token_ctx.get()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except ImportError:
                pass
            payload["headers"] = headers
        except ImportError:
            headers = None

        result = await _http_post(SRE_AGENT_URL, payload, headers=headers, timeout=900)
        response_text = result.get("response", "")
        
        # Try to parse JSON from response
        import json
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text
                
            output_dict = json.loads(json_str)
            
            # Validate against schema
            sre_output = SREOutput(**output_dict)
            elapsed = _time.monotonic() - call_start
            logger.info(
                f"[{session_id}] SRE completed | status={sre_output.status} | "
                f"confidence={sre_output.confidence} | elapsed={elapsed:.1f}s"
            )
            
            final_output = sre_output.dict()
            # Inject execution trace from the raw API response (if present) to propagate to UI
            if "execution_trace" in result:
                final_output["execution_trace"] = result["execution_trace"]
                
            return final_output
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"[{session_id}] SRE output invalid or not JSON: {e}")
            logger.error(f"[{session_id}] Raw SRE response: {response_text[:1000] if response_text else 'EMPTY'}")
            return {
                "status": "FAILURE",
                "confidence": 0.0,
                "evidence": {
                    "timestamp": "N/A",
                    "error_signature": "Invalid Agent Output",
                    "stack_trace": response_text[:500] if response_text else str(e)
                },
                "blockers": ["Agent returned non-JSON response"],
                "recommendations": ["Review agent logs for internal crashes."]
            }
    
    return await retry_async(
        _call,
        max_attempts=2,
        session_id=session_id,
        agent_name="SRE"
    )


@trace_span("delegate_investigator", kind="AGENT")
async def delegate_to_investigator(
    task_description: str,
    sre_context: str,
    repo_url: str,
    session_id: str = "unknown",
    job_id: str = None,
    user_email: str = None
) -> Dict[str, Any]:
    """
    Delegate task to Investigator Agent.
    
    Args:
        task_description: What to investigate
        sre_context: Context from SRE findings
        repo_url: GitHub repository URL
        session_id: Investigation session ID
        job_id: Async Job ID
        
    Returns:
        InvestigatorOutput schema dict
    """
    prompt = f"""
Repository: {repo_url}

SRE Context:
{sre_context}

Task: {task_description}

Please investigate the code and return findings in this JSON format:
{{
    "status": "ROOT_CAUSE_FOUND|HYPOTHESIS|INSUFFICIENT_DATA",
    "confidence": 0.0-1.0,
    "root_cause": {{
        "file": "path",
        "line": 123,
        "function": "function_name",
        "defect_type": "null_check|timeout|race_condition|logic_error|config_error",
        "evidence": "code snippet"
    }},
    "dependency_chain": [],
    "hypothesis": "string if not definitive",
    "blockers": [],
    "recommendations": []
}}
"""
    
    async def _call():
        import time as _time
        call_start = _time.monotonic()
        logger.info(
            f"[{session_id}] Delegating to Investigator → {INVESTIGATOR_AGENT_URL} | "
            f"repo={repo_url} | task={task_description[:80]}"
        )
        payload = {"message": prompt, "session_id": session_id, "user_email": user_email}  # Pass session_id and user_email
        if job_id:
            payload["job_id"] = job_id
            payload["orchestrator_url"] = "http://mats-orchestrator:8084" 
            
        # Inject Trace Headers & Auth
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            try:
                from context import _auth_token_ctx
                token = _auth_token_ctx.get()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except ImportError:
                pass
            payload["headers"] = headers
        except ImportError:
            headers = None
            
        result = await _http_post(INVESTIGATOR_AGENT_URL, payload, headers=headers, timeout=900)
        response_text = result.get("response", "")
        
        import json
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text
                
            output_dict = json.loads(json_str)
            inv_output = InvestigatorOutput(**output_dict)
            elapsed = _time.monotonic() - call_start
            logger.info(
                f"[{session_id}] Investigator completed | status={inv_output.status} | elapsed={elapsed:.1f}s"
            )
            return inv_output.dict()
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"[{session_id}] Investigator output invalid or not JSON: {e}")
            logger.error(f"[{session_id}] Raw Investigator response: {response_text[:1000] if response_text else 'EMPTY'}")
            return {
                "status": "INSUFFICIENT_DATA",
                "confidence": 0.0,
                "root_cause": None,
                "hypothesis": f"Investigator returned invalid output: {response_text[:500] if response_text else str(e)}",
                "blockers": ["Agent returned non-JSON response"],
                "recommendations": ["Check investigator logs for internal errors."]
            }
    
    return await retry_async(
        _call,
        max_attempts=2,
        session_id=session_id,
        agent_name="Investigator"
    )


@trace_span("delegate_architect", kind="AGENT")
async def delegate_to_architect(
    sre_findings: Dict[str, Any],
    investigator_findings: Dict[str, Any],
    session_id: str = "unknown",
    user_request: str = "",
    user_email: str = None
) -> Dict[str, Any]:
    """
    Delegate RCA synthesis to Architect Agent.
    
    Args:
        sre_findings: SRE output
        investigator_findings: Investigator output
        session_id: Investigation session ID
        user_request: Original user query (for context extraction)
        
    Returns:
        ArchitectOutput schema dict
    """
    import json
    
    # Fetch RCA Template
    template_content = None
    try:
        from google.cloud import storage
        def _fetch_template():
             client = storage.Client()
             bucket = client.bucket("rca-reports-mats")
             blob = bucket.blob("rca-templates/RCA-Template-V1.json")
             return blob.download_as_text()
        
        template_content = await asyncio.to_thread(_fetch_template)
        logger.info(f"[{session_id}] Successfully loaded RCA-Template-V1.json from GCS")
    except Exception as e:
        logger.warning(f"[{session_id}] Failed to load RCA template from GCS: {e}")
        # Fallback to standard JSON structure if GCS fails
        template_content = """
{
  "docs": { "title": "RCA Report", "description": "Fallback Template" },
  "metadata": { "incident_id": "UNKNOWN", "status": "Pending" },
  "root_cause_analysis": { "root_cause": "UNKNOWN" },
  "remediation_spec": { "remediation_command": "" }
}
"""

    prompt = f"""
Please synthesize the following investigation reports into a formal Root Cause Analysis document.

CRITICAL: You MUST use the following Session ID for constructing the GCS folder path when calling upload_rca_to_gcs: {session_id}

[ORIGINAL USER REQUEST]
{user_request}

[SRE REPORT]
{json.dumps(sre_findings, indent=2)}

[INVESTIGATOR REPORT]
{json.dumps(investigator_findings, indent=2)}

Generate a complete RCA as a **Valid JSON Object** strictly following the structure defined in the template above.

{template_content}

Also return your final agent response in this specific JSON wrapper:
{{
    "status": "SUCCESS|PARTIAL|FAILURE",
    "confidence": 0.0-1.0,
    "rca_content": (The full RCA JSON Object),
    "rca_url": "The link returned by upload_rca_to_gcs",
    "limitations": [],
    "recommendations": []
}}
"""
    
    async def _call():
        logger.info(f"[{session_id}] Delegating to Architect for RCA synthesis")
        payload = {"message": prompt, "session_id": session_id, "user_email": user_email}  # Pass session_id and user_email
        
        # Inject Trace Headers & Auth
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            try:
                from context import _auth_token_ctx
                token = _auth_token_ctx.get()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except ImportError:
                pass
            payload["headers"] = headers
        except ImportError:
            headers = None

        result = await _http_post(ARCHITECT_AGENT_URL, payload, headers=headers, timeout=900)
        response_text = result.get("response", "")
        
        import json
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text
                
            output_dict = json.loads(json_str)
            arch_output = ArchitectOutput(**output_dict)
            logger.info(f"[{session_id}] Architect completed with status={arch_output.status}")
            return arch_output.dict()
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"[{session_id}] Architect output invalid or not JSON: {e}")
            logger.error(f"[{session_id}] Raw Architect response: {response_text[:1000] if response_text else 'EMPTY'}")
            # If parsing fails, try to extract markdown content directly
            return {
                "status": "PARTIAL",
                "confidence": 0.5,
                "rca_content": response_text if response_text else f"Parsing error: {str(e)}",
                "limitations": ["Output parsing failed, using raw response"],
                "recommendations": ["Check architect logs for internal errors."]
            }
    
    return await retry_async(
        _call,
        max_attempts=2,
        session_id=session_id,
        agent_name="Architect"
    )

@trace_span("delegate_operational", kind="AGENT")
async def delegate_to_operational_agent(
    task_description: str,
    agent_url: str,
    agent_name: str,
    session_id: str = "unknown",
    user_email: str = None
) -> Dict[str, Any]:
    """
    Delegate task to an Operational Agent (GCloud, GitHub, etc.)
    using the standard /execute endpoint.
    
    Args:
        task_description: The prompt/command to execute
        agent_url: Base URL of the agent
        agent_name: Name for logging
        session_id: Investigation session ID
        user_email: User email context
        
    Returns:
        Dict with 'success' and 'response' (or 'output')
    """
    async def _call():
        logger.info(f"[{session_id}] Delegating to {agent_name}: {task_description[:50]}...")
        
        payload = {
            "prompt": task_description,
            "session_id": session_id,
            "user_email": user_email or "unknown"
        }
        
        # Inject Trace Headers
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            try:
                from context import _auth_token_ctx
                token = _auth_token_ctx.get()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except ImportError:
                pass
            # Some agents might check headers directly, others via payload
            # For standard Flask wrapper in gcloud_agent, headers are propagated via request context
            # But we can't easily set headers in _http_post helper without modifying it.
            # However, _http_post uses aiohttp.ClientSession(). It doesn't take custom headers arg.
            # We will rely on payload propagation if supported, or modify _http_post if needed.
            # GCloud agent's main.py checks X-Request-ID, but not W3C traceparent essentially?
            # Actually, `send_message` in agent.py uses InMemoryRunner which creates a new trace?
            # Let's just send the payload.
            payload["headers"] = headers
        except ImportError:
            headers = None

        # Operational agents use /execute endpoint
        # We need to manually construct the URL since _http_post appends /chat
        # So we can't use _http_post directly. We'll duplicate logic briefly or refactor.
        # Let's assume we use _http_post but we need to change the endpoint.
        # Refactor time: Let's just use aiohttp directly here to avoid breaking _http_post
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{agent_url}/execute",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                if resp.status >= 500:
                    text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {text}")
                elif resp.status >= 400:
                    text = await resp.text()
                    raise NonRetryableError(f"HTTP {resp.status}: {text}")
                    
                result = await resp.json()
                return result

    return await retry_async(
        _call,
        max_attempts=1, # Operational commands might not always be safe to retry
        session_id=session_id,
        agent_name=agent_name
    )


@trace_span("delegate_remediation", kind="AGENT")
async def delegate_to_remediation(
    session,
    user_request: str
) -> Dict[str, Any]:
    """
    Delegate fix execution to Remediation Agent.
    
    Args:
        session: InvestigationSession object with context
        user_request: The user's "fix it" command
        
    Returns:
        Remediation agent response
    """
    REMEDIATION_AGENT_URL = os.getenv("REMEDIATION_AGENT_URL", "http://finopti-remediation-agent:8085")
    
    # Extract Context
    rca_doc = ""
    resolution_plan = user_request
    
    if session.architect_output:
        rca_doc = session.architect_output.get("rca_content", "")
    
    # If Resolution Plan isn't explicit, we use the RCA recommendations
    # Remediation Agent parses the RCA anyway.
    
    prompt = f"""
    USER REQUEST: {user_request}
    
    CONTEXT:
    RCA Document provided.
    SESSION_ID: {session.session_id}
    """
    
    async def _call():
        logger.info(f"[{session.session_id}] Delegating to Remediation Agent")
        
        payload = {
            "rca_document": rca_doc,
            "resolution_plan": resolution_plan,
            "session_id": session.session_id,
            "user_email": session.user_id,
            "prompt": prompt
        }
        
        # Inject Trace Headers
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            try:
                from context import _auth_token_ctx
                token = _auth_token_ctx.get()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except ImportError:
                pass
            # Use headers? Remediation Agent is Flask, accepts standard headers?
            # It accepts them via `request.headers` in main.py
            # But we use `aiohttp` in `_http_post` style or direct?
            # Remediation Agent `main.py` uses `request.headers`.
            payload["headers"] = headers
        except ImportError:
            headers = None

        # Direct AIOHTTP call to /execute
        async with aiohttp.ClientSession() as client:
            # We can pass headers here
            async with client.post(
                f"{REMEDIATION_AGENT_URL}/execute",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise Exception(f"Remediation Agent Error {resp.status}: {text}")
                
                return await resp.json()

    return await retry_async(
        _call,
        max_attempts=1,
        session_id=session.session_id,
        agent_name="Remediation"
    )
