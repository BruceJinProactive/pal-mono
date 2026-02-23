"""Tests for menu upload endpoints."""

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from api.routes.admin import admin_router
from api.routes.admin._onboarding import (
    _verify_project_access,
    get_menu_processing_status,
    process_menu_upload_background,
    upload_menu_api,
)
from api.schemas.admin.onboarding import MenuUploaderResponse
from db.tables import Project
from services.menu_service.menu_processing_service import (
    JobStatus,
    MenuProcessingService,
)


@pytest.fixture
def mock_context():
    """Create a mock user context."""
    context = MagicMock()
    context.username = str(uuid.uuid4())
    context.role = MagicMock()
    context.role.value = "Admin"
    return context


@pytest.fixture
def mock_upload_file():
    """Create a mock upload file."""
    file_content = b"fake image content"
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "menu.jpg"
    mock_file.content_type = "image/jpeg"
    mock_file.file = BytesIO(file_content)
    mock_file.read = AsyncMock(return_value=file_content)
    return mock_file


@pytest.fixture
def mock_pdf_file():
    """Create a mock PDF file."""
    file_content = b"%PDF-1.4 fake pdf"
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "menu.pdf"
    mock_file.content_type = "application/pdf"
    mock_file.file = BytesIO(file_content)
    mock_file.read = AsyncMock(return_value=file_content)
    return mock_file


@pytest.fixture(autouse=True)
def clear_jobs():
    """Clear all jobs before and after each test."""
    MenuProcessingService._clear_all_jobs()
    yield
    MenuProcessingService._clear_all_jobs()


class TestUploadMenuApi:
    """Tests for upload_menu_api endpoint."""

    @pytest.mark.asyncio
    async def test_upload_single_image(self, mock_context, mock_upload_file):
        """Test uploading a single image file."""
        project_id = uuid.uuid4()

        with patch("api.routes.admin._onboarding.asyncio.create_task") as mock_task:
            response = await upload_menu_api(mock_upload_file, mock_context, project_id)

        assert isinstance(response, MenuUploaderResponse)
        assert response.status == "accepted"
        assert response.project_id == str(project_id)
        assert response.job_id is not None
        assert uuid.UUID(response.job_id)  # Verify it's a valid UUID
        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_multiple_files(
        self, mock_context, mock_upload_file, mock_pdf_file
    ):
        """Test uploading multiple files."""
        project_id = uuid.uuid4()
        files = [mock_upload_file, mock_pdf_file]

        with patch("api.routes.admin._onboarding.asyncio.create_task"):
            response = await upload_menu_api(files, mock_context, project_id)

        assert response.status == "accepted"
        assert response.project_id == str(project_id)
        assert response.job_id is not None

    @pytest.mark.asyncio
    async def test_upload_pdf_file(self, mock_context, mock_pdf_file):
        """Test uploading a PDF file."""
        project_id = uuid.uuid4()

        with patch("api.routes.admin._onboarding.asyncio.create_task"):
            response = await upload_menu_api(mock_pdf_file, mock_context, project_id)

        assert response.status == "accepted"
        assert response.project_id == str(project_id)

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(self, mock_context):
        """Test uploading an invalid file type."""
        project_id = uuid.uuid4()
        invalid_file = MagicMock(spec=UploadFile)
        invalid_file.filename = "menu.txt"
        invalid_file.content_type = "text/plain"
        invalid_file.file = BytesIO(b"text content")
        invalid_file.read = AsyncMock(return_value=b"text content")

        with pytest.raises(Exception) as exc_info:
            await upload_menu_api(invalid_file, mock_context, project_id)

        assert "Invalid file type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_file_no_content_type(self, mock_context):
        """Test uploading a file without content type."""
        project_id = uuid.uuid4()
        file_no_type = MagicMock(spec=UploadFile)
        file_no_type.filename = "menu.jpg"
        file_no_type.content_type = None
        file_no_type.file = BytesIO(b"content")
        file_no_type.read = AsyncMock(return_value=b"content")

        with pytest.raises(Exception) as exc_info:
            await upload_menu_api(file_no_type, mock_context, project_id)

        assert "File type could not be determined" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_job_created_in_service(self, mock_context, mock_upload_file):
        """Test that a job is created in the service."""
        project_id = uuid.uuid4()

        with patch("api.routes.admin._onboarding.asyncio.create_task"):
            response = await upload_menu_api(mock_upload_file, mock_context, project_id)

        # Verify job was created in service
        job_id = uuid.UUID(response.job_id)
        job = MenuProcessingService.get_job(job_id)

        assert job is not None
        assert job.project_id == project_id
        assert job.status == JobStatus.PENDING


