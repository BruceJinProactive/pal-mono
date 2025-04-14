from datetime import datetime, timedelta
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


######### TOAST API CLASS START ############
class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class ToastHubResponse(BaseModel):
    """Class to handle Toast API response data"""

    status: int
    reason: str
    decoded_body: str


class ToastAccessToken(BaseModel):
    """
    This class represents the response from the Toast Authentication API.
    It contains the access token used to authenticate subsequent API calls.

    Based on the Toast API documentation, this token is obtained by sending a POST request to:
    https://[toast-api-hostname]/authentication/v1/authentication/login
    """

    access_token: str
    expires_in: int
    token_type: str
    scope: str | None = None
    id_token: str | None = None
    refresh_token: str | None = None
    created_at: datetime = datetime.now()

    @classmethod
    def from_toast_response(cls, response_data: dict) -> "ToastAccessToken":
        """
        Creates a ToastAccessToken from the raw API response.

        Args:
            response_data: The JSON response from Toast authentication API

        Returns:
            ToastAccessToken instance
        """
        token_data = response_data.get("token", {})

        return cls(
            access_token=token_data.get("accessToken", ""),
            expires_in=token_data.get("expiresIn", 0),
            token_type=token_data.get("tokenType", "Bearer"),
            scope=token_data.get("scope"),
            id_token=token_data.get("idToken"),
            refresh_token=token_data.get("refreshToken"),
        )

    def is_expired(self) -> bool:
        """
        Checks if the token is expired.

        Returns:
            bool: True if the token is expired, False otherwise
        """
        expiration_time = self.created_at + timedelta(seconds=self.expires_in)
        return datetime.now() > expiration_time

    def get_token_header_value(self) -> str:
        """Returns the properly formatted token for use in headers"""
        return f"{self.token_type} {self.access_token}"

    def is_valid(self) -> bool:
        """Basic check to see if token has required fields"""
        return bool(self.access_token and self.token_type)


class RestaurantInfo(BaseModel):
    """
    RestaurantInfo object returned from the Toast API.
    """

    guid: str
    general: dict
    urls: dict
    location: dict
    schedules: dict
    delivery: dict
    online_ordering: dict
    prep_times: dict


class OrderingStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class OrderingStatusReasonKey(str, Enum):
    AVAILABILITY_ONLINE = "AVAILABILITY_ONLINE"
    AVAILABILITY_OFFLINE = "AVAILABILITY_OFFLINE"


class RestaurantOrderingStatus(BaseModel):

    restaurant_guid: str
    status: OrderingStatus
    reason_key: OrderingStatusReasonKey
    reason: str


class DiningBehavior(str, Enum):
    DINE_IN = "DINE_IN"
    TAKE_OUT = "TAKE_OUT"
    DELIVERY = "DELIVERY"


class DiningOption(BaseModel):
    guid: str
    entityType: str = "DiningOption"
    curbside: Optional[bool]
    behavior: Optional[DiningBehavior]
    name: Optional[str]
    external_id: Optional[Any]


class ItemBase(BaseModel):
    guid: str


class OptionGroup(ItemBase):
    pass


class MenuItem(ItemBase):
    entityType: str = "MenuItem"


class ItemGroup(ItemBase):
    pass


class Modifier(BaseModel):
    entityType: str = "MenuItemSelection"
    optionGroup: OptionGroup
    item: MenuItem
    quantity: int


class ItemSelection(BaseModel):
    entityType: str = "MenuItemSelection"
    itemGroup: ItemGroup
    item: ItemBase
    quantity: int
    modifiers: Optional[List[Modifier]] = []


class Selections(BaseModel):
    selections: List[ItemSelection]


# Payment type must either be "CREDIT" or "OTHER"
class PaymentType(str, Enum):
    CREDIT = "CREDIT"
    OTHER = "OTHER"


class Payment(BaseModel):
    guid: str
    amount: float
    tipAmount: float = 0.0
    type: PaymentType


class Customer(BaseModel):
    firstName: str
    lastName: str
    phone: str
    email: str


class Check(BaseModel):
    customer: Customer
    payments: List[Payment]
    selections: List[Selections]
    amount: Optional[float]
    taxAmount: Optional[float]
    totalAmount: Optional[float]


# TODO: Implement input and output Order classes
class Order(BaseModel):
    checks: List[Check]
    diningOption: DiningOption
    guid: Optional[str]
    estimatedFulfillmentDate: Optional[str]


########### TOAST API CLASS END ############


class SubQueries(BaseModel):
    queries: list[str] = Field(
        description=(
            "Decompose the chat history into individual order items. For example,"
            "If the chat history is 'I would like to order a pizza with extra cheese "
            "and pickles, burger, and salad.' The return would be ['pizza', "
            "'burger', 'salad']\n\n"
            "DO NOT include modifications (e.g. extra cheese, pickles)."
        ),
    )
