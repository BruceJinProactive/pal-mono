"""Tests for menu processing service."""

import uuid
from datetime import UTC, datetime, timedelta

from services.menu_service.menu_processing_service import (
    JobStatus,
    MenuProcessingJob,
    MenuProcessingService,
)


class TestMenuProcessingJob:
    """Tests for MenuProcessingJob dataclass."""

    def test_job_creation(self):
        """Test creating a job with default values."""
        job_id = uuid.uuid4()
        project_id = uuid.uuid4()
        job = MenuProcessingJob(job_id=job_id, project_id=project_id)

        assert job.job_id == job_id
        assert job.project_id == project_id
        assert job.status == JobStatus.PENDING
        assert job.completed is False
        assert job.progress_percent == 0
        assert job.data == {}
        assert job.error is None
        assert isinstance(job.created_at, datetime)
        assert isinstance(job.updated_at, datetime)

    def test_job_to_dict(self):
        """Test converting job to dictionary."""
        job_id = uuid.uuid4()
        project_id = uuid.uuid4()
        job = MenuProcessingJob(
            job_id=job_id,
            project_id=project_id,
            status=JobStatus.COMPLETED,
            completed=True,
            progress_percent=100,
            data={"menu": "test menu"},
        )

        result = job.to_dict()

        assert result["job_id"] == str(job_id)
        assert result["project_id"] == str(project_id)
        assert result["status"] == "completed"
        assert result["completed"] is True
        assert result["progress_percent"] == 100
        assert result["data"] == {"menu": "test menu"}
        assert result["error"] is None
        assert "created_at" in result
        assert "updated_at" in result


class TestMenuProcessingService:
    """Tests for MenuProcessingService."""

    def setup_method(self):
        """Clear all jobs before each test."""
        MenuProcessingService._clear_all_jobs()

    def teardown_method(self):
        """Clear all jobs after each test."""
        MenuProcessingService._clear_all_jobs()

    def test_create_job(self):
        """Test creating a new job."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)

        assert isinstance(job.job_id, uuid.UUID)
        assert job.project_id == project_id
        assert job.status == JobStatus.PENDING
        assert job.completed is False
        assert job.progress_percent == 0

    def test_get_job_exists(self):
        """Test getting an existing job."""
        project_id = uuid.uuid4()
        created_job = MenuProcessingService.create_job(project_id)

        retrieved_job = MenuProcessingService.get_job(created_job.job_id)

        assert retrieved_job is not None
        assert retrieved_job.job_id == created_job.job_id
        assert retrieved_job.project_id == project_id

    def test_get_job_not_exists(self):
        """Test getting a non-existent job."""
        job_id = uuid.uuid4()
        job = MenuProcessingService.get_job(job_id)

        assert job is None

    def test_update_job_status(self):
        """Test updating job status."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)

        updated_job = MenuProcessingService.update_job(
            job_id=job.job_id, status=JobStatus.PROCESSING, progress_percent=50
        )

        assert updated_job is not None
        assert updated_job.status == JobStatus.PROCESSING
        assert updated_job.progress_percent == 50

    def test_update_job_completion(self):
        """Test marking job as completed."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)
        test_data = {"menu": "test menu content"}

        updated_job = MenuProcessingService.update_job(
            job_id=job.job_id,
            status=JobStatus.COMPLETED,
            progress_percent=100,
            completed=True,
            data=test_data,
        )

        assert updated_job is not None
        assert updated_job.status == JobStatus.COMPLETED
        assert updated_job.progress_percent == 100
        assert updated_job.completed is True
        assert updated_job.data == test_data

    def test_update_job_with_error(self):
        """Test updating job with error."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)
        error_message = "Processing failed"

        updated_job = MenuProcessingService.update_job(
            job_id=job.job_id,
            status=JobStatus.FAILED,
            completed=True,
            error=error_message,
        )

        assert updated_job is not None
        assert updated_job.status == JobStatus.FAILED
        assert updated_job.completed is True
        assert updated_job.error == error_message

    def test_update_nonexistent_job(self):
        """Test updating a job that doesn't exist."""
        job_id = uuid.uuid4()
        result = MenuProcessingService.update_job(
            job_id=job_id, status=JobStatus.PROCESSING
        )

        assert result is None

    def test_progress_percent_clamping(self):
        """Test that progress percent is clamped to 0-100."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)

        # Test upper bound
        updated_job = MenuProcessingService.update_job(
            job_id=job.job_id, progress_percent=150
        )
        assert updated_job is not None
        assert updated_job.progress_percent == 100

        # Test lower bound
        updated_job = MenuProcessingService.update_job(
            job_id=job.job_id, progress_percent=-10
        )
        assert updated_job is not None
        assert updated_job.progress_percent == 0

    def test_cleanup_expired_jobs(self):
        """Test that expired terminal jobs are cleaned up."""
        # Create a job
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)
        job_id = job.job_id

        # Mark job as completed (terminal state)
        MenuProcessingService.update_job(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            completed=True,
        )

        # Manually set updated_at to 11 minutes ago (beyond expiration)
        with MenuProcessingService._lock:
            MenuProcessingService._jobs[job_id].updated_at = datetime.now(
                UTC
            ) - timedelta(minutes=11)

        # Trigger cleanup by creating a new job
        MenuProcessingService.create_job(project_id)

        # Verify the expired job was removed
        expired_job = MenuProcessingService.get_job(job_id)
        assert expired_job is None

    def test_multiple_jobs(self):
        """Test managing multiple jobs simultaneously."""
        project_id_1 = uuid.uuid4()
        project_id_2 = uuid.uuid4()

        job1 = MenuProcessingService.create_job(project_id_1)
        job2 = MenuProcessingService.create_job(project_id_2)

        # Update first job
        MenuProcessingService.update_job(
            job_id=job1.job_id, status=JobStatus.PROCESSING, progress_percent=50
        )

        # Retrieve both jobs
        retrieved_job1 = MenuProcessingService.get_job(job1.job_id)
        retrieved_job2 = MenuProcessingService.get_job(job2.job_id)

        assert retrieved_job1 is not None
        assert retrieved_job2 is not None
        assert retrieved_job1.status == JobStatus.PROCESSING
        assert retrieved_job2.status == JobStatus.PENDING
        assert retrieved_job1.progress_percent == 50
        assert retrieved_job2.progress_percent == 0

    def test_cleanup_expired_jobs_deletion(self):
        """Test that _cleanup_expired_jobs deletes jobs older than expiration."""
        # Create a job and mark it as completed (terminal state)
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)
        job_id = job.job_id

        # Mark job as completed
        MenuProcessingService.update_job(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            completed=True,
        )

        # Manually set updated_at to 11 minutes ago (beyond expiration)
        with MenuProcessingService._lock:
            MenuProcessingService._jobs[job_id].updated_at = datetime.now(
                UTC
            ) - timedelta(minutes=MenuProcessingService.JOB_EXPIRATION_MINUTES + 1)

            # Call cleanup directly
            MenuProcessingService._cleanup_expired_jobs()

        # Verify the expired job was removed
        expired_job = MenuProcessingService.get_job(job_id)
        assert expired_job is None
