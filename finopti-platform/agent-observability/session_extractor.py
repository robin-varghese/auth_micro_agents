"""
Phoenix Session Extractor Plugin

This plugin extracts session IDs from OpenTelemetry spans to enable
Phoenix to group multiple traces under a single session.

Phoenix calls the `session_id` function for each span to determine
which session it belongs to.
"""

from typing import Optional
from phoenix.trace import SpanEvaluation


def session_id(span) -> Optional[str]:
    """
    Extract session ID from span attributes.
    
    Phoenix calls this function for each span. It should return the session ID
    that this span belongs to, or None if no session ID is found.
    
    Args:
        span: Phoenix span object with attributes
        
    Returns:
        Session ID string or None
    """
    if not span or not hasattr(span, 'attributes'):
        return None
    
    attributes = span.attributes
    if not attributes:
        return None
    
    # Priority order for session ID extraction
    # 1. session.id (OpenInference standard - recommended)
    if 'session.id' in attributes:
        return str(attributes['session.id'])
    
    # 2. session_id (custom attribute)
    if 'session_id' in attributes:
        return str(attributes['session_id'])
    
    # 3. openinference.session.id (alternative format)
    if 'openinference.session.id' in attributes:
        return str(attributes['openinference.session.id'])
    
    # 4. Fallback to user.email for grouping if available
    # This allows grouping by user even if explicit session wasn't set
    if 'user.email' in attributes:
        return f"user_{attributes['user.email']}"
    
    # No session ID found
    return None
