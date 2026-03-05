"""Tests for knowledge base management endpoints."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services.auth_types import UserRole


class TestUpdateAgentKb:
    """Tests for update_agent_kb function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock user context with admin role."""
        context = MagicMock()
        context.email = "admin@example.com"
        context.username = str(uuid.uuid4())
        context.display_name = "Admin User"
        context.role = UserRole.Admin
        return context

    @pytest.fixture
    def mock_project(self):
        """Create a mock project with valid name."""
        project = MagicMock()
        project.id = uuid.uuid4()
        project.account_id = uuid.uuid4()
        project.name = "Test Project"
        return project

    @pytest.fixture
    def mock_project_no_name(self):
        """Create a mock project with None name."""
        project = MagicMock()
        project.id = uuid.uuid4()
        project.account_id = uuid.uuid4()
        project.name = None
        return project

    @pytest.fixture
    def mock_project_empty_name(self):
        """Create a mock project with empty/whitespace name."""
        project = MagicMock()
        project.id = uuid.uuid4()
        project.account_id = uuid.uuid4()
        project.name = "   "  # Only whitespace
        return project

    @pytest.mark.asyncio
    async def test_update_agent_kb_missing_project_name(
        self, mock_context, mock_project_no_name
    ):
        """Test that update_agent_kb raises ValueError when project.name is None."""
        mock_session = MagicMock()
        project_id = mock_project_no_name.id
        account_name = "test-account"
        pinecone_index_name = "test-index"

        with patch("api.routes.admin._knowledge._auth"):
            with patch("api.routes.admin._knowledge.project_service"):
                # Import here to ensure module is loaded with patches
                from api.routes.admin._knowledge import update_agent_kb

                with patch(
                    "api.routes.admin._knowledge.project_service.get_project"
                ) as mock_get_project:
                    mock_get_project.return_value = mock_project_no_name

                    # Should raise HTTPException with 400 status code due to ValueError
                    with pytest.raises(HTTPException) as exc_info:
                        await update_agent_kb(
                            context=mock_context,
                            session=mock_session,
                            account_name=account_name,
                            project_id=project_id,
                            pinecone_index_name=pinecone_index_name,
                        )

                    assert exc_info.value.status_code == 400
                    assert "Project name is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_agent_kb_empty_project_name(
        self, mock_context, mock_project_empty_name
    ):
        """Test that update_agent_kb raises ValueError when project.name is empty/whitespace."""
        mock_session = MagicMock()
        project_id = mock_project_empty_name.id
        account_name = "test-account"
        pinecone_index_name = "test-index"

        with patch("api.routes.admin._knowledge._auth"):
            with patch("api.routes.admin._knowledge.project_service"):
                # Import here to ensure module is loaded with patches
                from api.routes.admin._knowledge import update_agent_kb

                with patch(
                    "api.routes.admin._knowledge.project_service.get_project"
                ) as mock_get_project:
                    mock_get_project.return_value = mock_project_empty_name

                    # Should raise HTTPException with 400 status code due to ValueError
                    with pytest.raises(HTTPException) as exc_info:
                        await update_agent_kb(
                            context=mock_context,
                            session=mock_session,
                            account_name=account_name,
                            project_id=project_id,
                            pinecone_index_name=pinecone_index_name,
                        )

                    assert exc_info.value.status_code == 400
                    assert "Project name is required" in exc_info.value.detail
