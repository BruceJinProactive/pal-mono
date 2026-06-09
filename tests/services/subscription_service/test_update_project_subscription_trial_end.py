"""Tests for trial_end handling in update_project_subscription()."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from db.tables.subscriptions import SubscriptionStatus
from services.subscription_service._subscription import update_project_subscription


class _FakeColumn:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeTable:
    """Minimal stand-in for SQLAlchemy __table__ used by service clone logic."""

    columns = (
        _FakeColumn("external_id"),
        _FakeColumn("project_id"),
        _FakeColumn("version"),
        _FakeColumn("status"),
        _FakeColumn("trial_start_date"),
        _FakeColumn("start_date"),
        _FakeColumn("end_date"),
        _FakeColumn("payment_method"),
        _FakeColumn("stripe_subscription_id"),
        _FakeColumn("subscription_plan_id"),
        _FakeColumn("recurring_credit_enabled"),
        _FakeColumn("recurring_credit_amount"),
        _FakeColumn("recurring_credit_frequency"),
    )


class FakeProjectSubscription:
    """Minimal project subscription satisfying type(instance).__table__.columns."""

    __table__ = _FakeTable()

    id: uuid.UUID
    external_id: uuid.UUID
    project_id: uuid.UUID
    version: int
    status: SubscriptionStatus
    trial_start_date: datetime | None
    start_date: datetime
    end_date: datetime | None
    payment_method: str
    stripe_subscription_id: str | None
    subscription_plan_id: uuid.UUID
    recurring_credit_enabled: bool
    recurring_credit_amount: float | None
    recurring_credit_frequency: str | None

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.add = MagicMock()
    session.flush = MagicMock()
    session.refresh = MagicMock()
    return session


@pytest.fixture
def mock_context() -> MagicMock:
    context = MagicMock()
    context.email = "admin@test.com"
    return context


@pytest.fixture
def trialing_project_subscription() -> FakeProjectSubscription:
    return FakeProjectSubscription(
        id=uuid.uuid4(),
        external_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version=1,
        status=SubscriptionStatus.trialing,
        trial_start_date=datetime.now(UTC) - timedelta(days=7),
        start_date=datetime.now(UTC) + timedelta(days=7),
        end_date=None,
        payment_method="card",
        stripe_subscription_id=None,
        subscription_plan_id=uuid.uuid4(),
        recurring_credit_enabled=False,
        recurring_credit_amount=None,
        recurring_credit_frequency=None,
    )


@pytest.fixture
def active_project_subscription() -> FakeProjectSubscription:
    return FakeProjectSubscription(
        id=uuid.uuid4(),
        external_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version=1,
        status=SubscriptionStatus.active,
        trial_start_date=None,
        start_date=datetime.now(UTC) - timedelta(days=30),
        end_date=None,
        payment_method="card",
        stripe_subscription_id="sub_project_123",
        subscription_plan_id=uuid.uuid4(),
        recurring_credit_enabled=False,
        recurring_credit_amount=None,
        recurring_credit_frequency=None,
    )


def _mock_project(project_id: uuid.UUID) -> MagicMock:
    project = MagicMock()
    project.id = project_id
    project.account_id = uuid.uuid4()
    return project


class TestProjectTrialEnd:
    """trial_end on project subscriptions."""

    @patch("services.subscription_service._subscription.project_service.get_project")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
    def test_trial_end_sets_start_date(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_get_project: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        trialing_project_subscription: FakeProjectSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=21)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_project_subscription_by_external_id.return_value = (
            trialing_project_subscription
        )
        mock_get_project.return_value = _mock_project(
            trialing_project_subscription.project_id
        )
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        result = update_project_subscription(
            session=mock_session,
            context=mock_context,
            project_id=trialing_project_subscription.project_id,
            external_id=trialing_project_subscription.external_id,
            update_data={"trial_end": trial_end},
        )

        assert result.start_date == trial_end

    @patch("services.subscription_service._subscription.project_service.get_project")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
    def test_trial_end_sets_trial_start_date_when_missing(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_get_project: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        active_project_subscription: FakeProjectSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=14)
        active_project_subscription.stripe_subscription_id = None
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_project_subscription_by_external_id.return_value = (
            active_project_subscription
        )
        mock_get_project.return_value = _mock_project(
            active_project_subscription.project_id
        )
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        before = datetime.now(UTC)
        result = update_project_subscription(
            session=mock_session,
            context=mock_context,
            project_id=active_project_subscription.project_id,
            external_id=active_project_subscription.external_id,
            update_data={"trial_end": trial_end},
        )
        after = datetime.now(UTC)

        assert result.trial_start_date is not None
        assert result.trial_start_date >= before
        assert result.trial_start_date <= after
        assert result.status == SubscriptionStatus.trialing

    @patch("services.subscription_service._subscription.project_service.get_project")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
    def test_past_trial_end_does_not_create_inverted_trial_dates(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_get_project: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        active_project_subscription: FakeProjectSubscription,
    ) -> None:
        active_project_subscription.stripe_subscription_id = None
        requested_trial_end = datetime.now(UTC) - timedelta(days=1)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_project_subscription_by_external_id.return_value = (
            active_project_subscription
        )
        mock_get_project.return_value = _mock_project(
            active_project_subscription.project_id
        )
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        before = datetime.now(UTC)
        result = update_project_subscription(
            session=mock_session,
            context=mock_context,
            project_id=active_project_subscription.project_id,
            external_id=active_project_subscription.external_id,
            update_data={"trial_end": requested_trial_end},
        )
        after = datetime.now(UTC)

        assert result.start_date is not None
        assert result.start_date >= before
        assert result.start_date <= after
        assert result.trial_start_date is None
        assert result.status == SubscriptionStatus.active

    @patch("services.subscription_service._subscription.stripe")
    @patch("services.subscription_service._subscription.project_service.get_project")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
    def test_trial_end_calls_stripe_modify(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_get_project: MagicMock,
        mock_stripe: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        active_project_subscription: FakeProjectSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=14)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_project_subscription_by_external_id.return_value = (
            active_project_subscription
        )
        mock_get_project.return_value = _mock_project(
            active_project_subscription.project_id
        )
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        update_project_subscription(
            session=mock_session,
            context=mock_context,
            project_id=active_project_subscription.project_id,
            external_id=active_project_subscription.external_id,
            update_data={"trial_end": trial_end},
        )

        mock_stripe.Subscription.modify.assert_called_once_with(
            "sub_project_123",
            trial_end=int(trial_end.timestamp()),
        )

    @patch("services.subscription_service._subscription.stripe")
    @patch("services.subscription_service._subscription.project_service.get_project")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
    def test_past_trial_end_syncs_to_stripe_as_now(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_get_project: MagicMock,
        mock_stripe: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        active_project_subscription: FakeProjectSubscription,
    ) -> None:
        requested_trial_end = datetime.now(UTC) - timedelta(days=1)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_project_subscription_by_external_id.return_value = (
            active_project_subscription
        )
        mock_get_project.return_value = _mock_project(
            active_project_subscription.project_id
        )
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        update_project_subscription(
            session=mock_session,
            context=mock_context,
            project_id=active_project_subscription.project_id,
            external_id=active_project_subscription.external_id,
            update_data={"trial_end": requested_trial_end},
        )

        mock_stripe.Subscription.modify.assert_called_once_with(
            "sub_project_123",
            trial_end="now",
        )

    @patch("services.subscription_service._subscription.stripe")
    @patch("services.subscription_service._subscription.project_service.get_project")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
    def test_trial_end_rolls_back_when_stripe_sync_fails(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_get_project: MagicMock,
        mock_stripe: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        active_project_subscription: FakeProjectSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=14)
        mock_stripe.StripeError = RuntimeError
        mock_stripe.Subscription.modify.side_effect = RuntimeError("stripe down")
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_project_subscription_by_external_id.return_value = (
            active_project_subscription
        )
        mock_get_project.return_value = _mock_project(
            active_project_subscription.project_id
        )
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(
            RuntimeError, match="Failed to sync project subscription trial_end"
        ):
            update_project_subscription(
                session=mock_session,
                context=mock_context,
                project_id=active_project_subscription.project_id,
                external_id=active_project_subscription.external_id,
                update_data={"trial_end": trial_end},
            )

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    @patch("services.subscription_service._subscription.stripe")
    @patch("services.subscription_service._subscription.project_service.get_project")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
    def test_trial_end_skips_stripe_when_no_stripe_id(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_get_project: MagicMock,
        mock_stripe: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        trialing_project_subscription: FakeProjectSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=21)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_project_subscription_by_external_id.return_value = (
            trialing_project_subscription
        )
        mock_get_project.return_value = _mock_project(
            trialing_project_subscription.project_id
        )
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        update_project_subscription(
            session=mock_session,
            context=mock_context,
            project_id=trialing_project_subscription.project_id,
            external_id=trialing_project_subscription.external_id,
            update_data={"trial_end": trial_end},
        )

        mock_stripe.Subscription.modify.assert_not_called()


class TestProjectTrialEndSchemaValidation:
    """Schema-level validation for project trial_end."""

    def test_trial_end_and_start_date_conflict_raises(self) -> None:
        from api.schemas.admin.subscription import UpdateProjectSubscriptionRequest

        with pytest.raises(
            ValueError, match="Cannot specify both trial_end and start_date"
        ):
            UpdateProjectSubscriptionRequest(
                trial_end=datetime.now(UTC) + timedelta(days=14),
                start_date=datetime.now(UTC) + timedelta(days=7),
            )

    def test_trial_end_alone_is_valid(self) -> None:
        from api.schemas.admin.subscription import UpdateProjectSubscriptionRequest

        req = UpdateProjectSubscriptionRequest(
            trial_end=datetime.now(UTC) + timedelta(days=14),
        )
        assert req.trial_end is not None
        assert req.start_date is None
