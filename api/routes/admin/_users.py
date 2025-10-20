from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from api.routes.admin._utils import UserContext, UserRole
from api.schemas.admin.user_management import (
    CreateUserRequest,
    ListUsersResponse,
    UpdateUserAccountNamesRequest,
    UserAccountNamesResponse,
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


async def get_user_account_names(
    user_email: str,
    context: UserContext,
) -> UserAccountNamesResponse:
    """
    Get the account_names attribute for a Cognito user.

    This endpoint allows admins and account managers to retrieve the list of accounts
    a user has access to.

    Args:
        user_email: The email address of the user to retrieve account names for
        context: The user context for authorization

    Returns:
        UserAccountNamesResponse: The user's email and list of account names

    Raises:
        HTTPException: 403 if user is not an admin or account manager
        HTTPException: 404 if user not found
        HTTPException: 500 for other errors
    """
    # Only Admin and AccountManager users can get account names
    if context.role not in [UserRole.Admin, UserRole.AccountManager]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin and AccountManager users can retrieve account names",
        )

    try:
        account_names = await run_in_threadpool(
            admin_service.get_user_account_names, user_email
        )

        return UserAccountNamesResponse(
            email=user_email,
            account_names=account_names,
        )
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )


async def update_user_account_names(
    user_email: str,
    request: UpdateUserAccountNamesRequest,
    context: UserContext,
) -> None:
    """
    Update the account_names attribute for a Cognito user.

    This endpoint allows admins to update the list of accounts a user has access to.
    Only Admin users can call this endpoint.

    Args:
        user_email: The email address of the user to update
        request: The request containing the list of account names
        context: The user context for authorization

    Raises:
        HTTPException: 403 if user is not an admin
        HTTPException: 404 if user not found
        HTTPException: 400 if account_names is empty
        HTTPException: 500 for other errors
    """
    # Only Admin users can update account names
    if context.role != UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin users can update account names",
        )

    if not request.account_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_names list cannot be empty",
        )

    try:
        admin_service.update_user_account_names(user_email, request.account_names)
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        elif "cannot be empty" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )
