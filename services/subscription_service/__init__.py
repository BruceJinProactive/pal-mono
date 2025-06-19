from sqlalchemy.orm import Session

from api.routes.admin import UserContext
from services.subscription_service.schema import (
    SubscriptionParams,
    SubscriptionPlanParams,
)

from . import _implementation


def create_subscription(
    session: Session,
    context: UserContext,
    account_name: str,
    params: SubscriptionParams,
):
    return _implementation.create_subscription(session, context, account_name, params)


def create_subscription_plan(
    session: Session,
    context: UserContext,
    params: SubscriptionPlanParams,
):
    return _implementation.create_subscription_plan(session, context, params)


def get_subscription_plans(
    session: Session,
):
    return _implementation.get_subscription_plans(session)


def get_subscription_plan_by_id(
    session: Session,
    plan_id,
):
    return _implementation.get_subscription_plan_by_id(session, plan_id)
