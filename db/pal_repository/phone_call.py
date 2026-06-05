from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.phone_call import PhoneCallData
from db.tables.phonecalls import PhoneCall
from db.tables.types import CallEndedReason, CallLanguage, CallPurpose, UserSatisfaction
from utils.log import logger


def _to_data(row: PhoneCall) -> PhoneCallData:
    """Convert an ORM PhoneCall to a PhoneCallData.

    Enum fields are converted to their string values so the record does not
    expose ``db.tables.types`` to consumers.
    """
    return PhoneCallData(
        id=row.id,
        call_id=row.call_id,
        conversation_id=row.conversation_id,
        duration=row.duration,
        turn_latency_avg=row.turn_latency_avg,
        model_latency_avg=row.model_latency_avg,
        voice_latency_avg=row.voice_latency_avg,
        transcriber_latency_avg=row.transcriber_latency_avg,
        endpointing_latency_avg=row.endpointing_latency_avg,
        ended_reason=row.ended_reason.value if row.ended_reason else None,
        call_purpose=(
            tuple(p.value for p in row.call_purpose) if row.call_purpose else ()
        ),
        user_satisfaction=(
            row.user_satisfaction.value if row.user_satisfaction else None
        ),
        language=row.language.value if row.language else None,
        transfer_reason_category=row.transfer_reason_category,
        transfer_agent_was_at_fault=row.transfer_agent_was_at_fault,
        created_at=row.created_at,
    )


class PhoneCallRepository:
    """Async-only repository for PhoneCall records.

    All methods return ``PhoneCallData`` — ORM objects never escape this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_call_id(self, call_id: str) -> PhoneCallData | None:
        """Retrieve a phone call record by its provider call ID.

        Raises ``MultipleResultsFound`` if more than one row matches,
        since call_id is expected to be unique.
        """
        try:
            result = await self.session.execute(
                select(PhoneCall).filter(PhoneCall.call_id == call_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving phone call by call_id: {e}")
            raise

    async def create(self, record: PhoneCallData) -> PhoneCallData:
        """Create a new phone call record and return the persisted record.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            phone_call = PhoneCall(
                call_id=record.call_id,
                conversation_id=record.conversation_id,
                duration=record.duration,
                turn_latency_avg=record.turn_latency_avg,
                model_latency_avg=record.model_latency_avg,
                voice_latency_avg=record.voice_latency_avg,
                transcriber_latency_avg=record.transcriber_latency_avg,
                endpointing_latency_avg=record.endpointing_latency_avg,
                ended_reason=(
                    CallEndedReason(record.ended_reason)
                    if record.ended_reason
                    else None
                ),
                call_purpose=(
                    [CallPurpose(p) for p in record.call_purpose]
                    if record.call_purpose
                    else None
                ),
                user_satisfaction=(
                    UserSatisfaction(record.user_satisfaction)
                    if record.user_satisfaction
                    else None
                ),
                language=CallLanguage(record.language) if record.language else None,
                transfer_reason_category=record.transfer_reason_category,
                transfer_agent_was_at_fault=record.transfer_agent_was_at_fault,
            )
            self.session.add(phone_call)
            await self.session.commit()
            await self.session.refresh(phone_call)
            return _to_data(phone_call)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating phone call record: {e}")
            raise

    async def update(
        self,
        call_id: str,
        record: PhoneCallData,
    ) -> PhoneCallData | None:
        """Update an existing phone call record by call_id.

        Fields from *record* that are non-None overwrite the existing values.
        Returns the updated record, or None if no match was found.
        """
        try:
            result = await self.session.execute(
                select(PhoneCall).filter(PhoneCall.call_id == call_id)
            )
            phone_call = result.scalar_one_or_none()
            if not phone_call:
                logger.warning(f"Phone call not found for call_id: {call_id}")
                return None

            if record.duration is not None:
                phone_call.duration = record.duration
            if record.turn_latency_avg is not None:
                phone_call.turn_latency_avg = record.turn_latency_avg
            if record.model_latency_avg is not None:
                phone_call.model_latency_avg = record.model_latency_avg
            if record.voice_latency_avg is not None:
                phone_call.voice_latency_avg = record.voice_latency_avg
            if record.transcriber_latency_avg is not None:
                phone_call.transcriber_latency_avg = record.transcriber_latency_avg
            if record.endpointing_latency_avg is not None:
                phone_call.endpointing_latency_avg = record.endpointing_latency_avg
            if record.ended_reason is not None:
                phone_call.ended_reason = CallEndedReason(record.ended_reason)
            if record.call_purpose:
                phone_call.call_purpose = [CallPurpose(p) for p in record.call_purpose]
            if record.user_satisfaction is not None:
                phone_call.user_satisfaction = UserSatisfaction(
                    record.user_satisfaction
                )
            if record.language is not None:
                phone_call.language = CallLanguage(record.language)
            if record.transfer_reason_category is not None:
                phone_call.transfer_reason_category = record.transfer_reason_category
            if record.transfer_agent_was_at_fault is not None:
                phone_call.transfer_agent_was_at_fault = (
                    record.transfer_agent_was_at_fault
                )

            await self.session.commit()
            await self.session.refresh(phone_call)
            return _to_data(phone_call)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating phone call record: {e}")
            raise
