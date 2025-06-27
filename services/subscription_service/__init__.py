import uuid

from sqlalchemy.orm import Session

from api.routes.admin import UserContext
from db.tables.subscriptions import SubscriptionStatus
from services.subscription_service.schema import (
    SubscriptionParams,
    SubscriptionPlanParams,
)

from . import _implementation
from ._stripe import create_checkout_session


def create_subscription(
    session: Session,
    context: UserContext,
    account_name: str,
    params: SubscriptionParams,
):
    return _implementation.create_subscription(session, context, account_name, params)


def get_account_subscriptions(
    session: Session,
    account_name: str,
):
    return _implementation.get_account_subscriptions(session, account_name)


def update_account_subscription(
    session: Session,
    context: UserContext,
    account_name: str,
    external_id: uuid.UUID,
    request: dict,
    force_update: bool = False,
):
    return _implementation.update_account_subscription(
        session, context, account_name, external_id, request, force_update
    )


def create_subscription_plan(
    session: Session,
    context: UserContext,
    params: SubscriptionPlanParams,
):
    return _implementation.create_subscription_plan(session, context, params)


def update_account_subscription_status(
    session: Session,
    context: UserContext,
    account_name: str,
    external_id: uuid.UUID,
    status: SubscriptionStatus,
):
    return _implementation.update_account_subscription_status(
        session, context, account_name, external_id, status
    )


def get_subscription_plans(
    session: Session,
):
    return _implementation.get_subscription_plans(session)


def cancel_account_subscription(
    session: Session,
    context: UserContext,
    account_name: str,
    external_id: uuid.UUID,
    hard_delete: bool = False,
):
    return _implementation.cancel_account_subscription(
        session, context, account_name, external_id, hard_delete
    )


def get_subscription_plan_by_id(
    session: Session,
    plan_id,
):
    return _implementation.get_subscription_plan_by_id(session, plan_id)


def update_subscription_plan(
    session: Session,
    context: UserContext,
    plan_id: uuid.UUID,
    params: SubscriptionPlanParams,
):
    return _implementation.update_subscription_plan(session, context, plan_id, params)


def expire_subscription_plan(
    session: Session,
    context: UserContext,
    plan_id: uuid.UUID,
    hard_delete: bool = False,
):
    return _implementation.expire_subscription_plan(
        session, context, plan_id, hard_delete
    )


__all__ = [
    "create_subscription",
    "get_account_subscriptions",
    "update_account_subscription",
    "create_subscription_plan",
    "update_account_subscription_status",
    "get_subscription_plans",
    "cancel_account_subscription",
    "get_subscription_plan_by_id",
    "update_subscription_plan",
    "expire_subscription_plan",
    "create_checkout_session",
]
