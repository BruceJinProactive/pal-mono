"""Integration test fixtures with real PostgreSQL database.

Uses SAVEPOINT-based rollback so that session.commit() inside tested code
hits a SAVEPOINT, not the real transaction. The outer transaction rolls back
everything unconditionally at teardown — no cleanup fixtures needed.

Fixture dependency graph:
  db_engine (session) -> db_session (function) -> world (function)
                                                -> app_with_overrides -> client
  async_engine (session) -> async_session (function) -^
"""

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import AsyncGenerator, Callable, Generator
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session

# Override test defaults with real Docker database settings
# These must be set before importing db_settings
# Use setdefault to respect CI/local overrides
os.environ.setdefault("db_host", "postgres")
os.environ.setdefault("db_port", "5432")
os.environ.setdefault("db_user", "app")
os.environ.setdefault("db_pass", "app")
os.environ.setdefault("db_database", "app")

from db.session import get_db, get_db_async
from db.settings import db_settings
from db.tables import Account, User
from db.tables.accounts import AccountStatus
from db.tables.base import Base
from services.auth_types import UserContext, UserRole
from tests.factories import World, make_world


@dataclass
class TestUserData:
    """Container for test user data with associated email."""

    user: User
    email: str


# ---------------------------------------------------------------------------
# Sync engine + SAVEPOINT session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_engine():
    """Session-scoped sync engine. Creates schema once."""
    db_url = db_settings.get_db_url()
    engine = create_engine(
        db_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Function-scoped SAVEPOINT session.

    When tested code calls session.commit(), it commits to the SAVEPOINT,
    not the real transaction. The outer transaction.rollback() at teardown
    undoes everything — including commits.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Async engine + SAVEPOINT session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def async_engine():
    """Session-scoped async engine."""
    db_url_async = db_settings.get_db_url_async()
    engine = create_async_engine(
        db_url_async,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    yield engine
    # dispose is sync-safe on the async engine object
    engine.sync_engine.dispose()


@pytest.fixture
async def async_session(async_engine):
    """Function-scoped async SAVEPOINT session."""
    async with async_engine.connect() as conn:
        trans = await conn.begin()
        await conn.begin_nested()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")

        # When the session commits (hitting the SAVEPOINT), restart a nested
        # transaction so subsequent commits also go to a SAVEPOINT.
        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(session_inner, transaction):  # type: ignore[no-untyped-def]
            if conn.closed:
                return
            if not conn.in_nested_transaction():
                conn.sync_connection.begin_nested()  # type: ignore[union-attr]

        yield session
        await session.close()
        await trans.rollback()


# ---------------------------------------------------------------------------
# Pool-health autouse fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _assert_sync_pool_healthy(db_engine):
    """Catches DB connection leaks after every test."""
    before = db_engine.pool.checkedout()
    yield
    after = db_engine.pool.checkedout()
    assert (
        before == after
    ), f"DB connection leak detected: {before} -> {after} checked out"


# ---------------------------------------------------------------------------
# World fixture (uses factory library)
# ---------------------------------------------------------------------------


@pytest.fixture
def world(db_session: Session) -> World:
    """Create a minimal tenant hierarchy: Account + Agent + Project + User."""
    return make_world(db_session)


# ---------------------------------------------------------------------------
# Convenience fixtures for existing tests
# ---------------------------------------------------------------------------


@pytest.fixture
def test_account(db_session: Session) -> Account:
    """Create a test account in the database."""
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
def test_user(db_session: Session, test_account: Account) -> TestUserData:
    """Create a test user associated with the test account."""
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


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def auth_as(
    username: str | None = None,
    email: str = "test@test.com",
    role: UserRole = UserRole.AccountManager,
    groups: list[str] | None = None,
    display_name: str = "Test User",
) -> UserContext:
    """Build a UserContext for DI overrides."""
    return UserContext(
        username=username or str(uuid.uuid4()),
        email=email,
        role=role,
        groups=groups or [],
        display_name=display_name,
    )


# ---------------------------------------------------------------------------
# FastAPI app with DI overrides + httpx.AsyncClient
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_overrides(db_session: Session) -> Generator:
    """FastAPI app with DB and auth dependencies overridden for testing."""
    from api.main import app
    from api.routes.admin._auth import authenticate_user, require_admin

    # Sync DB override
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    # Async DB override
    async def override_get_db_async() -> AsyncGenerator[Session, None]:
        yield db_session  # type: ignore[misc]

    # Auth overrides — default to admin for convenience
    default_context = auth_as(role=UserRole.Admin)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_db_async] = override_get_db_async
    app.dependency_overrides[authenticate_user] = lambda: default_context
    app.dependency_overrides[require_admin] = lambda: default_context

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def auth_override(app_with_overrides) -> Callable[..., None]:  # type: ignore[type-arg]
    """Override auth for a specific test. Call with auth_override(role=..., username=...)."""
    from api.routes.admin._auth import authenticate_user, require_admin

    def _override(**kwargs: object) -> None:
        ctx = auth_as(**kwargs)  # type: ignore[arg-type]
        app_with_overrides.dependency_overrides[authenticate_user] = lambda: ctx
        app_with_overrides.dependency_overrides[require_admin] = lambda: ctx

    return _override


@pytest.fixture
async def client(app_with_overrides) -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx.AsyncClient with ASGI transport — supports SSE streaming."""
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def patch_async_session_local(db_session: Session):
    """Patch AsyncSessionLocal for streaming endpoints that bypass DI (ADR-019).

    Use explicitly in tests that exercise streaming generators.
    NOT autouse — only requested by tests that need it.
    """

    async def _fake_session_factory() -> AsyncGenerator[Session, None]:
        yield db_session  # type: ignore[misc]

    class FakeSessionLocal:
        def __call__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aenter__(self) -> Session:
            return db_session  # type: ignore[return-value]

        async def __aexit__(self, *args: object) -> None:
            pass

    with patch("db.session.AsyncSessionLocal", FakeSessionLocal()):
        yield
