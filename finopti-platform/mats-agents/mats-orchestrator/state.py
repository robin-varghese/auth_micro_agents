import os
import json
import logging
import asyncio
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis_session_store")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Global Redis Client
_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        logger.info(f"Initializing Redis Client: host={REDIS_HOST}, port={REDIS_PORT}, db={REDIS_DB}")
        _redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    return _redis_client

class WorkflowPhase(Enum):
    """Investigation workflow phases"""
    INTAKE = "intake"
    PLANNING = "planning"
    TRIAGE = "triage"
    CODE_ANALYSIS = "code_analysis"
    SYNTHESIS = "synthesis"
    PUBLISH = "publish"
    COMPLETED = "completed"
    FAILED = "failed"
    
    def to_dict(self):
        return self.value

@dataclass
class PhaseTransition:
    """Records a phase change"""
    from_phase: WorkflowPhase
    to_phase: WorkflowPhase
    timestamp: datetime
    reason: Optional[str] = None
    
    def to_dict(self):
        return {
            "from_phase": self.from_phase.value,
            "to_phase": self.to_phase.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            from_phase=WorkflowPhase(data["from_phase"]),
            to_phase=WorkflowPhase(data["to_phase"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            reason=data.get("reason")
        )


@dataclass
class WorkflowState:
    """State of the current investigation workflow"""
    current_phase: WorkflowPhase = WorkflowPhase.INTAKE
    phase_transitions: List[PhaseTransition] = field(default_factory=list)
    
    def transition_to(self, new_phase: WorkflowPhase, reason: Optional[str] = None):
        """Record a phase transition"""
        transition = PhaseTransition(
            from_phase=self.current_phase,
            to_phase=new_phase,
            timestamp=datetime.utcnow(),
            reason=reason
        )
        self.phase_transitions.append(transition)
        self.current_phase = new_phase
        
    def to_dict(self):
        return {
            "current_phase": self.current_phase.value,
            "phase_transitions": [t.to_dict() for t in self.phase_transitions]
        }
        
    @classmethod
    def from_dict(cls, data):
        state = cls(current_phase=WorkflowPhase(data["current_phase"]))
        if "phase_transitions" in data:
            state.phase_transitions = [PhaseTransition.from_dict(t) for t in data["phase_transitions"]]
        return state


@dataclass
class InvestigationSession:
    """Complete investigation session state"""
    # Identifiers
    session_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "default"
    project_id: Optional[str] = None
    repo_url: Optional[str] = None
    
    # Workflow tracking
    workflow: WorkflowState = field(default_factory=WorkflowState)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Evidence collection
    sre_findings: Optional[Dict[str, Any]] = None
    investigator_findings: Optional[Dict[str, Any]] = None
    architect_output: Optional[Dict[str, Any]] = None
    
    # Quality metrics
    total_tool_calls: int = 0
    failed_calls: int = 0
    retry_attempts: Dict[str, int] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    
    # Error tracking
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Final artifacts
    rca_url: Optional[str] = None
    status: str = "IN_PROGRESS"
    
    def add_blocker(self, error_code: str, message: str):
        """Add a blocker that halts the workflow"""
        blocker = f"{error_code}: {message}"
        self.blockers.append(blocker)
        
    def add_warning(self, message: str):
        """Add a non-blocking warning"""
        self.warnings.append(message)
        
    def increment_retry(self, agent: str):
        """Increment retry counter for an agent"""
        if agent not in self.retry_attempts:
            self.retry_attempts[agent] = 0
        self.retry_attempts[agent] += 1
        
    def get_retry_count(self, agent: str) -> int:
        """Get retry count for an agent"""
        return self.retry_attempts.get(agent, 0)
    
    def calculate_overall_confidence(self) -> float:
        """Calculate overall confidence from agent scores"""
        if not self.confidence_scores:
            return 0.0
        return sum(self.confidence_scores.values()) / len(self.confidence_scores)
    
    def mark_completed(self, status: str = "SUCCESS"):
        """Mark investigation as completed"""
        self.completed_at = datetime.utcnow()
        self.status = status
        self.workflow.transition_to(
            WorkflowPhase.COMPLETED,
            reason=f"Investigation {status.lower()}"
        )
        
    def to_dict(self):
        d = asdict(self)
        d["workflow"] = self.workflow.to_dict()
        d["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            d["completed_at"] = self.completed_at.isoformat()
        return d
        
    @classmethod
    def from_dict(cls, data):
        # Handle Clean datetime parsing
        started_at = datetime.fromisoformat(data["started_at"])
        completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        
        # Remove complex fields to init via standard args first, then populate
        workflow_data = data.pop("workflow", None)
        
        # Clean basic args
        basic_args = {k: v for k, v in data.items() if k in cls.__annotations__ and k not in ["workflow", "started_at", "completed_at"]}
        
        session = cls(**basic_args)
        session.started_at = started_at
        session.completed_at = completed_at
        
        if workflow_data:
            session.workflow = WorkflowState.from_dict(workflow_data)
            
        return session


# In-memory session storage (Fallback)
_sessions: Dict[str, InvestigationSession] = {}


async def create_session(user_id: str, project_id: str, repo_url: str, provided_session_id: str = None) -> InvestigationSession:
    """Create a new investigation session
    
    Args:
        user_id: User identifier
        project_id: GCP project ID
        repo_url: Repository URL
        provided_session_id: Optional session ID from UI (for Phoenix tracking)
    """
    # Only pass session_id if provided, otherwise let dataclass generate UUID
    kwargs = {
        "user_id": user_id,
        "project_id": project_id,
        "repo_url": repo_url
    }
    if provided_session_id:
        kwargs["session_id"] = provided_session_id
        
    session = InvestigationSession(**kwargs)
    # Save to Redis
    await update_session(session)
    return session


async def get_session(session_id: str) -> Optional[InvestigationSession]:
    """Retrieve a session by ID (Try Redis, then Memory)"""
    # Try Redis
    try:
         client = get_redis_client()
         val = await client.get(f"session:{session_id}")
         if val:
             return InvestigationSession.from_dict(json.loads(val))
    except Exception as e:
        logger.warning(f"Redis get failed: {e}")
            
    return _sessions.get(session_id)


async def update_session(session: InvestigationSession):
    """Update a session in storage"""
    # Update Memory
    _sessions[session.session_id] = session
    
    # Update Redis
    try:
        logger.info(f"Attempting to save session {session.session_id} to Redis...")
        client = get_redis_client()
        logger.info(f"Redis client created: {client}")
        data = json.dumps(session.to_dict())
        logger.info(f"Session data to save: {len(data)} bytes")
        await client.set(f"session:{session.session_id}", data)
        logger.info(f"Successfully saved session {session.session_id} to Redis")
    except Exception as e:
        logger.error(f"Redis set failed completely: {e}", exc_info=True)