class TestGetMenuProcessingStatus:
    """Tests for get_menu_processing_status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_job_exists(self, mock_context):
        """Test getting status for an existing job."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)

        # Update job status
        MenuProcessingService.update_job(
            job_id=job.job_id,
            status=JobStatus.PROCESSING,
            progress_percent=50,
        )

        mock_session = MagicMock()
        mock_project = Project(id=project_id, account_id=mock_context.account_id)

        with patch(
            "api.routes.admin._onboarding.project_service.get_project"
        ) as mock_get_project:
            mock_get_project.return_value = mock_project

            with patch("api.routes.admin._onboarding._verify_project_access"):
                response = await get_menu_processing_status(
                    job.job_id, mock_context, mock_session
                )

        assert response.job_id == str(job.job_id)
        assert response.project_id == str(project_id)
        assert response.status == "processing"
        assert response.progress_percent == 50
        assert response.completed is False

    @pytest.mark.asyncio
    async def test_get_status_completed_job(self, mock_context):
        """Test getting status for a completed job."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)
        menu_data = {"menu": "Test menu content"}

        # Mark job as completed
        MenuProcessingService.update_job(
            job_id=job.job_id,
            status=JobStatus.COMPLETED,
            progress_percent=100,
            completed=True,
            data=menu_data,
        )

        mock_session = MagicMock()
        mock_project = Project(id=project_id, account_id=mock_context.account_id)

        with patch(
            "api.routes.admin._onboarding.project_service.get_project"
        ) as mock_get_project:
            mock_get_project.return_value = mock_project

            with patch("api.routes.admin._onboarding._verify_project_access"):
                response = await get_menu_processing_status(
                    job.job_id, mock_context, mock_session
                )

        assert response.status == "completed"
        assert response.completed is True
        assert response.progress_percent == 100
        assert response.data == menu_data

    @pytest.mark.asyncio
    async def test_get_status_failed_job(self, mock_context):
        """Test getting status for a failed job."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)
        error_message = "Processing failed"

        # Mark job as failed
        MenuProcessingService.update_job(
            job_id=job.job_id,
            status=JobStatus.FAILED,
            completed=True,
            error=error_message,
        )

        mock_session = MagicMock()
        mock_project = Project(id=project_id, account_id=mock_context.account_id)

        with patch(
            "api.routes.admin._onboarding.project_service.get_project"
        ) as mock_get_project:
            mock_get_project.return_value = mock_project

            with patch("api.routes.admin._onboarding._verify_project_access"):
                response = await get_menu_processing_status(
                    job.job_id, mock_context, mock_session
                )

        assert response.status == "failed"
        assert response.completed is True
        assert response.error == error_message

    @pytest.mark.asyncio
    async def test_get_status_job_not_found(self, mock_context):
        """Test getting status for a non-existent job."""
        job_id = uuid.uuid4()
        mock_session = MagicMock()

        with pytest.raises(Exception) as exc_info:
            await get_menu_processing_status(job_id, mock_context, mock_session)

        assert (
            "404" in str(exc_info.value) or "not found" in str(exc_info.value).lower()
        )


