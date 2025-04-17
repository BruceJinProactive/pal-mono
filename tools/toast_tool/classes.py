from datetime import datetime, timedelta
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema


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
        """Basic check to see if token has required fields and is not expired"""

        return bool(self.access_token and self.token_type and not self.is_expired())


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
    onlineOrdering: dict
    prepTimes: dict


class OrderingStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class OrderingStatusReasonKey(str, Enum):
    AVAILABILITY_ONLINE = "AVAILABILITY_ONLINE"
    AVAILABILITY_OFFLINE = "AVAILABILITY_OFFLINE"


class RestaurantOrderingStatus(BaseModel):

    restaurantGuid: str
    status: OrderingStatus
    reasonKey: OrderingStatusReasonKey
    reason: str


class DiningBehavior(str, Enum):
    DINE_IN = "DINE_IN"
    TAKE_OUT = "TAKE_OUT"
    DELIVERY = "DELIVERY"


class DiningOption(BaseModel):
    guid: str
    entityType: str = "DiningOption"
    curbside: Optional[bool] = None
    behavior: Optional[DiningBehavior] = None
    name: Optional[str] = None
    externalId: Optional[Any] = None


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
    selections: List[ItemSelection]
    payments: Optional[List[Payment]] = None
    amount: Optional[float] = None
    taxAmount: Optional[float] = None
    totalAmount: Optional[float] = None


# TODO: Implement input and output Order classes
class Order(BaseModel):
    checks: List[Check]
    diningOption: DiningOption
    guid: Optional[str] = None
    estimatedFulfillmentDate: Optional[str] = None


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


class DeliveryAddress(BaseModel):
    address: str = Field(description="Street address")
    extended_address: str = Field(
        description="Extended address (if applicable)",
        default="",
        serialization_alias="extendedAddress",
    )
    city: str = Field(description="City name")
    state: str = Field(description="State abbreviation")
    zip: str = Field(description="ZIP code")
    lat: float = Field(description="Latitude", default=0)
    lng: float = Field(description="Longitude", default=0)
    instruction: str = Field(
        description="Special instructions for the delivery address"
    )
    type_id: SkipJsonSchema[int] = Field(default=1, serialization_alias="typeId")
    extra_field_1: SkipJsonSchema[str] = Field(
        description="Extra field 1", default="", serialization_alias="extraField1"
    )
    extra_field_2: SkipJsonSchema[str] = Field(
        description="Extra field 2", default="", serialization_alias="extraField2"
    )
    zone_id: SkipJsonSchema[int] = Field(default=0, serialization_alias="zoneId")
