from pydantic import BaseModel


class User(BaseModel):
    """User Model"""

    id: str
    email: str
    display_name: str
    account_name: str


class SignUpRequest(BaseModel):
    """Sign Up Request"""

    account_name: str
    name: str
    email: str
    password: str


class SignUpResponse(BaseModel):
    """Sign Up Response"""

    AccessToken: str
    RefreshToken: str
    ExpiresIn: int
    IdToken: str