class TestVerifyProjectAccess:
    """Tests for _verify_project_access helper function."""

    def test_verify_admin_role_access(self, mock_context):
        """Test that admin role has access to any project."""
        mock_context.role.value = "Admin"
        mock_session = MagicMock()
        mock_project = Project(id=uuid.uuid4(), account_id=uuid.uuid4())
        project_id = mock_project.id

        # Should not raise for admin
        _verify_project_access(mock_context, mock_session, mock_project, project_id)

    def test_verify_account_owner_access(self, mock_context):
        """Test that account owner has access to their projects."""
        account_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_context.role.value = "User"
        mock_context.username = str(user_id)
        mock_context.account_id = account_id

        mock_session = MagicMock()
        mock_project = Project(id=uuid.uuid4(), account_id=account_id)

        with patch(
            "db.repositories.resource_role_assignment_repository.ResourceRoleAssignmentRepository"
        ) as mock_repo:
            mock_repo_instance = MagicMock()
            mock_repo.return_value = mock_repo_instance
            mock_repo_instance.get_roles_for_resource.return_value = ["Owner"]

            _verify_project_access(
                mock_context, mock_session, mock_project, mock_project.id
            )

    def test_verify_project_role_access(self, mock_context):
        """Test that user with project role has access."""
        account_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_context.role.value = "User"
        mock_context.username = str(user_id)
        mock_context.account_id = account_id

        mock_session = MagicMock()
        mock_project = Project(id=uuid.uuid4(), account_id=uuid.uuid4())

        with patch(
            "db.repositories.resource_role_assignment_repository.ResourceRoleAssignmentRepository"
        ) as mock_repo:
            mock_repo_instance = MagicMock()
            mock_repo.return_value = mock_repo_instance
            # Return empty for account, has role for project
            mock_repo_instance.get_roles_for_resource.side_effect = [[], ["Admin"]]

            _verify_project_access(
                mock_context, mock_session, mock_project, mock_project.id
            )

    def test_verify_no_access(self, mock_context):
        """Test that user without proper roles is denied access."""
        account_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_context.role.value = "User"
        mock_context.username = str(user_id)
        mock_context.account_id = account_id

        mock_session = MagicMock()
        mock_project = Project(id=uuid.uuid4(), account_id=uuid.uuid4())

        with patch(
            "db.repositories.resource_role_assignment_repository.ResourceRoleAssignmentRepository"
        ) as mock_repo:
            mock_repo_instance = MagicMock()
            mock_repo.return_value = mock_repo_instance
            # Return empty for both account and project roles
            mock_repo_instance.get_roles_for_resource.return_value = []

            with pytest.raises(HTTPException) as exc_info:
                _verify_project_access(
                    mock_context, mock_session, mock_project, mock_project.id
                )

            assert exc_info.value.status_code == 403


