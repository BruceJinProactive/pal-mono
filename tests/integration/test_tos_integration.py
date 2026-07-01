"""Integration tests for TOS acceptance with real PostgreSQL database.

These tests use the actual Docker PostgreSQL database to verify end-to-end
TOS acceptance flows, including database transactions, constraints, and queries.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.routes.admin._account import accept_account_terms, get_account_terms_status
from api.schemas.admin.account import AcceptTermsRequest
from db.repositories.tos_acceptance_repository import TosAcceptanceRepository
from db.tables import Account, TosAcceptance
from db.tables.accounts import AccountStatus
from services import account_service


class TestTosAcceptanceIntegration:
    """Integration tests for TOS acceptance with real database."""

    def test_accept_tos_creates_record_in_database(
        self,
        db_session: Session,
        test_account: Account,
        test_user,
    ):
        """
        Test: Accept TOS v1.0 → create record → query shows v1.0

        This test verifies the entire flow:
        1. Accept TOS for an account
        2. Record is created in tos_acceptances table
        3. Querying the repository returns the correct version
        """
        # Arrange
        repo = TosAcceptanceRepository(db_session)
        tos_version = "v1.0"
        accepted_at = datetime.now(UTC)

        # Act - Create TOS acceptance
        tos_acceptance = repo.create_tos_acceptance(
            account_id=test_account.id,
            display_name=test_account.display_name or test_account.name,
            tos_version=tos_version,
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=accepted_at,
        )
        db_session.commit()

        # Assert - Record was created
        assert tos_acceptance.id is not None
        assert tos_acceptance.account_id == test_account.id
        assert tos_acceptance.tos_version == tos_version
        assert tos_acceptance.user_id == test_user.user.id
        assert tos_acceptance.user_email == test_user.email

        # Act - Query the record back
        latest_acceptance = repo.get_latest_tos_acceptance(test_account.id)

        # Assert - Query returns the correct record
        assert latest_acceptance is not None
        assert latest_acceptance.id == tos_acceptance.id
        assert latest_acceptance.tos_version == tos_version
        assert latest_acceptance.account_id == test_account.id

        # Act - Query by specific version
        version_acceptance = repo.get_tos_acceptance_by_version(
            test_account.id, tos_version
        )

        # Assert - Query by version returns the correct record
        assert version_acceptance is not None
        assert version_acceptance.id == tos_acceptance.id
        assert version_acceptance.tos_version == tos_version

    def test_account_without_acceptance_returns_none(
        self, db_session: Session, test_account: Account
    ):
        """
        Test: Account without acceptance → query returns None

        Verifies that querying TOS acceptance for an account that has
        never accepted TOS returns None.
        """
        # Arrange
        repo = TosAcceptanceRepository(db_session)

        # Act - Query for non-existent acceptance
        latest_acceptance = repo.get_latest_tos_acceptance(test_account.id)

        # Assert - Returns None
        assert latest_acceptance is None

        # Act - Query by specific version
        version_acceptance = repo.get_tos_acceptance_by_version(test_account.id, "v1.0")

        # Assert - Returns None
        assert version_acceptance is None

    def test_duplicate_acceptance_raises_integrity_error(
        self,
        db_session: Session,
        test_account: Account,
        test_user,
    ):
        """
        Test: Accepting the same TOS version twice raises IntegrityError

        Verifies the unique constraint on (account_id, tos_version) is enforced.
        """
        # Arrange
        repo = TosAcceptanceRepository(db_session)
        tos_version = "v1.0"
        accepted_at = datetime.now(UTC)

        # Act - Create first acceptance
        repo.create_tos_acceptance(
            account_id=test_account.id,
            display_name=test_account.display_name or test_account.name,
            tos_version=tos_version,
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=accepted_at,
        )
        db_session.commit()

        # Act & Assert - Try to create duplicate acceptance
        with pytest.raises(IntegrityError):
            repo.create_tos_acceptance(
                account_id=test_account.id,
                display_name=test_account.display_name or test_account.name,
                tos_version=tos_version,
                user_id=test_user.user.id,
                user_email=test_user.email,
                accepted_at=accepted_at,
            )

        # Cleanup - rollback the failed transaction
        db_session.rollback()

    def test_multiple_versions_same_account(
        self,
        db_session: Session,
        test_account: Account,
        test_user,
    ):
        """
        Test: Same account can accept multiple TOS versions

        Verifies that an account can accept v1.0, then later accept v2.0,
        and both records are stored in the database.
        """
        # Arrange
        repo = TosAcceptanceRepository(db_session)
        accepted_at_v1 = datetime.now(UTC)

        # Act - Accept v1.0
        acceptance_v1 = repo.create_tos_acceptance(
            account_id=test_account.id,
            display_name=test_account.display_name or test_account.name,
            tos_version="v1.0",
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=accepted_at_v1,
        )
        db_session.commit()

        # Act - Accept v2.0
        accepted_at_v2 = datetime.now(UTC)
        acceptance_v2 = repo.create_tos_acceptance(
            account_id=test_account.id,
            display_name=test_account.display_name or test_account.name,
            tos_version="v2.0",
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=accepted_at_v2,
        )
        db_session.commit()

        # Assert - Both records exist
        v1_record = repo.get_tos_acceptance_by_version(test_account.id, "v1.0")
        v2_record = repo.get_tos_acceptance_by_version(test_account.id, "v2.0")

        assert v1_record is not None
        assert v1_record.id == acceptance_v1.id
        assert v1_record.tos_version == "v1.0"

        assert v2_record is not None
        assert v2_record.id == acceptance_v2.id
        assert v2_record.tos_version == "v2.0"

        # Assert - Latest acceptance returns v2.0 (most recent)
        latest = repo.get_latest_tos_acceptance(test_account.id)
        assert latest is not None
        assert latest.tos_version == "v2.0"

    def test_get_tos_status_with_acceptance(
        self,
        db_session: Session,
        test_account: Account,
        test_user,
    ):
        """
        Test: get_tos_status returns correct status when TOS is accepted

        Verifies the service layer correctly determines TOS compliance status.
        """
        # Arrange - Create TOS acceptance
        repo = TosAcceptanceRepository(db_session)
        tos_version = "v1.0"
        accepted_at = datetime.now(UTC)

        repo.create_tos_acceptance(
            account_id=test_account.id,
            display_name=test_account.display_name or test_account.name,
            tos_version=tos_version,
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=accepted_at,
        )
        db_session.commit()

        # Act - Get TOS status
        with patch("services.account_service.CURRENT_TOS_VERSION", tos_version):
            status = account_service.get_tos_status(
                db_session, test_account.id, tos_version
            )

        # Assert - Status shows compliance
        assert status["accepted_tos_version"] == tos_version
        assert status["is_compliant"] is True
        assert status["accepted_at"] is not None

    def test_get_tos_status_without_acceptance(
        self, db_session: Session, test_account: Account
    ):
        """
        Test: get_tos_status returns non-compliant when TOS not accepted

        Verifies the service layer correctly identifies accounts without TOS acceptance.
        """
        # Act - Get TOS status for account without acceptance
        with patch("services.account_service.CURRENT_TOS_VERSION", "v1.0"):
            status = account_service.get_tos_status(db_session, test_account.id, "v1.0")

        # Assert - Status shows non-compliance
        assert status["accepted_tos_version"] is None
        assert status["is_compliant"] is False
        assert status["accepted_at"] is None

    def test_get_accounts_without_version(
        self,
        db_session: Session,
        test_account: Account,
        test_user,
    ):
        """
        Test: get_accounts_without_version returns accounts that haven't accepted a version

        Verifies the repository method correctly filters accounts based on TOS acceptance.
        """
        # Arrange - Create a second account that won't accept TOS
        account2_id = uuid.uuid4()
        now = datetime.now(UTC)
        account2 = Account(
            id=account2_id,
            name=f"test-account-2-{account2_id.hex[:8]}",
            display_name="Test Account 2 Without TOS",
            status=AccountStatus.active,
            created_at=now,
            updated_at=now,
        )
        db_session.add(account2)

        # Arrange - Create a third account that accepted a different version (v0.9)
        account3_id = uuid.uuid4()
        account3 = Account(
            id=account3_id,
            name=f"test-account-3-{account3_id.hex[:8]}",
            display_name="Test Account 3 With Old TOS",
            status=AccountStatus.active,
            created_at=now,
            updated_at=now,
        )
        db_session.add(account3)
        db_session.flush()

        # Arrange - Have test_account accept v1.0, account3 accept v0.9, account2 accept nothing
        repo = TosAcceptanceRepository(db_session)
        repo.create_tos_acceptance(
            account_id=test_account.id,
            display_name=test_account.display_name or test_account.name,
            tos_version="v1.0",
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=datetime.now(UTC),
        )
        repo.create_tos_acceptance(
            account_id=account3.id,
            display_name=account3.name,
            tos_version="v0.9",
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=datetime.now(UTC),
        )
        db_session.commit()

        # Act - Get accounts without v1.0 acceptance
        accounts_without_v1 = repo.get_accounts_without_version("v1.0")

        # Assert - account2 and account3 are in the list, test_account is not
        account_ids_without = [acc.id for acc in accounts_without_v1]
        assert (
            account2.id in account_ids_without
        ), "Account with no acceptance should be included"
        assert (
            account3.id in account_ids_without
        ), "Account with different version should be included"
        assert (
            test_account.id not in account_ids_without
        ), "Account with v1.0 should not be included"


class TestTermsStatusEndpointIntegration:
    """Integration tests for /terms_status endpoint with real database."""

    def test_terms_status_endpoint_with_acceptance(
        self,
        db_session: Session,
        test_account: Account,
        test_user,
    ):
        """
        Test: /terms_status endpoint returns correct data when TOS is accepted

        Tests the full API endpoint flow with real database.
        """
        # Arrange - Create TOS acceptance in database
        repo = TosAcceptanceRepository(db_session)
        tos_version = "v1.0"
        accepted_at = datetime.now(UTC)

        repo.create_tos_acceptance(
            account_id=test_account.id,
            display_name=test_account.display_name or test_account.name,
            tos_version=tos_version,
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=accepted_at,
        )
        db_session.commit()

        # Arrange - Mock user context
        mock_context = MagicMock()
        mock_context.email = test_user.email
        mock_context.username = str(test_user.user.id)

        # Act - Call the endpoint
        with patch("services.account_service.CURRENT_TOS_VERSION", tos_version):
            with patch(
                "api.routes.admin._account.account_service.get_account",
                return_value=test_account,
            ):
                response = get_account_terms_status(
                    test_account.name, mock_context, db_session
                )

        # Assert - Response contains correct data
        assert response.id == test_account.id
        assert response.name == test_account.name
        assert response.display_name == test_account.display_name
        assert response.accepted_tos_version == tos_version
        assert response.is_compliant is True
        assert response.accepted_at is not None
        assert response.current_tos_version == tos_version

    def test_terms_status_endpoint_without_acceptance(
        self, db_session: Session, test_account: Account
    ):
        """
        Test: /terms_status endpoint returns non-compliant when TOS not accepted

        Tests the API endpoint with an account that has never accepted TOS.
        """
        # Arrange - Mock user context
        mock_context = MagicMock()

        # Act - Call the endpoint
        with patch("services.account_service.CURRENT_TOS_VERSION", "v1.0"):
            with patch(
                "api.routes.admin._account.account_service.get_account",
                return_value=test_account,
            ):
                response = get_account_terms_status(
                    test_account.name, mock_context, db_session
                )

        # Assert - Response shows non-compliance
        assert response.id == test_account.id
        assert response.name == test_account.name
        assert response.accepted_tos_version is None
        assert response.is_compliant is False
        assert response.accepted_at is None
        assert response.current_tos_version == "v1.0"

    def test_terms_status_endpoint_account_not_found(self, db_session: Session):
        """
        Test: /terms_status endpoint returns 404 when account not found

        Tests error handling in the API endpoint.
        """
        # Arrange
        mock_context = MagicMock()

        # Act & Assert - Endpoint raises 404
        with patch(
            "api.routes.admin._account.account_service.get_account", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_account_terms_status("nonexistent", mock_context, db_session)

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail


class TestAcceptTermsEndpointIntegration:
    """Integration tests for accept_terms endpoint with real database."""

    @pytest.mark.asyncio
    async def test_accept_terms_endpoint_creates_record(
        self, db_session: Session, test_account: Account, test_user
    ):
        """
        Test: accept_terms endpoint creates TOS acceptance record

        Tests the full accept TOS flow through the API endpoint.
        """
        # Arrange
        mock_context = MagicMock()
        mock_context.email = test_user.email
        mock_context.username = str(test_user.user.id)

        request = AcceptTermsRequest(tos_version="v1.0")

        # Act - Call the endpoint
        with patch("services.account_service.CURRENT_TOS_VERSION", "v1.0"):
            with patch(
                "api.routes.admin._account.account_service.get_account",
                return_value=test_account,
            ):
                with patch(
                    "api.routes.admin._account.get_user_role_on_account",
                    return_value="owner",
                ):
                    response = await accept_account_terms(
                        test_account.name, request, mock_context, db_session
                    )

        # Assert - Response indicates success
        assert response.accepted is True
        assert response.tos_version == "v1.0"

        # Assert - Record exists in database (query from same session)
        db_session.expire_all()  # Force reload from database
        repo = TosAcceptanceRepository(db_session)
        acceptance = repo.get_tos_acceptance_by_version(test_account.id, "v1.0")
        assert acceptance is not None
        assert acceptance.account_id == test_account.id
        assert acceptance.tos_version == "v1.0"
        assert acceptance.user_id == test_user.user.id

    @pytest.mark.asyncio
    async def test_accept_terms_endpoint_idempotent(
        self,
        db_session: Session,
        test_account: Account,
        test_user,
    ):
        """
        Test: accept_terms endpoint is idempotent (accepting twice succeeds)

        Verifies that accepting the same TOS version twice is safe.
        """
        # Arrange - Create initial acceptance
        repo = TosAcceptanceRepository(db_session)
        accepted_at = datetime.now(UTC)

        repo.create_tos_acceptance(
            account_id=test_account.id,
            display_name=test_account.display_name or test_account.name,
            tos_version="v1.0",
            user_id=test_user.user.id,
            user_email=test_user.email,
            accepted_at=accepted_at,
        )
        db_session.commit()

        # Arrange - Mock context and request
        mock_context = MagicMock()
        mock_context.email = test_user.email
        mock_context.username = str(test_user.user.id)
        request = AcceptTermsRequest(tos_version="v1.0")

        # Act - Try to accept again
        with patch("services.account_service.CURRENT_TOS_VERSION", "v1.0"):
            with patch(
                "api.routes.admin._account.account_service.get_account",
                return_value=test_account,
            ):
                with patch(
                    "api.routes.admin._account.get_user_role_on_account",
                    return_value="owner",
                ):
                    response = await accept_account_terms(
                        test_account.name, request, mock_context, db_session
                    )

        # Assert - Second acceptance succeeds (idempotent)
        assert response.accepted is True
        assert response.tos_version == "v1.0"

        # Assert - Still only one record in database
        db_session.expire_all()  # Force reload from database
        all_acceptances = (
            db_session.query(TosAcceptance)
            .filter(
                TosAcceptance.account_id == test_account.id,
                TosAcceptance.tos_version == "v1.0",
            )
            .all()
        )
        assert len(all_acceptances) == 1

    @pytest.mark.asyncio
    async def test_accept_terms_endpoint_blocks_internal_users(
        self, db_session: Session, test_account: Account, test_user
    ):
        """
        Test: accept_terms endpoint blocks @proactiveailab.com users

        Verifies internal users cannot accept TOS.
        """
        # Arrange
        mock_context = MagicMock()
        mock_context.email = "internal@proactiveailab.com"
        mock_context.username = str(test_user.user.id)
        request = AcceptTermsRequest(tos_version="v1.0")

        # Act & Assert - Endpoint raises 403
        with patch("services.account_service.CURRENT_TOS_VERSION", "v1.0"):
            with patch(
                "api.routes.admin._account.account_service.get_account",
                return_value=test_account,
            ):
                with patch(
                    "api.routes.admin._account.get_user_role_on_account",
                    return_value="owner",
                ):
                    with pytest.raises(HTTPException) as exc_info:
                        await accept_account_terms(
                            test_account.name, request, mock_context, db_session
                        )

                    assert exc_info.value.status_code == 403
                    assert "Internal team members" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_accept_terms_endpoint_requires_owner_role(
        self, db_session: Session, test_account: Account, test_user
    ):
        """
        Test: accept_terms endpoint requires owner role

        Verifies only account owners can accept TOS.
        """
        # Arrange
        mock_context = MagicMock()
        mock_context.email = test_user.email
        mock_context.username = str(test_user.user.id)
        request = AcceptTermsRequest(tos_version="v1.0")

        # Act & Assert - Non-owner role raises 403
        with patch("services.account_service.CURRENT_TOS_VERSION", "v1.0"):
            with patch(
                "api.routes.admin._account.account_service.get_account",
                return_value=test_account,
            ):
                with patch(
                    "api.routes.admin._account.get_user_role_on_account",
                    return_value="manager",  # Not owner
                ):
                    with pytest.raises(HTTPException) as exc_info:
                        await accept_account_terms(
                            test_account.name, request, mock_context, db_session
                        )

                    assert exc_info.value.status_code == 403
                    assert "Only account Admins" in exc_info.value.detail
