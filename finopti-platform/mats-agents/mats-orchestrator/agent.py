"""
MATS Orchestrator - Core Agent

Orchestrator agent using Sequential Thinking for planning and delegation.
Follows AI_AGENT_DEVELOPMENT_GUIDE.md v5.0 standards.

Refactored per REFACTORING_GUIDELINE.md:
- Core agent definition (create_app) and workflow (run_investigation_async) remain here
- Supporting modules: observability, context, mcp_client, planner, routing, response_builder
"""
import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.genai import types

# Ensure paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
sys.path.append('/app/redis_common')

try:
    from redis_publisher import RedisEventPublisher
except ImportError:
    RedisEventPublisher = None

from config import config
from utils.tracing import trace_span

# --- EXTRACTED MODULES ---
from observability import setup_observability, ensure_api_key_env
from context import (
    _session_id_ctx, _user_email_ctx, _redis_publisher_ctx,
    _sequential_thinking_ctx, _report_progress
)
from mcp_client import SequentialThinkingClient
from planner import generate_plan, load_agent_registry, classify_issue
from routing import match_operational_route, handle_operational_request
from response_builder import format_investigation_response, safe_confidence

# --- SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize observability (Phoenix, OTel, ADK Instrumentor)
tracer_provider, tracer = setup_observability()

# Set API key if needed
ensure_api_key_env()

# OTel imports for span attributes
from opentelemetry import trace, propagate
from openinference.semconv.trace import SpanAttributes


# --- COMPONENT FACTORY (Rule 8) ---
def create_app():
    """Factory to create loop-safe App and Agent instances."""
    ensure_api_key_env()
    
    orchestrator_agent = Agent(
        name="mats_orchestrator",
        model=config.FINOPTIAGENTS_LLM,
        description="MATS Orchestrator - Autonomous troubleshooting manager",
        instruction="""
    You are the MATS Orchestrator, the brain of the Micro Agent Troubleshooting System.

    YOUR ROLE:
    - Plan investigations using Sequential Thinking
    - Delegate tasks to Team Lead agents (SRE, Investigator, Architect)
    - Monitor progress and handle failures
    - Report status to users

    WORKFLOW:
    1. PLANNING: Use generate_plan() to create investigation steps
    2. EXECUTION: Execute steps by calling team leads
    3. VALIDATION: Check quality gates between phases
    4. SYNTHESIS: Collect RCA from Architect
    5. REPORTING: Return results to user

    ERROR HANDLING:
    - IF SRE returns "NO_LOGS_FOUND": Expand time window and retry
    - IF any agent returns "PERMISSION_DENIED": Escalate to user
    - IF confidence < 0.5: Flag as "Low Confidence" in final report
    - IF retry count >= 3: Proceed with partial results

    OUTPUT:
    Always provide structured updates including:
    - Current phase
    - Progress (step X of Y)
    - Any blockers or warnings
    - Final RCA URL when complete
    """,
        tools=[] 
    )

    bq_plugin = BigQueryAgentAnalyticsPlugin(
        project_id=os.getenv("GCP_PROJECT_ID"),
        dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
        table_id=config.BQ_ANALYTICS_TABLE,
        config=BigQueryLoggerConfig(
            enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
        )
    )

    return App(
        name="mats_orchestrator_app",
        root_agent=orchestrator_agent,
        plugins=[
            ReflectAndRetryToolPlugin(max_retries=2),
            bq_plugin
        ]
    )


