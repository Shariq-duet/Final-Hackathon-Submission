"""
telemetry.py — Thread-safe event store for Mission Control SSE streaming.

Every agent emits structured events through this module. Events are:
1. Stored per-job for SSE streaming to the frontend
2. Printed to stdout for Cloud Run log compatibility
"""

import time
import threading
import uuid
from datetime import datetime, timezone


class _JobStore:
    """Singleton store managing per-job telemetry events."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def create_job(self) -> str:
        """Create a new job and return its ID."""
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "status": "running",
                "events": [],
                "result": None,
                "error": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        return job_id

    def emit(self, job_id: str | None, message: str, event_type: str = "info"):
        """
        Append a timestamped event and print to stdout.

        If job_id is None (standalone agent usage), just prints.
        """
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        tag = event_type.upper()
        log_line = f"[{timestamp}] [{tag}] {message}"

        # Always print for Cloud Run / terminal compatibility
        print(log_line, flush=True)

        if job_id is None:
            return

        event = {
            "timestamp": timestamp,
            "type": event_type,
            "message": message,
        }

        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job["events"].append(event)

    def complete_job(self, job_id: str, result: dict):
        """Mark a job as successfully completed with its result payload."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job["status"] = "complete"
                job["result"] = result

    def fail_job(self, job_id: str, error: str):
        """Mark a job as failed."""
        self.emit(job_id, error, "error")
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job["status"] = "failed"
                job["error"] = error

    def get_job(self, job_id: str) -> dict | None:
        """Return a snapshot of job state."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return dict(job)  # shallow copy
            return None

    def get_events_since(self, job_id: str, cursor: int) -> tuple[list[dict], str]:
        """
        Return (new_events, current_status) since the given cursor index.
        Used by the SSE generator to yield only unseen events.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return [], "not_found"
            return job["events"][cursor:], job["status"]


# Module-level singleton — importable by all agents
store = _JobStore()


def emit(job_id: str | None, message: str, event_type: str = "info"):
    """Convenience shortcut: telemetry.emit(job_id, msg, type)"""
    store.emit(job_id, message, event_type)


def retry_with_backoff(fn, job_id: str = None, max_retries: int = 3):
    """
    Call fn(). On 429/RESOURCE_EXHAUSTED, retry with exponential backoff.
    Used by all agents to wrap Vertex AI generate_content calls.
    """
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < max_retries:
                wait = (2 ** attempt) * 5  # 5s, 10s, 20s
                emit(job_id, f"Rate limited (429). Retrying in {wait}s (attempt {attempt+1}/{max_retries})...", "warning")
                time.sleep(wait)
            else:
                raise
