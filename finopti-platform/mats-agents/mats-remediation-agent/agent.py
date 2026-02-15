"""
MATS Remediation Agent - Core Logic
Matches AI_AGENT_DEVELOPMENT_GUIDE_V2.0.md
"""
import asyncio
import logging
import json
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.genai import types

from observability import setup_observability
from context import _session_id_ctx, _user_email_ctx, _report_progress
from instructions import AGENT_INSTRUCTIONS, AGENT_NAME
from tools import run_puppeteer_test, apply_gcloud_fix, check_monitoring, upload_to_gcs

logger = logging.getLogger(__name__)

# 1. Setup Observability
setup_observability()

# 2. Define Agent
def create_remediation_agent(model_name=None):
    return Agent(
        name=AGENT_NAME,
        model=model_name or "gemini-2.0-flash",
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
async def process_remediation_async(rca_document: str, resolution_plan: str, session_id: str = None, user_email: str = None):
    # Context Propagation
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email)
    
    await _report_progress("Starting Remediation Workflow...", icon="🛡️")

    workflow_log = []
    
    try:
        # Step 1: Pre-Verification (Reproduce Issue)
        await _report_progress("Phase 1: Pre-verification (Puppeteer)...", icon="🧪")
        # Heuristic: Extract URL from RCA or resolution
        target_url = "http://test-app-url" # Placeholder - needs extraction logic
        pre_verify = await run_puppeteer_test(scenario="Verify broken state", url=target_url)
        workflow_log.append(f"## Pre-Verification\nStatus: {pre_verify}")
        
        if pre_verify.get("status") == "SUCCESS":
             await _report_progress("Wait, the application seems already working?", event_type="THOUGHT")
        
        # Step 2: Apply Fix
        await _report_progress("Phase 2: Applying Fix (GCloud)...", icon="🔧")
        # In a real scenario, we'd use the LLM to convert 'resolution_plan' to 'gcloud command'
        # For now, we assume the resolution plan *contains* the command or is the command
        fix_result = await apply_gcloud_fix(command=resolution_plan)
        workflow_log.append(f"## Fix Application\nResult: {fix_result}")
        
        # Step 3: Post-Verification (Monitoring)
        await _report_progress("Phase 3: Validation (Monitoring)...", icon="📊")
        monitoring_result = await check_monitoring(query="error_rate")
        workflow_log.append(f"## Validation\nMonitoring: {monitoring_result}")
        
        # Step 4: Documentation (Storage)
        await _report_progress("Phase 4: Documentation...", icon="📝")
        final_report = f"# Remediation Report\n\n**Session:** {session_id}\n\n" + "\n".join(workflow_log)
        report_url = await upload_to_gcs(final_report, filename=f"remediation_{session_id}.md")
        
        await _report_progress(f"Remediation Complete. Report: {report_url}", icon="✅")
        
        return {
            "status": "SUCCESS",
            "report_url": report_url,
            "steps": workflow_log
        }

    except Exception as e:
        await _report_progress(f"Remediation Failed: {e}", event_type="ERROR")
        logger.error(f"Remediation error: {e}", exc_info=True)
        return {"status": "FAILURE", "error": str(e)}

def process_remediation(rca_document, resolution_plan, session_id=None, user_email=None):
    return asyncio.run(process_remediation_async(rca_document, resolution_plan, session_id, user_email))
