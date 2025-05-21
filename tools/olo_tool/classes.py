from enum import Enum
from typing import Optional

from pydantic import BaseModel


######### OLO API CLASS START ############
class OloAccessToken(BaseModel):
    access_token: str
    expires_in: Optional[int] = None
    token_type: str = "OloKey"

    def get_token_header_value(self) -> str:
        return f"{self.token_type} {self.access_token}"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class OloHubResponse(BaseModel):
    status: int
    reason: str
    decoded_body: str
