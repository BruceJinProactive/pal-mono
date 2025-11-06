"""
Helper utilities for team service operations.

TODO: Remove these mock functions once email field is added to account_users table.
"""

import uuid


def get_mock_email_for_user(user_id: uuid.UUID) -> str:
    """
    Generate a mock email for a user ID.

    This is a temporary workaround until we add the email field to account_users table.
    In production, we should:
    1. Add email column to account_users table
    2. Store email when creating membership
    3. Query email directly from account_users

    Args:
        user_id: UUID of the user

    Returns:
        Mock email like "user-abc123@pending.palona.ai"
    """
    short_id = str(user_id)[:8]
    return f"user-{short_id}@pending.palona.ai"


def get_mock_display_name_for_user(user_id: uuid.UUID) -> str:
    """
    Generate a mock display name for a user ID.

    This is a temporary workaround until we add display_name tracking.

    Args:
        user_id: UUID of the user

    Returns:
        Mock name like "User abc123"
    """
    short_id = str(user_id)[:8]
    return f"User {short_id}"


def user_id_matches_email(user_id: uuid.UUID, email: str, context_email: str) -> bool:
    """
    Check if a user_id corresponds to an email.

    This is a temporary workaround. Currently only supports matching the current user
    via their context email.

    Args:
        user_id: UUID of the user to check
        email: Email to match against
        context_email: Email from UserContext (current authenticated user)

    Returns:
        True if this appears to be the same user

    TODO: Replace with proper email lookup from account_users table
    """
    # For now, we can only match if the email is the current user's email
    # This means operations like "remove user by email" only work for self-removal testing
    return email == context_email
