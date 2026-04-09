"""Tests for save_reservation_from_agent_async and _parse_datetime."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from db.tables.types import IntegrationProvider
from services.reservation_service._implementation import (
    _parse_datetime,
    save_reservation_from_agent_async,
)


class FakeReservationDetails:
    """Fake reservation details object similar to pal-agents ReservationDetails."""

    def __init__(
        self,
        vendor: str = "minitable",
        entry_type: str = "reservation",
        reservation_id: str | None = "BOOKING-123",
        store_id: str = "REST-456",
        status: str = "confirmed",
        party_size: int | None = 4,
        notes: str | None = "Window seat please",
        reservation_time: str | None = "2026-04-10T19:00",
        arrive_by_time: str | None = None,
        expected_seating_time: str | None = None,
        tracking_link: str | None = "https://example.com/status/BOOKING-123",
    ):
        self.vendor = vendor
        self.entry_type = entry_type
        self.reservation_id = reservation_id
        self.store_id = store_id
        self.status = status
        self.party_size = party_size
        self.notes = notes
        self.reservation_time = reservation_time
        self.arrive_by_time = arrive_by_time
        self.expected_seating_time = expected_seating_time
        self.tracking_link = tracking_link


@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def conversation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_reservation() -> Mock:
    """Mock reservation ORM object."""
    reservation = Mock()
    reservation.id = uuid.uuid4()
    reservation.conversation_id = uuid.uuid4()
    reservation.entry_type = "reservation"
    reservation.vendor = IntegrationProvider.minitable
    return reservation


# ── _parse_datetime tests ────────────────────────────────────────────


class TestParseDatetime:
    def test_none_returns_none(self) -> None:
        assert _parse_datetime(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_datetime("") is None

    def test_iso_format(self) -> None:
        result = _parse_datetime("2026-04-10T19:00:00")
        assert result == datetime(2026, 4, 10, 19, 0, 0)

    def test_iso_format_with_timezone(self) -> None:
        result = _parse_datetime("2026-04-10T19:00:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_unix_epoch_string(self) -> None:
        result = _parse_datetime("1700000000")
        assert result is not None
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_unix_epoch_float_string(self) -> None:
        result = _parse_datetime("1700000000.5")
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_garbage_returns_none(self) -> None:
        assert _parse_datetime("not-a-date") is None


# ── save_reservation_from_agent_async tests ──────────────────────────


@pytest.mark.asyncio
class TestSaveReservationFromAgentAsync:
    async def test_success_minitable_reservation(
        self,
        mock_session: AsyncMock,
        mock_reservation: Mock,
        conversation_id: uuid.UUID,
    ) -> None:
        """Successful MiniTable reservation is persisted and committed."""
        details = FakeReservationDetails()

        async def mock_run_sync(func):
            mock_sync_session = Mock()
            mock_repo = Mock()
            mock_repo.create_reservation = Mock(return_value=mock_reservation)

            with (
                patch(
                    "services.reservation_service._implementation.ReservationRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "services.reservation_service._implementation._update_customer_converted",
                    return_value=True,
                ),
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        result = await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert result == mock_reservation.id
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    async def test_success_yelp_waitlist(
        self,
        mock_session: AsyncMock,
        mock_reservation: Mock,
        conversation_id: uuid.UUID,
    ) -> None:
        """Yelp waitlist with epoch timestamps is persisted correctly."""
        mock_reservation.entry_type = "waitlist"
        details = FakeReservationDetails(
            vendor="yelp",
            entry_type="waitlist",
            reservation_id="VISIT-789",
            store_id="BIZ-456",
            status="queued",
            party_size=2,
            notes=None,
            reservation_time=None,
            arrive_by_time="1700000000",
            expected_seating_time="1700001800",
            tracking_link=None,
        )

        captured_kwargs: dict = {}

        async def mock_run_sync(func):
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create(**kwargs):
                captured_kwargs.update(kwargs)
                return mock_reservation

            mock_repo.create_reservation = Mock(side_effect=capture_create)

            with (
                patch(
                    "services.reservation_service._implementation.ReservationRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "services.reservation_service._implementation._update_customer_converted",
                    return_value=True,
                ),
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        result = await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert result is not None
        # Epoch timestamps should be parsed to datetime
        assert isinstance(captured_kwargs["arrive_by_time"], datetime)
        assert captured_kwargs["arrive_by_time"].tzinfo == timezone.utc
        assert isinstance(captured_kwargs["expected_seating_time"], datetime)
        # party_size maps to table_size
        assert captured_kwargs["table_size"] == 2

    async def test_invalid_vendor_returns_none(
        self, mock_session: AsyncMock, conversation_id: uuid.UUID
    ) -> None:
        """Unknown vendor returns None without persisting."""
        details = FakeReservationDetails(vendor="unknown_vendor")

        result = await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert result is None
        mock_session.commit.assert_not_called()

    async def test_auto_commit_false_on_repository(
        self,
        mock_session: AsyncMock,
        mock_reservation: Mock,
        conversation_id: uuid.UUID,
    ) -> None:
        """Repository is created with auto_commit=False (outer commit owns txn)."""
        details = FakeReservationDetails()
        captured_auto_commit = None

        async def mock_run_sync(func):
            nonlocal captured_auto_commit
            mock_sync_session = Mock()

            class CapturingRepo:
                def __init__(self, session, auto_commit=True):
                    nonlocal captured_auto_commit
                    captured_auto_commit = auto_commit

                def create_reservation(self, **kwargs):
                    return mock_reservation

            with (
                patch(
                    "services.reservation_service._implementation.ReservationRepository",
                    CapturingRepo,
                ),
                patch(
                    "services.reservation_service._implementation._update_customer_converted",
                    return_value=True,
                ),
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert captured_auto_commit is False

    async def test_customer_converted_triggered_for_confirmed_reservation(
        self,
        mock_session: AsyncMock,
        mock_reservation: Mock,
        conversation_id: uuid.UUID,
    ) -> None:
        """Confirmed reservation triggers _update_customer_converted."""
        details = FakeReservationDetails(status="confirmed", entry_type="reservation")
        update_called = False

        async def mock_run_sync(func):
            nonlocal update_called
            mock_sync_session = Mock()
            mock_repo = Mock()
            mock_repo.create_reservation = Mock(return_value=mock_reservation)

            def track_update(**kwargs):
                nonlocal update_called
                update_called = True
                return True

            with (
                patch(
                    "services.reservation_service._implementation.ReservationRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "services.reservation_service._implementation._update_customer_converted",
                    side_effect=track_update,
                ),
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert update_called

    async def test_customer_converted_triggered_for_queued_waitlist(
        self,
        mock_session: AsyncMock,
        mock_reservation: Mock,
        conversation_id: uuid.UUID,
    ) -> None:
        """Queued waitlist triggers _update_customer_converted."""
        details = FakeReservationDetails(
            entry_type="waitlist", status="queued", vendor="yelp"
        )
        update_called = False

        async def mock_run_sync(func):
            nonlocal update_called
            mock_sync_session = Mock()
            mock_repo = Mock()
            mock_repo.create_reservation = Mock(return_value=mock_reservation)

            def track_update(**kwargs):
                nonlocal update_called
                update_called = True
                return True

            with (
                patch(
                    "services.reservation_service._implementation.ReservationRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "services.reservation_service._implementation._update_customer_converted",
                    side_effect=track_update,
                ),
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert update_called

    async def test_customer_converted_not_triggered_for_pending_status(
        self,
        mock_session: AsyncMock,
        mock_reservation: Mock,
        conversation_id: uuid.UUID,
    ) -> None:
        """Non-conversion status does NOT trigger _update_customer_converted."""
        details = FakeReservationDetails(status="pending", entry_type="reservation")
        update_called = False

        async def mock_run_sync(func):
            nonlocal update_called
            mock_sync_session = Mock()
            mock_repo = Mock()
            mock_repo.create_reservation = Mock(return_value=mock_reservation)

            def track_update(**kwargs):
                nonlocal update_called
                update_called = True
                return True

            with (
                patch(
                    "services.reservation_service._implementation.ReservationRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "services.reservation_service._implementation._update_customer_converted",
                    side_effect=track_update,
                ),
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert not update_called

    async def test_error_triggers_rollback(
        self, mock_session: AsyncMock, conversation_id: uuid.UUID
    ) -> None:
        """Database error triggers rollback and returns None."""
        details = FakeReservationDetails()

        async def mock_run_sync(func):
            raise Exception("Database error")

        mock_session.run_sync = mock_run_sync

        result = await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert result is None
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    async def test_field_mapping_party_size_to_table_size(
        self,
        mock_session: AsyncMock,
        mock_reservation: Mock,
        conversation_id: uuid.UUID,
    ) -> None:
        """party_size from ReservationDetails maps to table_size in ReservationData."""
        details = FakeReservationDetails(party_size=6)
        captured_kwargs: dict = {}

        async def mock_run_sync(func):
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create(**kwargs):
                captured_kwargs.update(kwargs)
                return mock_reservation

            mock_repo.create_reservation = Mock(side_effect=capture_create)

            with (
                patch(
                    "services.reservation_service._implementation.ReservationRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "services.reservation_service._implementation._update_customer_converted",
                    return_value=True,
                ),
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert captured_kwargs["table_size"] == 6

    async def test_field_mapping_notes_to_special_requests(
        self,
        mock_session: AsyncMock,
        mock_reservation: Mock,
        conversation_id: uuid.UUID,
    ) -> None:
        """notes from ReservationDetails maps to special_requests in ReservationData."""
        details = FakeReservationDetails(notes="No onions please")
        captured_kwargs: dict = {}

        async def mock_run_sync(func):
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create(**kwargs):
                captured_kwargs.update(kwargs)
                return mock_reservation

            mock_repo.create_reservation = Mock(side_effect=capture_create)

            with (
                patch(
                    "services.reservation_service._implementation.ReservationRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "services.reservation_service._implementation._update_customer_converted",
                    return_value=True,
                ),
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        await save_reservation_from_agent_async(
            session=mock_session,
            reservation_details=details,
            conversation_id=conversation_id,
        )

        assert captured_kwargs["special_requests"] == "No onions please"
