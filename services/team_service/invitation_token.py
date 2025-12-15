"""
Invitation token utilities for secure credential transmission.

This module provides JWT-based token generation for team invitations that
securely embed temporary passwords for seamless sign-in experience.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from utils.secret import get_server_secret_with_fallback

INVITATION_JWT_ALGORITHM = "HS256"


def _get_jwt_secret() -> str:
    """
    Get JWT secret from AWS Secrets Manager or environment variable.

    Returns:
        str: The JWT secret for signing invitation tokens

    Raises:
        ValueError: If INVITATION_JWT_SECRET is not found in Secrets Manager or env vars
    """
    return get_server_secret_with_fallback("INVITATION_JWT_SECRET")


def generate_invitation_jwt(
    invitation_token: str,
    email: str,
    temporary_password: str | None = None,
    expires_at: datetime | None = None,
) -> str:
    """
    Generate a JWT token that securely encodes invitation details and temporary password.

    Args:
        invitation_token: The unique invitation token from database
        email: User's email address
        temporary_password: Optional temporary password for new users
        expires_at: Optional expiration time (defaults to 7 days)

    Returns:
        str: Encoded JWT token

    Raises:
        ValueError: If INVITATION_JWT_SECRET is not found in AWS Secrets Manager or env vars

    Example:
        >>> token = generate_invitation_jwt("abc123", "user@example.com", "TempPass123")
        >>> # Frontend receives: /accept-invitation?token={token}
    """
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    payload: dict[str, Any] = {
        "invitation_token": invitation_token,
        "email": email,
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
    }

    # Only include password if provided (new users)
    if temporary_password:
        payload["temp_password"] = temporary_password

    secret = _get_jwt_secret()
    return jwt.encode(payload, secret, algorithm=INVITATION_JWT_ALGORITHM)


def decode_invitation_jwt(token: str) -> dict[str, Any]:
    """
    Decode and validate an invitation JWT token.

    Args:
        token: The encoded JWT token

    Returns:
        dict containing:
        - invitation_token: str
        - email: str
        - temp_password: str | None (only for new users)

    Raises:
        ValueError: If INVITATION_JWT_SECRET is not found in AWS Secrets Manager or env vars
        jwt.ExpiredSignatureError: If token has expired
        jwt.InvalidTokenError: If token is invalid or malformed
    """
    secret = _get_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[INVITATION_JWT_ALGORITHM])

        return {
            "invitation_token": payload["invitation_token"],
            "email": payload["email"],
            "temp_password": payload.get("temp_password"),  # May be None
        }
    except jwt.ExpiredSignatureError:
        raise jwt.ExpiredSignatureError("Invitation token has expired")
    except jwt.InvalidTokenError as e:
        raise jwt.InvalidTokenError(f"Invalid invitation token: {str(e)}")
