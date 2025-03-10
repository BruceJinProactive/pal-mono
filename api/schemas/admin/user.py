from pydantic import BaseModel


class User(BaseModel):
    """User Model"""

    id: str
    email: str
    display_name: str
