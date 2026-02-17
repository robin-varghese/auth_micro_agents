"""
Orchestrator ADK - Routing and Execution Logic
"""
import requests
import json
import logging
import time
from typing import Dict, Any, Optional

from config import config
from structured_logging import propagate_request_id
from registry import get_agent_by_id
from context import _redis_publisher_ctx, _report_progress

logger = logging.getLogger(__name__)

async def route_to_agent(target_agent: str, prompt: str, user_email: str, project_id: str = None, auth_token: str = None, session_id: str = None) -> Dict[str, Any]:
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
                 "user_request": prompt, 
                 "user_email": user_email,
                 "session_id": session_id # Pass session to MATS
             }
             
        # 2. Dynamic Routing for Sub-Agents (APISIX)
        elif agent_def:
             source_path = agent_def.get("_source_path", "")
             # Convention: sub_agents/gcloud_agent_adk -> agent/gcloud/execute
             parts = source_path.split('/')
             if len(parts) > 1 and parts[-1].endswith("_agent_adk"):
                 short_name = parts[-1].replace("_agent_adk", "")
                 endpoint = f"{config.APISIX_URL}/agent/{short_name}/execute"
             elif len(parts) > 1 and parts[-1].startswith("mats-") and parts[-1].endswith("-agent"):
                 short_name = parts[-1].replace("mats-", "").replace("-agent", "")
                 endpoint = f"{config.APISIX_URL}/agent/{short_name}/execute"
             else:
                 pass
                 
             payload = {
                "prompt": prompt,
                "user_email": user_email,
                "session_id": session_id # Pass session to Sub-Agent
             }
             if project_id:
                payload["project_id"] = project_id
        
        if not endpoint:
            # Fallback for legacy specific IDs if they exist in APISIX map and registry convention fails
            # (Keeping old map as fallback if registry lookup fails)
            agent_endpoints = {
                'gcloud': f"{config.APISIX_URL}/agent/gcloud/execute",
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
                response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
                
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

async def chain_screenshot_upload(
    agent_response: Dict[str, Any],
    user_email: str,
    project_id: str = None,
    auth_token: str = None,
    session_id: str = None
) -> Dict[str, Any]:
    """
    Check for screenshot files in response and auto-upload to GCS.
    """
    if not agent_response.get("success"):
        return agent_response
        
    final_response = agent_response.get("data", {})
    # Extract text if nested
    text_response = final_response
    if isinstance(final_response, dict):
        text_response = final_response.get("response", str(final_response))
        if isinstance(text_response, dict):
            text_response = text_response.get("response", str(text_response))
            
    # Check for screenshot trigger
    if "File Name:" in str(text_response):
        try:
            import re
            filename_match = re.search(r"File Name:\s*([a-zA-Z0-9_.-]+\.png)", str(text_response))
            if filename_match:
                filename = filename_match.group(1)
                bucket_name = "finoptiagents_puppeteer_screenshots"
                upload_prompt = f"Upload /projects/{filename} to bucket {bucket_name} as screenshots/{filename}. Please provide a secure HTTPS access URL in your response."
                
                await _report_progress(f"Auto-uploading screenshot {filename} to GCS...", event_type="STATUS_UPDATE", icon="☁️")
                
                upload_response = await route_to_agent(
                    target_agent="storage_specialist",
                    prompt=upload_prompt,
                    user_email=user_email,
                    project_id=project_id,
                    auth_token=auth_token,
                    session_id=session_id
                )
                
                if upload_response.get("success"):
                    upload_data = upload_response.get("data", {})
                    upload_text = upload_data.get("response", str(upload_data)) if isinstance(upload_data, dict) else str(upload_data)
                    
                    links_text = ""
                    if isinstance(upload_data, dict):
                         signed_url = upload_data.get("signed_url")
                         if signed_url:
                             links_text = f"\n\n**Secure Access Link (Valid for 60m):**\n[View Screenshot]({signed_url})"
                    
                    # Update the response text with upload info
                    new_text = f"{text_response}\n\n---\n**GCS Upload Status:**\n{upload_text}{links_text}"
                    
                    # Return updated response structure
                    return {
                        "success": True,
                        "data": {"response": new_text},
                        "agent": agent_response.get("agent")
                    }
                else:
                    new_text = f"{text_response}\n\n---\n**GCS Upload Warning:** Failed to auto-upload to GCS: {upload_response.get('error')}"
                    return {
                        "success": True,
                        "data": {"response": new_text},
                        "agent": agent_response.get("agent")
                    }
        except Exception as chain_err:
            logger.error(f"Error in screenshot chaining: {chain_err}")
            
    return agent_response
