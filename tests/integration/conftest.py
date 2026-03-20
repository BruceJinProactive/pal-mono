"""Integration test fixtures with real PostgreSQL database.

These fixtures use the Docker PostgreSQL database for end-to-end integration testing.
They create real database sessions and clean up after each test.
"""

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Override test defaults with real Docker database settings
# These must be set before importing db_settings
# Use setdefault to respect CI/local overrides
os.environ.setdefault("db_host", "postgres")
os.environ.setdefault("db_port", "5432")
os.environ.setdefault("db_user", "app")
os.environ.setdefault("db_pass", "app")
os.environ.setdefault("db_database", "app")

from db.settings import db_settings
from db.tables import Account, User
from db.tables.accounts import AccountStatus
from db.tables.base import Base


@dataclass
class TestUserData:
    """Container for test user data with associated email."""

    user: User
    email: str


@pytest.fixture(scope="session")
def db_engine():
    """
    Create a database engine for the entire test session.
    Uses the same database configuration as the application.
    Initializes schema if tables don't exist.
    """
    db_url = db_settings.get_db_url()
    engine = create_engine(
        db_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    # Initialize schema - creates tables if they don't exist
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def db_session_factory(db_engine):
    """Create a session factory for creating database sessions."""
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture
def db_session(db_session_factory):
    """
    Provide a transactional database session for each test.

    Creates a new session, yields it for the test, then rolls back
    all changes to keep tests isolated.

    Note: session.rollback() only undoes uncommitted changes. If a test
    calls session.commit(), those changes are persisted to the database
    and will not be reverted by the rollback. For tests that commit changes,
    use explicit cleanup fixtures (e.g., cleanup_tos_acceptances) or
    ensure test isolation through other means.
    """
    session: Session = db_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_account(db_session: Session):
    """
    Create a test account in the database for TOS testing.

    Returns:
        Account: A test account with predictable data
    """
    account_id = uuid.uuid4()
    now = datetime.now(UTC)
    account = Account(
        id=account_id,
        name=f"test-account-{account_id.hex[:8]}",
        display_name="Test Account for TOS",
        status=AccountStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(account)
    db_session.flush()
    return account


@pytest.fixture
def test_user(db_session: Session, test_account):
    """
    Create a test user associated with the test account.

    Returns:
        TestUserData: A container with user and email
    """
    user_id = uuid.uuid4()
    email = f"test-owner-{user_id.hex[:8]}@example.com"
    now = datetime.now(UTC)
    user = User(
        id=user_id,
        account_id=test_account.id,
        channel_identifiers=[email],
        created_at=now,
        updated_at=now,
    )
    db_session.add(user)
    db_session.flush()
    return TestUserData(user=user, email=email)


@pytest.fixture
def cleanup_tos_acceptances(db_session: Session):
    """
    Clean up TOS acceptance records after tests.

    Use this fixture when you need to ensure TOS records are cleaned up
    even if the test creates them outside the session transaction.
    """
    created_account_ids = []

    def register_account(account_id: uuid.UUID):
        created_account_ids.append(account_id)

    yield register_account

    # Cleanup
    if created_account_ids:
        # Delete TOS acceptances for each registered account
        for account_id in created_account_ids:
            db_session.execute(
                text("DELETE FROM tos_acceptances WHERE account_id = :account_id"),
                {"account_id": str(account_id)},
            )
        db_session.commit()
