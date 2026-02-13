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
    
    # We also need the routing key to know WHERE to publish
    # In a real system, this might be inferred from context, 
    # but for this specific Gateway, we'll ask the client to provide the target session
    # OR we can keep it separate from the event payload. 
    # Let's keep it separate in the API request model.
