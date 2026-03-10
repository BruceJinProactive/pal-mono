"""Unit tests for TOS wrapper functions in account_service/__init__.py."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from services import account_service
from services.account_service import CURRENT_TOS_VERSION


class TestTosWrapperFunctions:
    """Tests for TOS wrapper functions exported from account_service."""

    def test_check_tos_compliance_wrapper(self):
        """Test that check_tos_compliance wrapper correctly delegates to _tos module."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()

        # Patch the _tos module function
        with patch("services.account_service._tos.check_tos_compliance") as mock_check:
            mock_check.return_value = True

            # Act - Must pass explicit version
            result = account_service.check_tos_compliance(
                mock_session, account_id, CURRENT_TOS_VERSION
            )

            # Assert
            assert result is True
            mock_check.assert_called_once_with(
                mock_session, account_id, CURRENT_TOS_VERSION
            )

    def test_get_tos_status_wrapper(self):
        """Test that get_tos_status wrapper correctly delegates to _tos module."""
        # Arrange
        mock_session = MagicMock()
        account_id = uuid.uuid4()
        expected_status = {
            "accepted_tos_version": CURRENT_TOS_VERSION,
            "is_compliant": True,
            "accepted_at": datetime.now(UTC),
        }

        # Patch the _tos module function
        with patch("services.account_service._tos.get_tos_status") as mock_status:
            mock_status.return_value = expected_status

            # Act - Must pass explicit version
            result = account_service.get_tos_status(
                mock_session, account_id, CURRENT_TOS_VERSION
            )

            # Assert
            assert result == expected_status
            mock_status.assert_called_once_with(
                mock_session, account_id, CURRENT_TOS_VERSION
            )
