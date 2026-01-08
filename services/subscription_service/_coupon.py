"""
Coupon management service functions for accounts and projects.
"""

import uuid

import stripe
from sqlalchemy.orm import Session

import db
from db.tables.change_log import ChangeResourceType
from services import account_service, project_service
from services.auth_types import UserContext
from services.history_service import change_log_context
from services.subscription_service import _stripe_subscription
from utils.log import logger


def assign_coupon_to_account(
    session: Session,
    context: UserContext,
    account_name: str,
    coupon_id: str,
) -> db.Account:
    """
    Assign a Stripe coupon to an account.

    The coupon will be automatically applied to all future subscriptions
    created for this account.

    Args:
        session: Database session
        context: User context for authorization and logging
        account_name: Name of the account
        coupon_id: Stripe coupon ID to assign

    Returns:
        Updated account with coupon assigned

    Raises:
        ValueError: If account doesn't exist or coupon is invalid
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    # Validate the coupon exists and is valid
    try:
        _stripe_subscription.validate_stripe_coupon(coupon_id)
    except ValueError as e:
        logger.error(
            f"Failed to assign invalid coupon to account: {e}",
            extra={
                "account_name": account_name,
                "coupon_id": coupon_id,
            },
        )
        raise

    old_coupon_id = account.stripe_coupon_id

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Account,
        author=context.email,
        account_id=account.id,
        resource_id=str(account.id),
        auto_commit=False,
    ):
        account.stripe_coupon_id = coupon_id

    logger.info(
        f"Assigned coupon {coupon_id} to account {account_name}",
        extra={
            "account_id": str(account.id),
            "account_name": account_name,
            "old_coupon_id": old_coupon_id,
            "new_coupon_id": coupon_id,
        },
    )

    return account


def update_account_coupon(
    session: Session,
    context: UserContext,
    account_name: str,
    coupon_id: str,
) -> db.Account:
    """
    Update the Stripe coupon for an account.

    This replaces any existing coupon with the new one.

    Args:
        session: Database session
        context: User context for authorization and logging
        account_name: Name of the account
        coupon_id: New Stripe coupon ID

    Returns:
        Updated account with new coupon

    Raises:
        ValueError: If account doesn't exist or coupon is invalid
    """
    # Same implementation as assign, just a semantic alias
    return assign_coupon_to_account(session, context, account_name, coupon_id)


def remove_coupon_from_account(
    session: Session,
    context: UserContext,
    account_name: str,
) -> db.Account:
    """
    Remove the Stripe coupon from an account.

    Future subscriptions will not have any coupon applied.

    Args:
        session: Database session
        context: User context for authorization and logging
        account_name: Name of the account

    Returns:
        Updated account with coupon removed

    Raises:
        ValueError: If account doesn't exist
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    old_coupon_id = account.stripe_coupon_id

    if not old_coupon_id:
        logger.info(
            f"No coupon to remove from account {account_name}",
            extra={"account_name": account_name},
        )
        return account

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Account,
        author=context.email,
        account_id=account.id,
        resource_id=str(account.id),
        auto_commit=False,
    ):
        account.stripe_coupon_id = None

    logger.info(
        f"Removed coupon from account {account_name}",
        extra={
            "account_id": str(account.id),
            "account_name": account_name,
            "removed_coupon_id": old_coupon_id,
        },
    )

    return account


