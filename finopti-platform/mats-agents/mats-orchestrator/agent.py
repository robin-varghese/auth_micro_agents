"""
MATS Orchestrator - Main Agent

Orchestrator agent using Sequential Thinking for planning and delegation.
Follows AI_AGENT_DEVELOPMENT_GUIDE.md v3.0 standards.
"""
import os
import sys
import asyncio
import json
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Dict, Any, Optional

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.genai import types

# Observability
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from utils.tracing import trace_span

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(session_id)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize tracing
# Use SimpleSpanProcessor for debugging to ensure immediate export 
# (register uses BatchSpanProcessor by default)
TRACE_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces")

tracer_provider = register(
    project_name="finoptiagents-MATS",
    endpoint=TRACE_ENDPOINT,
    set_global_tracer_provider=True
)

# Force SimpleSpanProcessor for immediate export debug
# Note: register() adds a BatchSpanProcessor. We are adding a second processor.
# ideally we would replace it, but adding a simple one ensures at least one path flushes immediately.
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
http_exporter = OTLPSpanExporter(endpoint=TRACE_ENDPOINT)
tracer_provider.add_span_processor(SimpleSpanProcessor(http_exporter))

GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# Send manual test trace on startup
from opentelemetry import trace, propagate
from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues

# Get tracer for creating spans
tracer = trace.get_tracer(__name__)

# Send manual test trace on startup
with tracer.start_as_current_span("agent-startup-check") as span:
    span.set_attribute("status", "startup_ok")
    logger.info("Sent manual startup trace to Phoenix")


# Set API key
if config.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

# --- CONTEXT ISOLATION (Rule 1) ---
_sequential_thinking_ctx: ContextVar["SequentialThinkingClient"] = ContextVar("seq_thinking_client", default=None)