class TestProcessMenuUploadBackground:
    """Tests for process_menu_upload_background function."""

    @pytest.mark.asyncio
    async def test_process_single_image(self, mock_context):
        """Test processing a single image in background."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)

        materialized_files = [
            {
                "content_bytes": b"fake image content",
                "filename": "menu.jpg",
                "content_type": "image/jpeg",
            }
        ]

        with patch("api.routes.admin._onboarding.SyncSessionLocal") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            with patch("api.routes.admin._onboarding.logger"):
                with patch(
                    "api.routes.admin._onboarding.admin_service.build_menu_from_upload"
                ) as mock_build:
                    mock_build.return_value = {"menu": "test menu"}

                    with patch(
                        "api.routes.admin._onboarding.project_service.update_project"
                    ):
                        await process_menu_upload_background(
                            materialized_files, mock_context, project_id, job.job_id
                        )

        # Verify job progressed through states
        final_job = MenuProcessingService.get_job(job.job_id)
        assert final_job is not None
        assert final_job.status == JobStatus.COMPLETED
        assert final_job.completed is True
        assert final_job.progress_percent == 100

    @pytest.mark.asyncio
    async def test_process_multiple_files(self, mock_context):
        """Test processing multiple files in background."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)

        materialized_files = [
            {
                "content_bytes": b"fake image content",
                "filename": "menu1.jpg",
                "content_type": "image/jpeg",
            },
            {
                "content_bytes": b"%PDF-1.4 fake pdf",
                "filename": "menu2.pdf",
                "content_type": "application/pdf",
            },
        ]

        with patch("api.routes.admin._onboarding.SyncSessionLocal") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            with patch("api.routes.admin._onboarding.logger"):
                with patch(
                    "api.routes.admin._onboarding.admin_service.build_menu_from_upload"
                ) as mock_build:
                    mock_build.return_value = {"menu": "test menu"}

                    with patch(
                        "api.routes.admin._onboarding.project_service.update_project"
                    ):
                        await process_menu_upload_background(
                            materialized_files, mock_context, project_id, job.job_id
                        )

        final_job = MenuProcessingService.get_job(job.job_id)
        assert final_job is not None
        assert final_job.status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_with_error(self, mock_context):
        """Test background processing handles errors correctly."""
        project_id = uuid.uuid4()
        job = MenuProcessingService.create_job(project_id)

        materialized_files = [
            {
                "content_bytes": b"fake content",
                "filename": "menu.jpg",
                "content_type": "image/jpeg",
            }
        ]

        with patch("api.routes.admin._onboarding.SyncSessionLocal") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            with patch("api.routes.admin._onboarding.logger"):
                with patch(
                    "api.routes.admin._onboarding.admin_service.build_menu_from_upload"
                ) as mock_build:
                    mock_build.side_effect = Exception("Processing error")

                    await process_menu_upload_background(
                        materialized_files, mock_context, project_id, job.job_id
                    )

        # Verify job marked as failed
        final_job = MenuProcessingService.get_job(job.job_id)
        assert final_job is not None
        assert final_job.status == JobStatus.FAILED
        assert final_job.completed is True
        assert final_job.error is not None
        assert "unexpected error" in final_job.error.lower()


class TestMenuProcessingStatusRoute:
    """Test route-level GET /menu-processing/{job_id}/status endpoint."""

    def test_get_menu_processing_status_route(self):
        """Test the FastAPI route wrapper for get_menu_processing_status."""
        from fastapi import FastAPI

        import db
        from api.routes.admin._auth import authenticate_user

        # Create a test app with the admin router
        app = FastAPI()
        app.include_router(admin_router)

        # Create test data
        project_id = uuid.uuid4()

        # Create mock dependencies
        mock_context = MagicMock()
        mock_context.username = str(uuid.uuid4())
        mock_context.role = MagicMock()
        mock_context.role.value = "Admin"
        mock_context.account_id = uuid.uuid4()

        mock_session = MagicMock()

        # Create a job in the service
        job = MenuProcessingService.create_job(project_id)
        MenuProcessingService.update_job(
            job_id=job.job_id,
            status=JobStatus.COMPLETED,
            progress_percent=100,
            completed=True,
            data={"menu": "test data"},
        )

        # Override dependencies
        app.dependency_overrides[authenticate_user] = lambda: mock_context
        app.dependency_overrides[db.get_db] = lambda: mock_session

        # Create test client
        client = TestClient(app)

        # Mock project_service and _verify_project_access
        with patch(
            "api.routes.admin._onboarding.project_service.get_project"
        ) as mock_get_project:
            mock_project = MagicMock()
            mock_project.id = project_id
            mock_project.account_id = mock_context.account_id
            mock_get_project.return_value = mock_project

            with patch("api.routes.admin._onboarding._verify_project_access"):
                # Call the endpoint (admin_router has /admin prefix)
                response = client.get(f"/admin/menu-processing/{job.job_id}/status")

        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["job_id"] == str(job.job_id)
        assert response_data["project_id"] == str(project_id)
        assert response_data["status"] == "completed"
        assert response_data["completed"] is True
        assert response_data["progress_percent"] == 100
        assert response_data["data"] == {"menu": "test data"}
