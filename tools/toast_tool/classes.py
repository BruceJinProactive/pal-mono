from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema


######### TOAST API CLASS START ############
class ToastAccessToken(BaseModel):
    """
    This class represents the response from the Toast Authentication API.
    It contains the access token used to authenticate subsequent API calls.

    Based on the Toast API documentation, this token is obtained by sending a POST request to:
    https://[toast-api-hostname]/authentication/v1/authentication/login
    """

    # The access token is the JWT token string (header.payload.signature)
    # The decoded payload containing claims like exp, iat, aud, etc.
    access_token: str
    expires_in: int
    token_type: str
    scope: str | None = None
    id_token: str | None = None
    refresh_token: str | None = None
    # UTC time
    expires_at: datetime

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
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(seconds=token_data.get("expiresIn") - 60)
            ),
        )

    def get_token_header_value(self) -> str:
        """Returns the properly formatted token for use in headers"""
        return f"{self.token_type} {self.access_token}"


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
    guid: str = Field(description="The GUID of the item", min_length=1)


class MenuItem(ItemBase):
    pass


class ItemGroup(ItemBase):
    pass


class OptionGroup(ItemBase):
    pass


class SelectionType(str, Enum):
    NONE = "NONE"
    SPECIAL_REQUEST = "SPECIAL_REQUEST"


class Modifier(BaseModel):
    optionGroup: Optional[OptionGroup] = Field(
        description="The option group GUID of the modifier associated with the item. Find the correct group ID corresponding to the item ID.",
        default=None,
    )
    item: Optional[MenuItem] = Field(
        description="The item ID associated with the modifier", default=None
    )
    quantity: Optional[int] = Field(
        description="The quantity of the modifier. If the modifier is a special request, set the quantity to None.",
        gt=0,
        default=None,
    )
    modifiers: List["Modifier"] = Field(
        default_factory=list,
        description="Nested modifiers for this modifier. Always include as empty array [].",
    )
    displayName: Optional[str] = Field(
        description="The display name of the modifier. If there is a special request, include the special request in this field. If there is no special request, set the field to None.",
        default=None,
    )
    selectionType: SelectionType = Field(
        description="The type of selection for the modifier. If there is a special request, set the field to SPECIAL_REQUEST and include the special request in the `displayName` field. If there is no special request, set the field to NONE.",
        default=SelectionType.NONE,
    )


class OrderItemFulfillmentStatus(str, Enum):
    NEW = "NEW"
    HOLD = "HOLD"
    SENT = "SENT"
    READY = "READY"


