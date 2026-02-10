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

logger = logging.getLogger(__name__)

# Service URLs from environment
SRE_AGENT_URL = os.getenv("SRE_AGENT_URL", "http://mats-sre-agent:8081")
INVESTIGATOR_AGENT_URL = os.getenv("INVESTIGATOR_AGENT_URL", "http://mats-investigator-agent:8082")
ARCHITECT_AGENT_URL = os.getenv("ARCHITECT_AGENT_URL", "http://mats-architect-agent:8083")


async def _http_post(url: str, data: Dict[str, Any], timeout: int = 900) -> Dict[str, Any]:
    """
    Make HTTP POST request with error handling.
    
    Raises:
        NonRetryableError: For 4xx HTTP errors
        RetryableError: For 5xx HTTP errors
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{url}/chat",
                json=data,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status >= 500:
                    text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {text}")
                    
                elif resp.status >= 400:
                    text = await resp.text()
                    raise NonRetryableError(f"HTTP {resp.status}: {text}")
                    
                result = await resp.json()
                return result
                
        except asyncio.TimeoutError:
            raise Exception(f"Request to {url} timed out after {timeout}s")


@trace_span("delegate_sre", kind="AGENT")
async def delegate_to_sre(
    task_description: str,
    project_id: str,
    session_id: str = "unknown",
    job_id: str = None
) -> Dict[str, Any]:
    """
    Delegate task to SRE Agent.
    
    Args:
        task_description: What the SRE should investigate
        project_id: GCP project ID
        session_id: Investigation session ID for logging
        job_id: Async Job ID for progress reporting
        
    Returns:
        SREOutput schema dict
        
    Raises:
        ValidationError: If output doesn't match schema
    """
    prompt = f"""
Project ID: {project_id}

Task: {task_description}

Please analyze the logs and metrics. Return your findings in the following JSON format:
{{
    "status": "SUCCESS|PARTIAL|FAILURE",
    "confidence": 0.0-1.0,
    "evidence": {{
        "timestamp": "ISO8601",
        "error_signature": "string",
        "stack_trace": "string",
        "version_sha": "string|null",
        "metric_anomalies": []
    }},
    "blockers": [],
    "recommendations": []
}}
"""
    
    async def _call():
        logger.info(f"[{session_id}] Delegating to SRE: {task_description[:100]}")
        # Use 300s for SRE as it does heavy lifting
        payload = {"message": prompt, "session_id": session_id}  # Pass session_id for Phoenix grouping
        if job_id:
            payload["job_id"] = job_id
            payload["orchestrator_url"] = "http://mats-orchestrator:8084" 
        
        # Explicitly pass project_id for context setting
        if project_id:
            payload["project_id"] = project_id
            
        # Inject Trace Headers
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            payload["headers"] = headers
        except ImportError:
            pass

        result = await _http_post(SRE_AGENT_URL, payload, timeout=600)
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
            logger.info(f"[{session_id}] SRE completed with status={sre_output.status}, confidence={sre_output.confidence}")
            
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
    job_id: str = None
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
        logger.info(f"[{session_id}] Delegating to Investigator")
        payload = {"message": prompt, "session_id": session_id}  # Pass session_id for Phoenix grouping
        if job_id:
            payload["job_id"] = job_id
            payload["orchestrator_url"] = "http://mats-orchestrator:8084" 
            
        # Inject Trace Headers
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            payload["headers"] = headers
        except ImportError:
            pass
            
        result = await _http_post(INVESTIGATOR_AGENT_URL, payload, timeout=900)
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
            logger.info(f"[{session_id}] Investigator completed with status={inv_output.status}")
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
    user_request: str = ""
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
    
    prompt = f"""
Please synthesize the following investigation reports into a formal Root Cause Analysis document.

[ORIGINAL USER REQUEST]
{user_request}

[SRE REPORT]
{json.dumps(sre_findings, indent=2)}

[INVESTIGATOR REPORT]
{json.dumps(investigator_findings, indent=2)}

Generate a complete RCA markdown document with these sections:
## 1. Executive Summary
## 2. Timeline & Detection
## 3. Root Cause
## 4. Recommended Fix
## 5. Prevention Plan
## 6. Known Limitations

Also return your response in this JSON format:
{{
    "status": "SUCCESS|PARTIAL|FAILURE",
    "confidence": 0.0-1.0,
    "rca_content": "full markdown content",
    "rca_url": "The link returned by upload_rca_to_gcs",
    "limitations": [],
    "recommendations": []
}}
"""
    
    async def _call():
        logger.info(f"[{session_id}] Delegating to Architect for RCA synthesis")
        payload = {"message": prompt, "session_id": session_id}  # Pass session_id for Phoenix grouping
        
        # Inject Trace Headers
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            payload["headers"] = headers
        except ImportError:
            pass

        result = await _http_post(ARCHITECT_AGENT_URL, payload, timeout=900)
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
