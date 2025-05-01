from typing import List

from pydantic import BaseModel


class UserInfo(BaseModel):
    """User information model for admin users"""

    email: str
    name: str


class ListUsersResponse(BaseModel):
    """Response model for listing admin users"""

    users: List[UserInfo]


class CreateUserRequest(BaseModel):
    """Request model for creating a new admin user"""

    email: str
    name: str