class ItemSelection(BaseModel):
    itemGroup: ItemGroup = Field(
        description="The item group associated with the item selection."
    )
    item: ItemBase = Field(description="The item selected")
    quantity: int = Field(description="The quantity of the item selection.", gt=0)
    modifiers: Optional[List[Modifier]] = Field(
        default_factory=list,
        description=(
            "The modifiers associated with the item selection. "
            "Find the correct group ID and corresponding item ID. They cannot be Null. "
            "Do not add a modifier if the item has no modifiers. "
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
    phone: str
    email: str
    lastName: str = Field(default="(via PalonaAI)")


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

    class Config:
        # Allow extra fields in case API response includes additional data
        extra = "allow"


class ToastDeliveryInfo(BaseModel):
    address1: str = Field(description="Street address")
    address2: Optional[str] = Field(description="Extended address (if applicable)")
    city: str
    state: str
    notes: str = Field(
        description="Special notes that the user has provided, including but not limited to any adjustments to the menu items ordered. Notes must be between 2 and 100 characters in length."
    )
    zipCode: str


class ToastCurbsidePickupInfo(BaseModel):
    notes: str = Field(
        description="Special notes that the user has provided, including but not limited to any adjustments to the menu items ordered. Do not include transport description in this field. Notes must be between 2 and 100 characters in length."
    )
    transportDescription: str = Field(
        description="The description of the transport method used for curbside pickup. If the order type is not curbside pickup, set the field to 'None'.",
        default="No transport",
    )


# TODO: Implement input and output Order classes
class OrderInput(BaseModel):
    checks: List[Check] = Field(
        description="List of checks in the order. This must NOT be a dictionary."
    )
    diningOption: DiningOption
    deliveryInfo: Optional[ToastDeliveryInfo] = None
    curbsidePickupInfo: Optional[ToastCurbsidePickupInfo] = None
    externalId: Optional[str] = Field(
        None,
        description="An optional external identifier for the order, used to GET and check if the order exists.",
    )


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


class InventoryItem(BaseModel):
    guid: str = Field(description="Unique identifier for the menu item")
    itemGuidValidityId: str = Field(description="Validity ID for the item GUID")
    status: str = Field(
        description="Stock status (e.g., IN_STOCK, OUT_OF_STOCK, QUANTITY)"
    )
    quantity: int = Field(description="Available quantity of the item")
    multiLocationId: str = Field(description="Multi-location identifier")
    versionId: str = Field(description="Version identifier for the item")


class InventoryResponse(BaseModel):
    items: List[InventoryItem] = Field(description="List of inventory items")


class LastOrderConfiguration(str, Enum):
    """Enum for last order configuration options"""

    UNTIL_CLOSING_TIME = "UNTIL_CLOSING_TIME"
    UNTIL_PREPTIME_CUTOFF = "UNTIL_PREPTIME_CUTOFF"


class OverrideTimeRanges(BaseModel):
    """Time range when the override starts and ends"""

    startTime: Optional[str] = Field(None, description="Start time of the override")
    endTime: Optional[str] = Field(None, description="End time of the override")


class DateOverride(BaseModel):
    """Override object that contains information about planned overrides"""

    businessDate: int = Field(
        description="The day when the override applies in YYYYMMDD format"
    )
    description: Optional[str] = Field(
        None, description="Description of the planned override"
    )
    diningOptionBehavior: List[DiningBehavior] = Field(
        description="The diningOptionBehavior the override applies to (TAKE_OUT or DELIVERY or both)"
    )
    timeRanges: List[OverrideTimeRanges] = Field(
        description="The time range when the override starts and ends"
    )


class TimeRange(BaseModel):
    """Time range with start and end times"""

    start: str = Field(description="Start time")
    end: str = Field(description="End time")


class DayPeriod(BaseModel):
    """Day period object that contains information about specific day and time range"""

    day: str = Field(description="Day of the week")
    timeRanges: List[TimeRange] = Field(description="Array of time ranges for this day")


class ServicePeriod(BaseModel):
    """Service period object that contains information about days and times when restaurant accepts online orders"""

    dayPeriods: List[DayPeriod] = Field(
        description="Array of DayPeriods objects with information about specific day and time range"
    )
    diningOptionBehavior: DiningBehavior = Field(
        description="The dining option behavior the online ordering schedule is returned for (TAKE_OUT or DELIVERY)"
    )


class OrderingScheduleResponse(BaseModel):
    """Response from the Toast ordering schedule API"""

    lastOrderConfiguration: LastOrderConfiguration = Field(
        description="Allows guests to place online orders until closing time or closing time minus prep time"
    )
    overrides: List[DateOverride] = Field(
        description="Array of override objects that contain information about planned overrides"
    )
    scheduledOrderMaxDays: int = Field(
        description="Number of days an online order can be placed into the future"
    )
    servicePeriods: List[ServicePeriod] = Field(
        description="Array of servicePeriods objects with information about days and times when restaurant accepts online orders"
    )
    timeZoneId: str = Field(description="The time zone of the restaurant location")


class PaymentIntentRequest(BaseModel):
    """Request model for creating a Toast payment intent."""

    amount: int = Field(description="Payment amount in cents (e.g., 1000 = $10.00)")
    amountDetails: dict = Field(
        default_factory=lambda: {"tip": 0},
        description="Breakdown of amount details including tip",
    )
    currency: str = Field(default="USD", description="Currency code")
    externalReferenceId: str = Field(
        description="Merchant's unique identifier for this payment intent"
    )
    captureMethod: str = Field(
        default="MANUAL", description="Payment capture method (MANUAL or AUTOMATIC)"
    )


class PaymentIntentResponse(BaseModel):
    """Response model from Toast payment intent creation."""

    id: str = Field(description="Toast payment intent ID")
    sessionSecret: str = Field(
        description="Session secret needed to initialize the checkout iframe"
    )
    amount: int = Field(description="Payment amount in cents")
    currency: str = Field(description="Currency code", default="USD")
    externalReferenceId: str = Field(
        description="Merchant's unique identifier for this payment intent"
    )
    status: Optional[str] = Field(None, description="Payment intent status")

    class Config:
        extra = "allow"


class ToastPayment(BaseModel):
    """
    Toast payment object for creating payments.
    Based on Toast API payment schema with required fields and optional externalId.
    """

    amount: float = Field(description="The amount of this payment, excluding tips")
    entityType: Optional[str] = Field(
        None, description="The type of object this is (response-only)"
    )
    guid: str = Field(description="The GUID maintained by the Toast platform")
    tipAmount: float = Field(description="The amount tipped on this payment")
    type: str = Field(description="The payment method (e.g., CREDIT, OTHER)")
    externalId: Optional[str] = Field(
        None,
        description="External identifier string that is prefixed by the naming authority",
    )

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


# Rebuild models to resolve forward references
OptionGroup.model_rebuild()
Modifier.model_rebuild()
