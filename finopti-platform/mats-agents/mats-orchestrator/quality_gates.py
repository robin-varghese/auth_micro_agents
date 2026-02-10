"""
MATS Orchestrator - Quality Gates

Validation checkpoints between workflow phases.
"""
import logging
from typing import Dict, Any, Optional, Tuple
from enum import Enum

from schemas import SREOutput, InvestigatorOutput, ArchitectOutput
from error_codes import ErrorCode

logger = logging.getLogger(__name__)


class GateDecision(Enum):
    """Quality gate decision"""
    PASS = "pass"
    FAIL = "fail"
    RETRY = "retry"


def gate_planning_to_triage(plan: Dict[str, Any], session_id: str) -> Tuple[GateDecision, Optional[str]]:
    """
    Validate plan structure before starting triage.
    
    Returns:
        (decision, reason)
    """
    if not plan:
        return (GateDecision.FAIL, "No plan generated")
    
    steps = plan.get('steps', [])
    if not steps:
        return (GateDecision.FAIL, "Plan has no steps")
    
    # Verify first step is SRE-related
    first_step = steps[0]
    if 'sre' not in first_step.get('assigned_lead', '').lower():
        logger.warning(f"[{session_id}] First step should be SRE, got {first_step.get('assigned_lead')}")
    
    logger.info(f"[{session_id}] Planning gate PASSED - {len(steps)} steps")
    return (GateDecision.PASS, f"Valid plan with {len(steps)} steps")


def gate_triage_to_analysis(
    sre_output: Dict[str, Any],
    session_id: str
) -> Tuple[GateDecision, Optional[str]]:
    """
    Validate SRE evidence before proceeding to code analysis.
    
    Returns:
        (decision, reason)
    """
    try:
        sre = SREOutput(**sre_output)
    except Exception as e:
        return (GateDecision.FAIL, f"Invalid SRE output schema: {e}")
    
    # Check status
    if sre.status == "FAILURE":
        return (GateDecision.FAIL, "SRE found no actionable evidence")
    
    # Check for minimum evidence
    if not sre.error_signature and not sre.stack_trace:
        if sre.blockers:
            return (GateDecision.FAIL, f"SRE blocked: {sre.blockers[0]}")
        return (GateDecision.RETRY, "No error signature found, retry with expanded window")
    
    # Check confidence
    sre_conf = sre.confidence if sre.confidence is not None else 0.0
    if sre_conf < 0.3:
        return (GateDecision.RETRY, f"Low SRE confidence ({sre_conf})")
    
    logger.info(f"[{session_id}] Triage gate PASSED - confidence={sre.confidence}")
    return (GateDecision.PASS, "Sufficient evidence for analysis")


def gate_analysis_to_synthesis(
    investigator_output: Dict[str, Any],
    session_id: str
) -> Tuple[GateDecision, Optional[str]]:
    """
    Validate Investigator findings before synthesis.
    
    Returns:
        (decision, reason)
    """
    try:
        inv = InvestigatorOutput(**investigator_output)
    except Exception as e:
        return (GateDecision.FAIL, f"Invalid Investigator output: {e}")
    
    # Check status
    if inv.status == "INSUFFICIENT_DATA":
        if inv.blockers:
            return (GateDecision.FAIL, f"Investigator blocked: {inv.blockers[0]}")
        return (GateDecision.RETRY, "Insufficient data for root cause")
    
    # Even hypothesis is acceptable if confidence > 0.3
    inv_conf = inv.confidence if inv.confidence is not None else 0.0
    if inv_conf < 0.3:
        return (GateDecision.FAIL, f"Very low confidence ({inv_conf}), cannot proceed")
    
    # Prefer definitive root cause, but accept hypothesis
    if inv.status == "HYPOTHESIS":
        logger.warning(f"[{session_id}] Proceeding with hypothesis (confidence={inv.confidence})")
    
    logger.info(f"[{session_id}] Analysis gate PASSED - status={inv.status}")
    return (GateDecision.PASS, f"Analysis complete ({inv.status})")


def gate_synthesis_to_publish(
    architect_output: Dict[str, Any],
    session_id: str
) -> Tuple[GateDecision, Optional[str]]:
    """
    Validate RCA completeness before publishing.
    
    Returns:
        (decision, reason)
    """
    try:
        arch = ArchitectOutput(**architect_output)
    except Exception as e:
        return (GateDecision.FAIL, f"Invalid Architect output: {e}")
    
    # Check status
    if arch.status == "FAILURE":
        return (GateDecision.FAIL, "Architect failed to generate RCA")
    
    # Check RCA content exists
    if not arch.rca_content or len(arch.rca_content) < 100:
        return (GateDecision.RETRY, "RCA content too short or missing")
    
    # Verify key sections (basic check)
    required_sections = ["Root Cause", "Summary"]
    missing = [s for s in required_sections if s.lower() not in arch.rca_content.lower()]
    if missing:
        logger.warning(f"[{session_id}] RCA missing sections: {missing}")
    
    logger.info(f"[{session_id}] Synthesis gate PASSED")
    return (GateDecision.PASS, "RCA generated successfully")
