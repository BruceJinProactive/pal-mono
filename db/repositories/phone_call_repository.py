import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.tables import PhoneCall
from db.tables.types import (
    CallEndedReason,
    CallLanguage,
    CallPurpose,
    CallQualityLabel,
    UserSatisfaction,
)
from utils.log import logger


class PhoneCallRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_call_id(self, call_id: str) -> PhoneCall | None:
        """
        Get a phone call record by call_id.

        Args:
            call_id: The call ID to search for

        Returns:
            PhoneCall | None: The phone call record if found, None otherwise
        """
        try:
            from sqlalchemy import select

            result = await self.session.execute(
                select(PhoneCall).filter(PhoneCall.call_id == call_id)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving phone call by call_id: {e}")
            return None

    async def create_phone_call(
        self,
        call_id: str,
        conversation_id: uuid.UUID,
        duration: float | None = None,
        turn_latency_avg: float | None = None,
        model_latency_avg: float | None = None,
        voice_latency_avg: float | None = None,
        transcriber_latency_avg: float | None = None,
        endpointing_latency_avg: float | None = None,
        ended_reason: CallEndedReason | None = None,
        call_purpose: list[CallPurpose] | None = None,
        user_satisfaction: UserSatisfaction | None = None,
        language: CallLanguage | None = None,
        transfer_reason_category: str | None = None,
        transfer_agent_was_at_fault: bool | None = None,
        call_quality_label: CallQualityLabel | None = None,
        call_quality_reason_codes: list[str] | None = None,
    ) -> PhoneCall:
        """
        Create a new phone call record.

        Args:
            call_id: Unique identifier for the call from the voice provider
            conversation_id: Associated conversation ID
            duration: Call duration in seconds
            turn_latency_avg: Average turn latency in seconds
            model_latency_avg: Average model latency in milliseconds
            voice_latency_avg: Average voice latency in milliseconds
            transcriber_latency_avg: Average transcriber latency in milliseconds
            endpointing_latency_avg: Average endpointing latency in milliseconds
            ended_reason: Reason the call ended
            call_purpose: List of call purposes identified
            user_satisfaction: User satisfaction level
            language: Language used in the call
            transfer_reason_category: Retrospective reason the call was transferred
            transfer_agent_was_at_fault: Whether the transfer was caused by agent fault
            call_quality_label: Post-call quality/spam classifier label
            call_quality_reason_codes: Short reason codes supporting the classifier

        Returns:
            PhoneCall: The created phone call record

        Raises:
            SQLAlchemyError: If there is an error creating the phone call
        """
        phone_call = PhoneCall(
            call_id=call_id,
            conversation_id=conversation_id,
            duration=duration,
            turn_latency_avg=turn_latency_avg,
            model_latency_avg=model_latency_avg,
            voice_latency_avg=voice_latency_avg,
            transcriber_latency_avg=transcriber_latency_avg,
            endpointing_latency_avg=endpointing_latency_avg,
            ended_reason=ended_reason,
            call_purpose=call_purpose,
            user_satisfaction=user_satisfaction,
            language=language,
            transfer_reason_category=transfer_reason_category,
            transfer_agent_was_at_fault=transfer_agent_was_at_fault,
            call_quality_label=call_quality_label,
            call_quality_reason_codes=call_quality_reason_codes,
        )

        self.session.add(phone_call)
        await self.session.flush()

        # Store ID before logging to avoid accessing expired object attributes
        phone_call_id = phone_call.id
        logger.info(f"Phone call record created: {phone_call_id} for call {call_id}")
        return phone_call

    async def update_phone_call(
        self,
        call_id: str,
        duration: float | None = None,
        turn_latency_avg: float | None = None,
        model_latency_avg: float | None = None,
        voice_latency_avg: float | None = None,
        transcriber_latency_avg: float | None = None,
        endpointing_latency_avg: float | None = None,
        ended_reason: CallEndedReason | None = None,
        call_purpose: list[CallPurpose] | None = None,
        user_satisfaction: UserSatisfaction | None = None,
        language: CallLanguage | None = None,
        transfer_reason_category: str | None = None,
        transfer_agent_was_at_fault: bool | None = None,
        call_quality_label: CallQualityLabel | None = None,
        call_quality_reason_codes: list[str] | None = None,
    ) -> PhoneCall | None:
        """
        Update an existing phone call record by call_id.

        Args:
            call_id: The call ID to update
            duration: Call duration in seconds
            turn_latency_avg: Average turn latency in seconds
            model_latency_avg: Average model latency in milliseconds
            voice_latency_avg: Average voice latency in milliseconds
            transcriber_latency_avg: Average transcriber latency in milliseconds
            endpointing_latency_avg: Average endpointing latency in milliseconds
            ended_reason: Reason the call ended
            call_purpose: List of call purposes identified
            user_satisfaction: User satisfaction level
            language: Language used in the call
            transfer_reason_category: Retrospective reason the call was transferred
            transfer_agent_was_at_fault: Whether the transfer was caused by agent fault
            call_quality_label: Post-call quality/spam classifier label
            call_quality_reason_codes: Short reason codes supporting the classifier

        Returns:
            PhoneCall | None: The updated phone call record if found, None otherwise

        Raises:
            SQLAlchemyError: If there is an error updating the phone call
        """
        try:
            from sqlalchemy import select

            result = await self.session.execute(
                select(PhoneCall).filter(PhoneCall.call_id == call_id)
            )
            phone_call = result.scalar_one_or_none()

            if not phone_call:
                logger.warning(f"Phone call not found for call_id: {call_id}")
                return None

            # Update only provided fields
            if duration is not None:
                phone_call.duration = duration
            if turn_latency_avg is not None:
                phone_call.turn_latency_avg = turn_latency_avg
            if model_latency_avg is not None:
                phone_call.model_latency_avg = model_latency_avg
            if voice_latency_avg is not None:
                phone_call.voice_latency_avg = voice_latency_avg
            if transcriber_latency_avg is not None:
                phone_call.transcriber_latency_avg = transcriber_latency_avg
            if endpointing_latency_avg is not None:
                phone_call.endpointing_latency_avg = endpointing_latency_avg
            if ended_reason is not None:
                phone_call.ended_reason = ended_reason
            if call_purpose is not None:
                phone_call.call_purpose = call_purpose
            if user_satisfaction is not None:
                phone_call.user_satisfaction = user_satisfaction
            if language is not None:
                phone_call.language = language
            if transfer_reason_category is not None:
                phone_call.transfer_reason_category = transfer_reason_category
            if transfer_agent_was_at_fault is not None:
                phone_call.transfer_agent_was_at_fault = transfer_agent_was_at_fault
            if call_quality_label is not None:
                phone_call.call_quality_label = call_quality_label
            if call_quality_reason_codes is not None:
                phone_call.call_quality_reason_codes = call_quality_reason_codes

            await self.session.flush()

            # Store ID before logging to avoid accessing expired object attributes
            phone_call_id = phone_call.id
            logger.info(
                f"Phone call record updated: {phone_call_id} for call {call_id}"
            )
            return phone_call

        except SQLAlchemyError as e:
            logger.error(f"Error updating phone call record: {e}")
            return None


class PhoneCallRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_phone_call(
        self,
        call_id: str,
        conversation_id: uuid.UUID,
        duration: float | None = None,
        turn_latency_avg: float | None = None,
        model_latency_avg: float | None = None,
        voice_latency_avg: float | None = None,
        transcriber_latency_avg: float | None = None,
        endpointing_latency_avg: float | None = None,
        ended_reason: CallEndedReason | None = None,
        call_purpose: list[CallPurpose] | None = None,
        user_satisfaction: UserSatisfaction | None = None,
        language: CallLanguage | None = None,
        transfer_reason_category: str | None = None,
        transfer_agent_was_at_fault: bool | None = None,
        call_quality_label: CallQualityLabel | None = None,
        call_quality_reason_codes: list[str] | None = None,
    ) -> PhoneCall:
        """
        Create a new phone call record (sync version).

        Args:
            call_id: Unique identifier for the call from the voice provider
            conversation_id: Associated conversation ID
            duration: Call duration in seconds
            turn_latency_avg: Average turn latency in seconds
            model_latency_avg: Average model latency in seconds
            voice_latency_avg: Average voice latency in seconds
            transcriber_latency_avg: Average transcriber latency in seconds
            endpointing_latency_avg: Average endpointing latency in seconds
            ended_reason: Reason the call ended
            call_purpose: List of call purposes identified
            user_satisfaction: User satisfaction level
            language: Language used in the call
            transfer_reason_category: Retrospective reason the call was transferred
            transfer_agent_was_at_fault: Whether the transfer was caused by agent fault
            call_quality_label: Post-call quality/spam classifier label
            call_quality_reason_codes: Short reason codes supporting the classifier

        Returns:
            PhoneCall: The created phone call record

        Raises:
            SQLAlchemyError: If there is an error creating the phone call
        """
        try:
            phone_call = PhoneCall(
                call_id=call_id,
                conversation_id=conversation_id,
                duration=duration,
                turn_latency_avg=turn_latency_avg,
                model_latency_avg=model_latency_avg,
                voice_latency_avg=voice_latency_avg,
                transcriber_latency_avg=transcriber_latency_avg,
                endpointing_latency_avg=endpointing_latency_avg,
                ended_reason=ended_reason,
                call_purpose=call_purpose,
                user_satisfaction=user_satisfaction,
                language=language,
                transfer_reason_category=transfer_reason_category,
                transfer_agent_was_at_fault=transfer_agent_was_at_fault,
                call_quality_label=call_quality_label,
                call_quality_reason_codes=call_quality_reason_codes,
            )

            self.session.add(phone_call)
            self.session.flush()
            self.session.refresh(phone_call)
            self.session.commit()

            logger.info(
                f"Phone call record created: {phone_call.id} for call {call_id}"
            )
            return phone_call

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating phone call record: {e}")
            raise
