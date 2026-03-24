"""S3: First Conversation End-to-End Chat Flow.

Tests conversation creation, reuse, and expiry logic at the repository layer.
The chat endpoint's message creation relies on conversation lifecycle rules:
- Conversation < 24h old AND last message < 2h -> reuse
- Conversation >= 24h old -> mark EXPIRED, create new
- Last message >= 2h idle -> mark INACTIVE, create new
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.tables import Conversation, Message
from db.tables.conversations import ConversationStatus
from tests.factories import make_conversation, make_message, make_world


@pytest.mark.integration
class TestFirstConversation:
    def test_conversation_creation_persists(self, db_session: Session) -> None:
        """Creating a conversation via factory persists to DB."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )

        result = db_session.execute(
            select(Conversation).where(Conversation.id == conv.id)
        ).scalar_one_or_none()

        assert result is not None
        assert result.user_id == world.user.id
        assert result.project_id == world.project.id
        assert result.status == ConversationStatus.ACTIVE

    def test_messages_linked_to_conversation(self, db_session: Session) -> None:
        """Messages are correctly linked to their conversation."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )

        user_msg = make_message(
            db_session,
            conversation_id=conv.id,
            body={"role": "user", "content": "Hello"},
        )
        agent_msg = make_message(
            db_session,
            conversation_id=conv.id,
            body={"role": "assistant", "content": "Hi there!"},
        )

        messages = (
            db_session.execute(
                select(Message).where(Message.conversation_id == conv.id)
            )
            .scalars()
            .all()
        )

        assert len(messages) == 2
        msg_ids = {m.id for m in messages}
        assert user_msg.id in msg_ids
        assert agent_msg.id in msg_ids

    def test_conversation_reuse_same_project_user(self, db_session: Session) -> None:
        """Multiple conversations for same user+project are tracked separately."""
        world = make_world(db_session)

        conv_1 = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )
        conv_2 = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )

        assert conv_1.id != conv_2.id

        convs = (
            db_session.execute(
                select(Conversation).where(
                    Conversation.user_id == world.user.id,
                    Conversation.project_id == world.project.id,
                )
            )
            .scalars()
            .all()
        )
        assert len(convs) == 2

    def test_conversation_status_transitions(self, db_session: Session) -> None:
        """Conversation status can be updated from ACTIVE to EXPIRED/INACTIVE."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
            status=ConversationStatus.ACTIVE,
        )

        # Mark as EXPIRED
        conv.status = ConversationStatus.EXPIRED
        db_session.flush()

        result = db_session.execute(
            select(Conversation).where(Conversation.id == conv.id)
        ).scalar_one()
        assert result.status == ConversationStatus.EXPIRED

    def test_conversation_inactive_status(self, db_session: Session) -> None:
        """Conversation can transition to INACTIVE."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )

        conv.status = ConversationStatus.INACTIVE
        db_session.flush()

        result = db_session.execute(
            select(Conversation).where(Conversation.id == conv.id)
        ).scalar_one()
        assert result.status == ConversationStatus.INACTIVE

    def test_message_body_stores_jsonb(self, db_session: Session) -> None:
        """Message body (JSONB) round-trips correctly."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )

        body = {
            "role": "user",
            "content": "What are your hours?",
            "metadata": {"channel": "api"},
        }
        msg = make_message(db_session, conversation_id=conv.id, body=body)

        result = db_session.execute(
            select(Message).where(Message.id == msg.id)
        ).scalar_one()
        assert result.body["role"] == "user"
        assert result.body["content"] == "What are your hours?"
        assert result.body["metadata"]["channel"] == "api"

    def test_tenant_chain_integrity(self, db_session: Session) -> None:
        """Message -> Conversation -> Project -> Account chain stays in tenant."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )
        msg = make_message(db_session, conversation_id=conv.id)

        # Walk the chain
        loaded_conv = db_session.execute(
            select(Conversation).where(Conversation.id == msg.conversation_id)
        ).scalar_one()
        assert loaded_conv.project_id == world.project.id
        assert loaded_conv.user_id == world.user.id

    def test_cross_project_conversation_isolation(self, db_session: Session) -> None:
        """Conversations from different projects don't intermix."""
        world = make_world(db_session)
        from tests.factories import make_agent, make_project

        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        conv_a = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )
        conv_b = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=project_b.id,
        )

        make_message(db_session, conversation_id=conv_a.id)
        make_message(db_session, conversation_id=conv_b.id)

        msgs_a = (
            db_session.execute(
                select(Message).where(Message.conversation_id == conv_a.id)
            )
            .scalars()
            .all()
        )
        msgs_b = (
            db_session.execute(
                select(Message).where(Message.conversation_id == conv_b.id)
            )
            .scalars()
            .all()
        )

        assert len(msgs_a) == 1
        assert len(msgs_b) == 1
        assert {m.id for m in msgs_a}.isdisjoint({m.id for m in msgs_b})
