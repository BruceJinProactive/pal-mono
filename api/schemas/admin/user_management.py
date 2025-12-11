from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    """User information model for admin users"""

    email: str
    name: str
    status: str | None = None


class ListUsersResponse(BaseModel):
    """Response model for listing admin users"""

    users: List[UserInfo]


class CreateUserRequest(BaseModel):
    """Request model for creating a new admin user"""

    email: str
    name: str


class AssignAccountRequest(BaseModel):
    """Request model for assigning an account to a user"""

    user_id: UUID = Field(..., description="UUID of the user to assign to the account")
    account_name: str = Field(..., description="Name of the account to assign")
    role: str = Field(
        default="viewer",
        description="Role to assign (e.g., 'owner', 'manager', 'viewer')",
    )


class AssignAccountResponse(BaseModel):
    """Response model for account assignment"""

    status: str = Field(..., description="Status of the operation")
    message: str = Field(..., description="Success or error message")
