from enum import Enum

from pydantic import BaseModel, Field


class BackdoorToolPrompt(str, Enum):
    ORDER_ITEM_PROMPT = "order_item_prompt"
    SYSTEM_PROMPT = "system_prompt"
    USER_PROMPT = "user_prompt"


class OrderType(str, Enum):
    UNDEFINED = "Undefined"
    DINE_IN = "DineIn"
    TAKE_OUT = "TakeOut"
    DELIVERY = "Delivery"


class PaymentType(str, Enum):
    PAY_IN_STORE = "PayInStore"
    PAYMENT_LINK = "PaymentLink"


class DeliveryAddress(BaseModel):
    model_config = {"populate_by_name": True}

    address: str = Field(description="Street address")
    extended_address: str = Field(
        description="Extended address (if applicable)",
        default="",
        alias="extendedAddress",
    )
    city: str = Field(description="City name")
    state: str = Field(
        description="Two-letter US state abbreviation (e.g., 'CA', 'NY', 'TX')"
    )
    zip: str = Field(description="ZIP code")
    lat: float = Field(description="Latitude", default=0)
    lng: float = Field(description="Longitude", default=0)
    instruction: str = Field(
        description="Special instructions for the delivery address", default=""
    )
    type_id: int = Field(default=1, alias="typeId")
    extra_field_1: str = Field(
        description="Extra field 1", default="", alias="extraField1"
    )
    extra_field_2: str = Field(
        description="Extra field 2", default="", alias="extraField2"
    )
    zone_id: int = Field(default=0, alias="zoneId")


class ClientCustomerInfo(BaseModel):
    name: str = Field(description="Customer first name, non-empty, required")
    lastname: str = Field(
        description="Customer last name (optional), if not provided, use 'via Palona' as the last name",
        default="via Palona",
    )
    phone: str = Field(
        description="Customer phone number in format (123) 456-7890, non-empty, required"
    )
    email: str = Field(description="Customer email address, non-empty, required")


class ClientModifier(BaseModel):
    model_config = {"populate_by_name": True}

    id: int = Field(description="Modifier ID, required")
    is_default: bool = Field(
        description="Whether this is a default modifier, required",
        alias="isDefault",
    )
    price: float = Field(description="Modifier price", default=0.0)
    weight_id: int = Field(
        description="Weight ID for the modifier, set to 0 if not provided",
        default=0,
        alias="weightId",
    )


class ClientGroup(BaseModel):
    model_config = {"populate_by_name": True}

    item_id: int = Field(description="Item ID, required", alias="itemId")
    size_id: int = Field(description="Size ID, required", alias="sizeId")
    quantity: int = Field(
        description="Item quantity, required, range [1..1000]", ge=1, le=1000
    )
    comment: str | None = Field(
        description="Special instructions or comments, optional, max 250 characters",
        default=None,
        max_length=250,
    )
    price: float = Field(description="Item price", default=0.0)
    modifiers: list[ClientModifier] = Field(
        description="List of modifiers for this item. Only populate if the customer explicitly requested modifications to the item. Leave as empty list if no modifications were specified.",
        default_factory=list,
    )


class ClientItem(BaseModel):
    group: list[ClientGroup] = Field(description="List of item groups, required")


class OrderRequestBase(BaseModel):
    """Base order request without delivery address (used for LLM extraction)"""

    model_config = {"populate_by_name": True}

    order_type: OrderType = Field(
        description=f"Type of order. Options: {', '.join([e.value for e in OrderType])}",
        alias="OrderType",
    )
    payment_type: PaymentType = Field(
        description=f"Payment type. Options: {', '.join([e.value for e in PaymentType])}",
        default=PaymentType.PAYMENT_LINK,
        alias="paymentType",
    )
    promise_date_time: str | None = Field(
        description="Promise date and time in ISO date-time format (only if customer requests scheduled/future order)",
        default=None,
        alias="promiseDateTime",
    )
    customer: ClientCustomerInfo = Field(description="Customer information, required")
    items: list[ClientItem] = Field(description="List of order items, required")
    order_comment: str = Field(
        description="Order comment, optional, max 500 characters",
        default="(via PalonaAI)",
        max_length=500,
        alias="orderComment",
    )


