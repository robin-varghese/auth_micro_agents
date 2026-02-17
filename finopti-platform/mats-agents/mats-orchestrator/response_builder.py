"""
MATS Orchestrator - Response Builder

Extracted from agent.py per REFACTORING_GUIDELINE.md (Step 1).
Consolidates the 3 duplicated response-formatting blocks into a single reusable function.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def safe_confidence(value) -> float:
    """Safely extract confidence score, guarding against None.
    
    Used 4+ times across agent.py to normalize confidence values.
    """
    return value if value is not None else 0.0


def extract_executive_summary(rca_content: Any, max_length: int = 2000) -> str:
    """Extract executive summary from RCA content (String or Dict).
    
    Args:
        rca_content: Full RCA content (JSON dict or Markdown string)
        max_length: Maximum summary length for UI safety
        
    Returns:
        Extracted or truncated summary text
    """
    if not rca_content:
        return "No details available."
    
    summary_text = ""
    
    # Handle Dictionary (JSON RCA)
    if isinstance(rca_content, dict):
        # Try to extract from standard JSON schema
        exec_sum = rca_content.get("executive_summary", {})
        if isinstance(exec_sum, dict):
            summary_text = exec_sum.get("summary_text", "")
        elif isinstance(exec_sum, str):
            summary_text = exec_sum
            
        # Fallback: if empty, try to dump whole dict (truncated)
        if not summary_text:
            summary_text = str(rca_content)
            
    else:
        # Handle String (Legacy Markdown)
        summary_text = str(rca_content)
        
        # Try to find Executive Summary section (## 1. format)
        if "## 1. Executive Summary" in summary_text:
            parts = summary_text.split("## 1. Executive Summary")
            if len(parts) > 1:
                # Take content after header, stop at next header
                summary_text = parts[1].split("##")[0].strip()
        elif "Executive Summary" in summary_text:
            parts = summary_text.split("Executive Summary")
            if len(parts) > 1:
                # If using standard markdown headers, split on next header
                if "##" in parts[1]:
                    summary_text = parts[1].split("##")[0].strip()
                else:
                    # Fallback for plain text, take first 2 paragraphs
                    paragraphs = parts[1].strip().split("\n\n")
                    summary_text = "\n\n".join(paragraphs[:2])
    
    # Truncate for UI safety
    if len(summary_text) > max_length:
        summary_text = summary_text[:max_length - 3] + "..."
    
    return summary_text


def format_investigation_response(
    session,
    arch_result: Dict[str, Any],
    sre_result: Dict[str, Any] = None,
    session_id: str = None,
) -> Dict[str, Any]:
    """Build the final investigation response dict.
    
    Replaces the 3 duplicated response-formatting blocks in run_investigation_async.
    
    Args:
        session: Investigation session object
        arch_result: Architect agent results (must have rca_content, rca_url, recommendations, confidence)
        sre_result: SRE agent results (optional, for execution_trace propagation)
        session_id: Session ID for response metadata
        
    Returns:
        Standardized investigation response dict
    """
    # Calculate overall confidence
    overall_confidence = session.calculate_overall_confidence()
    status = "SUCCESS" if overall_confidence >= 0.5 else "PARTIAL_SUCCESS"
    session.mark_completed(status)
    
    # Store architect results on session
    session.architect_output = arch_result
    arch_conf = safe_confidence(arch_result.get('confidence'))
    session.confidence_scores['architect'] = arch_conf
    session.rca_url = arch_result.get('rca_url')
    
    # Build response message
    response_msg = f"**Investigation Complete** (Confidence: {overall_confidence:.2f})\n\n"
    
    if session.rca_url:
        response_msg += f"📄 **RCA Document**: {session.rca_url}\n\n"
    elif arch_result.get('rca_content'):
        response_msg += "📄 **RCA generated** (See content below).\n\n"
    
    response_msg += "**Summary:**\n"
    rca_content = arch_result.get('rca_content', 'No details available.')
    response_msg += extract_executive_summary(rca_content)
    
    if session.rca_url:
        response_msg += f"\n\n[View Full RCA Document]({session.rca_url})"
    
    logger.info(f"[{session_id or session.session_id}] Investigation complete, confidence={overall_confidence:.2f}")
    
    return {
        "status": "SUCCESS",
        "session_id": session_id or session.session_id,
        "response": response_msg,
        "confidence": overall_confidence,
        "rca_url": session.rca_url,
        "rca_content": arch_result.get('rca_content'),
        "warnings": session.warnings,
        "recommendations": arch_result.get('recommendations', []),
        "execution_trace": sre_result.get("execution_trace", []) if sre_result else []
    }
