"""S7: Cross-Project Conversation Isolation.

Multi-location scenario: one Account owns multiple Projects.
Agent for Project A must never see Project B's messages.
Conversations are scoped by project_id.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.tables import Conversation, Message
from tests.factories import (
    make_agent,
    make_conversation,
    make_message,
    make_project,
    make_world,
)


@pytest.mark.integration
class TestCrossProjectConversationIsolation:
    def test_conversations_scoped_by_project(self, db_session: Session) -> None:
        """Conversations filtered by project_id return only that project's conversations."""
        world = make_world(db_session)

        # Create a second project in the same account
        agent_b = make_agent(db_session, account_id=world.account.id, name="agent-b")
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        # Create conversations for each project
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

        # Query by project_id
        result_a = (
            db_session.execute(
                select(Conversation).where(Conversation.project_id == world.project.id)
            )
            .scalars()
            .all()
        )
        result_b = (
            db_session.execute(
                select(Conversation).where(Conversation.project_id == project_b.id)
            )
            .scalars()
            .all()
        )

        assert len(result_a) == 1
        assert result_a[0].id == conv_a.id
        assert len(result_b) == 1
        assert result_b[0].id == conv_b.id

    def test_messages_disjoint_across_projects(self, db_session: Session) -> None:
        """Messages in Project A's conversation never appear in Project B's query."""
        world = make_world(db_session)
        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        # 5 messages per project
        conv_a = make_conversation(
            db_session, user_id=world.user.id, project_id=world.project.id
        )
        conv_b = make_conversation(
            db_session, user_id=world.user.id, project_id=project_b.id
        )

        msg_ids_a = set()
        msg_ids_b = set()
        for i in range(5):
            m = make_message(
                db_session,
                conversation_id=conv_a.id,
                body={"role": "user", "content": f"Location 1 message {i}"},
            )
            msg_ids_a.add(m.id)
        for i in range(5):
            m = make_message(
                db_session,
                conversation_id=conv_b.id,
                body={"role": "user", "content": f"Location 2 message {i}"},
            )
            msg_ids_b.add(m.id)

        # Query messages via conversation
        messages_for_a = (
            db_session.execute(
                select(Message).where(Message.conversation_id == conv_a.id)
            )
            .scalars()
            .all()
        )
        messages_for_b = (
            db_session.execute(
                select(Message).where(Message.conversation_id == conv_b.id)
            )
            .scalars()
            .all()
        )

        fetched_ids_a = {m.id for m in messages_for_a}
        fetched_ids_b = {m.id for m in messages_for_b}

        # Disjoint
        assert fetched_ids_a == msg_ids_a
        assert fetched_ids_b == msg_ids_b
        assert fetched_ids_a.isdisjoint(fetched_ids_b)

    def test_set_intersection_is_empty(self, db_session: Session) -> None:
        """query(conversations, project=A) INTERSECT query(conversations, project=B) = empty set."""
        world = make_world(db_session)
        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        for _ in range(3):
            make_conversation(
                db_session, user_id=world.user.id, project_id=world.project.id
            )
            make_conversation(
                db_session, user_id=world.user.id, project_id=project_b.id
            )

        ids_a = {
            c.id
            for c in db_session.execute(
                select(Conversation).where(Conversation.project_id == world.project.id)
            )
            .scalars()
            .all()
        }
        ids_b = {
            c.id
            for c in db_session.execute(
                select(Conversation).where(Conversation.project_id == project_b.id)
            )
            .scalars()
            .all()
        }

        assert len(ids_a) == 3
        assert len(ids_b) == 3
        assert ids_a.isdisjoint(ids_b)
