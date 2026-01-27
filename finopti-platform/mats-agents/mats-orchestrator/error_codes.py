"""
MATS Orchestrator - Error Code Taxonomy

Defines error codes and recovery strategies for troubleshooting workflow.
"""
from enum import Enum
from typing import Dict, Callable, Any
from dataclasses import dataclass


class ErrorCode(Enum):
    """Standard error codes for MATS workflows"""
    E001 = "NO_LOGS_FOUND"
    E002 = "PERMISSION_DENIED"
    E003 = "REPO_NOT_ACCESSIBLE"
    E004 = "STACK_TRACE_UNRECOGNIZED"
    E005 = "VERSION_SHA_NOT_FOUND"
    E006 = "LOW_CONFIDENCE"


@dataclass
class ErrorMetadata:
    """Metadata for an error code"""
    code: ErrorCode
    description: str
    user_message: str
    recovery_strategy: str
    is_blocker: bool = False  # Does this halt the workflow?
    

# Error code definitions with recovery strategies
ERROR_DEFINITIONS: Dict[ErrorCode, ErrorMetadata] = {
    ErrorCode.E001: ErrorMetadata(
        code=ErrorCode.E001,
        description="No logs found in the specified time window",
        user_message="No error logs were found for the specified service and time period.",
        recovery_strategy="EXPAND_TIME_WINDOW",
        is_blocker=False
    ),
    
    ErrorCode.E002: ErrorMetadata(
        code=ErrorCode.E002,
        description="Permission denied accessing GCP resources",
        user_message="Insufficient permissions to access logs/metrics. Please grant the following IAM roles: roles/logging.viewer, roles/monitoring.viewer",
        recovery_strategy="REQUEST_PERMISSION",
        is_blocker=True
    ),
    
    ErrorCode.E003: ErrorMetadata(
        code=ErrorCode.E003,
        description="Code repository not accessible",
        user_message="Unable to access the GitHub repository. Please verify the repository URL and Personal Access Token.",
        recovery_strategy="VERIFY_PAT",
        is_blocker=True
    ),
    
    ErrorCode.E004: ErrorMetadata(
        code=ErrorCode.E004,
        description="Stack trace format not recognized",
        user_message="The error stack trace could not be parsed. Proceeding with full log text analysis.",
        recovery_strategy="USE_REGEX_EXTRACTION",
        is_blocker=False
    ),
    
    ErrorCode.E005: ErrorMetadata(
        code=ErrorCode.E005,
        description="Version/commit SHA not found in logs",
        user_message="Could not determine the exact code version. Analysis will use the 'main' branch.",
        recovery_strategy="FLAG_UNCERTAINTY",
        is_blocker=False
    ),
    
    ErrorCode.E006: ErrorMetadata(
        code=ErrorCode.E006,
        description="Low confidence in root cause analysis",
        user_message="The analysis has low confidence (<50%). Human review is recommended.",
        recovery_strategy="SUGGEST_HUMAN_REVIEW",
        is_blocker=False
    ),
}


def get_error_info(code: ErrorCode) -> ErrorMetadata:
    """Get error metadata for a code"""
    return ERROR_DEFINITIONS[code]


def is_blocker(code: ErrorCode) -> bool:
    """Check if error code blocks workflow"""
    return ERROR_DEFINITIONS[code].is_blocker


def get_user_message(code: ErrorCode) -> str:
    """Get user-friendly message for error"""
    return ERROR_DEFINITIONS[code].user_message


def get_recovery_strategy(code: ErrorCode) -> str:
    """Get recovery strategy name"""
    return ERROR_DEFINITIONS[code].recovery_strategy


# Recovery strategy implementations
class RecoveryStrategies:
    """Recovery strategy implementations"""
    
    @staticmethod
    def expand_time_window(context: Dict[str, Any]) -> Dict[str, Any]:
        """Expand log search time window"""
        current_hours = context.get('hours_ago', 1)
        new_hours = min(current_hours * 2, 24)  # Cap at 24 hours
        return {
            'action': 'retry_sre',
            'params': {'hours_ago': new_hours},
            'message': f"Expanding search window to {new_hours} hours"
        }
    
    @staticmethod
    def request_permission(context: Dict[str, Any]) -> Dict[str, Any]:
        """Request user to grant permissions"""
        return {
            'action': 'escalate_to_user',
            'required_roles': ['roles/logging.viewer', 'roles/monitoring.viewer'],
            'message': "Please grant the required IAM permissions and retry."
        }
    
    @staticmethod
    def verify_pat(context: Dict[str, Any]) -> Dict[str, Any]:
        """Request user to verify GitHub PAT"""
        return {
            'action': 'escalate_to_user',
            'message': "Please verify your GitHub Personal Access Token has 'repo' scope."
        }
    
    @staticmethod
    def use_regex_extraction(context: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback to regex-based extraction"""
        return {
            'action': 'continue_with_warning',
            'message': "Using fallback extraction. Results may be less accurate."
        }
    
    @staticmethod
    def flag_uncertainty(context: Dict[str, Any]) -> Dict[str, Any]:
        """Flag version uncertainty in final RCA"""
        return {
            'action': 'add_limitation',
            'limitation': "Analysis based on 'main' branch. Production version unknown.",
            'message': "Proceeding with 'main' branch code analysis."
        }
    
    @staticmethod
    def suggest_human_review(context: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest human review for low confidence"""
        return {
            'action': 'flag_in_rca',
            'confidence': context.get('confidence', 0.0),
            'message': "Low confidence. Human review recommended."
        }


# Map recovery strategy names to implementations
RECOVERY_IMPLEMENTATIONS: Dict[str, Callable] = {
    "EXPAND_TIME_WINDOW": RecoveryStrategies.expand_time_window,
    "REQUEST_PERMISSION": RecoveryStrategies.request_permission,
    "VERIFY_PAT": RecoveryStrategies.verify_pat,
    "USE_REGEX_EXTRACTION": RecoveryStrategies.use_regex_extraction,
    "FLAG_UNCERTAINTY": RecoveryStrategies.flag_uncertainty,
    "SUGGEST_HUMAN_REVIEW": RecoveryStrategies.suggest_human_review,
}


def execute_recovery(code: ErrorCode, context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute recovery strategy for an error code"""
    strategy_name = get_recovery_strategy(code)
    strategy_func = RECOVERY_IMPLEMENTATIONS.get(strategy_name)
    
    if not strategy_func:
        return {
            'action': 'no_recovery',
            'message': f"No recovery strategy for {code.value}"
        }
    
    return strategy_func(context)
