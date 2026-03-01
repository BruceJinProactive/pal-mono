"""Tests for TosAcceptanceRepository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from db.repositories.tos_acceptance_repository import TosAcceptanceRepository
from db.tables import TosAcceptance


class TestTosAcceptanceRepository:
    """Tests for TosAcceptanceRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def repository(self, mock_session):
        """Create a TosAcceptanceRepository instance."""
        return TosAcceptanceRepository(mock_session)

    @pytest.fixture
    def sample_account_id(self):
        """Sample account UUID."""
        return uuid.uuid4()

    @pytest.fixture
    def sample_user_id(self):
        """Sample user UUID."""
        return uuid.uuid4()

    def test_create_tos_acceptance_success(
        self, repository, mock_session, sample_account_id, sample_user_id
    ):
        """Should successfully create TOS acceptance record."""
        # Setup
        accepted_at = datetime.now(UTC)
        display_name = "Test Account"
        tos_version = "v1.0"
        user_email = "user@example.com"

        # Execute
        result = repository.create_tos_acceptance(
            account_id=sample_account_id,
            display_name=display_name,
            tos_version=tos_version,
            user_id=sample_user_id,
            user_email=user_email,
            accepted_at=accepted_at,
        )

        # Assert
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()
        assert isinstance(result, TosAcceptance)

    def test_create_tos_acceptance_raises_integrity_error(
        self, repository, mock_session, sample_account_id, sample_user_id
    ):
        """Should raise IntegrityError when duplicate record exists."""
        # Setup
        accepted_at = datetime.now(UTC)
        mock_session.flush.side_effect = IntegrityError("statement", {}, Exception())

        # Execute and assert
        with pytest.raises(IntegrityError):
            repository.create_tos_acceptance(
                account_id=sample_account_id,
                display_name="Test Account",
                tos_version="v1.0",
                user_id=sample_user_id,
                user_email="user@example.com",
                accepted_at=accepted_at,
            )

    def test_get_latest_tos_acceptance_success(
        self, repository, mock_session, sample_account_id
    ):
        """Should return the most recent TOS acceptance."""
        # Setup
        mock_acceptance = MagicMock(spec=TosAcceptance)
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_acceptance

        # Execute
        result = repository.get_latest_tos_acceptance(sample_account_id)

        # Assert
        assert result == mock_acceptance
        mock_session.query.assert_called_once_with(TosAcceptance)
        mock_query.order_by.assert_called_once()
        mock_query.first.assert_called_once()

    def test_get_latest_tos_acceptance_not_found(
        self, repository, mock_session, sample_account_id
    ):
        """Should return None when no acceptance found."""
        # Setup
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        # Execute
        result = repository.get_latest_tos_acceptance(sample_account_id)

        # Assert
        assert result is None

    def test_get_tos_acceptance_by_version_success(
        self, repository, mock_session, sample_account_id
    ):
        """Should return TOS acceptance for specific version."""
        # Setup
        mock_acceptance = MagicMock(spec=TosAcceptance)
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_acceptance

        # Execute
        result = repository.get_tos_acceptance_by_version(
            account_id=sample_account_id, tos_version="v1.0"
        )

        # Assert
        assert result == mock_acceptance
        mock_session.query.assert_called_once_with(TosAcceptance)
        mock_query.first.assert_called_once()

    def test_get_tos_acceptance_by_version_not_found(
        self, repository, mock_session, sample_account_id
    ):
        """Should return None when version not accepted."""
        # Setup
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        # Execute
        result = repository.get_tos_acceptance_by_version(
            account_id=sample_account_id, tos_version="v2.0"
        )

        # Assert
        assert result is None
