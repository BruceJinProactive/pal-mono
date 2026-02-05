"""Service for backfilling accounts without owners."""

import os
import uuid
from typing import Any
from uuid import UUID

import boto3
from sqlalchemy.orm import Session

from db.repositories.account_repository import AccountRepository
from db.repositories.account_user_repository import AccountUserRepository
from db.repositories.resource_role_assignment_repository import (
    ResourceRoleAssignmentRepository,
    ResourceType,
)
from db.tables.account_user import AccountUserStatus
from utils.log import logger

AWS_ADMIN_CONSOLE_USER_POOL_ID = os.environ.get("AWS_ADMIN_CONSOLE_USER_POOL_ID", "")


def _get_cognito_user_id(user_email: str) -> UUID:
    """
    Get the Cognito user_id (sub) for a given email address.

    Args:
        user_email: Email address of the user

    Returns:
        UUID of the user's Cognito sub

    Raises:
        ValueError: If user not found or sub attribute missing
    """
    cognito_client = boto3.client("cognito-idp")

    try:
        user_response = cognito_client.admin_get_user(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID, Username=user_email
        )

        # Extract user_sub (user_id) from attributes
        user_sub = None
        for attr in user_response["UserAttributes"]:
            if attr["Name"] == "sub":
                user_sub = attr["Value"]
                break

        if not user_sub:
            raise ValueError(f"User sub not found for email: {user_email}")

        return UUID(user_sub)
    except Exception as e:
        logger.error(f"Failed to get Cognito user_id for {user_email}: {e}")
        raise


def get_default_owners_for_env() -> list[dict[str, str | uuid.UUID]]:
    """
    Get default owner emails and names based on RUNTIME_ENV.
    Fetches actual user_ids from Cognito.

    Returns:
        List of dicts with 'email', 'name', and 'user_id' keys
    """
    env = os.getenv("RUNTIME_ENV", "dev")

    if env == "lat":
        owners = [
            {
                "email": "jacob+palona.lat@proactiveailab.com",
                "name": "Jacob Wang",
            },
            {
                "email": "kelvin+lat@proactiveailab.com",
                "name": "Kelvin Ren",
            },
        ]
    elif env == "prd":
        owners = [
            {
                "email": "jacob+palona@proactiveailab.com",
                "name": "Jacob Wang",
            },
            {
                "email": "kelvin@proactiveailab.com",
                "name": "Kelvin Ren",
            },
        ]
    else:
        # Default to empty list for dev/unknown environments
        return []

    # Fetch user_ids from Cognito for each owner
    result = []
    for owner in owners:
        email = owner["email"]
        assert isinstance(email, str)
        try:
            user_id = _get_cognito_user_id(email)
            result.append(
                {
                    "email": email,
                    "name": owner["name"],
                    "user_id": user_id,
                }
            )
        except Exception as e:
            logger.error(f"Failed to fetch user_id for {email}, skipping: {e}")
            # Skip this owner if we can't get their user_id
            continue

    return result


def backfill_accounts_without_owners(
    session: Session, context: Any, dry_run: bool = False
) -> dict[str, Any]:
    """
    Backfill accounts that have no owners with default internal owners.

    For each account without owners:
    1. Creates AccountUser records for default owners (if they don't exist)
    2. Creates ResourceRoleAssignment records with role='owner'

    Args:
        session: Database session
        context: User context for authorization and audit logging
        dry_run: If True, only report what would be done without making changes

    Returns:
        Dict with:
        - accounts_without_owners: List of account IDs that have no owners
        - accounts_updated: List of account IDs that were updated (or would be)
        - owners_added: Dict mapping account_id to list of owner emails added
        - total_assignments: Total number of role assignments created
    """
    account_repo = AccountRepository(session)
    account_user_repo = AccountUserRepository(session)
    role_repo = ResourceRoleAssignmentRepository(session)

    # Get all accounts
    all_accounts = account_repo.filter_accounts_by_name()

    # Get default owners for this environment
    default_owners = get_default_owners_for_env()

    accounts_without_owners = []
    accounts_updated = []
    owners_added = {}
    total_assignments = 0

    for account in all_accounts:
        # Check if account has any owners
        all_assignments = role_repo.get_assignments_for_resource(
            resource_type=ResourceType.ACCOUNT,
            resource_id=account.id,
        )
        existing_owners = [a for a in all_assignments if a.role == "owner"]

        if not existing_owners or len(existing_owners) == 0:
            accounts_without_owners.append(str(account.id))
            account_owners_added = []

            logger.info(
                f"Account {account.name} ({account.id}) has no owners. "
                f"{'Would add' if dry_run else 'Adding'} default owners."
            )

            for owner in default_owners:
                owner_email_val = owner["email"]
                owner_name_val = owner["name"]
                owner_user_id_val = owner["user_id"]

                # Type assertions for pyright
                assert isinstance(owner_email_val, str)
                assert isinstance(owner_name_val, str)
                assert isinstance(owner_user_id_val, uuid.UUID)

                owner_email = owner_email_val
                owner_name = owner_name_val
                owner_user_id = owner_user_id_val

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would add owner {owner_email} to account {account.name}"
                    )
                    account_owners_added.append(owner_email)
                    total_assignments += 1
                else:
                    # Create or get AccountUser record
                    existing_account_user = account_user_repo.get_by_user_and_account(
                        user_id=owner_user_id, account_id=account.id
                    )

                    if existing_account_user:
                        # Reactivate if deactivated
                        if existing_account_user.status != AccountUserStatus.active:
                            account_user_repo.update_status(
                                user_id=owner_user_id,
                                account_id=account.id,
                                new_status=AccountUserStatus.active,
                            )
                            logger.info(
                                f"Reactivated account membership for {owner_email} in account {account.name}"
                            )
                    else:
                        # Create new account_user record
                        account_user_repo.create(
                            account_id=account.id,
                            user_id=owner_user_id,
                            email=owner_email,
                            name=owner_name,
                            added_by=None,  # System/admin operation
                            status=AccountUserStatus.active,
                        )
                        logger.info(
                            f"Created account membership for {owner_email} in account {account.name}"
                        )

                    # Assign owner role via ResourceRoleAssignment
                    try:
                        role_repo.add_role(
                            user_id=owner_user_id,
                            resource_type=ResourceType.ACCOUNT,
                            resource_id=account.id,
                            role="owner",
                            assigned_by=None,  # System operation
                            reason="Backfill: Adding default owners to accounts without owners",
                        )
                        logger.info(
                            f"Assigned owner role to {owner_email} on account {account.name}"
                        )
                        account_owners_added.append(owner_email)
                        total_assignments += 1
                    except Exception as e:
                        # Role might already exist - log warning but continue
                        logger.warning(
                            f"Failed to assign owner role to {owner_email} on account {account.name}: {e}"
                        )

            if account_owners_added:
                accounts_updated.append(str(account.id))
                owners_added[str(account.id)] = account_owners_added

    if not dry_run:
        session.commit()
        logger.info(
            f"Backfill complete: Updated {len(accounts_updated)} accounts with {total_assignments} owner assignments"
        )
    else:
        logger.info(
            f"[DRY RUN] Would update {len(accounts_updated)} accounts with {total_assignments} owner assignments"
        )

    return {
        "environment": os.getenv("RUNTIME_ENV", "dev"),
        "dry_run": dry_run,
        "accounts_without_owners": accounts_without_owners,
        "accounts_updated": accounts_updated,
        "owners_added": owners_added,
        "total_assignments": total_assignments,
        "default_owners": [o["email"] for o in default_owners],
        "executed_by": getattr(context, "email", None),
    }
