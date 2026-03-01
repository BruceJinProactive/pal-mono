"""Tests for TOS acceptance functionality in account routes."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import exc as sqlalchemy_exc

from api.routes.admin._account import accept_account_terms, get_account_terms_status
from api.schemas.admin.account import AcceptTermsRequest
from db.tables.accounts import Account


class TestAcceptAccountTerms:
    """Tests for accept_account_terms function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock user context."""
        context = MagicMock()
        context.email = "owner@example.com"
        context.username = str(uuid.uuid4())
        return context

    @pytest.fixture
    def mock_account(self):
        """Create a mock account."""
        account = MagicMock(spec=Account)
        account.id = uuid.uuid4()
        account.name = "test-account"
        account.display_name = "Test Account"
        return account

    @pytest.fixture
    def mock_request(self):
        """Create a mock TOS acceptance request."""
        return AcceptTermsRequest(tos_version="v1.0")

    @pytest.mark.asyncio
    async def test_accept_terms_success(self, mock_context, mock_account, mock_request):
        """Should successfully accept terms when all conditions are met."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = None
            tos_repo_instance.create_tos_acceptance.return_value = MagicMock()

            # Execute
            result = await accept_account_terms(
                "test-account", mock_request, mock_context, mock_session
            )

            # Assert
            assert result.accepted is True
            mock_session.commit.assert_called_once()
            tos_repo_instance.create_tos_acceptance.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_terms_blocks_internal_email(
        self, mock_context, mock_account, mock_request
    ):
        """Should block acceptance from @proactiveailab.com emails."""
        mock_context.email = "user@proactiveailab.com"
        mock_session = MagicMock()

        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = mock_account

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 403
            assert "proactiveailab.com" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_accept_terms_account_not_found(self, mock_context, mock_request):
        """Should raise 404 when account not found."""
        mock_session = MagicMock()

        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = None

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "nonexistent", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_accept_terms_invalid_user_id(
        self, mock_context, mock_account, mock_request
    ):
        """Should raise 401 when user ID is invalid."""
        mock_context.username = "invalid-uuid"
        mock_session = MagicMock()

        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = mock_account

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 401
            assert "Invalid authentication context" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_accept_terms_non_owner_forbidden(
        self, mock_context, mock_account, mock_request
    ):
        """Should raise 403 when non-owner tries to accept terms."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
        ):
            mock_account_service.get_account.return_value = mock_account
            mock_get_role.return_value = "manager"  # Not owner

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 403
            assert "Only account Owners" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_accept_terms_already_accepted_idempotent(
        self, mock_context, mock_account, mock_request
    ):
        """Should be idempotent when version already accepted."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_get_role.return_value = "owner"

            # Already accepted
            tos_repo_instance = mock_tos_repo.return_value
            existing_acceptance = MagicMock()
            tos_repo_instance.get_tos_acceptance_by_version.return_value = (
                existing_acceptance
            )

            # Execute
            result = await accept_account_terms(
                "test-account", mock_request, mock_context, mock_session
            )

            # Assert
            assert result.accepted is True
            mock_session.commit.assert_called_once()
            # Should not create new record since it already exists
            tos_repo_instance.create_tos_acceptance.assert_not_called()

    @pytest.mark.asyncio
    async def test_accept_terms_race_condition_integrity_error(
        self, mock_context, mock_account, mock_request
    ):
        """Should handle race condition with IntegrityError gracefully."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value

            # First check: not exists
            # create_tos_acceptance: raises IntegrityError (race condition)
            # Second check: exists (another request created it)
            existing_acceptance = MagicMock()
            tos_repo_instance.get_tos_acceptance_by_version.side_effect = [
                None,
                existing_acceptance,
            ]
            tos_repo_instance.create_tos_acceptance.side_effect = (
                sqlalchemy_exc.IntegrityError("statement", {}, Exception())
            )

            # Execute
            result = await accept_account_terms(
                "test-account", mock_request, mock_context, mock_session
            )

            # Assert
            assert result.accepted is True
            mock_session.rollback.assert_called_once()
            mock_session.commit.assert_called_once()
            # Should have checked twice (before and after IntegrityError)
            assert tos_repo_instance.get_tos_acceptance_by_version.call_count == 2

    @pytest.mark.asyncio
    async def test_accept_terms_race_condition_unexpected_integrity_error(
        self, mock_context, mock_account, mock_request
    ):
        """Should raise 500 when IntegrityError occurs but record still not found."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value

            # First check: not exists
            # create_tos_acceptance: raises IntegrityError
            # Second check: still not exists (unexpected!)
            tos_repo_instance.get_tos_acceptance_by_version.side_effect = [
                None,
                None,
            ]
            tos_repo_instance.create_tos_acceptance.side_effect = (
                sqlalchemy_exc.IntegrityError("statement", {}, Exception())
            )

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 500
            assert "Failed to record TOS acceptance" in exc_info.value.detail
            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_terms_generic_database_error(
        self, mock_context, mock_account, mock_request
    ):
        """Should handle generic database errors with rollback."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = None
            tos_repo_instance.create_tos_acceptance.side_effect = Exception(
                "Database error"
            )

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 500
            assert "Failed to record TOS acceptance" in exc_info.value.detail
            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_terms_account_update_fails(
        self, mock_context, mock_account, mock_request
    ):
        """Should raise 400 when account update fails."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
        ):
            mock_account_service.get_account.return_value = mock_account
            mock_get_role.return_value = "owner"
            mock_account_service.update_account.side_effect = ValueError(
                "Update failed"
            )

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 400
            assert "Update failed" in exc_info.value.detail


class TestGetAccountTermsStatus:
    """Tests for get_account_terms_status function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock user context."""
        context = MagicMock()
        return context

    @pytest.fixture
    def mock_account(self):
        """Create a mock account."""
        account = MagicMock(spec=Account)
        account.id = uuid.uuid4()
        account.name = "test-account"
        account.display_name = "Test Account"
        account.terms_accepted = False
        return account

    def test_get_terms_status_success(self, mock_context, mock_account):
        """Should return terms status with current version from environment."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch.dict("os.environ", {"CURRENT_TOS_VERSION": "v2.0"}),
        ):
            mock_account_service.get_account.return_value = mock_account

            # Execute
            result = get_account_terms_status(
                "test-account", mock_context, mock_session
            )

            # Assert
            assert result.id == mock_account.id
            assert result.name == mock_account.name
            assert result.display_name == mock_account.display_name
            assert result.terms_accepted is False
            assert result.current_tos_version == "v2.0"

    def test_get_terms_status_default_version(self, mock_context, mock_account):
        """Should use default version v1.0 when env var not set."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch.dict("os.environ", {}, clear=False),
        ):
            # Remove CURRENT_TOS_VERSION if it exists
            import os

            os.environ.pop("CURRENT_TOS_VERSION", None)

            mock_account_service.get_account.return_value = mock_account

            # Execute
            result = get_account_terms_status(
                "test-account", mock_context, mock_session
            )

            # Assert
            assert result.current_tos_version == "v1.0"

    def test_get_terms_status_account_not_found(self, mock_context):
        """Should raise 404 when account not found."""
        mock_session = MagicMock()

        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = None

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                get_account_terms_status("nonexistent", mock_context, mock_session)

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail
