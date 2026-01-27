"""
MATS Orchestrator - Validators

Schema validation for agent outputs.
"""
import json
import logging
from typing import Dict, Any, Optional, Tuple
from pydantic import ValidationError

from schemas import SREOutput, InvestigatorOutput, ArchitectOutput

logger = logging.getLogger(__name__)


def extract_json_from_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from agent response (handles markdown code blocks).
    
    Returns:
        Parsed JSON dict or None if extraction fails
    """
    try:
        # Try direct parse first
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code blocks
    if "```json" in response_text:
        try:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        except (IndexError, json.JSONDecodeError):
            pass
    
    if "```" in response_text:
        try:
            json_str = response_text.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
        except (IndexError, json.JSONDecodeError):
            pass
    
    return None


def validate_sre_output(response: Dict[str, Any], session_id: str) -> Tuple[bool, Optional[SREOutput], Optional[str]]:
    """
    Validate SRE agent output.
    
    Returns:
        (is_valid, parsed_output, error_message)
    """
    try:
        response_text = response.get("response", "")
        output_dict = extract_json_from_response(response_text)
        
        if not output_dict:
            return (False, None, "Could not extract JSON from response")
        
        sre_output = SREOutput(**output_dict)
        logger.info(f"[{session_id}] SRE output validated: status={sre_output.status}")
        return (True, sre_output, None)
        
    except ValidationError as e:
        error_msg = f"Schema validation failed: {e}"
        logger.error(f"[{session_id}] {error_msg}")
        return (False, None, error_msg)
    except Exception as e:
        error_msg = f"Validation error: {e}"
        logger.error(f"[{session_id}] {error_msg}")
        return (False, None, error_msg)


def validate_investigator_output(response: Dict[str, Any], session_id: str) -> Tuple[bool, Optional[InvestigatorOutput], Optional[str]]:
    """
    Validate Investigator agent output.
    
    Returns:
        (is_valid, parsed_output, error_message)
    """
    try:
        response_text = response.get("response", "")
        output_dict = extract_json_from_response(response_text)
        
        if not output_dict:
            return (False, None, "Could not extract JSON from response")
        
        inv_output = InvestigatorOutput(**output_dict)
        logger.info(f"[{session_id}] Investigator output validated: status={inv_output.status}")
        return (True, inv_output, None)
        
    except ValidationError as e:
        error_msg = f"Schema validation failed: {e}"
        logger.error(f"[{session_id}] {error_msg}")
        return (False, None, error_msg)
    except Exception as e:
        error_msg = f"Validation error: {e}"
        logger.error(f"[{session_id}] {error_msg}")
        return (False, None, error_msg)


def validate_architect_output(response: Dict[str, Any], session_id: str) -> Tuple[bool, Optional[ArchitectOutput], Optional[str]]:
    """
    Validate Architect agent output.
    
    Returns:
        (is_valid, parsed_output, error_message)
    """
    try:
        response_text = response.get("response", "")
        output_dict = extract_json_from_response(response_text)
        
        if not output_dict:
            # If JSON extraction fails, try to use raw response as RCA content
            logger.warning(f"[{session_id}] Could not extract JSON, using raw response")
            output_dict = {
                "status": "PARTIAL",
                "confidence": 0.5,
                "rca_content": response_text,
                "limitations": ["Output format not standard, using raw response"]
            }
        
        arch_output = ArchitectOutput(**output_dict)
        logger.info(f"[{session_id}] Architect output validated: status={arch_output.status}")
        return (True, arch_output, None)
        
    except ValidationError as e:
        error_msg = f"Schema validation failed: {e}"
        logger.error(f"[{session_id}] {error_msg}")
        return (False, None, error_msg)
    except Exception as e:
        error_msg = f"Validation error: {e}"
        logger.error(f"[{session_id}] {error_msg}")
        return (False, None, error_msg)
