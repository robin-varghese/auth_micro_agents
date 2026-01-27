"""
MATS Orchestrator - State Management

Manages investigation session state across the troubleshooting workflow.
"""
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4


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


@dataclass
class PhaseTransition:
    """Records a phase change"""
    from_phase: WorkflowPhase
    to_phase: WorkflowPhase
    timestamp: datetime
    reason: Optional[str] = None


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


# In-memory session storage (TODO: replace with persistent storage)
_sessions: Dict[str, InvestigationSession] = {}


def create_session(user_id: str, project_id: str, repo_url: str) -> InvestigationSession:
    """Create a new investigation session"""
    session = InvestigationSession(
        user_id=user_id,
        project_id=project_id,
        repo_url=repo_url
    )
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> Optional[InvestigationSession]:
    """Retrieve a session by ID"""
    return _sessions.get(session_id)


def update_session(session: InvestigationSession):
    """Update a session in storage"""
    _sessions[session.session_id] = session
