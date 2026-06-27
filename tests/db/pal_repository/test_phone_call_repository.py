"""Tests for db.pal_repository.PhoneCallRepository.

Validates the async DTO-based repository: ORM objects stay inside the
repository layer and only PhoneCallData instances are returned to callers.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError

from db.pal_repository.data_classes.phone_call import PhoneCallData
from db.pal_repository.phone_call import PhoneCallRepository
from db.tables.phonecalls import PhoneCall
from db.tables.types import (
    CallEndedReason,
    CallLanguage,
    CallPurpose,
    CallQualityLabel,
    UserSatisfaction,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> PhoneCallRepository:
    return PhoneCallRepository(mock_session)


@pytest.fixture
def sample_phone_call_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_conversation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_phone_call_id: uuid.UUID, sample_conversation_id: uuid.UUID
) -> MagicMock:
    row = MagicMock(spec=PhoneCall)
    row.id = sample_phone_call_id
    row.call_id = "call-abc-123"
    row.conversation_id = sample_conversation_id
    row.duration = 42.5
    row.turn_latency_avg = 0.8
    row.model_latency_avg = 200.0
    row.voice_latency_avg = 150.0
    row.transcriber_latency_avg = 100.0
    row.endpointing_latency_avg = 50.0
    row.ended_reason = CallEndedReason.customer_ended
    row.call_purpose = [CallPurpose.ordering]
    row.user_satisfaction = UserSatisfaction.positive
    row.language = CallLanguage.english
    row.transfer_reason_category = "tool_failure_order"
    row.transfer_agent_was_at_fault = True
    row.call_quality_label = CallQualityLabel.legitimate_restaurant_call
    row.call_quality_reason_codes = ["restaurant_intent_present"]
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# TestGetByCallId
# ---------------------------------------------------------------------------


class TestGetByCallId:
    """Lookup by provider call ID — used during end-of-call processing."""

    @pytest.mark.asyncio
    async def test_returns_dto_when_found(
        self,
        repo: PhoneCallRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        dto = await repo.get_by_call_id("call-abc-123")

        assert isinstance(dto, PhoneCallData)
        assert dto.call_id == "call-abc-123"
        assert dto.duration == 42.5
        assert dto.ended_reason == "customer_ended"
        assert dto.call_purpose == ("ordering",)
        assert dto.user_satisfaction == "positive"
        assert dto.language == "english"
        assert dto.transfer_reason_category == "tool_failure_order"
        assert dto.transfer_agent_was_at_fault is True
        assert dto.call_quality_label == "legitimate_restaurant_call"
        assert dto.call_quality_reason_codes == ("restaurant_intent_present",)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: PhoneCallRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        dto = await repo.get_by_call_id("nonexistent")
        assert dto is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: PhoneCallRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_call_id("call-abc-123")
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_multiple_results(
        self, repo: PhoneCallRepository, mock_session: AsyncMock
    ) -> None:
        """Duplicate call_id rows must surface as an error, not be silently ignored."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = MultipleResultsFound()
        mock_session.execute.return_value = mock_result

        with pytest.raises(MultipleResultsFound):
            await repo.get_by_call_id("call-dup")


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new phone call record during call setup."""

    @pytest.mark.asyncio
    async def test_create_returns_dto(
        self,
        repo: PhoneCallRepository,
        mock_session: AsyncMock,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        created_id = uuid.uuid4()
        now = datetime(2025, 6, 1, tzinfo=timezone.utc)

        def capture_add(obj: PhoneCall) -> None:
            obj.id = created_id
            obj.created_at = now

        mock_session.add.side_effect = capture_add

        input_dto = PhoneCallData(
            id=uuid.uuid4(),
            call_id="call-new-1",
            conversation_id=sample_conversation_id,
            duration=10.0,
            ended_reason="customer_ended",
            transfer_reason_category="cold_opt_out",
            transfer_agent_was_at_fault=False,
            call_quality_label="promotional_sales",
            call_quality_reason_codes=("sales_or_vendor_outreach",),
        )

        dto = await repo.create(input_dto)

        assert isinstance(dto, PhoneCallData)
        assert dto.call_id == "call-new-1"
        assert dto.conversation_id == sample_conversation_id
        assert dto.duration == 10.0
        assert dto.ended_reason == "customer_ended"
        assert dto.transfer_reason_category == "cold_opt_out"
        assert dto.transfer_agent_was_at_fault is False
        assert dto.call_quality_label == "promotional_sales"
        assert dto.call_quality_reason_codes == ("sales_or_vendor_outreach",)
        mock_session.add.assert_called_once()
        added = mock_session.add.call_args.args[0]
        assert added.call_quality_label is CallQualityLabel.promotional_sales
        assert added.call_quality_reason_codes == ["sales_or_vendor_outreach"]
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: PhoneCallRepository,
        mock_session: AsyncMock,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_dto = PhoneCallData(
            id=uuid.uuid4(),
            call_id="call-fail",
            conversation_id=sample_conversation_id,
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_dto)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Updating call analytics at end-of-call."""

    @pytest.mark.asyncio
    async def test_update_returns_dto_with_updated_fields(
        self,
        repo: PhoneCallRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        update_dto = PhoneCallData(
            id=uuid.uuid4(),
            call_id="call-abc-123",
            conversation_id=uuid.uuid4(),
            duration=99.9,
            ended_reason="customer_ended",
            transfer_reason_category="failed_transfer_attempt",
            transfer_agent_was_at_fault=True,
            call_quality_label="prank_or_abusive",
            call_quality_reason_codes=("abusive_or_prank_language",),
        )

        dto = await repo.update(call_id="call-abc-123", record=update_dto)

        assert isinstance(dto, PhoneCallData)
        assert dto.call_id == "call-abc-123"
        assert sample_orm_row.transfer_reason_category == "failed_transfer_attempt"
        assert sample_orm_row.transfer_agent_was_at_fault is True
        assert sample_orm_row.call_quality_label is CallQualityLabel.prank_or_abusive
        assert sample_orm_row.call_quality_reason_codes == ["abusive_or_prank_language"]
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_returns_none_when_not_found(
        self, repo: PhoneCallRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        update_dto = PhoneCallData(
            id=uuid.uuid4(),
            call_id="nonexistent",
            conversation_id=uuid.uuid4(),
            duration=1.0,
        )

        dto = await repo.update(call_id="nonexistent", record=update_dto)
        assert dto is None

    @pytest.mark.asyncio
    async def test_update_raises_on_db_error(
        self, repo: PhoneCallRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        update_dto = PhoneCallData(
            id=uuid.uuid4(),
            call_id="call-abc-123",
            conversation_id=uuid.uuid4(),
            duration=1.0,
        )

        with pytest.raises(SQLAlchemyError):
            await repo.update(call_id="call-abc-123", record=update_dto)
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_only_sets_non_none_fields(
        self,
        repo: PhoneCallRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        """Verify that None fields in the DTO are skipped — no field is accidentally cleared."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        # Only set duration; everything else is default (None)
        update_dto = PhoneCallData(
            id=uuid.uuid4(),
            call_id="call-abc-123",
            conversation_id=uuid.uuid4(),
            duration=100.0,
        )

        await repo.update(call_id="call-abc-123", record=update_dto)

        # duration was set
        assert sample_orm_row.duration == 100.0
        # ended_reason was NOT overwritten (still the original value from fixture)
        assert sample_orm_row.ended_reason == CallEndedReason.customer_ended
        assert (
            sample_orm_row.call_quality_label
            is CallQualityLabel.legitimate_restaurant_call
        )


# ---------------------------------------------------------------------------
# TestDTOImmutability
# ---------------------------------------------------------------------------


class TestDTOImmutability:
    """PhoneCallData is a frozen dataclass — mutations are disallowed."""

    def test_dto_is_immutable(self) -> None:
        dto = PhoneCallData(
            id=uuid.uuid4(),
            call_id="call-x",
            conversation_id=uuid.uuid4(),
        )
        with pytest.raises(AttributeError):
            dto.call_id = "changed"  # type: ignore[misc]

    def test_call_purpose_defaults_to_empty_tuple(self) -> None:
        dto = PhoneCallData(
            id=uuid.uuid4(),
            call_id="call-y",
            conversation_id=uuid.uuid4(),
        )
        assert dto.call_purpose == ()
        assert dto.call_quality_reason_codes == ()
