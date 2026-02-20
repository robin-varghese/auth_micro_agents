
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
    def update_result(cls, job_id: str, result: Any, status: str = "COMPLETED"):
        if job_id in cls._jobs:
            cls._jobs[job_id]["result"] = result
            cls._jobs[job_id]["status"] = status
            cls.add_event(job_id, "SYSTEM", f"Job {status}", "orchestrator")

    @classmethod
    def update_job(cls, job_id: str, updates: Dict[str, Any]):
        """Update arbitrary job fields"""
        if job_id in cls._jobs:
            cls._jobs[job_id].update(updates)
            if "status" in updates:
                cls.add_event(job_id, "SYSTEM", f"Job status updated to {updates['status']}", "orchestrator")

    @classmethod
    def fail_job(cls, job_id: str, error: str):
        if job_id in cls._jobs:
            cls._jobs[job_id]["error"] = error
            cls._jobs[job_id]["status"] = "FAILED"
            cls.add_event(job_id, "ERROR", error, "orchestrator")

    @classmethod
    def get_job(cls, job_id: str) -> Optional[Dict[str, Any]]:
        return cls._jobs.get(job_id)

    @classmethod
    def get_active_job_for_user(cls, user_email: str) -> Optional[str]:
        """Find a running or waiting job for a user"""
        # Linear search is fine for in-memory POC
        for job in cls._jobs.values():
            # Check if job belongs to user (heuristic via user_request or metadata if we had it)
            # For now, we only have user_request. Real impl would store user_email in job.
            # We'll rely on the caller to handle email matching if not stored, 
            # BUT we should store it. Let's assume we store it in create_job or update it.
            if job.get("user_email") == user_email and job.get("status") in ["RUNNING", "WAITING_FOR_USER"]:
                return job["id"]
        return None

    @classmethod
    def create_job(cls, user_request: str, user_email: str = "unknown") -> str:
        job_id = str(uuid.uuid4())
        cls._jobs[job_id] = {
            "id": job_id,
            "status": "RUNNING",
            "created_at": time.time(),
            "user_request": user_request,
            "user_email": user_email,
            "events": [], 
            "result": None,
            "error": None
        }
        cls.add_event(job_id, "SYSTEM", "Job started", "orchestrator")
        return job_id

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
