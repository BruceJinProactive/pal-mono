"""S8: Voice Call Lifecycle.

Tests voice config and phone call DB operations:
creation, retrieval, project isolation, conversation linkage.
Also tests repository-layer CRUD and analytics field round-trips.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.repositories.phone_call_repository import PhoneCallRepository
from db.repositories.voice_config_repository import VoiceConfigRepository
from db.tables import (
    Account,
    Agent,
    Conversation,
    PhoneCall,
    Project,
    User,
    VoiceConfig,
)
from db.tables.accounts import AccountStatus
from db.tables.types import (
    CallEndedReason,
    CallLanguage,
    CallPurpose,
    SpeechRate,
    UserSatisfaction,
)
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


@pytest.mark.integration
class TestVoiceRepositoryIntegration:
    """Repository-layer tests for voice config and phone call operations."""

    def test_voice_config_repo_create_all_fields(self, db_session: Session) -> None:
        """VoiceConfigRepository persists all extended fields correctly."""
        world = make_world(db_session)
        repo = VoiceConfigRepository(db_session, auto_commit=False)

        vc = repo.create_voice_config(
            project_id=world.project.id,
            language="english",
            voice_id="voice-en-us",
            first_message="Hello!",
            transfer_message="Transferring...",
            replacements={"Hi": "Hello"},
            speech_rate="faster",
            background_sound="restaurant",
            raw_config={"custom": True},
            cloned_voice_id="clone-123",
            voice_model="sonic-3",
            transcriber={"provider": "deepgram"},
        )

        result = db_session.execute(
            select(VoiceConfig).where(VoiceConfig.id == vc.id)
        ).scalar_one()

        assert result.speech_rate == SpeechRate.faster
        assert result.background_sound == "restaurant"
        assert result.replacements == {"Hi": "Hello"}
        assert result.cloned_voice_id == "clone-123"
        assert result.voice_model == "sonic-3"
        assert result.transcriber == {"provider": "deepgram"}
        assert result.raw_config == {"custom": True}

    def test_voice_config_update_via_orm(self, db_session: Session) -> None:
        """VoiceConfig fields can be updated and persisted (mirrors async update path)."""
        world = make_world(db_session)
        vc = make_voice_config(
            db_session,
            project_id=world.project.id,
            voice_id="voice-old",
            language="english",
        )

        # Update via ORM (sync repo has no update method; async repo does)
        vc.voice_id = "voice-new"
        vc.speech_rate = SpeechRate.slower
        db_session.flush()

        result = db_session.execute(
            select(VoiceConfig).where(VoiceConfig.id == vc.id)
        ).scalar_one()
        assert result.voice_id == "voice-new"
        assert result.speech_rate == SpeechRate.slower

    def test_voice_config_repo_delete(self, db_session: Session) -> None:
        """VoiceConfigRepository.delete_voice_config removes the record."""
        world = make_world(db_session)
        repo = VoiceConfigRepository(db_session, auto_commit=False)

        vc = repo.create_voice_config(
            project_id=world.project.id,
            language="english",
            voice_id="voice-del",
            first_message="Hi",
            transfer_message="Hold",
        )

        assert repo.delete_voice_configs_by_project(world.project.id) == 1

        result = db_session.execute(
            select(VoiceConfig).where(VoiceConfig.id == vc.id)
        ).scalar_one_or_none()
        assert result is None

    def test_voice_config_multi_language_per_project(self, db_session: Session) -> None:
        """Multiple VoiceConfigs (english, spanish, chinese) coexist per project."""
        world = make_world(db_session)

        make_voice_config(db_session, project_id=world.project.id, language="english")
        make_voice_config(db_session, project_id=world.project.id, language="spanish")
        make_voice_config(db_session, project_id=world.project.id, language="chinese")

        repo = VoiceConfigRepository(db_session, auto_commit=False)
        configs = repo.get_voice_configs_by_project(world.project.id)
        assert len(configs) == 3

        languages = {c.language for c in configs}
        assert languages == {"english", "spanish", "chinese"}

    def test_phone_call_create_with_analytics(self, db_session: Session) -> None:
        """PhoneCallRepository.create_phone_call persists all analytics fields."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session, user_id=world.user.id, project_id=world.project.id
        )
        repo = PhoneCallRepository(db_session)

        pc = repo.create_phone_call(
            call_id="analytics-call-001",
            conversation_id=conv.id,
            duration=125.5,
            turn_latency_avg=0.8,
            model_latency_avg=450.0,
            voice_latency_avg=120.0,
            transcriber_latency_avg=80.0,
            endpointing_latency_avg=200.0,
            ended_reason=CallEndedReason.customer_ended,
            call_purpose=[CallPurpose.ordering, CallPurpose.store_info],
            user_satisfaction=UserSatisfaction.positive,
            language=CallLanguage.english,
            transfer_reason_category="tool_failure_order",
            transfer_agent_was_at_fault=True,
        )

        result = db_session.execute(
            select(PhoneCall).where(PhoneCall.id == pc.id)
        ).scalar_one()

        assert result.duration == 125.5
        assert result.turn_latency_avg == 0.8
        assert result.model_latency_avg == 450.0
        assert result.voice_latency_avg == 120.0
        assert result.transcriber_latency_avg == 80.0
        assert result.endpointing_latency_avg == 200.0
        assert result.ended_reason == CallEndedReason.customer_ended
        assert result.call_purpose == [CallPurpose.ordering, CallPurpose.store_info]
        assert result.user_satisfaction == UserSatisfaction.positive
        assert result.language == CallLanguage.english
        assert result.transfer_reason_category == "tool_failure_order"
        assert result.transfer_agent_was_at_fault is True

    def test_phone_call_update_analytics(self, db_session: Session) -> None:
        """PhoneCall analytics can be updated after initial creation (end_voice_call path)."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session, user_id=world.user.id, project_id=world.project.id
        )
        pc = make_phone_call(db_session, conversation_id=conv.id)

        # Initially no analytics
        assert pc.duration is None
        assert pc.ended_reason is None

        # Simulate end_voice_call update
        pc.duration = 95.2
        pc.ended_reason = CallEndedReason.assistant_forwarded
        pc.user_satisfaction = UserSatisfaction.neutral
        pc.language = CallLanguage.spanish
        db_session.flush()

        result = db_session.execute(
            select(PhoneCall).where(PhoneCall.id == pc.id)
        ).scalar_one()
        assert result.duration == 95.2
        assert result.ended_reason == CallEndedReason.assistant_forwarded
        assert result.user_satisfaction == UserSatisfaction.neutral
        assert result.language == CallLanguage.spanish

    @pytest.mark.parametrize(
        "reason",
        list(CallEndedReason),
        ids=[r.value for r in CallEndedReason],
    )
    def test_phone_call_all_ended_reasons(
        self, db_session: Session, reason: CallEndedReason
    ) -> None:
        """Every CallEndedReason enum value round-trips through PostgreSQL."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session, user_id=world.user.id, project_id=world.project.id
        )
        pc = make_phone_call(db_session, conversation_id=conv.id, ended_reason=reason)

        result = db_session.execute(
            select(PhoneCall).where(PhoneCall.id == pc.id)
        ).scalar_one()
        assert result.ended_reason == reason

    def test_phone_call_array_call_purpose(self, db_session: Session) -> None:
        """PostgreSQL ARRAY(Enum) round-trips a multi-element call_purpose list."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session, user_id=world.user.id, project_id=world.project.id
        )
        purposes = [
            CallPurpose.ordering,
            CallPurpose.reservation,
            CallPurpose.customer_service,
        ]
        pc = make_phone_call(db_session, conversation_id=conv.id, call_purpose=purposes)

        result = db_session.execute(
            select(PhoneCall).where(PhoneCall.id == pc.id)
        ).scalar_one()
        assert result.call_purpose is not None
        assert result.call_purpose == purposes
        assert len(result.call_purpose) == 3


@pytest.mark.integration
class TestVoiceInitSessionRefresh:
    """Regression: project columns must survive session.commit() inside create_voice_message.

    create_voice_message commits the session, expiring all ORM objects.
    If project is only partially refreshed afterwards, accessing columns like
    agent_id triggers MissingGreenlet in async context.
    """

    @pytest.mark.asyncio
    async def test_project_attributes_accessible_after_commit(
        self, async_session: AsyncSession
    ) -> None:
        now = datetime.now(UTC)

        # --- Set up real ORM entities in the async session ---
        account = Account(
            id=uuid.uuid4(),
            name=f"test-account-{uuid.uuid4().hex[:8]}",
            display_name="Test Account",
            status=AccountStatus.active,
            created_at=now,
            updated_at=now,
        )
        async_session.add(account)
        await async_session.flush()

        agent = Agent(
            id=uuid.uuid4(),
            account_id=account.id,
            name="test-agent",
            raw_config={},
            created_at=now,
            updated_at=now,
        )
        async_session.add(agent)
        await async_session.flush()

        project = Project(
            id=uuid.uuid4(),
            account_id=account.id,
            agent_id=agent.id,
            name="test-project",
            display_name="Test Project",
            raw_config={},
            channel_identifiers=["voice:+15559876543"],
            timezone="America/New_York",
            created_at=now,
            updated_at=now,
        )
        async_session.add(project)
        await async_session.flush()

        user = User(
            id=uuid.uuid4(),
            account_id=account.id,
            channel_identifiers=["+15551234567"],
            created_at=now,
            updated_at=now,
        )
        async_session.add(user)
        await async_session.flush()

        vc = VoiceConfig(
            id=uuid.uuid4(),
            project_id=project.id,
            language="english",
            voice_id="test-voice-id",
            first_message="Hello!",
            transfer_message="Transferring...",
            raw_config={},
            created_at=now,
            updated_at=now,
        )
        async_session.add(vc)
        await async_session.flush()

        # --- Call init_voice_call with real async session ---
        from api.routes.internal._voice import init_voice_call
        from api.schemas.internal.voice_init import VoiceInitRequest, VoiceInitResponse

        request = VoiceInitRequest(
            caller_number="+15551234567",
            dialed_number="+15559876543",
            call_id=f"call-{uuid.uuid4().hex[:8]}",
        )

        # Mock only the service-layer lookups that do complex orchestration;
        # repositories use the real session so commit/expiration is exercised.
        with (
            patch(
                "api.routes.internal._voice.project_service.get_project_async",
                new_callable=AsyncMock,
                return_value=project,
            ),
            patch(
                "api.routes.internal._voice.user_service.get_user_async",
                new_callable=AsyncMock,
                return_value=(user, None),
            ),
        ):
            # This raises MissingGreenlet if project is not fully refreshed
            # after the commit inside create_voice_message.
            result = await init_voice_call(request, async_session)

        assert isinstance(result, VoiceInitResponse)
        assert result.voice_id == "test-voice-id"
        assert result.first_message == "Hello!"
        assert result.caller_info["timezone"] == "America/New_York"
