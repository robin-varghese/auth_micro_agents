
import asyncio
import uuid
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

class JobManager:
    """
    Simple In-Memory Job Manager.
    Stores job status, results, and an event log for UI polling.
    """
    _jobs: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def create_job(cls, user_request: str) -> str:
        job_id = str(uuid.uuid4())
        cls._jobs[job_id] = {
            "id": job_id,
            "status": "RUNNING",
            "created_at": time.time(),
            "user_request": user_request,
            "events": [],  # List of {timestamp, type, message, source}
            "result": None,
            "error": None
        }
        cls.add_event(job_id, "SYSTEM", "Job started", "orchestrator")
        return job_id

    @classmethod
    def get_job(cls, job_id: str) -> Optional[Dict[str, Any]]:
        return cls._jobs.get(job_id)

    @classmethod
    def update_result(cls, job_id: str, result: Any, status: str = "COMPLETED"):
        if job_id in cls._jobs:
            cls._jobs[job_id]["result"] = result
            cls._jobs[job_id]["status"] = status
            cls.add_event(job_id, "SYSTEM", f"Job {status}", "orchestrator")

    @classmethod
    def fail_job(cls, job_id: str, error: str):
        if job_id in cls._jobs:
            cls._jobs[job_id]["error"] = error
            cls._jobs[job_id]["status"] = "FAILED"
            cls.add_event(job_id, "ERROR", error, "orchestrator")

    @classmethod
    def add_event(cls, job_id: str, event_type: str, message: str, source: str = "orchestrator"):
        if job_id in cls._jobs:
            event = {
                "timestamp": datetime.utcnow().isoformat(),
                "type": event_type,
                "message": message,
                "source": source
            }
            cls._jobs[job_id]["events"].append(event)
            # Keep log size manageable
            if len(cls._jobs[job_id]["events"]) > 200:
                cls._jobs[job_id]["events"] = cls._jobs[job_id]["events"][-200:]
