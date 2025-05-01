from fastapi import HTTPException, status

from api.routes.admin._utils import UserContext
from api.schemas.admin.user_management import (
    CreateUserRequest,
    ListUsersResponse,
    UserInfo,
)
from services import admin_service

from . import _auth


async def list_account_users(
    account_name: str,
    context: UserContext,
) -> ListUsersResponse:
    """
    List all admin users for a specific account.

    Args:
        account_name: The name of the account to list users for
        context: The user context for authorization

    Returns:
        ListUsersResponse: A list of admin users for the account
    """
    _auth.authorize_user_account(context, account_name)

    try:
        users_data = admin_service.list_account_users(account_name)
        users = [
            UserInfo(
                email=user.email,
                name=user.name,
            )
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
) -> UserInfo:
    """
    Create a new admin user for a specific account.

    Args:
        account_name: The name of the account to create the user for
        user: The user information to create
        context: The user context for authorization

    Returns:
        UserInfo: The created user information
    """
    _auth.authorize_user_account(context, account_name)

    try:
        user_data = admin_service.create_account_user(
            account_name, user.email, user.name
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
) -> None:
    """
    Delete an admin user for a specific account.

    Args:
        account_name: The name of the account the user belongs to
        user_email: The user email to delete
        context: The user context for authorization
    """
    _auth.authorize_user_account(context, account_name)

    try:
        admin_service.delete_account_user(account_name, user_email)
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
