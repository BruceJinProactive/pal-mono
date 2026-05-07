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
            patch("api.routes.admin._account.slack_service") as mock_slack_service,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_get_role.return_value = "owner"
            mock_slack_service.send_tos_accepted_notification.return_value = None

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = None
            tos_repo_instance.create_tos_acceptance.return_value = MagicMock()

            # Execute
            result = await accept_account_terms(
                "test-account", mock_request, mock_context, mock_session
            )

            # Assert
            assert result.accepted is True
            assert result.tos_version == "v1.0"
            mock_session.commit.assert_called_once()
            tos_repo_instance.create_tos_acceptance.assert_called_once()
            mock_slack_service.send_tos_accepted_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_terms_blocks_internal_email(
        self, mock_context, mock_account, mock_request
    ):
        """Should block acceptance from @proactiveailab.com and @palona.ai."""
        mock_session = MagicMock()

        # Test @proactiveailab.com
        mock_context.email = "user@proactiveailab.com"
        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = mock_account

            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )
            assert exc_info.value.status_code == 403
            assert "internal team members" in exc_info.value.detail.lower()

        # Test @palona.ai
        mock_context.email = "user@palona.ai"
        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = mock_account

            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )
            assert exc_info.value.status_code == 403
            assert "internal team members" in exc_info.value.detail.lower()

        # Test case insensitive @PALONA.AI
        mock_context.email = "user@PALONA.AI"
        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = mock_account

            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )
            assert exc_info.value.status_code == 403
            assert "internal team members" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_accept_terms_empty_email(self, mock_request):
        """Should raise 400 when user email is missing."""
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.email = None  # Missing email
        mock_context.username = str(uuid.uuid4())

        with pytest.raises(HTTPException) as exc_info:
            await accept_account_terms(
                "test-account", mock_request, mock_context, mock_session
            )

        assert exc_info.value.status_code == 400
        assert "User email is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_accept_terms_version_mismatch(
        self, mock_context, mock_account, mock_request
    ):
        """Should reject TOS acceptance when version doesn't match current version."""
        mock_session = MagicMock()
        mock_request.tos_version = "v2.0"  # Wrong version

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
        ):
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_get_role.return_value = "owner"

            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 409
            assert "TOS version mismatch" in exc_info.value.detail
            assert "v2.0" in exc_info.value.detail
            assert "v1.0" in exc_info.value.detail

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
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
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
            assert result.tos_version == "v1.0"
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
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
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
            assert result.tos_version == "v1.0"
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
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
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
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
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
    async def test_accept_terms_metrics_on_create(
        self, mock_context, mock_account, mock_request
    ):
        """Should emit OTel metrics when creating acceptance."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
            patch("api.routes.admin._account.increment_counter") as mock_counter,
            patch("api.routes.admin._account.record_duration") as mock_histogram,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = None
            tos_repo_instance.create_tos_acceptance.return_value = MagicMock()

            # Execute
            result = await accept_account_terms(
                "test-account", mock_request, mock_context, mock_session
            )

            # Assert - business logic should succeed
            assert result.accepted is True
            assert result.tos_version == "v1.0"
            mock_session.commit.assert_called_once()
            tos_repo_instance.create_tos_acceptance.assert_called_once()

            # Verify OTel metrics were called
            mock_counter.assert_called_once_with(
                "tos.acceptance.created", attributes={"version": "v1.0"}
            )
            mock_histogram.assert_called_once()
            assert mock_histogram.call_args.args[0] == "tos.acceptance.duration"

    @pytest.mark.asyncio
    async def test_accept_terms_metrics_on_duplicate(
        self, mock_context, mock_account, mock_request
    ):
        """Should emit OTel metrics when acceptance already exists."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
            patch("api.routes.admin._account.increment_counter") as mock_counter,
            patch("api.routes.admin._account.record_duration") as mock_histogram,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
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

            # Assert - business logic should succeed
            assert result.accepted is True
            assert result.tos_version == "v1.0"
            mock_session.commit.assert_called_once()
            tos_repo_instance.create_tos_acceptance.assert_not_called()

            # Verify OTel metrics were called
            mock_counter.assert_called_once_with(
                "tos.acceptance.duplicate", attributes={"version": "v1.0"}
            )
            mock_histogram.assert_called_once()
            assert mock_histogram.call_args.args[0] == "tos.acceptance.duration"

    @pytest.mark.asyncio
    async def test_accept_terms_metrics_on_race_condition(
        self, mock_context, mock_account, mock_request
    ):
        """Should emit OTel metrics during race condition."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
            patch("api.routes.admin._account.increment_counter") as mock_counter,
            patch("api.routes.admin._account.record_duration") as mock_histogram,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value

            # First check: not exists, create raises IntegrityError, second check: exists
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

            # Assert - business logic should succeed
            assert result.accepted is True
            assert result.tos_version == "v1.0"
            mock_session.rollback.assert_called_once()
            mock_session.commit.assert_called_once()

            # Verify OTel metrics were called
            mock_counter.assert_called_once_with(
                "tos.acceptance.duplicate", attributes={"version": "v1.0"}
            )
            mock_histogram.assert_called_once()
            assert mock_histogram.call_args.args[0] == "tos.acceptance.duration"

    @pytest.mark.asyncio
    async def test_accept_terms_metrics_on_error(
        self, mock_context, mock_account, mock_request
    ):
        """Should emit OTel metrics during database errors."""
        mock_session = MagicMock()

        with (
            patch("api.routes.admin._account.account_service") as mock_account_service,
            patch(
                "api.routes.admin._account.get_user_role_on_account"
            ) as mock_get_role,
            patch("api.routes.admin._account.TosAcceptanceRepository") as mock_tos_repo,
            patch("api.routes.admin._account.increment_counter") as mock_counter,
            patch("api.routes.admin._account.record_duration") as mock_histogram,
        ):
            # Setup mocks
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.update_account.return_value = mock_account
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = None
            tos_repo_instance.create_tos_acceptance.side_effect = Exception(
                "Database error"
            )

            # Execute and assert - should still raise the database error
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 500
            assert "Failed to record TOS acceptance" in exc_info.value.detail
            mock_session.rollback.assert_called_once()

            # Verify OTel metrics were called even on error
            mock_counter.assert_called_once_with(
                "tos.acceptance.failed",
                attributes={"version": "v1.0", "error": "Exception"},
            )
            mock_histogram.assert_called_once()
            assert mock_histogram.call_args.args[0] == "tos.acceptance.duration"

    @pytest.mark.asyncio
    async def test_accept_terms_lookup_failure_before_insert(
        self, mock_context, mock_account, mock_request
    ):
        """Should handle repository lookup failures before insert."""
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
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value
            # Make the lookup raise a database error
            tos_repo_instance.get_tos_acceptance_by_version.side_effect = (
                sqlalchemy_exc.OperationalError(
                    "statement", {}, Exception("lookup failed")
                )
            )

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 500
            assert "Failed to check TOS acceptance status" in exc_info.value.detail
            # Should call rollback after lookup failure
            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_terms_commit_failure(
        self, mock_context, mock_account, mock_request
    ):
        """Should handle session.commit() failures gracefully."""
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
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_get_role.return_value = "owner"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = None
            tos_repo_instance.create_tos_acceptance.return_value = MagicMock()

            # Make commit fail
            mock_session.commit.side_effect = Exception("Commit failed")

            # Execute and assert
            with pytest.raises(HTTPException) as exc_info:
                await accept_account_terms(
                    "test-account", mock_request, mock_context, mock_session
                )

            assert exc_info.value.status_code == 500
            assert "Failed to save TOS acceptance" in exc_info.value.detail
            # Should call rollback after commit failure
            mock_session.rollback.assert_called_once()


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
        """Should return terms status from tos_acceptances table."""
        mock_session = MagicMock()

        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_account_service.get_tos_status.return_value = {
                "accepted_tos_version": "v1.0",
                "is_compliant": True,
                "accepted_at": None,
            }

            # Execute
            result = get_account_terms_status(
                "test-account", mock_context, mock_session
            )

            # Assert service call
            mock_account_service.get_tos_status.assert_called_once_with(
                mock_session, mock_account.id, "v1.0"
            )

            # Assert response
            assert result.id == mock_account.id
            assert result.name == mock_account.name
            assert result.display_name == mock_account.display_name
            # terms_accepted field removed - use is_compliant instead
            assert result.accepted_tos_version == "v1.0"
            assert result.is_compliant is True
            assert result.accepted_at is None

    def test_get_terms_status_not_compliant(self, mock_context, mock_account):
        """Should return not compliant when TOS not accepted."""
        mock_session = MagicMock()

        with patch("api.routes.admin._account.account_service") as mock_account_service:
            mock_account_service.get_account.return_value = mock_account
            mock_account_service.CURRENT_TOS_VERSION = "v1.0"
            mock_account_service.get_tos_status.return_value = {
                "accepted_tos_version": None,
                "is_compliant": False,
                "accepted_at": None,
            }

            # Execute
            result = get_account_terms_status(
                "test-account", mock_context, mock_session
            )

            # Assert service call
            mock_account_service.get_tos_status.assert_called_once_with(
                mock_session, mock_account.id, "v1.0"
            )

            # Assert response
            assert result.accepted_tos_version is None
            assert result.is_compliant is False
            assert result.accepted_at is None

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
