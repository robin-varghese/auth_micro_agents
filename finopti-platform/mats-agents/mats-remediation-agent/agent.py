"""
MATS Remediation Agent - Core Logic
Matches AI_AGENT_DEVELOPMENT_GUIDE_V2.0.md
"""
import asyncio
import logging
import json
import re
import os
import datetime
from typing import Dict, Any, Optional

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.genai import types

from observability import setup_observability
from context import _session_id_ctx, _user_email_ctx, _report_progress, _auth_token_ctx, _redis_publisher_ctx
from config import config
from instructions import AGENT_INSTRUCTIONS, AGENT_NAME
from tools import run_puppeteer_test, apply_gcloud_fix, check_monitoring, upload_to_gcs, upload_file_to_gcs

logger = logging.getLogger(__name__)

# 1. Setup Observability
setup_observability()

def extract_remediation_spec(doc: Any) -> Dict[str, Any]:
    """
    Parses the RCA document to extract the remediation spec.
    Supports both JSON (Spec V2) and Regex/Text (Spec V1) formats.
    """
    spec = {}
    
    # Pre-check: Is it already a dict?
    if isinstance(doc, dict):
        if "remediation_spec" in doc:
            return doc["remediation_spec"]
        if "target_url" in doc:
            return doc
        return doc # Return as-is, maybe it's just a flat spec

    # Attempt 1: JSON Parsing (if string)
    if isinstance(doc, str):
        try:
            data = json.loads(doc)
            if isinstance(data, dict):
                if "remediation_spec" in data:
                    return data["remediation_spec"]
                if "target_url" in data:
                    return data
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Attempt 2: Regex Extraction (Legacy Text Format)
        logger.info("JSON parsing failed, attempting regex extraction for legacy RCA.")
        
        patterns = {
            "target_url": r"TARGET_URL:\s*(.+)",
            "remediation_command": r"REMEDIATION_COMMAND:\s*(.+)",
            "validation_query": r"VALIDATION_QUERY:\s*(.+)",
            "reproduction_scenario": r"REPRODUCTION_SCENARIO:\s*(.+)",
            "validation_threshold": r"VALIDATION_THRESHOLD:\s*(.+)"
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, doc)
            if match:
                spec[key] = match.group(1).strip()
            
    return spec

# 2. Define Agent
def create_remediation_agent(model_name=None):
    return Agent(
        name=AGENT_NAME,
        model=model_name or config.FINOPTIAGENTS_LLM,
        instruction=AGENT_INSTRUCTIONS,
        tools=[] # Tools are called via Python logic, not LLM tool use
    )

# 3. Define App
def create_app(model_name=None):
    return App(
        name="mats_remediation_app",
        root_agent=create_remediation_agent(model_name),
        plugins=[ReflectAndRetryToolPlugin()]
    )