class SequentialThinkingClient:
    """MCP client for Sequential Thinking specialist"""
    
    def __init__(self):
        self.image = os.getenv("SEQUENTIAL_THINKING_MCP_DOCKER_IMAGE", "sequentialthinking")
        self.mount_path = os.getenv('GCLOUD_MOUNT_PATH', f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud")
        self.process = None
        self.request_id = 0
        
    async def connect(self):
        """Start the Sequential Thinking MCP server"""
        # No need for gcloud mount for sequential thinking logic
        cmd = ["docker", "run", "-i", "--rm", self.image]
        logger.info(f"Starting Sequential Thinking MCP: {' '.join(cmd)}")
        
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024  # 10MB buffer
        )
        await self._handshake()
        
    async def _handshake(self):
        """Perform MCP initialization handshake"""
        init_msg = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {"name": "mats-orchestrator", "version": "1.0.0"}
            }
        }
        await self._send_json(init_msg)
        response = await self._read_json()
        logger.info(f"Sequential Thinking MCP initialized: {response}")

        # Send initialized notification
        await self._send_json({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })
        
    async def _send_json(self, data: dict):
        """Send JSON-RPC message"""
        message = json.dumps(data) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()
        
    async def _read_json(self) -> dict:
        """Read JSON-RPC response, skipping non-JSON lines"""
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise EOFError("MCP server process closed unexpectedly")
            
            line_str = line.decode().strip()
            if not line_str:
                continue
                
            try:
                return json.loads(line_str)
            except json.JSONDecodeError:
                logger.debug(f"MCP non-JSON output: {line_str}")
                continue
        
    async def call_tool(self, tool_name: str, args: dict) -> dict:
        """Call a tool on the MCP server"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args}
        }
        await self._send_json(request)
        response = await self._read_json()
        
        if "error" in response:
            raise Exception(f"Tool call error: {response['error']}")
            
        return response.get("result", {})
        
    async def close(self):
        """Close the MCP connection"""
        if self.process:
            try:
                self.process.stdin.close()
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Sequential Thinking MCP did not exit gracefully, killing")
                self.process.kill()
                await self.process.wait()


async def ensure_sequential_thinking():
    """Retrieve Sequential Thinking client for current context"""
    client = _sequential_thinking_ctx.get()
    if not client:
        raise RuntimeError("Sequential Thinking MCP not initialized for this context")
    return client


# --- TOOL WRAPPERS ---
async def generate_plan(user_request: str, agent_registry: list) -> Dict[str, Any]:
    """
    Generate investigation plan using LLM directly (Bypassing MCP tool to avoid schema errors).
    
    Args:
        user_request: User's problem description
        agent_registry: List of available agents/capabilities
        
    Returns:
        Plan with reasoning and steps
    """
    # Format agent registry for context
    capabilities_summary = "\n".join([
        f"- {agent['name']}: {agent.get('capabilities', 'N/A')}"
        for agent in agent_registry
    ])
    
    prompt = f"""
    You are a Principal SRE Investigator planning a troubleshooting session.
    
    USER REQUEST: {user_request}
    
    AVAILABLE CAPABILITIES:
    {capabilities_summary}
    
    Create a step-by-step investigation plan. Your plan should:
    1. Start with log/metric triage (SRE)
    2. Move to code analysis (Investigator)
    3. End with RCA synthesis (Architect)
    
    Think through the approach carefully and output a JSON plan with:
    - plan_id
    - reasoning (why this approach)
    - steps (array of {{step_id, assigned_lead, task, ui_label}})
    """
    
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        
        logger.info(f"Generating plan using model: {config.FINOPTIAGENTS_LLM}")
        response = client.models.generate_content(
            model=config.FINOPTIAGENTS_LLM,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        
        if not response.parsed:
             # Fallback parsing if needed
             import json
             plan = json.loads(response.text)
        else:
             plan = response.parsed
             
        # Robust parsing for List output (common small model behavior)
        if isinstance(plan, list):
            logger.warning(f"Plan generation returned a list, attempting to wrap: {str(plan)[:100]}...")
            if len(plan) > 0 and isinstance(plan[0], dict):
                # Case 1: List of steps
                if "step_id" in plan[0]:
                    plan = {
                        "plan_id": "auto-generated",
                        "reasoning": "Model returned raw list of steps",
                        "steps": plan
                    }
                # Case 2: List containing the plan object
                elif "steps" in plan[0]:
                    plan = plan[0]
                else:
                    return {
                        "plan_id": "fallback-list",
                        "reasoning": "Model returned unrecognized list format",
                        "steps": [
                            {"step_id": 1, "assigned_lead": "sre", "task": f"Analyze logs: {user_request}", "ui_label": "Investigating"}
                        ]
                    }
            else:
                 return {
                    "plan_id": "fallback-empty",
                    "reasoning": "Model returned empty/invalid list",
                    "steps": [
                        {"step_id": 1, "assigned_lead": "sre", "task": f"Analyze logs: {user_request}", "ui_label": "Investigating"}
                    ]
                 }
                 
        return plan
        
    except Exception as e:
        logger.error(f"Plan generation failed: {e}")
        # Fallback plan
        return {
            "plan_id": "fallback-001",
            "reasoning": "Using default 3-step investigation due to planning error",
            "steps": [
                {"step_id": 1, "assigned_lead": "sre", "task": f"Analyze logs for: {user_request}", "ui_label": "Investigating Logs"},
                {"step_id": 2, "assigned_lead": "investigator", "task": "Analyze code", "ui_label": "Analyzing Code"},
                {"step_id": 3, "assigned_lead": "architect", "task": "Generate RCA", "ui_label": "Generating RCA"}
            ]
        }


# Load agent registry
def load_agent_registry() -> list:
    """Load agent registry from JSON file"""
    registry_path = Path(__file__).parent / "agent_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            return json.load(f)
    return []


# --- AGENT DEFINITION ---
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
    tools=[]  # Tools will be dynamically added via delegation module
)

# BigQuery Analytics Plugin
bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=config.BQ_ANALYTICS_TABLE,
    config=BigQueryLoggerConfig(
        enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    )
)

app_instance = App(
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
    resume_job_id: str = None, # New optional param to signal resumption
    trace_context: Dict[str, Any] = None,
    provided_session_id: str = None  # NEW: Session ID from UI for Phoenix tracking
) -> Dict[str, Any]:
    """
    Run complete investigation workflow.
    
    Returns:
        Investigation results with RCA URL
    """
    from state import create_session, WorkflowPhase
    from delegation import delegate_to_sre, delegate_to_investigator, delegate_to_architect
    from quality_gates import (
        gate_planning_to_triage,
        gate_triage_to_analysis,
        gate_analysis_to_synthesis,
        GateDecision
    )
    # Import JobManager locally 
    try:
        from job_manager import JobManager
    except ImportError:
        JobManager = None
    
    # Create session (use provided_session_id from UI if available)
    session = await create_session(user_email or "default", project_id, repo_url, provided_session_id)
    session_id = session.session_id
    
    logger.info(f"[{session_id}] Starting investigation (Job: {job_id}): {user_request[:100]}")
    logger.info(f"[{session_id}] Using session ID from UI: {provided_session_id is not None}")

    # Set session.id on the current span (created by @trace_span decorator)
    # This ensures Phoenix can group traces by session
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute(SpanAttributes.SESSION_ID, session_id)
        current_span.set_attribute("user.email", user_email or "unknown")
        current_span.set_attribute("session.project_id", project_id or "unknown")
        current_span.set_attribute("session.repo_url", repo_url or "unknown")
        current_span.set_attribute("job.id", job_id or "none")
        logger.info(f"[{session_id}] Set session.id={session_id} on current span")
    
    # Inject trace context for propagation to sub-agents
    trace_headers = {}
    propagate.inject(trace_headers)
    
    # Store in session for delegation
    session.trace_headers = trace_headers
    logger.info(f"[{session_id}] Trace context injected with traceparent: {trace_headers.get('traceparent', 'N/A')[:50]}...")
    
    if job_id and JobManager and not resume_job_id:
        JobManager.add_event(job_id, "SYSTEM", f"Investigation started for session {session_id}", "orchestrator")

    
    # Initialize Sequential Thinking MCP
    seq_client = SequentialThinkingClient()
    token_reset = _sequential_thinking_ctx.set(seq_client)
    
    try:
        await seq_client.connect()
        
        # --- PHASE 1: PLANNING (Skip if Resuming) ---
        if not resume_job_id:
            session.workflow.transition_to(WorkflowPhase.PLANNING, "Generating investigation plan")
            agent_registry = load_agent_registry()
            plan = await generate_plan(user_request, agent_registry)
            
            # EMIT PLAN EVENT
            if job_id and JobManager:
                # Emit the raw plan or a formatted summary
                plan_summary = f"**Investigation Plan**\n\nReasoning: {plan.get('reasoning', 'N/A')}\n\nSteps:\n"
                for i, step in enumerate(plan.get('steps', []), 1):
                    plan_summary += f"{i}. {step.get('ui_label')} ({step.get('assigned_lead')})\n"
                
                JobManager.add_event(job_id, "PLAN", plan_summary, "orchestrator")
            
            gate_result, reason = gate_planning_to_triage(plan, session_id)
            if gate_result == GateDecision.FAIL:
                session.add_blocker("E000", f"Planning failed: {reason}")
                session.mark_completed("FAILURE")
                return {
                    "status": "FAILURE", 
                    "error": reason,
                    "response": f"❌ **Planning Failed**\n\n{reason}"
                }
        else:
            logger.info(f"[{session_id}] Resuming job {resume_job_id}. Skipping Planning.")
            # Restore state if possible (Mocking state restoration for now)
            # In real system, load session from DB using job_id linkage.
            # Here we will re-use the Job's last result if available via JobManager
            if JobManager:
                 prev_job = JobManager.get_job(resume_job_id)
                 if prev_job and prev_job.get("result"):
                     session.sre_findings = prev_job["result"].get("sre_findings")

        # --- PHASE 2: TRIAGE (SRE) ---
        session.workflow.transition_to(WorkflowPhase.TRIAGE, "Analyzing logs and metrics")
        
        sre_result = None
        
        # Determine if we call SRE fresh or Resume SRE
        if resume_job_id and session.sre_findings:
             # RESUME SRE
             logger.info(f"[{session_id}] Resuming SRE with user input: {user_request}")
             JobManager.add_event(job_id, "SYSTEM", "Resuming SRE Analysis...", "orchestrator")
             
             # Attempt to extract Project ID from user input (Heuristic)
             import re
             # Extract pattern like "project id: foo" or "project: bar"
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
             
             # Context for SRE to know what it did
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
             
             # Pass job_id to sub-agents for progress reporting
             sre_result = await delegate_to_sre(
                sre_resume_prompt,
                project_id,
                session_id,
                job_id=job_id
             )
        else:
            # FRESH SRE CALL
            # Pass job_id to sub-agents for progress reporting
            sre_result = await delegate_to_sre(
                f"{user_request}\n\nFocus on finding error signatures and stack traces.",
                project_id,
                session_id,
                job_id=job_id # Passing job_id
            )
            
        session.sre_findings = sre_result
        session.confidence_scores['sre'] = sre_result.get('confidence', 0.0)
        
        gate_result, reason = gate_triage_to_analysis(sre_result, session_id)
        
        # New: Handle Interactive SRE Pause
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
            # Check if failure is actually a definitive blocker (Infra/Auth issue)
            blockers = sre_result.get("blockers", [])
            # Heuristic: If we have specific blockers or low confidence but specific error signature
            infra_keywords = ["authentication", "permission", "access", "role", "limit", "quota", "iam", "policy", "forbidden", "403"]
            is_infra_blocker = any(any(k in b.lower() for k in infra_keywords) for b in blockers)
            
            if is_infra_blocker:
                logger.info(f"[{session_id}] SRE blocked by definitive Infra issue: {blockers}. Treated as Root Cause.")
                
                # Treat as Root Cause Found -> Go to Architect
                session.workflow.transition_to(WorkflowPhase.SYNTHESIS, "Generating RCA (Blocked by Infra)")
                
                inv_result_skipped = {
                    "status": "SKIPPED",
                    "confidence": 1.0, 
                    "root_cause": None,
                    "hypothesis": f"Service blocked by Infrastructure/Auth: {'; '.join(blockers)}",
                    "evidence": json.dumps(sre_result.get('evidence', {}))
                }
                
                arch_result = await delegate_to_architect(sre_result, inv_result_skipped, session_id, user_request=user_request)
                session.architect_output = arch_result
                session.confidence_scores['architect'] = arch_result.get('confidence', 0.0)
                session.rca_url = arch_result.get('rca_url')
                
                # Mark complete
                overall_confidence = session.calculate_overall_confidence()
                session.mark_completed("SUCCESS" if overall_confidence >= 0.5 else "PARTIAL_SUCCESS")
                
                response_msg = f"**Investigation Complete** (Confidence: {overall_confidence:.2f})\n\n"
                if session.rca_url:
                    response_msg += f"📄 **RCA Document**: {session.rca_url}\n\n"
                elif arch_result.get('rca_content'):
                     response_msg += "📄 **RCA generated** (See content below).\n\n"

                response_msg += "**Summary:**\n"
                rca_content = arch_result.get('rca_content', 'No details available.')
                response_msg += rca_content[:1000] + ("..." if len(rca_content) > 1000 else "")

                return {
                    "status": "SUCCESS",
                    "session_id": session_id,
                    "response": response_msg,
                    "confidence": overall_confidence,
                    "rca_url": session.rca_url,
                    "rca_content": arch_result.get('rca_content'),
                    "warnings": session.warnings,
                    "recommendations": arch_result.get('recommendations', []),
                    "execution_trace": sre_result.get("execution_trace", [])
                }

            # Genuine Failure
            session.add_blocker("E001", reason)
            session.mark_completed("PARTIAL_SUCCESS")
            return {
                "status": "PARTIAL", 
                "sre_findings": sre_result, 
                "error": reason,
                "response": f"⚠️ **Triage Incomplete**\n\nSRE found issues but could not proceed to code analysis.\n\nReason: {reason}",
                "execution_trace": sre_result.get("execution_trace", [])
            }
        
        # --- NEW SHORTCUT LOGIC ---
        # If SRE found the root cause (e.g., Infrastructure/IAM error), skip Investigator
        if sre_result.get("root_cause_found"):
            logger.info(f"[{session_id}] SRE identified root cause. Skipping Investigator phase.")
            
            # Phase 4: SYNTHESIS (Architect) - Direct Transition
            session.workflow.transition_to(WorkflowPhase.SYNTHESIS, "Generating RCA (Infra Root Cause)")
            
            # Create a dummy investigator result for the Architect
            inv_result_skipped = {
                "status": "SKIPPED",
                "confidence": 1.0, 
                "root_cause": None,
                "hypothesis": "Root cause identified by SRE (Infrastructure/Config)",
                "evidence": "See SRE Report"
            }
            
            arch_result = await delegate_to_architect(sre_result, inv_result_skipped, session_id)
            session.architect_output = arch_result
            session.confidence_scores['architect'] = arch_result.get('confidence', 0.0)
            session.rca_url = arch_result.get('rca_url')
            
            # Mark complete
            overall_confidence = session.calculate_overall_confidence()
            session.mark_completed("SUCCESS" if overall_confidence >= 0.5 else "PARTIAL_SUCCESS")
            
            logger.info(f"[{session_id}] Investigation complete (Shortcut), confidence={overall_confidence:.2f}")
            
            # Helper to format response (Duplicated for now, should be refactored)
            response_msg = f"**Investigation Complete** (Confidence: {overall_confidence:.2f})\n\n"
            if session.rca_url:
                response_msg += f"📄 **RCA Document**: {session.rca_url}\n\n"
            elif arch_result.get('rca_content'):
                 response_msg += "📄 **RCA generated** (See content below).\n\n"

            response_msg += "**Summary:**\n"
            rca_content = arch_result.get('rca_content', 'No details available.')
            response_msg += rca_content[:1000] + ("..." if len(rca_content) > 1000 else "")

            return {
                "status": "SUCCESS",
                "session_id": session_id,
                "response": response_msg,
                "confidence": overall_confidence,
                "rca_url": session.rca_url,
                "rca_content": arch_result.get('rca_content'),
                "warnings": session.warnings,
                "recommendations": arch_result.get('recommendations', []),
                "execution_trace": sre_result.get("execution_trace", [])
            }

        # Phase 3: CODE ANALYSIS (Investigator) - Normal Flow
        session.workflow.transition_to(WorkflowPhase.CODE_ANALYSIS, "Investigating code")
        sre_context = json.dumps(sre_result.get('evidence', {}), indent=2)
        inv_result = await delegate_to_investigator(
            f"{user_request}\n\nAnalyze the code based on the following evidence.",
            sre_context,
            repo_url,
            session_id
        )
        session.investigator_findings = inv_result
        session.confidence_scores['investigator'] = inv_result.get('confidence', 0.0)
        
        gate_result, reason = gate_analysis_to_synthesis(inv_result, session_id)
        gate_result, reason = gate_analysis_to_synthesis(inv_result, session_id)
        if gate_result == GateDecision.FAIL:
            # Smart Fallback: If SRE was very confident (e.g. found deletion/infra issue), proceed to RCA anyway
            sre_confidence = sre_result.get('confidence', 0.0)
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
        
        # Phase 4: SYNTHESIS (Architect)
        session.workflow.transition_to(WorkflowPhase.SYNTHESIS, "Generating RCA")
        arch_result = await delegate_to_architect(sre_result, inv_result, session_id, user_request=user_request)
        session.architect_output = arch_result
        session.confidence_scores['architect'] = arch_result.get('confidence', 0.0)
        session.rca_url = arch_result.get('rca_url')
        
        # Mark complete
        overall_confidence = session.calculate_overall_confidence()
        session.mark_completed("SUCCESS" if overall_confidence >= 0.5 else "PARTIAL_SUCCESS")
        
        logger.info(f"[{session_id}] Investigation complete, confidence={overall_confidence:.2f}")
        
        # Construct summary response for UI
        response_msg = f"**Investigation Complete** (Confidence: {overall_confidence:.2f})\n\n"
        if session.rca_url:
            response_msg += f"📄 **RCA Document**: {session.rca_url}\n\n"
        elif arch_result.get('rca_content'):
             response_msg += "📄 **RCA generated** (See content below).\n\n"

        response_msg += "**Summary:**\n"
        # Extract summary from Architect response
        rca_content = arch_result.get('rca_content', 'No details available.')
        
        # Smart Summary Extraction
        # Smart Summary Extraction
        summary_text = rca_content
        
        # Try to find Executive Summary section
        if "## 1. Executive Summary" in rca_content:
             parts = rca_content.split("## 1. Executive Summary")
             if len(parts) > 1:
                 # Take content after header, stop at next header
                 summary_text = parts[1].split("##")[0].strip()
        elif "Executive Summary" in rca_content:
             parts = rca_content.split("Executive Summary")
             if len(parts) > 1:
                 # If using standard markdown headers, split on next header
                 if "##" in parts[1]:
                    summary_text = parts[1].split("##")[0].strip()
                 else:
                    # Fallback for plain text, take first 2 paragraphs
                    paragraphs = parts[1].strip().split("\n\n")
                    summary_text = "\n\n".join(paragraphs[:2])

        # Truncate for UI safety (Increased from 500 to 2000)
        if len(summary_text) > 2000:
            summary_text = summary_text[:1997] + "..."
            
        response_msg += summary_text
        
        if session.rca_url:
             response_msg += f"\n\n[View Full RCA Document]({session.rca_url})"

        return {
            "status": "SUCCESS",
            "session_id": session_id,
            "response": response_msg,
            "confidence": overall_confidence,
            "rca_url": session.rca_url,
            "rca_content": arch_result.get('rca_content'),
            "warnings": session.warnings,
            "recommendations": arch_result.get('recommendations', []),
            # Propagate SRE traces for Verbose UI
            "execution_trace": sre_result.get("execution_trace", [])
        }
        
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
