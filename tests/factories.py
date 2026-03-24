"""Test factory library for creating entities with sensible defaults.

Usage:
    world = make_world(session)           # Account + Agent + Project + User
    conv = make_conversation(session, user_id=world.user.id, project_id=world.project.id)
    msg = make_message(session, conversation_id=conv.id)

Design principle: sensible defaults, override only what the test cares about.
All factories call session.add() + session.flush() so IDs are available immediately.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy.orm import Session

from db.tables import (
    Account,
    AccountSubscription,
    AccountUser,
    Agent,
    Conversation,
    Integration,
    Message,
    MonitoringConfig,
    MonitoringRun,
    PhoneCall,
    Project,
    ProjectIntegration,
    ProjectSubscription,
    ResourceRoleAssignment,
    Routine,
    RoutineExecution,
    RoutineItem,
    RoutineItemResponse,
    RoutineSchedule,
    RoutineSubmission,
    SignalFeed,
    SignalSource,
    SubscriptionPlan,
    User,
    VoiceConfig,
)
from db.tables.accounts import AccountStatus, OnboardingMethod
from db.tables.conversations import ConversationStatus
from db.tables.types import (
    AccountUserStatus,
    AuthType,
    CaptureMode,
    ExecutionStatus,
    FeedType,
    IntegrationProvider,
    IntegrationType,
    ItemResponseStatus,
    PaymentMethod,
    RoutineCategory,
    RoutineFrequency,
    RoutineInputType,
    SignalFeedStatus,
    SignalSourceStatus,
    SignalType,
    SubmissionStatus,
    SubscriptionStatus,
    TargetTier,
)


@dataclass
class World:
    """Minimal tenant hierarchy: Account + Agent + Project + User."""

    account: Account
    agent: Agent
    project: Project
    user: User


def _now() -> datetime:
    return datetime.now(UTC)


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------


def make_account(session: Session, **overrides: Any) -> Account:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": f"test-account-{_short_id()}",
        "display_name": "Test Account",
        "status": AccountStatus.active,
        "onboarding_method": OnboardingMethod.manage_onboarding,
        "notification_preferences": {"email_enabled": True},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    account = Account(**defaults)
    session.add(account)
    session.flush()
    return account


def make_agent(session: Session, *, account_id: uuid.UUID, **overrides: Any) -> Agent:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "account_id": account_id,
        "name": f"test-agent-{_short_id()}",
        "raw_config": {},
        "filler_words": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    agent = Agent(**defaults)
    session.add(agent)
    session.flush()
    return agent


def make_project(
    session: Session,
    *,
    account_id: uuid.UUID,
    agent_id: uuid.UUID,
    **overrides: Any,
) -> Project:
    short = _short_id()
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "account_id": account_id,
        "agent_id": agent_id,
        "name": f"test-project-{short}",
        "display_name": "Test Project",
        "raw_config": {},
        "channel_identifiers": [f"+1555{random.randint(1000000, 9999999)}"],
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    project = Project(**defaults)
    session.add(project)
    session.flush()
    return project


def make_user(session: Session, *, account_id: uuid.UUID, **overrides: Any) -> User:
    short = _short_id()
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "account_id": account_id,
        "channel_identifiers": [f"test-{short}@example.com"],
        "raw_config": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    user = User(**defaults)
    session.add(user)
    session.flush()
    return user


def make_world(session: Session, **overrides: Any) -> World:
    """Create a minimal tenant hierarchy in one call.

    Override sub-entities via nested dicts:
        make_world(session, account={"name": "custom"}, agent={"name": "bot"})
    """
    account = make_account(session, **(overrides.get("account") or {}))
    agent = make_agent(session, account_id=account.id, **(overrides.get("agent") or {}))
    project = make_project(
        session,
        account_id=account.id,
        agent_id=agent.id,
        **(overrides.get("project") or {}),
    )
    user = make_user(session, account_id=account.id, **(overrides.get("user") or {}))
    return World(account=account, agent=agent, project=project, user=user)


# ---------------------------------------------------------------------------
# Conversations & Messages
# ---------------------------------------------------------------------------


def make_conversation(
    session: Session,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    **overrides: Any,
) -> Conversation:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "project_id": project_id,
        "status": ConversationStatus.ACTIVE,
        "is_test": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    conv = Conversation(**defaults)
    session.add(conv)
    session.flush()
    return conv


def make_message(
    session: Session, *, conversation_id: uuid.UUID, **overrides: Any
) -> Message:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "conversation_id": conversation_id,
        "body": {"role": "user", "content": "test message"},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    msg = Message(**defaults)
    session.add(msg)
    session.flush()
    return msg


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


def make_integration(
    session: Session, *, account_id: uuid.UUID, **overrides: Any
) -> Integration:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "account_id": account_id,
        "provider": IntegrationProvider.toast,
        "integration_type": IntegrationType.pos,
        "auth_type": AuthType.client_secret,
        "secret_key": "test-secret-key",
        "raw_config": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    integration = Integration(**defaults)
    session.add(integration)
    session.flush()
    return integration


def make_project_integration(
    session: Session,
    *,
    project_id: uuid.UUID,
    integration_id: uuid.UUID,
    **overrides: Any,
) -> ProjectIntegration:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "project_id": project_id,
        "integration_id": integration_id,
        "store_identifier": f"store-{_short_id()}",
        "config": {},
        "created_at": _now(),
    }
    defaults.update(overrides)
    pi = ProjectIntegration(**defaults)
    session.add(pi)
    session.flush()
    return pi


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def make_account_user(
    session: Session,
    *,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    **overrides: Any,
) -> AccountUser:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "account_id": account_id,
        "user_id": user_id,
        "status": AccountUserStatus.active,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    au = AccountUser(**defaults)
    session.add(au)
    session.flush()
    return au


def make_role_assignment(
    session: Session,
    *,
    user_id: uuid.UUID,
    resource_type: str,
    resource_id: uuid.UUID,
    role: str,
    **overrides: Any,
) -> ResourceRoleAssignment:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "role": role,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    rra = ResourceRoleAssignment(**defaults)
    session.add(rra)
    session.flush()
    return rra


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


def make_subscription_plan(session: Session, **overrides: Any) -> SubscriptionPlan:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": f"test-plan-{_short_id()}",
        "tier": TargetTier.t1,
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    plan = SubscriptionPlan(**defaults)
    session.add(plan)
    session.flush()
    return plan


def make_account_subscription(
    session: Session,
    *,
    account_id: uuid.UUID,
    subscription_plan_id: uuid.UUID,
    **overrides: Any,
) -> AccountSubscription:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "external_id": uuid.uuid4(),
        "account_id": account_id,
        "subscription_plan_id": subscription_plan_id,
        "status": SubscriptionStatus.active,
        "payment_method": PaymentMethod.autopay,
        "start_date": _now(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    sub = AccountSubscription(**defaults)
    session.add(sub)
    session.flush()
    return sub


def make_project_subscription(
    session: Session,
    *,
    project_id: uuid.UUID,
    subscription_id: uuid.UUID,
    **overrides: Any,
) -> ProjectSubscription:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "project_id": project_id,
        "subscription_id": subscription_id,
        "status": SubscriptionStatus.active,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    ps = ProjectSubscription(**defaults)
    session.add(ps)
    session.flush()
    return ps


# ---------------------------------------------------------------------------
# Voice / Phone Calls
# ---------------------------------------------------------------------------


def make_voice_config(
    session: Session, *, project_id: uuid.UUID, **overrides: Any
) -> VoiceConfig:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "project_id": project_id,
        "language": "english",
        "voice_id": "test-voice-id",
        "first_message": "Hello, how can I help you?",
        "transfer_message": "Let me transfer you.",
        "raw_config": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    vc = VoiceConfig(**defaults)
    session.add(vc)
    session.flush()
    return vc


def make_phone_call(
    session: Session, *, conversation_id: uuid.UUID, **overrides: Any
) -> PhoneCall:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "call_id": f"call-{_short_id()}",
        "conversation_id": conversation_id,
        "created_at": _now(),
    }
    defaults.update(overrides)
    pc = PhoneCall(**defaults)
    session.add(pc)
    session.flush()
    return pc


# ---------------------------------------------------------------------------
# Monitoring (Signal Sources, Feeds, Configs, Runs)
# ---------------------------------------------------------------------------


def make_signal_source(
    session: Session, *, account_id: uuid.UUID, **overrides: Any
) -> SignalSource:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "account_id": account_id,
        "signal_type": SignalType.camera,
        "name": f"test-camera-{_short_id()}",
        "status": SignalSourceStatus.active,
        "config": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    ss = SignalSource(**defaults)
    session.add(ss)
    session.flush()
    return ss


def make_signal_feed(
    session: Session, *, source_id: uuid.UUID, **overrides: Any
) -> SignalFeed:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "source_id": source_id,
        "feed_type": FeedType.image_snapshot,
        "capture_mode": CaptureMode.pull,
        "status": SignalFeedStatus.active,
        "capture_count": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    sf = SignalFeed(**defaults)
    session.add(sf)
    session.flush()
    return sf


def make_monitoring_config(
    session: Session,
    *,
    project_id: uuid.UUID,
    signal_source_id: uuid.UUID,
    **overrides: Any,
) -> MonitoringConfig:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "project_id": project_id,
        "signal_source_id": signal_source_id,
        "name": f"test-monitor-{_short_id()}",
        "rules": {"prompt": "Check for cleanliness"},
        "enabled": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    mc = MonitoringConfig(**defaults)
    session.add(mc)
    session.flush()
    return mc


def make_monitoring_run(
    session: Session, *, monitoring_config_id: uuid.UUID, **overrides: Any
) -> MonitoringRun:
    now = _now()
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "monitoring_config_id": monitoring_config_id,
        "trigger_metadata": {"source": "test"},
        "started_at": now,
        "evaluation_result": {"result": "pass"},
    }
    defaults.update(overrides)
    mr = MonitoringRun(**defaults)
    session.add(mr)
    session.flush()
    return mr


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------


def make_routine(
    session: Session, *, project_id: uuid.UUID, **overrides: Any
) -> Routine:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "project_id": project_id,
        "name": f"test-routine-{_short_id()}",
        "category": RoutineCategory.custom,
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    r = Routine(**defaults)
    session.add(r)
    session.flush()
    return r


def make_routine_item(
    session: Session, *, routine_id: uuid.UUID, **overrides: Any
) -> RoutineItem:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "routine_id": routine_id,
        "name": f"test-item-{_short_id()}",
        "sort_order": 0,
        "input_type": RoutineInputType.photo,
        "is_required": True,
        "reference_images": [],
        "ai_rules": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    ri = RoutineItem(**defaults)
    session.add(ri)
    session.flush()
    return ri


def make_routine_schedule(
    session: Session, *, routine_id: uuid.UUID, **overrides: Any
) -> RoutineSchedule:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "routine_id": routine_id,
        "frequency": RoutineFrequency.daily,
        "start_time": time(9, 0),
        "end_time": time(17, 0),
        "timezone": "America/Los_Angeles",
        "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    rs = RoutineSchedule(**defaults)
    session.add(rs)
    session.flush()
    return rs


def make_routine_execution(
    session: Session,
    *,
    routine_id: uuid.UUID,
    schedule_id: uuid.UUID,
    **overrides: Any,
) -> RoutineExecution:
    now = _now()
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "routine_id": routine_id,
        "schedule_id": schedule_id,
        "scheduled_start": now,
        "scheduled_end": now,
        "status": ExecutionStatus.pending,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    re_ = RoutineExecution(**defaults)
    session.add(re_)
    session.flush()
    return re_


def make_routine_submission(
    session: Session, *, execution_id: uuid.UUID, **overrides: Any
) -> RoutineSubmission:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "execution_id": execution_id,
        "status": SubmissionStatus.draft,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    rs = RoutineSubmission(**defaults)
    session.add(rs)
    session.flush()
    return rs


def make_routine_item_response(
    session: Session,
    *,
    submission_id: uuid.UUID,
    routine_item_id: uuid.UUID,
    **overrides: Any,
) -> RoutineItemResponse:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "submission_id": submission_id,
        "routine_item_id": routine_item_id,
        "status": ItemResponseStatus.pending,
        "created_at": _now(),
        "updated_at": _now(),
    }
    defaults.update(overrides)
    rir = RoutineItemResponse(**defaults)
    session.add(rir)
    session.flush()
    return rir
