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

    guid: str = Field(description="Unique identifier for the restaurant")
    general: dict = Field(description="General information about the restaurant")
    urls: dict = Field(description="URLs related to the restaurant")
    location: dict = Field(description="Location details of the restaurant")
    schedules: dict = Field(description="Operating schedules of the restaurant")
    delivery: dict = Field(description="Delivery configuration details")
    onlineOrdering: dict = Field(description="Online ordering configuration")
    prepTimes: dict = Field(description="Preparation time configurations")


class OrderingStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class OrderingStatusReasonKey(str, Enum):
    AVAILABILITY_ONLINE = "AVAILABILITY_ONLINE"
    AVAILABILITY_OFFLINE = "AVAILABILITY_OFFLINE"


class RestaurantOrderingStatus(BaseModel):
    restaurantGuid: str = Field(description="GUID of the restaurant")
    status: OrderingStatus = Field(
        description="Current ordering status (ONLINE or OFFLINE)"
    )
    reasonKey: OrderingStatusReasonKey = Field(
        description="Key indicating the reason for the status"
    )
    reason: str = Field(description="Detailed reason for the ordering status")

    class Config:
        use_enum_values = True


class DiningBehavior(str, Enum):
    DINE_IN = "DINE_IN"
    TAKE_OUT = "TAKE_OUT"
    DELIVERY = "DELIVERY"


class DiningOption(BaseModel):
    guid: str = Field(
        description="Unique guid identifier for the dining option. This attribute IS NOT an English name."
    )
    curbside: SkipJsonSchema[Optional[bool]] = Field(
        None, description="Indicates if curbside pickup is available"
    )
    behavior: SkipJsonSchema[Optional[DiningBehavior]] = Field(
        None, description="Dining behavior (e.g., DINE_IN, TAKE_OUT, DELIVERY)"
    )
    name: SkipJsonSchema[Optional[str]] = Field(
        None, description="Name of the dining option"
    )
    externalId: SkipJsonSchema[Optional[Any]] = Field(
        None, description="External identifier for the dining option"
    )

    class Config:
        use_enum_values = True


class ItemBase(BaseModel):
    guid: str = Field(description="The GUID of the item")


class OptionGroup(ItemBase):
    pass


class MenuItem(ItemBase):
    pass


class ItemGroup(ItemBase):
    pass


class Modifier(BaseModel):
    optionGroup: OptionGroup = Field(
        description="The option group GUID of the modifier associated with the item. Find the correct group ID corresponding to the item ID."
    )
    item: MenuItem = Field(description="The item ID associated with the modifier")
    quantity: int = Field(description="The quantity of the modifier")


class OrderItemFulfillmentStatus(str, Enum):
    NEW = "NEW"
    HOLD = "HOLD"
    SENT = "SENT"
    READY = "READY"


class ItemSelection(BaseModel):
    itemGroup: ItemGroup = Field(
        description="The item group associated with the item selection"
    )
    item: ItemBase = Field(description="The item selected")
    quantity: int = Field(description="The quantity of the item selection", gt=0)
    modifiers: Optional[List[Modifier]] = Field(
        default_factory=list,
        description=(
            "The modifiers associated with the item selection. "
            "Find the correct group ID and corresponding item ID. They cannot be Null."
        ),
    )
    fulfillmentStatus: SkipJsonSchema[Optional[OrderItemFulfillmentStatus]] = Field(
        None, description="The fulfillment status of the item selection"
    )


# Payment type must either be "CREDIT" or "OTHER"
class PaymentType(str, Enum):
    CREDIT = "CREDIT"
    OTHER = "OTHER"


class Payment(BaseModel):
    guid: str = Field(description="The GUID of the payment")
    amount: float = Field(description="The amount of the payment")
    tipAmount: float = Field(description="The tip amount of the payment", default=0.0)
    type: PaymentType = Field(
        description="The type of payment, either credit or other",
        default=PaymentType.CREDIT,
    )

    class Config:
        use_enum_values = True


class Customer(BaseModel):
    firstName: str
    lastName: str
    phone: str
    email: str


class Price(BaseModel):
    amount: SkipJsonSchema[Optional[float]] = None  # response only
    taxAmount: SkipJsonSchema[Optional[float]] = None  # response only
    totalAmount: SkipJsonSchema[Optional[float]] = None  # response only


class Check(Price):
    customer: Customer
    selections: List[ItemSelection] = Field(
        description="List of item selections in the check. This must NOT be a dictionary."
    )
    payments: Optional[List[Payment]] = None


# TODO: Implement input and output Order classes
class OrderInput(BaseModel):
    checks: List[Check]
    diningOption: DiningOption


class Order(OrderInput):
    guid: Optional[str] = None  # Not required when submitting an order
    requiredPrepTime: Optional[str] = None  # Not required when submitting an order
    openedDate: Optional[str] = None  # Not required when submitting an order
    entityType: Optional[str] = None  # Not required when submitting an order
    estimatedFulfillmentDate: SkipJsonSchema[Optional[str]] = None  # response only
    businessDate: SkipJsonSchema[Optional[int]] = None  # YYYYMMDD, response only

    class Config:
        # Allow extra fields in case API response includes additional data
        extra = "allow"


########### TOAST API CLASS END ############


class SubQueries(BaseModel):
    queries: list[str] = Field(
        description=(
            "Decompose the chat history into individual order items. For example,"
            "If the chat history is 'I would like to order a pizza with extra cheese "
            "and pickles, burger, and salad, for takeout.' The return would be ['pizza', "
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