# --- EXECUTION LOGIC ---
@trace_span("investigation_run", kind="CHAIN")
async def run_investigation_async(
    user_request: str,
    project_id: str,
    repo_url: str,
    user_email: str = None,
    job_id: str = None,
    resume_job_id: str = None,
    trace_context: Dict[str, Any] = None,
    provided_session_id: str = None
) -> Dict[str, Any]:
    """
    Run complete investigation workflow.
    
    Returns:
        Investigation results with RCA URL
    """
    import re
    from state import create_session, WorkflowPhase, update_session
    from delegation import (
        delegate_to_sre, 
        delegate_to_investigator, 
        delegate_to_architect,
    )
    from quality_gates import (
        gate_planning_to_triage,
        gate_triage_to_analysis,
        gate_analysis_to_synthesis,
        GateDecision
    )
    try:
        from job_manager import JobManager
    except ImportError:
        JobManager = None

    # Create session
    session = await create_session(user_email or "default", project_id, repo_url, provided_session_id)
    session_id = session.session_id

    # --- CONTEXT SETTING (Rule 1 & 6) ---
    _session_id_ctx.set(session_id)
    _user_email_ctx.set(user_email or "unknown")

    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanAttributes.SESSION_ID, session_id)
        if user_email:
            span.set_attribute("user_id", user_email)

    logger.info(f"[{session_id}] Starting investigation (Job: {job_id}): {user_request[:100]}")

    # --- REDIS INSTRUMENTATION (Rule 6) ---
    redis_publisher = None
    if RedisEventPublisher:
        try:
            redis_publisher = RedisEventPublisher("MATS Orchestrator", "Orchestrator")
            _redis_publisher_ctx.set(redis_publisher)
        except Exception as e:
            logger.error(f"Failed to initialize RedisEventPublisher: {e}")

    await _report_progress(f"Received request: {user_request[:50]}...", event_type="STATUS_UPDATE", icon="📥", display_type="step_progress")

    # --- OPERATIONAL ROUTING: Bypass investigation for simple commands ---
    matched, agent_url, agent_name = match_operational_route(user_request)
    if matched:
        # Special handling for Remediation (Requires Context)
        if agent_name == "Remediation Agent":
            from delegation import delegate_to_remediation
            
            # 1. Try to find RCA context from current session
            if not session.architect_output:
                 # 2. Check if the prompt itself contains self-contained RCA details (Literal Spec)
                 if "TARGET_URL" in user_request and "REMEDIATION_COMMAND" in user_request:
                     logger.info(f"[{session_id}] Detected self-contained remediation prompt. Mocking architect_output.")
                     session.architect_output = {
                         "rca_content": user_request,
                         "status": "SUCCESS",
                         "confidence": 1.0
                     }
                 else:
                     # 3. Check for external RCA links (e.g. GCS or HTTP)
                     url_match = re.search(r'https?://[^\s{}()<>"]+', user_request)
                     if url_match:
                         url = url_match.group(0)
                         # Heuristic: Is it pointing to an rca.json or our bucket?
                         if "rca.json" in url or "rca-reports-mats" in url:
                             await _report_progress(f"Detected external RCA link. Fetching context...", icon="📥", display_type="toast")
                             
                             # Extract GS path if applicable
                             gs_match = re.search(r"storage\.(?:cloud\.google|googleapis)\.com/(rca-reports-mats/[^?\s]+)", url)
                             gs_path = f"gs://{gs_match.group(1)}" if gs_match else (url if url.startswith("gs://") else None)
                             
                             try:
                                 if gs_path:
                                     from google.cloud import storage
                                     path_parts = gs_path.replace("gs://", "").split("/")
                                     bucket_name = path_parts[0]
                                     blob_name = "/".join(path_parts[1:])
                                     
                                     def _fetch():
                                         client = storage.Client()
                                         return client.bucket(bucket_name).blob(blob_name).download_as_text()
                                     
                                     rca_text = await asyncio.to_thread(_fetch)
                                 else:
                                     import aiohttp
                                     async with aiohttp.ClientSession() as http_client:
                                         async with http_client.get(url, timeout=10) as resp:
                                             rca_text = await resp.text()
                                 
                                 # Parse and validate
                                 rca_data = json.loads(rca_text)
                                 # Remediation agent expects "rca_content" as string or the whole thing
                                 session.architect_output = {
                                     "rca_content": json.dumps(rca_data) if isinstance(rca_data, dict) else rca_text,
                                     "status": "SUCCESS",
                                     "confidence": 1.0,
                                     "external_source": url
                                 }
                                 logger.info(f"[{session_id}] Successfully loaded external RCA from {url}")
                             except Exception as e:
                                 logger.warning(f"[{session_id}] Failed to load external RCA from {url}: {e}")

            # Re-check if we found an RCA
            if not session.architect_output:
                 return {
                    "status": "FAILURE",
                    "response": "⚠️ **No Active Investigation Found**\n\nI cannot suggest a solution because I don't have a Root Cause Analysis (RCA) context yet. Please ask me to investigate an issue first (e.g., 'Troubleshoot service X') or provide a self-contained RCA spec with TARGET_URL and REMEDIATION_COMMAND."
                }
            
            await _report_progress(f"Starting auto-remediation (Session: {session_id})...", event_type="STATUS_UPDATE", icon="🛠️", display_type="step_progress")
            
            rem_result = await delegate_to_remediation(session, user_request)
            
            status = rem_result.get("status", "UNKNOWN")
            if status == "FAILURE":
                response = f"❌ **Remediation Failed**\n\n{rem_result.get('error', 'Unknown error occurred.')}"
            elif status == "MANUAL_INTERVENTION":
                response = f"⚠️ **Manual Intervention Required**\n\n{rem_result.get('message', 'The fix requires manual steps.')}\n\nReport: {rem_result.get('report_url')}"
            else:
                response = rem_result.get("response", "✅ **Remediation Completed Successfully**")
                if "report_url" in rem_result:
                    response += f"\n\n[View Detailed Remediation Report]({rem_result['report_url']})"
            
            return {
                "status": status,
                "orchestrator": {"target_agent": "Remediation Agent"},
                "response": response,
                "data": rem_result
            }

        return await handle_operational_request(
            user_request=user_request,
            agent_url=agent_url,
            agent_name=agent_name,
            session_id=session_id,
            user_email=user_email,
            job_id=job_id,
            report_progress=_report_progress
        )

    await _report_progress(f"Starting investigation: {user_request[:50]}...", event_type="STATUS_UPDATE", icon="🚀", display_type="step_progress")

    # Initialize Sequential Thinking MCP
    seq_client = SequentialThinkingClient()
    token_reset = _sequential_thinking_ctx.set(seq_client)
    
    try:
        await seq_client.connect()
        
        # --- PHASE 1: PLANNING (Skip if Resuming) ---
        if not resume_job_id:
            await _report_progress("Generating investigation plan...", event_type="STATUS_UPDATE", icon="📋", display_type="step_progress")
            session.workflow.transition_to(WorkflowPhase.PLANNING, "Generating investigation plan")
            agent_registry = load_agent_registry()
            try:
                plan = await generate_plan(user_request, agent_registry, seq_client=seq_client)
                issue_type = plan.get('issue_type', 'unknown')
                
                plan_summary = f"**Investigation Plan** (Issue Type: `{issue_type}`)\n\nReasoning: {plan.get('reasoning', 'N/A')}\n\nSteps:\n"
                for i, step in enumerate(plan.get('steps', []), 1):
                    plan_summary += f"{i}. {step.get('ui_label')} ({step.get('assigned_lead')})\n"
                
                await _report_progress(plan_summary, event_type="THOUGHT", icon="🧠")
                
                if job_id and JobManager:
                    JobManager.add_event(job_id, "PLAN", plan_summary, "orchestrator")
            except Exception as e:
                await _report_progress(f"Planning failed: {e}", event_type="ERROR", icon="❌", display_type="alert")
                raise e
            
            gate_result, reason = gate_planning_to_triage(plan, session_id)
            if gate_result == GateDecision.FAIL:
                session.add_blocker("E000", f"Planning failed: {reason}")
                await _report_progress(f"Planning failed: {reason}", event_type="ERROR", icon="❌", display_type="alert")
                session.mark_completed("FAILURE")
                return {
                    "status": "FAILURE", 
                    "error": reason,
                    "response": f"❌ **Planning Failed**\n\n{reason}"
                }
        else:
            logger.info(f"[{session_id}] Resuming job {resume_job_id}. Skipping Planning.")
            if JobManager:
                prev_job = JobManager.get_job(resume_job_id)
                if prev_job and prev_job.get("result"):
                    session.sre_findings = prev_job["result"].get("sre_findings")

        # --- PHASE 2: TRIAGE (SRE) ---
        await _report_progress("Triaging logs and metrics (SRE)...", event_type="STATUS_UPDATE", icon="🔍", display_type="step_progress")
        session.workflow.transition_to(WorkflowPhase.TRIAGE, "Analyzing logs and metrics")
        
        sre_result = None
        issue_type = plan.get('issue_type', 'unknown') if not resume_job_id else 'unknown'
        
        if resume_job_id and session.sre_findings:
            # RESUME SRE
            logger.info(f"[{session_id}] Resuming SRE with user input: {user_request}")
            if JobManager:
                JobManager.add_event(job_id, "SYSTEM", "Resuming SRE Analysis...", "orchestrator")
            
            # Extract Project ID from user input (Heuristic)
            patterns = [
                r"project\s*(?:id|name)?\s*[:=]\s*([a-z0-9-]+)",
                r"gcp\s*project\s*[:=]\s*([a-z0-9-]+)"
            ]
            for p in patterns:
                m = re.search(p, user_request, re.IGNORECASE)
                if m:
                    new_pid = m.group(1).strip()
                    if new_pid and new_pid.lower() != "yes":
                        project_id = new_pid
                        logger.info(f"[{session_id}] Extracted Project ID from user input: {project_id}")
                        break

            # Construct Resumption Prompt
            prev_findings = session.sre_findings
            pending_steps = prev_findings.get("pending_steps", [])
            
            sre_resume_prompt = f"""
             RESUMPTION INSTRUCTION:
             You previously paused analysis.
             User has APPROVED continuing with the following steps: {pending_steps}.
             User Note: "{user_request}"
             
             PREVIOUS FINDINGS:
             {json.dumps(prev_findings.get('evidence', {}), indent=2)}
             
             CRITICAL INSTRUCTION:
             1. EXECUTE the pending steps immediately.
             2. Do NOT ask for approval again for the same steps.
             3. If a step yields no results (0 logs), mark it as COMPLETED and move to the next.
             4. If you have executed 3 queries, STOP and return your findings (Success or Failure).
             
             GOAL: Finish the investigation or declared "ROOT_CAUSE_NOT_FOUND".
             """
             
            sre_result = await delegate_to_sre(
                sre_resume_prompt,
                project_id,
                session_id,
                job_id=job_id,
                user_email=user_email
            )
        else:
            # FRESH SRE CALL
            sre_result = await delegate_to_sre(
                f"{user_request}\n\nFocus on finding error signatures and stack traces.",
                project_id,
                session_id,
                job_id=job_id,
                user_email=user_email,
                issue_type=issue_type
            )
            
        session.sre_findings = sre_result
        session.confidence_scores['sre'] = safe_confidence(sre_result.get('confidence'))
        
        gate_result, reason = gate_triage_to_analysis(sre_result, session_id)
        
        # Handle Interactive SRE Pause
        if sre_result.get("status") == "WAITING_FOR_APPROVAL":
            pending_steps = sre_result.get("pending_steps", [])
            steps_list = "\n".join([f"- {s}" for s in pending_steps])
            response_msg = (
                f"⚠️ **SRE Analysis Paused**\n\n"
                f"The SRE Agent has completed initial checks but identified {len(pending_steps)} more potential analysis steps.\n\n"
                f"**Completed Work**: Analyzed initial logs.\n"
                f"**Pending Steps**:\n{steps_list}\n\n"
                f"**Action Required**: Check the steps above. If the agent is missing information (e.g., Project ID), please provide it.\n"
                f"Otherwise, reply **'Yes'** or **'Continue'** to proceed."
            )
            
            return {
                "status": "WAITING_FOR_USER",
                "sre_findings": sre_result,
                "response": response_msg,
                "execution_trace": sre_result.get("execution_trace", [])
            }

        if gate_result == GateDecision.FAIL:
            # Check if failure is an infra blocker (authentication, permission, etc.)
            blockers = sre_result.get("blockers", [])
            infra_keywords = ["authentication", "permission", "access", "role", "limit", "quota", "iam", "policy", "forbidden", "403"]
            is_infra_blocker = any(any(k in b.lower() for k in infra_keywords) for b in blockers)
            
            if is_infra_blocker:
                logger.info(f"[{session_id}] SRE blocked by Infra issue: {blockers}. Treated as Root Cause.")
                session.workflow.transition_to(WorkflowPhase.SYNTHESIS, "Generating RCA (Blocked by Infra)")
                
                inv_result_skipped = {
                    "status": "SKIPPED",
                    "confidence": 1.0, 
                    "root_cause": None,
                    "hypothesis": f"Service blocked by Infrastructure/Auth: {'; '.join(blockers)}",
                    "evidence": json.dumps(sre_result.get('evidence', {}))
                }
                
                arch_result = await delegate_to_architect(sre_result, inv_result_skipped, session_id, user_request=user_request)
                return format_investigation_response(session, arch_result, sre_result, session_id)

            # Genuine Failure / Inconclusive Triage
            # Instead of stopping, we pass what we have to the Architect to generate a report on the findings so far.
            logger.info(f"[{session_id}] SRE Triage failed/inconclusive: {reason}. Proceeding to RCA with available evidence.")
            session.workflow.transition_to(WorkflowPhase.SYNTHESIS, "Generating RCA (Partial Triage)")

            inv_result_skipped = {
                "status": "SKIPPED",
                "confidence": 0.5, 
                "root_cause": None,
                "hypothesis": f"Triage Incomplete/Inconclusive: {reason}",
                "evidence": json.dumps(sre_result.get('evidence', {}))
            }

            arch_result = await delegate_to_architect(sre_result, inv_result_skipped, session_id, user_request=user_request)
            return format_investigation_response(session, arch_result, sre_result, session_id)
        
        # --- SHORTCUT: SRE found root cause, skip Investigator ---
        if sre_result.get("root_cause_found"):
            logger.info(f"[{session_id}] SRE identified root cause. Skipping Investigator phase.")
            session.workflow.transition_to(WorkflowPhase.SYNTHESIS, "Generating RCA (Infra Root Cause)")
            
            inv_result_skipped = {
                "status": "SKIPPED",
                "confidence": 1.0, 
                "root_cause": None,
                "hypothesis": "Root cause identified by SRE (Infrastructure/Config)",
                "evidence": "See SRE Report"
            }
            
            arch_result = await delegate_to_architect(sre_result, inv_result_skipped, session_id)
            return format_investigation_response(session, arch_result, sre_result, session_id)

        # --- PHASE 3: CODE ANALYSIS (Investigator) ---
        await _report_progress("Analyzing code repositories (Investigator)...", event_type="STATUS_UPDATE", icon="💻", display_type="step_progress")
        session.workflow.transition_to(WorkflowPhase.CODE_ANALYSIS, "Investigating code")
        sre_context = json.dumps(sre_result.get('evidence', {}), indent=2)
        inv_result = await delegate_to_investigator(
            f"{user_request}\n\nAnalyze the code based on the following evidence.",
            sre_context,
            repo_url,
            session_id
        )
        session.investigator_findings = inv_result
        session.confidence_scores['investigator'] = safe_confidence(inv_result.get('confidence'))
        
        gate_result, reason = gate_analysis_to_synthesis(inv_result, session_id)
        if gate_result == GateDecision.FAIL:
            sre_confidence = safe_confidence(sre_result.get('confidence'))
            if sre_confidence > 0.7:
                logger.warning(f"[{session_id}] Investigator failed ({reason}) but SRE confidence high ({sre_confidence}). Proceeding to RCA.")
            else:
                session.add_blocker("E006", reason)
                session.mark_completed("PARTIAL_SUCCESS")
                return {
                    "status": "PARTIAL",
                    "sre_findings": sre_result,
                    "investigator_findings": inv_result,
                    "error": reason,
                    "response": f"⚠️ **Analysis Incomplete**\n\nInvestigator could not find the root cause in the code.\n\nReason: {reason}",
                    "execution_trace": sre_result.get("execution_trace", [])
                }
        
        # --- PHASE 4: SYNTHESIS (Architect) ---
        await _report_progress("Synthesizing Root Cause Analysis (Architect)...", event_type="STATUS_UPDATE", icon="🏗️", display_type="step_progress")
        session.workflow.transition_to(WorkflowPhase.SYNTHESIS, "Generating RCA")
        arch_result = await delegate_to_architect(sre_result, inv_result, session_id, user_request=user_request)
        
        return format_investigation_response(session, arch_result, sre_result, session_id)
        
    except Exception as e:
        logger.error(f"[{session_id}] Investigation failed: {e}", exc_info=True)
        session.add_blocker("E000", str(e))
        session.mark_completed("FAILURE")
        return {
            "status": "FAILURE", 
            "error": str(e),
            "response": f"💥 **System Error**\n\nAn unexpected error occurred during investigation.\n\nError: {str(e)}"
        }
        
    finally:
        if 'session' in locals():
            await update_session(session)
        await seq_client.close()
        _sequential_thinking_ctx.reset(token_reset)


def run_investigation(
    user_request: str,
    project_id: str,
    repo_url: str,
    user_email: str = None
) -> Dict[str, Any]:
    """Synchronous wrapper for investigation"""
    return asyncio.run(run_investigation_async(user_request, project_id, repo_url, user_email))
