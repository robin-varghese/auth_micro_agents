"""
Delegation Tools for MATS Remediation Agent
Pattern B: Native Tools (Delegating via HTTP)
"""
import os
import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional
from common.observability import FinOptiObservability
from context import _session_id_ctx, _user_email_ctx, _auth_token_ctx

logger = logging.getLogger(__name__)

# Agent URLs (from docker-compose env vars)
PUPPETEER_URL = os.getenv("PUPPETEER_AGENT_URL", "http://puppeteer-agent:8080")
GCLOUD_URL = os.getenv("GCLOUD_AGENT_URL", "http://finopti-gcloud-agent:5001")
MONITORING_URL = os.getenv("MONITORING_AGENT_URL", "http://monitoring-agent:8080")
STORAGE_URL = os.getenv("STORAGE_AGENT_URL", "http://storage-agent:8080")
GITHUB_URL = os.getenv("GITHUB_AGENT_URL", "http://github-mcp:8080")

async def _delegate(
    agent_name: str, 
    url: str, 
    payload: Dict[str, Any], 
    endpoint: str = "/execute",
    timeout: int = 600
) -> Dict[str, Any]:
    """Generic HTTP delegation helper with trace propagation."""
    
    # 1. Inject Context
    session_id = _session_id_ctx.get()
    user_email = _user_email_ctx.get()
    auth_token = _auth_token_ctx.get()
    
    payload["session_id"] = session_id
    payload["user_email"] = user_email
    
    # 2. Inject Tracing and Auth
    headers = {}
    if auth_token:
        headers["Authorization"] = auth_token
        
    try:
        FinOptiObservability.inject_trace_to_headers(headers)
    except Exception:
        pass
        
    # Some agents might support headers in payload if not via HTTP headers
    payload["headers"] = headers

    logger.info(f"Delegating to {agent_name} at {url}{endpoint}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{url}{endpoint}",
                json=payload,
                headers=headers, # Standard HTTP propagation
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status >= 500:
                    text = await resp.text()
                    raise Exception(f"{agent_name} Error {resp.status}: {text}")
                
                # Check for 400s but try to parse JSON error first
                try:
                    result = await resp.json()
                except:
                    text = await resp.text()
                    if resp.status >= 400:
                        raise Exception(f"{agent_name} Error {resp.status}: {text}")
                    return {"response": text}
                
                if resp.status >= 400:
                    raise Exception(f"{agent_name} Error: {result.get('error', result)}")
                    
                return result
        except asyncio.TimeoutError:
             raise Exception(f"Timeout waiting for {agent_name}")
        except Exception as e:
             raise Exception(f"Delegation failed: {e}")

async def run_puppeteer_test(scenario: str, url: str) -> Dict[str, Any]:
    """Delegates browser testing to Puppeteer Agent."""
    prompt = f"Navigate to {url} and verify the following scenario: {scenario}. Return a JSON with 'status' (SUCCESS/FAILURE) and 'screenshot_url' if applicable."
    return await _delegate("Puppeteer", PUPPETEER_URL, {"prompt": prompt})

async def apply_gcloud_fix(command: str) -> Dict[str, Any]:
    """Delegates infrastructure fix to GCloud Agent."""
    return await _delegate("GCloud", GCLOUD_URL, {"prompt": command}, endpoint="/execute")

async def check_monitoring(query: str, time_range: str = "5m") -> Dict[str, Any]:
    """Delegates validation to Monitoring Agent."""
    prompt = f"Run this monitoring query and analyze the last {time_range}: {query}"
    return await _delegate("Monitoring", MONITORING_URL, {"prompt": prompt})

async def upload_to_gcs(content: str, filename: str, bucket: str = "finopti-verify-reports") -> str:
    """Delegates report upload to Storage Agent."""
    prompt = f"Upload the following content to bucket '{bucket}' as file '{filename}'. Return the public URL.\n\nCONTENT:\n{content}"
    result = await _delegate("Storage", STORAGE_URL, {"prompt": prompt})
    
    # Extract URL from response text using heuristic or return raw
    if isinstance(result, dict) and "signed_url" in result:
        return result["signed_url"]
    
    response_text = result.get("response", str(result))
    import re
    match = re.search(r"(https://[^\s)]+)", response_text)
    if match:
        return match.group(1)
        
    return response_text
async def upload_file_to_gcs(local_path: str, destination_name: str, bucket: str = "rca-reports-mats") -> str:
    """Delegates local file upload to Storage Agent."""
    prompt = f"Upload the local file '{local_path}' to bucket '{bucket}' as '{destination_name}'. Return the signed URL."
    result = await _delegate("Storage", STORAGE_URL, {"prompt": prompt})
    
    if isinstance(result, dict) and "signed_url" in result:
        return result["signed_url"]
        
    response_text = result.get("response", str(result))
    import re
    match = re.search(r"(https://[^\s)]+)", response_text)
    if match:
        return match.group(1)
        
    return response_text
