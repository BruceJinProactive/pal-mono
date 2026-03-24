"""S8: Voice Call Lifecycle.

Tests voice config and phone call DB operations:
creation, retrieval, project isolation, conversation linkage.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.tables import Conversation, PhoneCall, VoiceConfig
from tests.factories import (
    make_agent,
    make_conversation,
    make_phone_call,
    make_project,
    make_voice_config,
    make_world,
)


@pytest.mark.integration
class TestVoiceCallLifecycle:
    def test_voice_config_creation(self, db_session: Session) -> None:
        """Voice config is created and linked to project."""
        world = make_world(db_session)
        vc = make_voice_config(db_session, project_id=world.project.id)

        result = db_session.execute(
            select(VoiceConfig).where(VoiceConfig.id == vc.id)
        ).scalar_one_or_none()

        assert result is not None
        assert result.project_id == world.project.id
        assert result.language == "english"
        assert result.voice_id == "test-voice-id"

    def test_voice_config_project_isolation(self, db_session: Session) -> None:
        """Two projects with different voice configs return correct ones."""
        world = make_world(db_session)
        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        vc_a = make_voice_config(
            db_session,
            project_id=world.project.id,
            language="english",
            voice_id="voice-en",
        )
        vc_b = make_voice_config(
            db_session,
            project_id=project_b.id,
            language="spanish",
            voice_id="voice-es",
        )

        configs_a = (
            db_session.execute(
                select(VoiceConfig).where(VoiceConfig.project_id == world.project.id)
            )
            .scalars()
            .all()
        )
        configs_b = (
            db_session.execute(
                select(VoiceConfig).where(VoiceConfig.project_id == project_b.id)
            )
            .scalars()
            .all()
        )

        assert len(configs_a) == 1
        assert configs_a[0].id == vc_a.id
        assert configs_a[0].language == "english"

        assert len(configs_b) == 1
        assert configs_b[0].id == vc_b.id
        assert configs_b[0].language == "spanish"

    def test_phone_call_linked_to_conversation(self, db_session: Session) -> None:
        """PhoneCall is correctly linked to a conversation."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )
        pc = make_phone_call(db_session, conversation_id=conv.id)

        result = db_session.execute(
            select(PhoneCall).where(PhoneCall.id == pc.id)
        ).scalar_one()

        assert result.conversation_id == conv.id
        assert result.call_id is not None

    def test_phone_call_retrieval_by_call_id(self, db_session: Session) -> None:
        """Phone call can be looked up by its call_id string."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )
        pc = make_phone_call(
            db_session,
            conversation_id=conv.id,
            call_id="livekit-call-12345",
        )

        result = db_session.execute(
            select(PhoneCall).where(PhoneCall.call_id == "livekit-call-12345")
        ).scalar_one_or_none()

        assert result is not None
        assert result.id == pc.id

    def test_phone_call_to_conversation_chain(self, db_session: Session) -> None:
        """PhoneCall -> Conversation -> Project -> Account stays within tenant."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )
        pc = make_phone_call(db_session, conversation_id=conv.id)

        # Walk chain
        loaded_pc = db_session.execute(
            select(PhoneCall).where(PhoneCall.id == pc.id)
        ).scalar_one()
        loaded_conv = db_session.execute(
            select(Conversation).where(Conversation.id == loaded_pc.conversation_id)
        ).scalar_one()

        assert loaded_conv.project_id == world.project.id
        assert loaded_conv.user_id == world.user.id

    def test_multiple_calls_per_project(self, db_session: Session) -> None:
        """Multiple phone calls for same project are all retrievable."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )

        make_phone_call(db_session, conversation_id=conv.id, call_id="call-001")
        make_phone_call(db_session, conversation_id=conv.id, call_id="call-002")

        calls = (
            db_session.execute(
                select(PhoneCall).where(PhoneCall.conversation_id == conv.id)
            )
            .scalars()
            .all()
        )

        call_ids = {c.call_id for c in calls}
        assert "call-001" in call_ids
        assert "call-002" in call_ids
        assert len(calls) == 2

    def test_cross_project_call_isolation(self, db_session: Session) -> None:
        """Phone calls from project A not visible via project B's conversations."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        conv_a = make_conversation(
            db_session,
            user_id=world_a.user.id,
            project_id=world_a.project.id,
        )
        conv_b = make_conversation(
            db_session,
            user_id=world_b.user.id,
            project_id=world_b.project.id,
        )

        make_phone_call(db_session, conversation_id=conv_a.id, call_id="call-A")
        make_phone_call(db_session, conversation_id=conv_b.id, call_id="call-B")

        calls_a = (
            db_session.execute(
                select(PhoneCall).where(PhoneCall.conversation_id == conv_a.id)
            )
            .scalars()
            .all()
        )
        calls_b = (
            db_session.execute(
                select(PhoneCall).where(PhoneCall.conversation_id == conv_b.id)
            )
            .scalars()
            .all()
        )

        assert len(calls_a) == 1
        assert calls_a[0].call_id == "call-A"
        assert len(calls_b) == 1
        assert calls_b[0].call_id == "call-B"
        assert {c.id for c in calls_a}.isdisjoint({c.id for c in calls_b})
