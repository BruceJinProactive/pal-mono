from pydantic import BaseModel


class AccessToken(BaseModel):
    access_token: str
    expires_in: int
    token_type: str
    scope: str

    def get_token_header_value(self) -> str:
        return f"{self.token_type} {self.access_token}"
