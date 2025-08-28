import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.tables import PhoneCall
from db.tables.types import CallEndedReason, CallLanguage, CallPurpose, UserSatisfaction
from utils.log import logger


class PhoneCallRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

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
    ) -> PhoneCall:
        """
        Create a new phone call record.

        Args:
            call_id: Unique identifier for the call from the voice provider
            conversation_id: Associated conversation ID
            duration: Call duration in seconds
            turn_latency_avg: Average turn latency in milliseconds
            model_latency_avg: Average model latency in milliseconds
            voice_latency_avg: Average voice latency in milliseconds
            transcriber_latency_avg: Average transcriber latency in milliseconds
            endpointing_latency_avg: Average endpointing latency in milliseconds
            ended_reason: Reason the call ended
            call_purpose: List of call purposes identified
            user_satisfaction: User satisfaction level
            language: Language used in the call

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
            )

            self.session.add(phone_call)
            await self.session.flush()
            await self.session.refresh(phone_call)

            logger.info(
                f"Phone call record created: {phone_call.id} for call {call_id}"
            )
            return phone_call

        except SQLAlchemyError as e:
            logger.error(f"Error creating phone call record: {e}")
            raise


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
    ) -> PhoneCall:
        """
        Create a new phone call record (sync version).

        Args:
            call_id: Unique identifier for the call from the voice provider
            conversation_id: Associated conversation ID
            duration: Call duration in seconds
            turn_latency_avg: Average turn latency in milliseconds
            model_latency_avg: Average model latency in milliseconds
            voice_latency_avg: Average voice latency in milliseconds
            transcriber_latency_avg: Average transcriber latency in milliseconds
            endpointing_latency_avg: Average endpointing latency in milliseconds
            ended_reason: Reason the call ended
            call_purpose: List of call purposes identified
            user_satisfaction: User satisfaction level
            language: Language used in the call

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
            )

            self.session.add(phone_call)
            self.session.flush()
            self.session.refresh(phone_call)

            logger.info(
                f"Phone call record created: {phone_call.id} for call {call_id}"
            )
            return phone_call

        except SQLAlchemyError as e:
            logger.error(f"Error creating phone call record: {e}")
            raise
