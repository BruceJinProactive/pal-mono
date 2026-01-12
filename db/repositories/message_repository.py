import datetime
import uuid

from sqlalchemy import Boolean, cast, distinct, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import coalesce

from db.tables import Channel, Conversation, ConversationStatus, Message, User
from utils.dd import send_dd_histogram_metrics
from utils.log import logger

CONVERSATION_RESET_SECONDS_SINCE_CREATED = 24 * 3600  # 24 hours
CONVERSATION_RESET_SECONDS_SINCE_LAST_MESSAGE = 2 * 3600  # 2 hours


def _normalize_channel(channel: Channel | str) -> Channel | None:
    """Convert string channel to Channel enum, handling 'unknown' as None."""
    if isinstance(channel, Channel):
        return channel
    if not isinstance(channel, str):
        logger.warning(
            "[db.message_repository._normalize_channel] Received invalid channel type",
            extra={"channel": channel, "type": type(channel).__name__},
        )
        return None
    if channel.lower() == "unknown":
        logger.warning(
            "[db.message_repository._normalize_channel] Received unknown channel",
            extra={"channel": channel},
        )
        return None
    try:
        return Channel(channel.lower())
    except ValueError:
        logger.warning(
            "[db.message_repository._normalize_channel] Failed to parse channel",
            extra={"channel": channel},
        )
        return None


class MessageRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_message(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        message_body: dict,
        channel: str,
        call_id: str | None = None,
    ):
        logger.debug(
            "[db.message_repository.create_message] Creating message",
            extra={
                "user_id": str(user_id),
                "project_id": str(project_id),
                "call_id": call_id,
                "channel": channel,
            },
        )

        # Step 1: Get the user from the database
        result = await self.session.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()

        # Step 2: If no such user exists, raise an error
        if not user:
            raise ValueError(f"No user found with id {user_id}")

        # Step 3: Get conversation with priority-based lookup
        # First try exact channel match, then fallback to any active conversation
        normalized_channel = _normalize_channel(channel)

        # Step 3a: Try exact channel match
        result = await self.session.execute(
            select(Conversation)
            .filter(Conversation.user_id == user.id)
            .filter(Conversation.project_id == project_id)
            .filter(Conversation.channel == normalized_channel)
            .filter(Conversation.status == ConversationStatus.ACTIVE)
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        latest_conversation = result.scalar_one_or_none()

        # Step 3b: Fallback to any active conversation (backwards compatibility)
        if not latest_conversation:
            result = await self.session.execute(
                select(Conversation)
                .filter(Conversation.user_id == user.id)
                .filter(Conversation.project_id == project_id)
                .filter(Conversation.status == ConversationStatus.ACTIVE)
                .order_by(Conversation.created_at.desc())
                .limit(1)
            )
            latest_conversation = result.scalar_one_or_none()

        # Step 4: Initialize conversation_id and determine if we need a new conversation
        current_time = datetime.datetime.now(datetime.timezone.utc)
        conversation_id = None

        if (
            latest_conversation
            and latest_conversation.status == ConversationStatus.ACTIVE
        ):
            latest_conversation_created_at = latest_conversation.created_at

            # Ensure created_at is UTC
            if latest_conversation.created_at.tzinfo is None:
                latest_conversation_created_at = latest_conversation_created_at.replace(
                    tzinfo=datetime.timezone.utc
                )
            else:
                latest_conversation_created_at = (
                    latest_conversation_created_at.astimezone(datetime.timezone.utc)
                )

            time_difference = current_time - latest_conversation_created_at

            # If created_at is in the future due to clock discrepancies, the time difference calculation could yield negative values, and conversations less than 24 hours old might be overlooked. Consider adding a check to handle this scenario.
            if time_difference.total_seconds() < 0:
                time_difference = datetime.timedelta(seconds=0)
            if (
                time_difference.total_seconds()
                < CONVERSATION_RESET_SECONDS_SINCE_CREATED
            ):  # Less than 24 hours
                conversation_id = latest_conversation.id
            else:
                latest_conversation.status = ConversationStatus.EXPIRED
                await self.session.flush()

            # Ensure latest message is under 2 hours old, if not then create a new conversation
            messages = await self.session.execute(
                select(Message.created_at)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            latest_message = messages.scalar_one_or_none()
            if latest_message:
                message_time_difference = current_time - latest_message
                if (
                    message_time_difference.total_seconds()
                    < CONVERSATION_RESET_SECONDS_SINCE_LAST_MESSAGE
                ):  # Less than 2 hours
                    conversation_id = latest_conversation.id
                else:
                    latest_conversation.status = ConversationStatus.INACTIVE
                    await self.session.flush()

        # If the latest conversation is closing, set it to closed
        elif (
            latest_conversation
            and latest_conversation.status is ConversationStatus.CLOSING
        ):
            latest_conversation.status = ConversationStatus.CLOSED
            await self.session.flush()

        # Step 5: Create a new conversation if needed
        if (
            latest_conversation is None
            or latest_conversation.status != ConversationStatus.ACTIVE
        ):
            metadata = message_body.get("metadata", {})
            is_test_message = metadata.get("testing", False)
            logger.debug(
                "[db.message_repository.create_message] Creating new conversation",
                extra={
                    "user_id": str(user_id),
                    "project_id": str(project_id),
                    "call_id": call_id,
                    "channel": channel,
                },
            )
            new_conversation = Conversation(
                user_id=user.id,
                project_id=project_id,
                is_test=is_test_message,
                call_id=call_id,
                channel=normalized_channel,
            )
            self.session.add(new_conversation)
            await self.session.flush()
            conversation_id = new_conversation.id
            logger.debug(
                "[db.message_repository.create_message] Successfully created conversation",
                extra={
                    "user_id": str(user_id),
                    "project_id": str(project_id),
                    "conversation_id": str(conversation_id),
                    "call_id": call_id,
                    "channel": channel,
                },
            )

        # Step 6: Create a message with message_body and add it to the conversation
        message = Message(conversation_id=conversation_id, body=message_body)
        self.session.add(message)
        await self.session.commit()
        # Refresh to get the new message ID
        await self.session.refresh(message)

        logger.debug(
            "[db.message_repository.create_message] Successfully created message",
            extra={
                "user_id": str(user_id),
                "project_id": str(project_id),
                "conversation_id": str(conversation_id),
                "message_id": str(message.id),
                "call_id": call_id,
                "channel": channel,
            },
        )

        return message

    async def create_voice_message(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        message_body: dict,
        call_id: str,
    ) -> Message:
        """
        Create a message for a voice call. Always creates a new conversation.

        Voice calls are distinct sessions - no conversation reuse logic.
        Each call gets its own conversation with a unique call_id.

        Args:
            user_id: The ID of the user making the call
            project_id: The project ID
            message_body: The message content as a dict
            call_id: The VAPI call ID (required for voice calls)

        Returns:
            Message: The created message

        Raises:
            ValueError: If user not found
        """
        logger.debug(
            "[db.message_repository.create_voice_message] Creating voice message",
            extra={
                "user_id": str(user_id),
                "project_id": str(project_id),
                "call_id": call_id,
            },
        )

        # Get the user from the database
        result = await self.session.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"No user found with id {user_id}")

        # Always create a new conversation for voice calls
        metadata = message_body.get("metadata", {})
        is_test_message = metadata.get("testing", False)

        new_conversation = Conversation(
            user_id=user.id,
            project_id=project_id,
            is_test=is_test_message,
            call_id=call_id,
            channel=Channel.VOICE,
        )
        self.session.add(new_conversation)
        await self.session.flush()

        # Store conversation_id before commit to avoid MissingGreenlet error
        # After commit(), SQLAlchemy expires objects; accessing new_conversation.id
        # would trigger a lazy load which fails in async context
        conversation_id = new_conversation.id

        logger.debug(
            "[db.message_repository.create_voice_message] Created conversation",
            extra={
                "user_id": str(user_id),
                "project_id": str(project_id),
                "conversation_id": str(conversation_id),
                "call_id": call_id,
            },
        )

        # Create the message
        message = Message(conversation_id=conversation_id, body=message_body)
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        logger.debug(
            "[db.message_repository.create_voice_message] Successfully created message",
            extra={
                "user_id": str(user_id),
                "project_id": str(project_id),
                "conversation_id": str(conversation_id),
                "message_id": str(message.id),
                "call_id": call_id,
            },
        )

        return message

    async def add_message_to_voice_conversation(
        self,
        user_id: uuid.UUID,
        message_body: dict,
        call_id: str,
    ) -> Message:
        """
        Add a message to an existing voice conversation identified by call_id.

        For voice calls, we want to reuse the conversation created during
        handle_assistant_request rather than applying text message reuse logic.

        Args:
            user_id: The ID of the user
            message_body: The message content as a dict
            call_id: The VAPI call ID to look up the conversation

        Returns:
            Message: The created message

        Raises:
            ValueError: If conversation not found for call_id
        """
        logger.debug(
            "[db.message_repository.add_message_to_voice_conversation] Adding message to conversation",
            extra={"user_id": str(user_id), "call_id": call_id},
        )

        # Look up existing conversation by call_id and user_id
        result = await self.session.execute(
            select(Conversation).filter(
                Conversation.call_id == call_id,
                Conversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"No conversation found for call_id {call_id}")

        # Store conversation_id before commit to avoid MissingGreenlet error
        conversation_id = conversation.id

        logger.debug(
            "[db.message_repository.add_message_to_voice_conversation] Found conversation",
            extra={
                "user_id": str(user_id),
                "conversation_id": str(conversation_id),
                "call_id": call_id,
            },
        )

        # Create the message in the existing conversation
        message = Message(conversation_id=conversation_id, body=message_body)
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        logger.debug(
            "[db.message_repository.add_message_to_voice_conversation] Successfully created message",
            extra={
                "user_id": str(user_id),
                "conversation_id": str(conversation_id),
                "message_id": str(message.id),
                "call_id": call_id,
            },
        )

        return message

    async def get_messages_by_conversation(
        self, conversation_id: uuid.UUID, limit: int = 20
    ):
        """
        Retrieves the most recent "limit" number of messages associated with a specific conversation id.
        Sorts them by creation timestamp so that the messages are in chronological order.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.
            limit (int): The number of messages.

        Returns:
            List[Message]: A list of messages, empty if an error occurs.
        """
        try:
            start_time = datetime.datetime.now(datetime.timezone.utc)
            result = await self.session.execute(
                select(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(
                    # filter by created_at decending so messages are the latest ones
                    Message.created_at.desc()
                )
                .limit(limit)
            )
            send_dd_histogram_metrics(
                "message_repo.execute_query_time_spent",
                start_time,
                [f"conversation_id:{conversation_id}"],
            )

            # reverse the list so the messages are in chronological order
            messages = result.scalars().all()[::-1]
            return messages
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving messages: {e}")
            return []

    async def add_message_to_conversation(
        self,
        conversation_id: uuid.UUID,
        message_body: dict,
    ) -> Message:
        """
        Add a message directly to an existing conversation.

        Unlike create_message(), this does not handle conversation
        creation/lookup - it expects the conversation to already exist.

        Args:
            conversation_id: The conversation to add the message to
            message_body: The message content as a dict

        Returns:
            Message: The created message

        Raises:
            ValueError: If conversation does not exist
        """
        logger.debug(
            "[db.message_repository.add_message_to_conversation] Adding message",
            extra={"conversation_id": str(conversation_id)},
        )

        # Verify conversation exists
        result = await self.session.execute(
            select(Conversation).filter(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"No conversation found with id {conversation_id}")

        message = Message(conversation_id=conversation_id, body=message_body)
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        logger.debug(
            "[db.message_repository.add_message_to_conversation] Created message",
            extra={
                "conversation_id": str(conversation_id),
                "message_id": str(message.id),
            },
        )

        return message


class MessageRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_message(self, user_id: uuid.UUID, message_body: dict):
        # Step 1: Get the user from the database
        user = self.session.query(User).filter(User.id == user_id).first()

        # Step 2: If no such user exists, raise an error
        if not user:
            raise ValueError(f"No user found with id {user_id}")

        # Step 3: Get the last conversation from the user
        conversation = (
            self.session.query(Conversation)
            .filter(Conversation.user_id == user.id)
            .order_by(Conversation.created_at.desc())
            .first()
        )

        # Step 4: If no conversation exists, create one for the user
        if not conversation:
            metadata = message_body.get("metadata", {})
            is_test_message = metadata.get("testing", False)

            conversation = Conversation(user_id=user.id, is_test=is_test_message)
            self.session.add(conversation)
            self.session.commit()
            self.session.refresh(conversation)  # Refresh to get the new conversation ID

        # Step 5: Create a message with message_body and add it to the conversation
        message = Message(conversation_id=conversation.id, body=message_body)
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)  # Refresh to get the new message ID

        return message

    def add_message_to_conversation(
        self,
        conversation_id: uuid.UUID,
        message_body: dict,
    ) -> Message:
        """
        Add a message directly to an existing conversation.

        Unlike create_message(), this does not handle conversation
        creation/lookup - it expects the conversation to already exist.

        Args:
            conversation_id: The conversation to add the message to
            message_body: The message content as a dict

        Returns:
            Message: The created message

        Raises:
            ValueError: If conversation does not exist
        """
        logger.debug(
            "[db.message_repository.add_message_to_conversation] Adding message",
            extra={"conversation_id": str(conversation_id)},
        )

        # Verify conversation exists
        conversation = (
            self.session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

        if not conversation:
            raise ValueError(f"No conversation found with id {conversation_id}")

        message = Message(conversation_id=conversation_id, body=message_body)
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)

        logger.debug(
            "[db.message_repository.add_message_to_conversation] Created message",
            extra={
                "conversation_id": str(conversation_id),
                "message_id": str(message.id),
            },
        )

        return message

    def is_conversation_escalated(self, conversation_id: uuid.UUID) -> bool:
        """
        Determine if any message in the conversation is escalated by checking
        for messages where the JSON field 'body' contains extras.escalated set to true.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.

        Return:
            True if any message in the conversation is escalated, False otherwise.
        """
        # Use a raw SQL query that extracts the 'escalated' value from the JSON field.
        message = (
            self.session.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.body["extras"]["escalated"].astext == "true",
            )
            .first()
        )
        return message is not None

    def get_message_by_id(self, message_id: uuid.UUID):
        """
        Retrieves a message by its unique identifier.

        Args:
            message_id (uuid.UUID): The unique identifier for the message.

        Returns:
            Message | None: The message, or None if an error occurs.
        """
        try:
            message = (
                self.session.query(Message).filter(Message.id == message_id).first()
            )
            return message
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving message: {e}")
            return None

    def get_messages_by_conversation(self, conversation_id: uuid.UUID):
        """
        Retrieves all messages associated with a specific conversation id.
        Sorts them by creation timestamp so that the messages are in chronological order.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.

        Returns:
            List[Message]: A list of messages, empty if an error occurs.
        """
        try:
            messages = (
                self.session.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(
                    # filter by created_at ascending so messages are in chronological order
                    Message.created_at.asc()
                )
                .all()
            )

            return messages
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving last message: {e}")
            return []

    def get_last_message_by_conversation(self, conversation_id: uuid.UUID):
        """
        Retrieves the most recently created message associated with a specific
        conversation id.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.

        Returns:
            Message | None: The most recent message, or None of an error occurs.
        """
        try:
            message = (
                self.session.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(
                    # filter by created_at desc so first message is most recent
                    Message.created_at.desc()
                )
                .first()
            )

            if not message:
                return None

            return message
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving last message: {e}")
            return None

    def get_last_user_message_by_conversation(self, conversation_id: uuid.UUID):
        """
        Retrieves the most recently created message associated with a specific
        conversation id that was created by a user.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.

        Returns:
            Message | None: The most recent user-generated message, or None of an error occurs.
        """
        try:
            message = (
                self.session.query(Message)
                .filter(Message.conversation_id == conversation_id)
                # filter by author_type to get only user-generated messages
                .filter(Message.body.has_key("author_type"))
                .filter(Message.body["author_type"].astext == "user")
                .order_by(
                    # filter by created_at desc so first message is most recent
                    Message.created_at.desc()
                )
                .first()
            )

            if not message:
                return None

            return message
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving last message: {e}")
            return None

    def get_message_count_by_conversation(self, conversation_id: uuid.UUID):
        """
        Retrieves the number of messages associated with a specific
        conversation id.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.

        Returns:
            int: The number of messages, 0 if an error occurs.
        """
        try:
            message_count = (
                self.session.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .count()
            )

            return message_count
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving message count: {e}")
            return 0

    def get_conversation_id_by_message_id(self, message_id: uuid.UUID):
        """
        Retrieves the conversation id associated with a specific message id.

        Args:
            message_id (uuid.UUID): The unique identifier for the message.

        Returns:
            str: The conversation id, None if an error occurs.
        """
        try:
            conversation_id = (
                self.session.query(Message.conversation_id)
                .filter(Message.id == message_id)
                .scalar()
            )

            return conversation_id
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversation id: {e}")
            return None

    def get_messages_by_ids(self, message_ids: list[uuid.UUID]) -> list[Message]:
        try:
            return self.session.query(Message).filter(Message.id.in_(message_ids)).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving messages: {e}")
            return []

    def get_escalated_conversation_count(
        self,
        conversation_ids: list[uuid.UUID],
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> int:
        try:
            return (
                self.session.query(Message.conversation_id.distinct())
                .filter(Message.conversation_id.in_(conversation_ids))
                .filter(Message.body["extras"]["escalated"].astext == "true")
                .filter(Message.created_at >= start_date)
                .filter(Message.created_at <= end_date)
                .count()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving escalated conversation count: {e}")
            return 0

    def filter_sessions_by_keyword(
        self,
        session_ids: list[uuid.UUID],
        keyword: str,
        channel: str | None,
        escalated: bool,
    ) -> list[uuid.UUID]:
        """
        Search for sessions in the provided session ids by message details.

        Args:
            session_ids: Limit the search to these session.
            keyword: A text to search against message content and sender phone number.
            channel: The channel of the message, e.g: sms, voice, etc...
            escalated: Search for escalated messages only if True.
            hide_testing_sessions: Filters out testing sessions is True.

        Returns:
            List of matching session ids.
        """
        try:
            conditions = [
                Message.body["author_type"].astext == "user",
            ]
            if escalated:
                # only search within those escalated conversations. We use
                # sub-query because these escalation booleans are usually
                # on the agent messages which are not included due to the
                # above user author type check. Be very careful about modifying
                # this logic.
                conditions.append(
                    Message.conversation_id.in_(
                        select(distinct(Message.conversation_id)).where(
                            cast(
                                coalesce(
                                    Message.body["extras"]["escalated"].astext, "false"
                                ),
                                Boolean,
                            ),
                            Message.conversation_id.in_(session_ids),
                        )
                    )
                )
            else:
                conditions.append(Message.conversation_id.in_(session_ids))
            if keyword:
                conditions.append(
                    or_(
                        Message.body["text"]["body"].astext.ilike(f"%{keyword}%"),
                        Message.body["sender_identifier"].astext.ilike(f"%{keyword}%"),
                    )
                )
            if channel:
                conditions.append(Message.body["channel"].astext == channel)

            query = select(distinct(Message.conversation_id)).where(*conditions)
            result = self.session.execute(query).scalars()
            return list(result.all())
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error filtering sessions by keyword: {e}")
            return []
