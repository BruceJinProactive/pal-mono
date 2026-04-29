"""Unit tests for TOS compliance service methods."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from services.account_service._tos import check_tos_compliance, get_tos_status


class TestCheckTosCompliance:
    """Tests for check_tos_compliance function."""

    def test_check_tos_compliance_with_acceptance(self):
        """Test compliance check when record exists for required version."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"
        mock_acceptance = MagicMock()
        mock_acceptance.tos_version = required_version

        # Mock repository to return acceptance for specific version
        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = mock_acceptance

        # Patch the repository instantiation
        with patch(
            "services.account_service._tos.TosAcceptanceRepository",
            return_value=mock_repo,
        ):
            # Act
            result = check_tos_compliance(mock_session, account_id, required_version)

            # Assert
            assert result is True
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, required_version
            )

    def test_check_tos_compliance_not_accepted(self):
        """Test compliance check when no acceptance exists for required version."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"

        # Mock repository to return None (no acceptance for required version)
        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = None

        # Patch the repository instantiation
        with patch(
            "services.account_service._tos.TosAcceptanceRepository",
            return_value=mock_repo,
        ):
            # Act
            result = check_tos_compliance(mock_session, account_id, required_version)

            # Assert
            assert result is False  # Forces re-acceptance
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, required_version
            )

    def test_check_tos_compliance_wrong_version(self):
        """Test that accepting v1.0 doesn't satisfy v2.0 requirement."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()

        # Mock repository to return None when checking for v2.0
        # (even though v1.0 might exist in the database)
        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = None

        # Patch the repository instantiation
        with patch(
            "services.account_service._tos.TosAcceptanceRepository",
            return_value=mock_repo,
        ):
            # Act - Check for v2.0 compliance
            result = check_tos_compliance(mock_session, account_id, "v2.0")

            # Assert
            assert result is False
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, "v2.0"
            )

    def test_check_tos_compliance_calls_metrics_compliant(self):
        """Test compliance check calls OTel metrics when compliant."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"
        mock_acceptance = MagicMock()
        mock_acceptance.tos_version = required_version

        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = mock_acceptance

        # Patch repository and OTel functions
        with (
            patch(
                "services.account_service._tos.TosAcceptanceRepository",
                return_value=mock_repo,
            ),
            patch("services.account_service._tos.increment_counter") as mock_increment,
            patch("services.account_service._tos.record_duration") as mock_histogram,
        ):
            # Act
            result = check_tos_compliance(mock_session, account_id, required_version)

            # Assert
            assert result is True
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, required_version
            )
            # Verify metrics were called
            assert mock_increment.call_count >= 2  # check + passed
            mock_histogram.assert_called_once()

    def test_check_tos_compliance_calls_metrics_not_compliant(self):
        """Test compliance check calls OTel metrics when not compliant."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"

        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = None

        # Patch repository and OTel functions
        with (
            patch(
                "services.account_service._tos.TosAcceptanceRepository",
                return_value=mock_repo,
            ),
            patch("services.account_service._tos.increment_counter") as mock_increment,
            patch("services.account_service._tos.record_duration") as mock_histogram,
        ):
            # Act
            result = check_tos_compliance(mock_session, account_id, required_version)

            # Assert
            assert result is False
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, required_version
            )
            # Verify metrics were called
            assert mock_increment.call_count >= 2  # check + failed
            mock_histogram.assert_called_once()

    def test_check_tos_compliance_calls_metrics_on_error(self):
        """Test compliance check calls OTel metrics during database errors."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"

        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.side_effect = Exception("DB error")

        # Patch repository and OTel functions
        with (
            patch(
                "services.account_service._tos.TosAcceptanceRepository",
                return_value=mock_repo,
            ),
            patch("services.account_service._tos.increment_counter") as mock_increment,
            patch("services.account_service._tos.record_duration") as mock_histogram,
        ):
            # Act and assert - should still raise the database error
            with pytest.raises(Exception, match="DB error"):
                check_tos_compliance(mock_session, account_id, required_version)

            # Verify error metrics were called
            mock_increment.assert_called()
            mock_histogram.assert_called_once()


class TestGetTosStatus:
    """Tests for get_tos_status function."""

    def test_get_tos_status_with_acceptance(self):
        """Test get_tos_status when record exists for required version."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"
        accepted_at = datetime.now(UTC)

        mock_acceptance = MagicMock()
        mock_acceptance.tos_version = required_version
        mock_acceptance.accepted_at = accepted_at

        # Mock repository
        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = mock_acceptance

        # Patch the repository instantiation
        with patch(
            "services.account_service._tos.TosAcceptanceRepository",
            return_value=mock_repo,
        ):
            # Act
            status = get_tos_status(mock_session, account_id, required_version)

            # Assert
            assert status["accepted_tos_version"] == required_version
            assert status["is_compliant"] is True
            assert status["accepted_at"] == accepted_at
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, required_version
            )

    def test_get_tos_status_not_accepted_ignores_legacy(self):
        """Test get_tos_status returns non-compliant when required version not accepted."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"

        # Mock repository to return None (no acceptance for required version)
        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = None

        # Patch the repository instantiation
        with patch(
            "services.account_service._tos.TosAcceptanceRepository",
            return_value=mock_repo,
        ):
            # Act
            status = get_tos_status(mock_session, account_id, required_version)

            # Assert - Should return not compliant (no acceptance for required version)
            assert status["accepted_tos_version"] is None
            assert status["is_compliant"] is False
            assert status["accepted_at"] is None
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, required_version
            )

    def test_get_tos_status_calls_metrics_with_acceptance(self):
        """Test get_tos_status calls OTel metrics when acceptance exists."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"
        accepted_at = datetime.now(UTC)

        mock_acceptance = MagicMock()
        mock_acceptance.tos_version = required_version
        mock_acceptance.accepted_at = accepted_at

        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = mock_acceptance

        # Patch repository and OTel functions
        with (
            patch(
                "services.account_service._tos.TosAcceptanceRepository",
                return_value=mock_repo,
            ),
            patch("services.account_service._tos.increment_counter") as mock_increment,
            patch("services.account_service._tos.record_duration") as mock_histogram,
        ):
            # Act
            status = get_tos_status(mock_session, account_id, required_version)

            # Assert
            assert status["accepted_tos_version"] == required_version
            assert status["is_compliant"] is True
            assert status["accepted_at"] == accepted_at
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, required_version
            )
            # Verify metrics were called
            mock_increment.assert_called_once()
            mock_histogram.assert_called_once()

    def test_get_tos_status_calls_metrics_not_accepted(self):
        """Test get_tos_status calls OTel metrics when not accepted."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"

        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.return_value = None

        # Patch repository and OTel functions
        with (
            patch(
                "services.account_service._tos.TosAcceptanceRepository",
                return_value=mock_repo,
            ),
            patch("services.account_service._tos.increment_counter") as mock_increment,
            patch("services.account_service._tos.record_duration") as mock_histogram,
        ):
            # Act
            status = get_tos_status(mock_session, account_id, required_version)

            # Assert
            assert status["accepted_tos_version"] is None
            assert status["is_compliant"] is False
            assert status["accepted_at"] is None
            mock_repo.get_tos_acceptance_by_version.assert_called_once_with(
                account_id, required_version
            )
            # Verify metrics were called
            mock_increment.assert_called_once()
            mock_histogram.assert_called_once()

    def test_get_tos_status_calls_metrics_on_error(self):
        """Test get_tos_status calls OTel metrics during database errors."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        required_version = "v1.0"

        mock_repo = MagicMock()
        mock_repo.get_tos_acceptance_by_version.side_effect = Exception("DB error")

        # Patch repository and OTel functions
        with (
            patch(
                "services.account_service._tos.TosAcceptanceRepository",
                return_value=mock_repo,
            ),
            patch("services.account_service._tos.increment_counter") as mock_increment,
            patch("services.account_service._tos.record_duration") as mock_histogram,
        ):
            # Act and assert - should still raise the database error
            with pytest.raises(Exception, match="DB error"):
                get_tos_status(mock_session, account_id, required_version)

            # Verify error metrics were called
            mock_increment.assert_called()
            mock_histogram.assert_called_once()
