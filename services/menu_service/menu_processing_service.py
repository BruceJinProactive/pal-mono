"""
Menu processing job tracker service.

This service manages in-memory state for menu upload processing jobs.
Jobs expire after 10 minutes to prevent memory leaks.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Optional


class JobStatus(str, Enum):
    """Job status enum"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class MenuProcessingJob:
    """Menu processing job data"""

    job_id: uuid.UUID
    project_id: uuid.UUID
    status: JobStatus = JobStatus.PENDING
    completed: bool = False
    progress_percent: int = 0
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """Convert job to dictionary for API response"""
        return {
            "job_id": str(self.job_id),
            "project_id": str(self.project_id),
            "status": self.status.value,
            "completed": self.completed,
            "progress_percent": self.progress_percent,
            "data": self.data,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class MenuProcessingService:
    """
    In-memory service for tracking menu processing jobs.

    This service uses a dictionary to store job state and automatically
    cleans up terminal jobs (completed/failed) older than 10 minutes.

    LIMITATION: This is a single-process in-memory store. Jobs are not shared
    across workers or preserved across restarts. For production multi-worker
    deployments, consider using Redis or another shared persistence layer.
    """

    # Class-level storage for jobs (shared across all instances)
    _jobs: dict[uuid.UUID, MenuProcessingJob] = {}
    _lock = Lock()

    # Job expiration time (10 minutes for terminal jobs)
    JOB_EXPIRATION_MINUTES = 10

    # Terminal statuses that can be expired
    TERMINAL_STATUSES = {JobStatus.COMPLETED, JobStatus.FAILED}

    @classmethod
    def create_job(cls, project_id: uuid.UUID) -> MenuProcessingJob:
        """
        Create a new menu processing job.

        Args:
            project_id: UUID of the project

        Returns:
            Created job with unique job_id
        """
        job_id = uuid.uuid4()
        job = MenuProcessingJob(
            job_id=job_id,
            project_id=project_id,
            status=JobStatus.PENDING,
            completed=False,
            progress_percent=0,
        )

        with cls._lock:
            cls._jobs[job_id] = job
            # Clean up old jobs
            cls._cleanup_expired_jobs()

        return job

    @classmethod
    def get_job(cls, job_id: uuid.UUID) -> Optional[MenuProcessingJob]:
        """
        Get a job by ID.

        Args:
            job_id: UUID of the job

        Returns:
            Job if found and not expired, None otherwise
        """
        with cls._lock:
            cls._cleanup_expired_jobs()
            return cls._jobs.get(job_id)

    @classmethod
    def update_job(
        cls,
        job_id: uuid.UUID,
        status: Optional[JobStatus] = None,
        progress_percent: Optional[int] = None,
        data: Optional[dict] = None,
        error: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> Optional[MenuProcessingJob]:
        """
        Update job status and progress.

        Args:
            job_id: UUID of the job
            status: New status (optional)
            progress_percent: Progress percentage 0-100 (optional)
            data: Data to store (optional)
            error: Error message (optional)
            completed: Whether job is completed (optional)

        Returns:
            Updated job if found, None otherwise
        """
        with cls._lock:
            job = cls._jobs.get(job_id)
            if not job:
                return None

            if status is not None:
                job.status = status
            if progress_percent is not None:
                job.progress_percent = min(100, max(0, progress_percent))
            if data is not None:
                job.data = data
            if error is not None:
                job.error = error
            if completed is not None:
                job.completed = completed

            job.updated_at = datetime.now(UTC)
            return job

    @classmethod
    def _cleanup_expired_jobs(cls) -> None:
        """
        Remove terminal jobs (completed/failed) older than JOB_EXPIRATION_MINUTES.
        Only removes jobs that are in a terminal state to avoid deleting in-flight jobs.
        Uses updated_at instead of created_at to measure age since last update.
        This method should be called with _lock already acquired.
        """
        now = datetime.now(UTC)
        expiration_time = timedelta(minutes=cls.JOB_EXPIRATION_MINUTES)

        expired_job_ids = [
            job_id
            for job_id, job in cls._jobs.items()
            if job.status in cls.TERMINAL_STATUSES
            and now - job.updated_at > expiration_time
        ]

        for job_id in expired_job_ids:
            del cls._jobs[job_id]

    @classmethod
    def _clear_all_jobs(cls) -> None:
        """Clear all jobs (for testing purposes only)"""
        with cls._lock:
            cls._jobs.clear()
