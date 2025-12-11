from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.user_management import (
    AssignAccountRequest,
    AssignAccountResponse,
    CreateUserRequest,
    ListUsersResponse,
    UserInfo,
)
from services import admin_service
from services.auth_types import UserContext


async def list_account_users(
    account_name: str,
    context: UserContext,
    session: Session,
) -> ListUsersResponse:
    """
    List all admin users for a specific account.
    Authorization is handled by require_account_permission in route decorator.

    Args:
        account_name: The name of the account to list users for
        context: The user context for authorization
        session: Database session

    Returns:
        ListUsersResponse: A list of admin users for the account
    """
    try:
        users_data = admin_service.list_account_users(account_name, session)
        users = [
            UserInfo(email=user.email, name=user.name, status=user.status)
            for user in users_data
        ]
        return ListUsersResponse(users=users)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


async def create_account_user(
    account_name: str,
    user: CreateUserRequest,
    context: UserContext,
    session: Session,
) -> UserInfo:
    """
    Create a new admin user for a specific account.
    Authorization is handled by require_account_permission in route decorator.

    Args:
        account_name: The name of the account to create the user for
        user: The user information to create
        context: The user context for authorization
        session: Database session

    Returns:
        UserInfo: The created user information
    """
    try:
        user_data = admin_service.create_account_user(
            account_name, user.email, user.name, session
        )
        return UserInfo(
            email=user_data.email,
            name=user_data.name,
        )
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )


async def delete_account_user(
    account_name: str,
    user_email: str,
    context: UserContext,
    session: Session,
) -> None:
    """
    Delete an admin user for a specific account.
    Authorization is handled by require_account_permission in route decorator.

    Args:
        account_name: The name of the account the user belongs to
        user_email: The user email to delete
        context: The user context for authorization
        session: Database session
    """
    try:
        admin_service.delete_account_user(account_name, user_email, session)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )


async def assign_account_to_user(
    request: AssignAccountRequest,
    context: UserContext,
    session: Session,
) -> AssignAccountResponse:
    """
    Assign an existing user to an account with a specified role.

    This creates:
    1. AccountUser record (membership)
    2. ResourceRoleAssignment record (role on account resource)

    Args:
        request: The assignment request containing user_id, account_name, and role
        context: The user context for authorization (admin only)
        session: Database session

    Returns:
        AssignAccountResponse: Status and message about the assignment

    Raises:
        HTTPException: 404 if account or user not found, 500 for other errors
    """
    try:
        result = admin_service.assign_account_to_user(
            user_id=request.user_id,
            account_name=request.account_name,
            role=request.role,
            session=session,
        )
        return AssignAccountResponse(
            status=result["status"],
            message=result["message"],
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )
