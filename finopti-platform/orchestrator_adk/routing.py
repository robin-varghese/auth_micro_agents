"""
Orchestrator ADK - Routing and Execution Logic
"""
import requests
import json
import logging
import time
from typing import Dict, Any, Optional, List

from config import config
from structured_logging import propagate_request_id
from registry import get_agent_by_id
from context import _redis_publisher_ctx, _report_progress, get_session_context, update_session_context

logger = logging.getLogger(__name__)

async def route_to_agent(target_agent: str, prompt: str, user_email: str, project_id: str = None, auth_token: str = None, session_id: str = None) -> Dict[str, Any]:
    """
    ADK tool: Route request to appropriate sub-agent using Master Registry.
    """
    # 0. Self-Routing for Orchestrator Context Updates
    if target_agent in ["finopti_orchestrator", "orchestrator"]:
        # When routing to itself, it usually means the agent is updating context
        # We handle this by returning a status that the agent.py loop can interpret
        return {
            "success": True,
            "response": "Context updated successfully.",
            "self_route": True
        }

    try:
        agent_def = get_agent_by_id(target_agent)
        endpoint = None
        
        # 1. Special Handling for MATS
        if target_agent == "mats-orchestrator":
             # Fetch full context from Redis to ensure all fields are propagated
             context = await get_session_context(session_id)
             
             # Direct internal routing to MATS service
             # Note: MATS requires specific payload structure
             endpoint = "http://mats-orchestrator:8084/troubleshoot"
             payload = {
                 "project_id": context.get("project_id") or project_id or config.GCP_PROJECT_ID,
                 "repo_url": context.get("repo_url") or "https://github.com/robin-varghese/auth_micro_agents", 
                 "user_request": prompt, 
                 "user_email": user_email,
                 "session_id": session_id,
                 # Propagate extra metadata fields
                 "environment": context.get("environment"),
                 "application_name": context.get("application_name"),
                 "repo_branch": context.get("repo_branch"),
                 "github_pat": context.get("github_pat")
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
        http_start = time.time()

        logger.info(
            f"[{session_id}] Routing → {target_agent} | "
            f"endpoint={endpoint} | payload_keys={list(payload.keys())}"
        )

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
                                logger.warning(
                                    f"[{session_id}] {target_agent}: 429 Rate Limit — "
                                    f"waiting {retry_delay:.2f}s (API suggested) | attempt={attempt+1}/{max_retries}"
                                )
                            else:
                                logger.warning(
                                    f"[{session_id}] {target_agent}: 429 Rate Limit — "
                                    f"exponential backoff {retry_delay}s | attempt={attempt+1}/{max_retries}"
                                )
                        except Exception as parse_err:
                            logger.warning(
                                f"[{session_id}] {target_agent}: 429 — could not parse retry-after | "
                                f"backoff={retry_delay}s | parse_error={parse_err}"
                            )

                        time.sleep(retry_delay)
                        continue  # Retry the request
                    else:
                        # Max retries reached, raise the error
                        logger.error(
                            f"[{session_id}] {target_agent}: 429 max retries ({max_retries}) exhausted"
                        )
                        response.raise_for_status()
                else:
                    # Success or non-429 error, break out of retry loop
                    break

            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    retry_delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"[{session_id}] {target_agent}: Timeout on attempt {attempt+1}/{max_retries} — "
                        f"retrying in {retry_delay}s"
                    )
                    time.sleep(retry_delay)
                    continue
                else:
                    elapsed = time.time() - http_start
                    logger.error(
                        f"[{session_id}] {target_agent}: Final timeout after {elapsed:.1f}s — "
                        f"all {max_retries} retries exhausted",
                        exc_info=True
                    )
                    raise
        

        elapsed = time.time() - http_start
        try:
            response.raise_for_status()
            data = response.json()
            logger.info(
                f"[{session_id}] {target_agent}: HTTP {response.status_code} OK | elapsed={elapsed:.1f}s"
            )
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors (4xx, 5xx) — always log body for debugging
            body_snippet = response.text[:500] if response.text else "<empty>"
            logger.error(
                f"[{session_id}] {target_agent}: HTTP {response.status_code} error after {elapsed:.1f}s | "
                f"body={body_snippet}",
                exc_info=True
            )
            try:
                error_data = response.json()
                return {
                    "success": False,
                    "error": error_data.get("message", str(e)),
                    "status_code": response.status_code,
                    "agent": target_agent
                }
            except ValueError:
                return {
                    "success": False,
                    "error": f"Agent request failed with HTTP {response.status_code}: {body_snippet}",
                    "status_code": response.status_code,
                    "agent": target_agent
                }
        except ValueError as e:
            # Handle valid 200 OK but invalid JSON
            body_snippet = response.text[:500] if response.text else "<empty>"
            logger.error(
                f"[{session_id}] {target_agent}: Invalid JSON in response after {elapsed:.1f}s | "
                f"body={body_snippet}"
            )
            return {
                "success": False,
                "error": f"Invalid JSON response from {target_agent}: {body_snippet}",
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
                    logger.warning(
                        f"[{session_id}] MATS job {job_id} poll attempt failed — "
                        f"will retry | error={poll_error}"
                    )
                    continue

            # Timeout after max polls
            logger.error(
                f"[{session_id}] MATS job {job_id} timed out after "
                f"{max_polls * 5}s ({poll_count} polls)"
            )
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
        logger.error(
            f"[{session_id}] route_to_agent → {target_agent}: Unhandled exception | "
            f"error_type={type(e).__name__} | error={e}",
            exc_info=True
        )
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
            logger.error(
                f"[{session_id}] Screenshot upload chain failed | "
                f"error_type={type(chain_err).__name__} | error={chain_err}",
                exc_info=True
            )

    return agent_response

async def list_gcp_projects(user_email: str) -> List[Dict[str, str]]:
    """
    List GCP projects the user has access to.
    Useful for helping the user select a project for troubleshooting.
    """
    await _report_progress(f"Fetching projects for {user_email}...", icon="📋")
    
    endpoint = f"{config.APISIX_URL}/agent/gcloud/execute"
    payload = {
        "prompt": "projects list --format=json",
        "user_email": user_email
    }
    
    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        projects_text = data.get("response", "")
        if isinstance(projects_text, dict):
            projects = projects_text
        else:
            try:
                # Basic cleaning
                if "```json" in str(projects_text):
                    projects_text = str(projects_text).split("```json")[1].split("```")[0].strip()
                projects = json.loads(str(projects_text))
            except (json.JSONDecodeError, TypeError) as parse_err:
                logger.warning(f"list_gcp_projects: could not parse projects JSON — returning empty | error={parse_err}")
                projects = []
                
        return [
            {"name": p.get("name"), "id": p.get("projectId")} 
            for p in projects if isinstance(p, dict)
        ]
    except Exception as e:
        logger.error(f"list_gcp_projects: Failed to list GCP projects | error_type={type(e).__name__} | error={e}", exc_info=True)
        return []