class ValidateOrderRequest(OrderRequestBase):
    """Complete order request with delivery address (used for API calls)"""

    store_id: str = Field(description="Store ID, non-empty, required", alias="storeId")
    delivery_address: DeliveryAddress | None = Field(
        description="Delivery address (required for delivery orders), optional",
        default=None,
        alias="deliveryAddress",
    )


class ValidateOrderResponse(BaseModel):
    model_config = {"populate_by_name": True}

    key: str | None = Field(description="Order key/GUID", default=None)
    is_payment_required: bool = Field(
        description="Whether payment is required",
        alias="isPaymentRequired",
        default=False,
    )
    sub_total: float = Field(
        description="Order subtotal", alias="subTotal", default=0.0
    )
    total: float = Field(description="Order total", default=0.0)
    discount: float = Field(description="Total discount amount", default=0.0)
    tax_amount: float = Field(description="Tax amount", alias="taxAmount", default=0.0)
    service_charge: float = Field(
        description="Service charge", alias="serviceCharge", default=0.0
    )
    delivery_charge: float = Field(
        description="Delivery charge", alias="deliveryCharge", default=0.0
    )
    payment_url: str | None = Field(
        description="Payment URL if payment link is required",
        default=None,
        alias="paymentUrl",
    )


class PaymentDetails(BaseModel):
    model_config = {"populate_by_name": True}

    sub_total: float = Field(description="Subtotal amount")
    tax: float = Field(description="Tax amount")
    total: float = Field(description="Total amount")


class ProcessOrderRequest(BaseModel):
    model_config = {"populate_by_name": True}

    store_id: str = Field(description="Store ID, non-empty, required", alias="storeId")
    order_type: OrderType = Field(
        description=f"Type of order. Options: {', '.join([e.value for e in OrderType])}",
        alias="OrderType",
    )
    payment_type: PaymentType = Field(
        description=f"Payment type. Options: {', '.join([e.value for e in PaymentType])}",
        default=PaymentType.PAYMENT_LINK,
        alias="paymentType",
    )
    guid: str = Field(description="Order GUID from validate order response, required")
    promise_date_time: str | None = Field(
        description="Promise date and time in ISO date-time format, optional",
        default=None,
        alias="promiseDateTime",
    )
    customer: ClientCustomerInfo = Field(description="Customer information, required")
    delivery_address: DeliveryAddress | None = Field(
        description="Delivery address (required for delivery orders), optional",
        default=None,
        alias="deliveryAddress",
    )
    items: list[ClientItem] = Field(description="List of order items, required")
    payment_details: PaymentDetails = Field(
        description="Payment details including subtotal, tax, and total"
    )
    order_comment: str = Field(
        description="Order comment, optional, max 500 characters",
        default="(via PalonaAI)",
        max_length=500,
        alias="orderComment",
    )


class ProcessOrderResponse(BaseModel):
    model_config = {"populate_by_name": True}

    success: int = Field(description="Success status (0 or 1)")
    order_id: int = Field(description="Processed order ID", default=0, alias="orderID")
    order_no: int = Field(description="Order number", default=0, alias="orderNo")
    order_date: str | None = Field(
        description="Order date in ISO format",
        default=None,
        alias="orderDate",
    )
    customer_id: int = Field(description="Customer ID", default=0, alias="customerID")
    address_id: int = Field(description="Address ID", default=0, alias="addressID")
    profile_id: int = Field(description="Profile ID", default=0, alias="profileID")
    msg: str | None = Field(description="Response message", default=None)
    prof_updated: int = Field(
        description="Profile updated flag", default=0, alias="profUpdated"
    )
    payment_url: str | None = Field(
        description="Payment URL if applicable",
        default=None,
        alias="paymentUrl",
    )
