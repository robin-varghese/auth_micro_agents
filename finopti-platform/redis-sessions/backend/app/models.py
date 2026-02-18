from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any, Union
from datetime import datetime
import uuid

class EventHeader(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    trace_id: str
    agent_name: str
    agent_role: str
    session_id: Optional[str] = None

class EventPayload(BaseModel):
    message: str
    severity: Literal["INFO", "WARN", "ERROR", "SUCCESS"] = "INFO"
    progress: Optional[int] = None
    metadata: Dict[str, Any] = {}

class UIRendering(BaseModel):
    display_type: Literal["toast", "timeline_item", "code_block", "markdown", "alert", "step_progress", "console_log", "alert_success"]
    icon: Optional[str] = None
    color: Optional[str] = None

class AgentEvent(BaseModel):
    """
    Standard Event Schema for FinOpti Platform.
    Task 2: Message Standardization
    """
    header: EventHeader
    type: Literal["LIFECYCLE", "THOUGHT", "ACTION", "STATUS_UPDATE", "ARTIFACT", "ERROR", "TOOL_CALL", "OBSERVATION"]
    payload: EventPayload
    ui_rendering: UIRendering
    
class TroubleshootingSessionContext(BaseModel):
    """
    Structured context for a troubleshooting session.
    """
    environment: Optional[str] = None
    project_id: Optional[str] = None
    region: Optional[str] = None
    application_name: Optional[str] = None
    application_url: Optional[str] = None
    repo_url: Optional[str] = None
    repo_branch: Optional[str] = None
    github_pat: Optional[str] = None
    issue_details: Dict[str, Any] = {}
    iam_status: Literal["VERIFIED", "PENDING_ACTION", "INSUFFICIENT_PERMISSIONS", "UNKNOWN"] = "UNKNOWN"
    last_updated: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
