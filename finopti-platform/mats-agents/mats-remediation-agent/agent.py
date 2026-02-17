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
from tools import run_puppeteer_test, apply_gcloud_fix, check_monitoring, upload_to_gcs, upload_file_to_gcs, read_from_gcs

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
    try:
        pub = RedisEventPublisher("Remediation Agent", "Remediation")
        _redis_publisher_ctx.set(pub)
    except Exception as e:
        logger.error(f"Failed to initialize RedisEventPublisher: {e}")
    
    await _report_progress("Starting Remediation Workflow...", icon="🛡️")

    # Load Template
    report_data = {}
    try:
        # Attempt to load from GCS via Storage Agent
        logger.info("Attempting to fetch Remediation-Template-V1.json from GCS...")
        template_gcs = await read_from_gcs("rca-reports-mats", "remediation-templates/Remediation-Template-V1.json")
        
        if template_gcs and isinstance(template_gcs, dict) and "docs" in template_gcs:
             report_data = template_gcs
             logger.info("Successfully loaded template from GCS.")
        else:
             logger.warning(f"GCS read returned invalid data: {template_gcs}. Falling back to local.")
             raise Exception("Invalid GCS template data")
             
    except Exception as e:
        logger.warning(f"Failed to load template from GCS ({e}). Using local fallback.")
        try:
            template_path = os.path.join(os.path.dirname(__file__), "Remediation-Template-V1.json")
            if os.path.exists(template_path):
                with open(template_path, "r") as f:
                    report_data = json.load(f)
            else:
                logger.warning(f"Template not found at {template_path}, using empty dict.")
        except Exception as local_e:
            logger.error(f"Failed to load local template: {local_e}")

    # Fill Initial Metadata
    if "metadata" not in report_data: report_data["metadata"] = {}
    report_data["metadata"]["incident_id"] = "UNKNOWN" # TODO: Extract from RCA
    report_data["metadata"]["session_id"] = session_id or "UNKNOWN"
    report_data["metadata"]["timestamp_utc"] = datetime.datetime.utcnow().isoformat()
    report_data["metadata"]["status"] = "IN_PROGRESS"

    
    try:
        # Step 0: Extract Spec
        spec = extract_remediation_spec(rca_document)
        if not spec:
             await _report_progress("Parsing Error: Could not extract remediation spec from RCA.", event_type="ERROR")
             return {"status": "FAILURE", "error": "Missing Remediation Spec"}
             
        # Heuristics for missing fields (backward compat)
        if not spec.get("remediation_command") and resolution_plan:
             spec["remediation_command"] = resolution_plan

        # Update metadata if available in spec or RCA
        # (Assuming RCA doc has incident_id somewhere, passing it in would be better)
        
        # Step 1: Pre-Verification (Reproduce Issue)
        if "pre_verification" not in report_data: report_data["pre_verification"] = {}
        report_data["pre_verification"]["target_url"] = spec.get("target_url", "N/A")
        report_data["pre_verification"]["reproduction_scenario"] = spec.get("reproduction_scenario", "N/A")

        if spec.get("target_url"):
            await _report_progress("Phase 1: Pre-verification (Puppeteer)...", icon="🧪")
            target_url = spec.get("target_url")
            scenario = spec.get("reproduction_scenario", "Verify broken state")
            
            pre_verify = await run_puppeteer_test(scenario=scenario, url=target_url)
            
            report_data["pre_verification"]["status"] = pre_verify.get("status", "UNKNOWN")
            
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

                # Update logs
                if "evidence" not in report_data["pre_verification"]: report_data["pre_verification"]["evidence"] = {}
                report_data["pre_verification"]["evidence"]["logs"] = clean_res

                screenshot_file = res_data.get("screenshot_url")
                local_path = None
                
                if not screenshot_file and "screenshot saved" in clean_res.lower():
                     # Fallback to regex
                     match = re.search(r"at:\s*(/projects/[^ \n]+)", clean_res)
                     if match:
                         local_path = match.group(1)
                else:
                    if screenshot_file:
                        local_path = f"/projects/{session_id}/{screenshot_file}"

                if local_path and os.path.exists(local_path):
                    filename = os.path.basename(local_path)
                    await _report_progress(f"Uploading screenshot {filename} to GCS...", icon="☁️")
                    
                    gcs_filename = f"{session_id}/screenshots/{filename}"
                    screenshot_url = await upload_file_to_gcs(local_path, destination_name=gcs_filename, bucket="rca-reports-mats")
                    
                    report_data["pre_verification"]["evidence"]["screenshot_url"] = screenshot_url
            except Exception as img_err:
                logger.error(f"Failed to check/upload screenshot: {img_err}")
        else:
             report_data["pre_verification"]["status"] = "SKIPPED (No Target URL)"
        
        # Step 2: Apply Fix
        if "remediation_action" not in report_data: report_data["remediation_action"] = {}
        report_data["remediation_action"]["action_type"] = "GCLOUD_COMMAND" # Default for now
        report_data["remediation_action"]["command_executed"] = spec.get("remediation_command", "N/A")

        await _report_progress("Phase 2: Applying Fix (GCloud)...", icon="🔧")
        remediation_command = spec.get("remediation_command")
        
        fix_applied = False
        fix_result = {}
        if remediation_command:
            if "MANUAL_CODE_FIX_REQUIRED" in remediation_command:
                 fix_result = {"status": "MANUAL_REQUIRED", "message": "The RCA indicates code changes are required."}
                 report_data["remediation_action"]["status"] = "MANUAL_REQUIRED"
                 report_data["remediation_action"]["output_log"] = "Manual code fix required as per RCA."
            else:
                 fix_result = await apply_gcloud_fix(command=remediation_command)
                 # GCloud Agent returns {success: bool, response: str}
                 report_data["remediation_action"]["output_log"] = str(fix_result.get("response", ""))
                 if fix_result.get("success"):
                     fix_applied = True
                     report_data["remediation_action"]["status"] = "SUCCESS"
                 else:
                     report_data["remediation_action"]["status"] = "FAILURE"
        else:
             fix_result = {"status": "SKIPPED", "reason": "No REMEDIATION_COMMAND found"}
             report_data["remediation_action"]["status"] = "SKIPPED"
             report_data["remediation_action"]["output_log"] = "No command provided."
             
        
        # Step 3: Post-Verification (Monitoring)
        if "post_verification" not in report_data: report_data["post_verification"] = {}
        report_data["post_verification"]["validation_query"] = spec.get("validation_query", "N/A")

        if spec.get("validation_query"):
            await _report_progress("Phase 3: Validation (Monitoring)...", icon="📊")
            validation_query = spec.get("validation_query")
            monitoring_result = await check_monitoring(query=validation_query)
            
            report_data["post_verification"]["monitoring_result"] = str(monitoring_result)
            # Simple heuristic for success? Monitoring returns JSON data usually.
            # If empty or error, verify failed.
            if monitoring_result and "error" not in str(monitoring_result).lower():
                 report_data["post_verification"]["status"] = "VERIFIED"
            else:
                 report_data["post_verification"]["status"] = "UNVERIFIED"

        else:
             report_data["post_verification"]["status"] = "SKIPPED (No Query)"
        
        # Determine Final Status
        if fix_result.get("status") == "MANUAL_REQUIRED":
            updated_status = "MANUAL_INTERVENTION"
            report_data["next_steps"]["manual_intervention_required"] = True
            report_data["next_steps"]["recommendations"] = "Manual code fix required. See RCA."
        elif fix_applied:
            updated_status = "SUCCESS"
            report_data["next_steps"]["manual_intervention_required"] = False
            report_data["next_steps"]["recommendations"] = "Monitor system stability."
        else:
            updated_status = "FAILURE"
            report_data["next_steps"]["manual_intervention_required"] = True
            report_data["next_steps"]["recommendations"] = "Remediation failed. Check logs."

        report_data["metadata"]["status"] = updated_status

        # Step 3.5: Populate Executive Summary
        if "executive_summary" not in report_data: report_data["executive_summary"] = {}
        
        summary_msg = f"Remediation initiated for Session {session_id}. "
        if fix_applied:
            summary_msg += f"Fix applied using command: '{spec.get('remediation_command')}'. "
        else:
            summary_msg += "No automated fix was applied. "
            
        summary_msg += f"Post-verification status: {report_data.get('post_verification', {}).get('status', 'UNKNOWN')}. "
        summary_msg += f"Final outcome: {updated_status}."
        
        report_data["executive_summary"]["summary_text"] = summary_msg

        # Step 4: Documentation (Storage)
        await _report_progress("Phase 4: Documentation...", icon="📝")
        
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        
        # Upload JSON Report
        json_content = json.dumps(report_data, indent=2)
        json_path = f"{session_id}/{timestamp}/remediation_report.json"
        json_url = await upload_to_gcs(json_content, filename=json_path, bucket="rca-reports-mats")
        
        # Generate Markdown Report from JSON
        md_content = f"""# {report_data['docs']['title']}

**Session ID:** {report_data['metadata']['session_id']}
**Timestamp:** {report_data['metadata']['timestamp_utc']}
**Status:** {report_data['metadata']['status']}

## Executive Summary
{report_data['executive_summary']['summary_text']}

## Pre-Verification
**Target URL:** {report_data['pre_verification']['target_url']}
**Scenario:** {report_data['pre_verification']['reproduction_scenario']}
**Status:** {report_data['pre_verification']['status']}

### Evidence
- **Screenshot:** [View Screenshot]({report_data['pre_verification']['evidence'].get('screenshot_url', 'N/A')})
- **Logs:** 
```
{report_data['pre_verification']['evidence'].get('logs', 'N/A')[:500]}...
```

## Remediation Action
**Command:** `{report_data['remediation_action']['command_executed']}`
**Status:** {report_data['remediation_action']['status']}
**Output:**
```
{report_data['remediation_action']['output_log'][:1000]}
```

## Post-Verification
**Query:** `{report_data['post_verification']['validation_query']}`
**Status:** {report_data['post_verification']['status']}
**Result:**
```
{report_data['post_verification']['monitoring_result'][:1000]}
```

## Next Steps
**Manual Intervention:** {report_data['next_steps']['manual_intervention_required']}
**Recommendations:** {report_data['next_steps']['recommendations']}
"""
        
        md_path = f"{session_id}/{timestamp}/remediation_report.md"
        md_url = await upload_to_gcs(md_content, filename=md_path, bucket="rca-reports-mats")

        await _report_progress(f"Remediation Complete. Report: {md_url}", icon="✅")

        return {
            "status": updated_status,
            "report_url": md_url,
            "json_url": json_url,
            "steps": [f"Generated report at {md_url}"] 
        }

    except Exception as e:
        await _report_progress(f"Remediation Failed: {e}", event_type="ERROR")
        logger.error(f"Remediation error: {e}", exc_info=True)
        return {"status": "FAILURE", "error": str(e)}

def process_remediation(rca_document, resolution_plan, session_id=None, user_email=None, auth_token=None):
    return asyncio.run(process_remediation_async(rca_document, resolution_plan, session_id, user_email, auth_token))