def get_account_coupon(
    session: Session,
    account_name: str,
) -> tuple[str | None, dict | None]:
    """
    Get the Stripe coupon assigned to an account.

    Args:
        session: Database session
        account_name: Name of the account

    Returns:
        Tuple of (coupon_id, coupon_details_dict) or (None, None) if no coupon

    Raises:
        ValueError: If account doesn't exist
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    if not account.stripe_coupon_id:
        return None, None

    # Fetch coupon details from Stripe
    try:
        coupon = stripe.Coupon.retrieve(account.stripe_coupon_id)
        coupon_details = {
            "id": coupon.id,
            "name": coupon.name,
            "percent_off": coupon.percent_off,
            "amount_off": coupon.amount_off,
            "currency": coupon.currency,
            "duration": coupon.duration,
            "duration_in_months": coupon.duration_in_months,
            "max_redemptions": coupon.max_redemptions,
            "times_redeemed": coupon.times_redeemed,
            "valid": coupon.valid,
            "redeem_by": coupon.redeem_by,
        }
        return account.stripe_coupon_id, coupon_details
    except stripe.StripeError as e:
        logger.error(
            f"Failed to retrieve coupon details from Stripe: {e}",
            extra={
                "account_name": account_name,
                "coupon_id": account.stripe_coupon_id,
            },
        )
        # Return coupon ID but no details if Stripe lookup fails
        return account.stripe_coupon_id, None


# Project Coupon Management Functions


def assign_coupon_to_project(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    coupon_id: str,
) -> db.Project:
    """
    Assign a Stripe coupon to a project.

    The coupon will be automatically applied to all future subscriptions
    created for this project.

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: UUID of the project
        coupon_id: Stripe coupon ID to assign

    Returns:
        Updated project with coupon assigned

    Raises:
        ValueError: If project doesn't exist or coupon is invalid
    """
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    # Validate the coupon exists and is valid
    try:
        _stripe_subscription.validate_stripe_coupon(coupon_id)
    except ValueError as e:
        logger.error(
            f"Failed to assign invalid coupon to project: {e}",
            extra={
                "project_id": str(project_id),
                "coupon_id": coupon_id,
            },
        )
        raise

    old_coupon_id = project.stripe_coupon_id

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Project,
        author=context.email,
        account_id=project.account_id,
        resource_id=str(project.id),
        auto_commit=False,
    ):
        project.stripe_coupon_id = coupon_id

    logger.info(
        f"Assigned coupon {coupon_id} to project {project.name}",
        extra={
            "project_id": str(project.id),
            "project_name": project.name,
            "old_coupon_id": old_coupon_id,
            "new_coupon_id": coupon_id,
        },
    )

    return project


def update_project_coupon(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    coupon_id: str,
) -> db.Project:
    """
    Update the Stripe coupon for a project.

    This replaces any existing coupon with the new one.

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: UUID of the project
        coupon_id: New Stripe coupon ID

    Returns:
        Updated project with new coupon

    Raises:
        ValueError: If project doesn't exist or coupon is invalid
    """
    # Same implementation as assign, just a semantic alias
    return assign_coupon_to_project(session, context, project_id, coupon_id)


def remove_coupon_from_project(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
) -> db.Project:
    """
    Remove the Stripe coupon from a project.

    Future subscriptions will fall back to the account-level coupon if set,
    or no coupon if account has none.

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: UUID of the project

    Returns:
        Updated project with coupon removed

    Raises:
        ValueError: If project doesn't exist
    """
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    old_coupon_id = project.stripe_coupon_id

    if not old_coupon_id:
        logger.info(
            f"No coupon to remove from project {project.name}",
            extra={"project_id": str(project_id), "project_name": project.name},
        )
        return project

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Project,
        author=context.email,
        account_id=project.account_id,
        resource_id=str(project.id),
        auto_commit=False,
    ):
        project.stripe_coupon_id = None

    logger.info(
        f"Removed coupon from project {project.name}",
        extra={
            "project_id": str(project.id),
            "project_name": project.name,
            "removed_coupon_id": old_coupon_id,
        },
    )

    return project


def get_project_coupon(
    session: Session,
    project_id: uuid.UUID,
) -> tuple[str | None, dict | None]:
    """
    Get the Stripe coupon assigned to a project.

    Args:
        session: Database session
        project_id: UUID of the project

    Returns:
        Tuple of (coupon_id, coupon_details_dict) or (None, None) if no coupon

    Raises:
        ValueError: If project doesn't exist
    """
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    if not project.stripe_coupon_id:
        return None, None

    # Fetch coupon details from Stripe
    try:
        coupon = stripe.Coupon.retrieve(project.stripe_coupon_id)
        coupon_details = {
            "id": coupon.id,
            "name": coupon.name,
            "percent_off": coupon.percent_off,
            "amount_off": coupon.amount_off,
            "currency": coupon.currency,
            "duration": coupon.duration,
            "duration_in_months": coupon.duration_in_months,
            "max_redemptions": coupon.max_redemptions,
            "times_redeemed": coupon.times_redeemed,
            "valid": coupon.valid,
            "redeem_by": coupon.redeem_by,
        }
        return project.stripe_coupon_id, coupon_details
    except stripe.StripeError as e:
        logger.error(
            f"Failed to retrieve coupon details from Stripe: {e}",
            extra={
                "project_id": str(project_id),
                "project_name": project.name,
                "coupon_id": project.stripe_coupon_id,
            },
        )
        # Return coupon ID but no details if Stripe lookup fails
        return project.stripe_coupon_id, None
