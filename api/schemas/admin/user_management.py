from typing import List

from pydantic import BaseModel


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


class UpdateUserAccountNamesRequest(BaseModel):
    """Request model for updating user's account names"""

    account_names: List[str]


class UserAccountNamesResponse(BaseModel):
    """Response model for getting user's account names"""

    email: str
    account_names: List[str]
