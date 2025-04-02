import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from db.tables import Conversation, ConversationStatus
from utils.log import logger


class ConversationRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_conversation_by_id(self, conversation_id: uuid.UUID):
        result = await self.session.execute(
            select(Conversation).filter(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"No conversation found with id {conversation_id}")

        return conversation


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_conversations(self, skip: int = 0, limit: int = 100):
        """
        Retrieve a paginated list of conversations.

        Args:
            skip (int, optional): Number of records to skip. Defaults to 0.
            limit (int, optional): Maximum number of records to return. Defaults to 100.

        Returns:
            list[Conversation] | None: A list of conversation objects, or None if an error occurs.
        """
        try:
            return self.session.query(Conversation).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversations: {e}")
            return None

    def get_conversations_by_user(self, user_id: uuid.UUID):
        """
        Retrieve all conversations for a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user whose conversations are being retrieved.

        Returns:
            list[Conversation] | None: A list of conversation objects for the specified user, or None if an error occurs.

        Raises:
            ValueError: If 'user_id' is not provided.
        """
        if not user_id:
            raise ValueError("'user_id' must be provided")
        try:
            return (
                self.session.query(Conversation)
                .filter(Conversation.user_id == user_id)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversations by user: {e}")
            return None

    def get_conversations_by_users(
        self, user_ids: list[uuid.UUID], page: int, page_size: int
    ) -> tuple[list[Conversation], int]:
        """
        Retrieve conversations for a list of user IDs with pagination support.

        Args:
            user_ids (List[uuid.UUID]): A list of user IDs to filter conversations by.
            page (int): The current page number (default is 1).
            page_size (int): The number of items per page (default is 10).

        Returns:
            tuple[List[Conversation], int]: A tuple containing the list of conversations and the total count.
        """
        if not user_ids:
            # If no user ids are passed, return an empty list
            return [], 0

        try:
            # Base query without pagination for counting
            base_query = self.session.query(Conversation).filter(
                Conversation.user_id.in_(user_ids)
            )
            total_count = base_query.count()

            # Apply ordering and pagination
            conversations = (
                base_query.order_by(Conversation.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            return conversations, total_count
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversations by users: {e}")
            return [], 0

    def get_conversation_ids_by_user_ids(
        self, user_ids: list[uuid.UUID]
    ) -> list[uuid.UUID]:
        try:
            stmt = select(Conversation.id).filter(Conversation.user_id.in_(user_ids))
            conversation_ids = self.session.execute(stmt).scalars().all()
            return list(conversation_ids)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversation ids: {e}")
            return []

    def get_conversation_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        try:
            return (
                self.session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversation by id: {e}")
            return None

    def create_conversation(self, user_id: uuid.UUID):
        """
        Create a new conversation for a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user for whom the conversation is being created.

        Returns:
            Conversation | None: The created conversation object if successful, or None if an error occurs.
        """
        try:
            db_conversation = Conversation(user_id=user_id)
            self.session.add(db_conversation)
            self.session.commit()
            return db_conversation
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating conversation: {e}")
            return None

    def get_session_count_by_user_and_status(
        self, user_ids: list[uuid.UUID], status: ConversationStatus | None
    ) -> int:
        """
        Returns all sessions that belong to the given list of user ids as well as having the
        specified status.
        """
        try:
            query = self.session.query(Conversation).filter(
                Conversation.user_id.in_(user_ids)
            )
            if status:
                query = query.filter(Conversation.status == status)
            return query.count()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving session count: {e}")
            return 0