# 4. State Machine / Workflow Logic
async def process_remediation_async(rca_document: str, resolution_plan: str, session_id: str = None, user_email: str = None, auth_token: str = None):
    # Context Propagation
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email)
    _auth_token_ctx.set(auth_token)
    
    # Initialize Redis Publisher (Rule 6)
    from redis_common.redis_publisher import RedisEventPublisher
    if RedisEventPublisher:
        try:
            pub = RedisEventPublisher("Remediation Agent", "Remediation")
            _redis_publisher_ctx.set(pub)
        except Exception as e:
            logger.error(f"Failed to initialize RedisEventPublisher: {e}")
    
    await _report_progress("Starting Remediation Workflow...", icon="🛡️")

    workflow_log = []
    
    try:
        # Step 0: Extract Spec
        spec = extract_remediation_spec(rca_document)
        if not spec:
             await _report_progress("Parsing Error: Could not extract remediation spec from RCA.", event_type="ERROR")
             return {"status": "FAILURE", "error": "Missing Remediation Spec"}
             
        # Heuristics for missing fields (backward compat)
        if not spec.get("remediation_command") and resolution_plan:
             spec["remediation_command"] = resolution_plan

        workflow_log.append(f"## Remediation Spec\n```json\n{json.dumps(spec, indent=2)}\n```")
        
        # Step 1: Pre-Verification (Reproduce Issue)
        if spec.get("target_url"):
            await _report_progress("Phase 1: Pre-verification (Puppeteer)...", icon="🧪")
            target_url = spec.get("target_url")
            scenario = spec.get("reproduction_scenario", "Verify broken state")
            
            pre_verify = await run_puppeteer_test(scenario=scenario, url=target_url)
            workflow_log.append(f"## Pre-Verification\nStatus: {pre_verify}")
            
            if pre_verify.get("status") == "SUCCESS":
                 await _report_progress("Wait, the application seems already working?", event_type="THOUGHT")
            
            # Check for screenshots and upload to GCS
            try:
                # Attempt to parse as JSON first
                res_data = {}
                clean_res = str(pre_verify.get("response", ""))
                # Strip markdown blocks if present
                if "```json" in clean_res:
                    clean_res = clean_res.split("```json")[1].split("```")[0].strip()
                
                try:
                    res_data = json.loads(clean_res)
                except: pass

                screenshot_file = res_data.get("screenshot_url")
                if not screenshot_file and "screenshot saved" in clean_res.lower():
                     # Fallback to regex
                     match = re.search(r"at:\s*(/projects/[^ \n]+)", clean_res)
                     if match:
                         local_path = match.group(1)
                     else: local_path = None
                else:
                    if screenshot_file:
                        local_path = f"/projects/{session_id}/{screenshot_file}"
                    else:
                        local_path = None

                if local_path and os.path.exists(local_path):
                    filename = os.path.basename(local_path)
                    await _report_progress(f"Uploading screenshot {filename} to GCS...", icon="☁️")
                    
                    gcs_filename = f"{session_id}/screenshots/{filename}"
                    screenshot_url = await upload_file_to_gcs(local_path, destination_name=gcs_filename, bucket="rca-reports-mats")
                    workflow_log.append(f"### Pre-Verification Screenshot\n[View Screenshot]({screenshot_url})")
            except Exception as img_err:
                logger.error(f"Failed to check/upload screenshot: {img_err}")
        else:
            workflow_log.append("## Pre-Verification\nSkipped (No Target URL)")
        
        # Step 2: Apply Fix
        await _report_progress("Phase 2: Applying Fix (GCloud)...", icon="🔧")
        remediation_command = spec.get("remediation_command")
        
        fix_applied = False
        fix_result = {}
        if remediation_command:
            if "MANUAL_CODE_FIX_REQUIRED" in remediation_command:
                 fix_result = {"status": "MANUAL_REQUIRED", "message": "The RCA indicates code changes are required."}
            else:
                 fix_result = await apply_gcloud_fix(command=remediation_command)
                 # GCloud Agent returns {success: bool, response: str}
                 if fix_result.get("success"):
                     fix_applied = True
        else:
             fix_result = {"status": "SKIPPED", "reason": "No REMEDIATION_COMMAND found"}
             
        workflow_log.append(f"## Fix Application\nResult: {fix_result}")
        
        # Step 3: Post-Verification (Monitoring)
        if spec.get("validation_query"):
            await _report_progress("Phase 3: Validation (Monitoring)...", icon="📊")
            validation_query = spec.get("validation_query")
            monitoring_result = await check_monitoring(query=validation_query)
            workflow_log.append(f"## Validation\nMonitoring: {monitoring_result}")
        else:
             workflow_log.append("## Validation\nSkipped (No Validation Query)")
        
        # Step 4: Documentation (Storage)
        await _report_progress("Phase 4: Documentation...", icon="📝")
        final_report = f"# Remediation Report\n\n**Session:** {session_id}\n\n" + "\n".join(workflow_log)
        
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        target_path = f"{session_id}/{timestamp}/remediation_report.md"
        
        # Use existing rca-reports-mats bucket
        report_url = await upload_to_gcs(final_report, filename=target_path, bucket="rca-reports-mats")
        
        await _report_progress(f"Remediation Complete. Report: {report_url}", icon="✅")
        
        if fix_result.get("status") == "MANUAL_REQUIRED":
            updated_status = "MANUAL_INTERVENTION"
        elif fix_applied:
            updated_status = "SUCCESS"
        else:
            updated_status = "FAILURE"
        
        return {
            "status": updated_status,
            "report_url": report_url,
            "steps": workflow_log
        }

    except Exception as e:
        await _report_progress(f"Remediation Failed: {e}", event_type="ERROR")
        logger.error(f"Remediation error: {e}", exc_info=True)
        return {"status": "FAILURE", "error": str(e)}

def process_remediation(rca_document, resolution_plan, session_id=None, user_email=None, auth_token=None):
    return asyncio.run(process_remediation_async(rca_document, resolution_plan, session_id, user_email, auth_token))
