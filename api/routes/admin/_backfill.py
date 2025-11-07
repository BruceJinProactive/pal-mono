import os
import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_admin
from api.routes.admin._utils import UserContext
from api.schemas.admin.backfill import (
    BackfillRoleAssignmentsRequest,
    BackfillRoleAssignmentsResponse,
    BackfillUserResult,
)
from db.repositories import AccountRepository, ResourceRoleAssignmentRepository
from db.repositories.resource_role_assignment_repository import ResourceType
from utils.log import logger

AWS_REGION = os.environ["AWS_REGION"]
AWS_ADMIN_CONSOLE_USER_POOL_ID = os.environ["AWS_ADMIN_CONSOLE_USER_POOL_ID"]


def get_attr(attrs: list[dict], key: str) -> str:
    """Helper to extract attribute value from Cognito attributes list."""
    return next((a["Value"] for a in attrs if a["Name"] == key), "")


def backfill_role_assignments(
    request: BackfillRoleAssignmentsRequest,
    context: UserContext,
    session: Session,
) -> BackfillRoleAssignmentsResponse:
    """
    Backfill role assignments from Cognito custom:account_names to ResourceRoleAssignment table.

    This endpoint reads all users from Cognito, extracts their custom:account_names attribute,
    and creates corresponding ResourceRoleAssignment records with owner role. Does NOT create
    AccountUser records - those should be managed separately.

    Args:
        request: The backfill request with dry_run and email_filter options
        context: The user context for authorization
        session: Database session

    Returns:
        BackfillRoleAssignmentsResponse: Summary of the backfill operation

    Raises:
        HTTPException: 403 if user is not an admin
        HTTPException: 500 for other errors
    """
    # Only Admin users can run backfill
    authorize_admin(context)

    # Initialize repositories (auto_commit=False for transactional consistency)
    account_repo = AccountRepository(session)
    role_repo = ResourceRoleAssignmentRepository(session, auto_commit=False)

    # Initialize Cognito client
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)

    # Tracking statistics
    total_users_processed = 0
    total_roles_created = 0
    total_memberships_created = 0
    total_accounts_skipped = 0
    total_errors = 0
    user_results: list[BackfillUserResult] = []

    try:
        pagination_token = None

        while True:
            # List users from Cognito (with optional email filter)
            try:
                if request.email_filter:
                    # Filter by specific email for testing
                    response = cognito_client.list_users(
                        UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
                        Filter=f'email="{request.email_filter}"',
                    )
                    fetched_users = response.get("Users", [])
                    pagination_token = None  # No pagination needed for single user
                else:
                    # List all users with pagination
                    if pagination_token:
                        response = cognito_client.list_users(
                            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
                            PaginationToken=pagination_token,
                        )
                    else:
                        response = cognito_client.list_users(
                            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
                        )
                    fetched_users = response.get("Users", [])
                    pagination_token = response.get("PaginationToken")

            except ClientError as e:
                logger.error(
                    f"Error listing Cognito users: {e}",
                    extra={"error": str(e)},
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to list Cognito users: {str(e)}",
                    headers={"Content-Type": "application/json"},
                )

            # Process each user
            for user in fetched_users:
                total_users_processed += 1
                username = user["Username"]
                attributes = user.get("Attributes", [])

                if not attributes:
                    logger.warning(
                        "User has no attributes, skipping",
                        extra={"username": username},
                    )
                    continue

                # Extract user info
                email = get_attr(attributes, "email")
                account_names_str = get_attr(attributes, "custom:account_names")
                account_name_str = get_attr(attributes, "custom:account_name")

                # Parse comma-separated account names from both attributes
                account_names = []

                # Add from plural attribute
                if account_names_str:
                    account_names.extend(
                        [
                            name.strip()
                            for name in account_names_str.split(",")
                            if name.strip()
                        ]
                    )

                # Add from singular attribute
                if account_name_str and account_name_str.strip():
                    account_names.append(account_name_str.strip())

                # Deduplicate while preserving order
                account_names = list(dict.fromkeys(account_names))

                if not account_names:
                    logger.info(
                        "User has no custom:account_names or custom:account_name attribute, skipping",
                        extra={"email": email, "username": username},
                    )
                    continue

                # Initialize user result
                user_result = BackfillUserResult(
                    email=email,
                    user_id=username,
                    account_names=account_names,
                    roles_created=0,
                    memberships_created=0,
                    skipped_accounts=[],
                    errors=[],
                )

                # Process each account for this user
                for account_name in account_names:
                    try:
                        # Look up account by name
                        account = account_repo.get_account(account_name=account_name)

                        if not account:
                            logger.warning(
                                f"Account not found: {account_name}",
                                extra={
                                    "user_email": email,
                                    "account_name": account_name,
                                },
                            )
                            user_result.skipped_accounts.append(account_name)
                            total_accounts_skipped += 1
                            continue

                        # Convert username to UUID
                        try:
                            user_id = uuid.UUID(username)
                        except ValueError:
                            error_msg = f"Invalid UUID format for username: {username}"
                            logger.error(error_msg, extra={"username": username})
                            user_result.errors.append(error_msg)
                            total_errors += 1
                            continue

                        # Create ResourceRoleAssignment
                        if not request.dry_run:
                            try:
                                role_repo.add_role(
                                    user_id=user_id,
                                    resource_type=ResourceType.ACCOUNT,
                                    resource_id=account.id,
                                    role="owner",
                                    assigned_by=None,
                                    reason="Cognito custom:account_names backfill migration",
                                )
                                session.commit()
                                logger.info(
                                    f"Created role assignment for user {email} in account {account_name}",
                                    extra={
                                        "user_id": str(user_id),
                                        "account_id": str(account.id),
                                        "role": "owner",
                                    },
                                )
                            except Exception as e:
                                session.rollback()
                                error_msg = (
                                    f"Failed to create role assignment: {str(e)}"
                                )
                                logger.error(
                                    error_msg,
                                    extra={
                                        "user_email": email,
                                        "account_name": account_name,
                                    },
                                )
                                user_result.errors.append(error_msg)
                                total_errors += 1
                                continue

                        user_result.roles_created += 1
                        total_roles_created += 1

                    except Exception as e:
                        error_msg = f"Error processing account {account_name}: {str(e)}"
                        logger.error(
                            error_msg,
                            extra={"user_email": email, "account_name": account_name},
                        )
                        user_result.errors.append(error_msg)
                        total_errors += 1

                # Add user result to response
                user_results.append(user_result)

            # Check if we should continue pagination
            if not pagination_token or not fetched_users or request.email_filter:
                break

        logger.info(
            f"Backfill complete (dry_run={request.dry_run}): "
            f"processed {total_users_processed} users, "
            f"created {total_roles_created} roles, "
            f"created {total_memberships_created} memberships, "
            f"skipped {total_accounts_skipped} accounts, "
            f"{total_errors} errors",
        )

        return BackfillRoleAssignmentsResponse(
            dry_run=request.dry_run,
            total_users_processed=total_users_processed,
            total_roles_created=total_roles_created,
            total_memberships_created=total_memberships_created,
            total_accounts_skipped=total_accounts_skipped,
            total_errors=total_errors,
            user_results=user_results,
        )

    except HTTPException:
        # Re-raise HTTPExceptions (authorization errors, etc.)
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error during backfill: {e}",
            extra={"error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during backfill: {str(e)}",
            headers={"Content-Type": "application/json"},
        )
