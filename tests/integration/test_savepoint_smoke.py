"""Smoke tests proving SAVEPOINT rollback works correctly.

Test A creates an Account and commits. Test B verifies that Account
does not exist — proving the outer transaction rolled back everything.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.tables import Account
from db.tables.accounts import AccountStatus

# Unique name shared between test A and test B within the same module run.
# Each test gets its own SAVEPOINT session, so test B should never see test A's data.
_SHARED_NAME = f"savepoint-smoke-{uuid.uuid4().hex[:8]}"


@pytest.mark.integration
class TestSavepointRollback:
    def test_a_create_account_and_commit(self, db_session: Session) -> None:
        """Create an account and commit — SAVEPOINT captures the commit."""
        now = datetime.now(UTC)
        account = Account(
            id=uuid.uuid4(),
            name=_SHARED_NAME,
            display_name="SAVEPOINT smoke test",
            status=AccountStatus.active,
            created_at=now,
            updated_at=now,
        )
        db_session.add(account)
        db_session.commit()

        # Visible within this test's session
        result = db_session.execute(
            select(Account).where(Account.name == _SHARED_NAME)
        ).scalar_one_or_none()
        assert result is not None
        assert result.name == _SHARED_NAME

    def test_b_account_does_not_exist(self, db_session: Session) -> None:
        """Prove the account from test A was rolled back."""
        result = db_session.execute(
            select(Account).where(Account.name == _SHARED_NAME)
        ).scalar_one_or_none()
        assert (
            result is None
        ), f"Account '{_SHARED_NAME}' should not exist — SAVEPOINT rollback failed"
