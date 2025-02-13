from decimal import Decimal
from enum import StrEnum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema


class AdoraSavedOrderResult(BaseModel):
    """
    This is the shape of the response from the Adora API at the save_validate_order step.
    """

    success: int | None = None
    orderID: int | None = (
        None  # this is the important value -- you need this to checkout the order using /textPaymentLink
    )
    orderNo: int | None = None
    customerID: int | None = None
    addressID: int | None = None
    profileID: int | None = None
    msg: str = ""
    profUpdated: int | None = None

    class Config:
        # Allow extra fields in case API response includes additional data
        extra = "allow"


class AdoraDeliveryAddress(BaseModel):
    """
    This is the shape of a delivery address that is sent to the Adora API at the place_order step.
    """

    address: str
    extendedAddress: str = (
        ""  # Required by Adora API, used for Apt/Suite number, can be empty string
    )
    city: str
    state: str
    zip: str
    lat: float  # this is calculated internally using an address to lat long API
    lng: float  # this is calculated internally using an address to lat long API
    instruction: str = ""  # Required by Adora API but can be empty string
    typeId: int  # this is calculated from address validation API
    extraField1: str = (
        ""  # Required by Adora API but not sure its use and can be empty string
    )
    extraField2: str = (
        ""  # Required by Adora API but not sure its use and can be empty string
    )


class AdoraAccessToken(BaseModel):
    """
    This is the response shape from the Adora API when you request an access token.
    This access token is used to authenticate subsequent API calls.
    """

    access_token: str
    expires_in: int
    token_type: str
    scope: str

    def get_token_header_value(self) -> str:
        return f"{self.token_type} {self.access_token}"


class AdoraHubResponse(BaseModel):
    """
    This is the response shape from the Adora API when you make a request to the OrderHub.
    """

    status: int
    reason: str
    decoded_body: str


class AdoraOrderItem(BaseModel):
    """
    This is the shape of an order item that is sent to the Adora API at the add_to_order step.
    """

    def __init__(
        self,
        item_id: int,
        size_id: int,
        quantity: int,
        comment: str,
        price: float,
        modifiers: list[str],
    ):
        self.itemId = item_id
        self.sizeId = size_id
        self.quantity = quantity
        self.comment = comment
        self.price = price

        self.taxes = [{"id": 0, "taxAmount": 0}]

        self.modifiers = modifiers

    def __str__(self):
        return f"quantity: {self.quantity} sizeId: {self.sizeId} itemId: {self.itemId} with {self.modifiers} for {str(self.price)}"

    def to_dict(self):
        """
        Returns a dictionary containing only the attributes of AdoraOrderItem.
        Use this to generate the JSON payload to send to the Adora API.
        """
        return {
            "itemId": self.itemId,
            "sizeId": self.sizeId,
            "quantity": self.quantity,
            "comment": self.comment,
            "price": self.price,
            "taxes": self.taxes,
            "modifiers": self.modifiers,
        }


class AdoraOrderType(StrEnum):
    Delivery = "Delivery"
    TakeOut = "TakeOut"


class AdoraOrderCalculationResult(BaseModel):
    """
    This is the response shape from the Adora API when you request an order calculation at the validate_order step.
    """

    # Key is used on the Adora Pos API side in subsequent API calls to refer to the order.
    key: str | None = None
    isPaymentRequired: bool | None = None
    subTotal: Decimal | None = None
    total: Decimal | None = None
    discount: Decimal | None = None
    taxAmount: Decimal | None = None
    serviceCharge: Decimal | None = None
    deliveryCharge: Decimal | None = None

    class Config:
        # Allow extra fields in case API response includes additional data
        extra = "allow"


################## LLM DATA MODEL TEMPLATES ##################
# Used for order item extraction from chat history
# `SkipJsonSchema` is used to skip fields for generation by Instructor-ai


# For now, we will set manual customer information
class CustomerInfo(BaseModel):
    first_name: Optional[str] = Field(
        description="Customer's first name", serialization_alias="name"
    )
    last_name: Optional[str] = Field(
        description="Customer's last name",
        serialization_alias="lastname",
    )
    phone_number: Optional[str] = Field(
        description="Customer's phone number",
        pattern=r"^\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})$",
        serialization_alias="phone",
    )
    email: Optional[str] = Field(description="Customer's email address")


# US Address Data Model
class DeliveryAddress(BaseModel):
    address: str = Field(description="Street address")
    city: str = Field(description="City name")
    state: str = Field(description="State abbreviation")
    zip: str = Field(description="ZIP code")
    lat: float = Field(description="Latitude")
    lng: float = Field(description="Longitude")
    type_id: SkipJsonSchema[int] = Field(default=1, serialization_alias="typeId")


class Modifier(BaseModel):
    modifier_id: int = Field(
        description="Modifier ID is the valued defined in `modifier_id` for the corresponding modifier name",
        serialization_alias="id",
    )
    modifier_name: str = Field(
        description="Modifier name like `Extra Cheese`, `Green Onion`, etc.",
        exclude=True,
    )
    is_default: SkipJsonSchema[bool] = Field(
        default=True, serialization_alias="isDefault"
    )
    price: SkipJsonSchema[float] = Field(default=0.0)
    quantity: int = Field(
        description="Quantity of modifier requested by the customer", exclude=True
    )
    weight_id: SkipJsonSchema[int] = Field(default=0, serialization_alias="weightId")
    group_id: SkipJsonSchema[int] = Field(default=0, serialization_alias="groupId")


class OrderItem(BaseModel):
    item_id: int = Field(
        description="Item ID is the valued defined in `item_id` for the corresponding item name",
        serialization_alias="itemId",
    )
    # TODO: We need to remove default assumption and prompt eng the model to ask. For now this is okay.
    size_id: int = Field(
        description="The size ID of an order item defined as `size_id`. If an item has only 'One Size' the `size_id` should be 0. By default, assume 1.",
        serialization_alias="sizeId",
    )
    item_name: str = Field(description="Item name", exclude=True)
    quantity: int = Field(description="Item quantity ordered by the customer")
    price: SkipJsonSchema[float] = Field(default=0.0, description="Price per unit")
    taxes: SkipJsonSchema[List[Dict[str, int | float]]] = Field(
        default=[{"id": 0, "taxAmount": 0.0}]
    )
    modifiers: List[Modifier] = Field(description="List of order item modifications")


class Order(BaseModel):
    store_id: SkipJsonSchema[Optional[str]] = Field(
        default=None, serialization_alias="storeId"
    )
    order_type: str = Field(
        default="TakeOut",
        description="Order type is either `TakeOut` or `Delivery`. By default, use `TakeOut`.",
        serialization_alias="OrderType",
    )
    order_subtype: SkipJsonSchema[str] = Field(
        default="PhoneOrder", serialization_alias="OrderTypeSubType"
    )
    # TODO: optional customer info -> we should prompt them in the future if this is missing
    customer: Optional[CustomerInfo] = Field(description="Customer information")
    # `order_items`` is what the llm will fill out
    order_items: List[OrderItem] = Field(
        description="List of order items", exclude=True
    )
    # `items` is the format and field that we actually submit to Adora API. This is their required format.
    items: SkipJsonSchema[List[Dict[str, List[OrderItem]]]] = Field(
        default=[{"group": []}]
    )
    delivery_address: Optional[DeliveryAddress] = Field(
        description="Delivery address", serialization_alias="deliveryAddress"
    )
    paid: SkipJsonSchema[bool] = Field(default=False)
    order_comment: Optional[str] = Field(
        description="Special ordering instructions requested by the customer. Empty if no special requests are made.",
        serialization_alias="orderComment",
    )
