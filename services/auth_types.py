"""
Authentication and authorization domain models.

This module contains shared types used for authentication and authorization
across the application. These types are used by both API routes (for JWT
token validation and authorization checks) and services (for audit logging).
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class UserRole(str, Enum):
    """
    User role enumeration for authorization.

    - AccountManager: Standard user with access to their assigned accounts
    - Admin: Internal admin with elevated privileges (Palona staff)
    """

    AccountManager = "AccountManager"
    Admin = "Admin"


@dataclass
class UserContext:
    """
    Represents an authenticated user's session context.

    This context is extracted from JWT tokens by the authentication layer
    and passed through to services for authorization checks and audit logging.

    Attributes:
        username: Cognito username (UUID)
        email: User's email address
        groups: Cognito groups the user belongs to
        display_name: User's display name
        role: User's role (Admin or AccountManager)
    """

    username: str
    email: str
    groups: List[str]
    display_name: str
    role: UserRole
