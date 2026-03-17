"""Tests for phone number API routes."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from api.routes.admin._phone_number import release_standalone_number
from api.schemas.admin.phone_number import ReleaseNumberRequest


class TestReleaseStandaloneNumber:
    """Tests for release_standalone_number endpoint."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock user context."""
        from services.auth_types import UserRole

        context = MagicMock()
        context.email = "test@example.com"
        context.username = str(uuid.uuid4())
        context.display_name = "Test User"
        context.role = UserRole.Admin
        return context

    @pytest.fixture
    def release_request(self):
        """Create a release number request."""
        return ReleaseNumberRequest(phone_number="+15551234567")

    @pytest.mark.asyncio
    async def test_release_number_success(self, mock_context, release_request):
        """Should successfully release a phone number and return correct message."""
        mock_session = MagicMock()

        with patch(
            "api.routes.admin._phone_number.NumberService"
        ) as mock_service_class:
            # Setup mock
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_number.return_value = None

            # Execute
            response = await release_standalone_number(
                release_request, mock_context, mock_session
            )

            # Assert service was called correctly
            mock_service_class.assert_called_once()
            mock_service.delete_number.assert_called_once_with("+15551234567")

            # Assert response
            assert response.phone_number == "+15551234567"
            assert "deleted successfully from Twilio" in response.message
            assert response.released_from_vapi is False  # VAPI no longer supported
            assert response.released_from_twilio is True

    @pytest.mark.asyncio
    async def test_release_number_not_found(self, mock_context, release_request):
        """Should raise 404 when number is not found."""
        from fastapi import HTTPException

        mock_session = MagicMock()

        with patch(
            "api.routes.admin._phone_number.NumberService"
        ) as mock_service_class:
            # Setup mock to raise ValueError
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_number.side_effect = ValueError("Number not found")

            # Execute and assert exception
            with pytest.raises(HTTPException) as exc_info:
                await release_standalone_number(
                    release_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 404
            assert "Number not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_release_number_general_error(self, mock_context, release_request):
        """Should raise 500 for unexpected errors."""
        from fastapi import HTTPException

        mock_session = MagicMock()

        with patch(
            "api.routes.admin._phone_number.NumberService"
        ) as mock_service_class:
            # Setup mock to raise unexpected exception
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_number.side_effect = Exception("Unexpected error")

            # Execute and assert exception
            with pytest.raises(HTTPException) as exc_info:
                await release_standalone_number(
                    release_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 500
            assert "Unexpected error" in str(exc_info.value.detail)
