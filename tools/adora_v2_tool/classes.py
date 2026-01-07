from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field


class BackdoorToolPrompt(str, Enum):
    ORDER_ITEM_PROMPT = "order_item_prompt"
    SYSTEM_PROMPT = "system_prompt"
    USER_PROMPT = "user_prompt"


class OrderType(str, Enum):
    TAKE_OUT = "TakeOut"
    DELIVERY = "Delivery"


class PaymentType(str, Enum):
    PAY_IN_STORE = "PayInStore"
    PAYMENT_LINK = "PaymentLink"


class BaseDeliveryAddress(BaseModel):
    """Base delivery address with core required fields for Azure OpenAI strict mode"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    street_number: str = Field(description="Street number (required)")
    street_name: str = Field(description="Street name (required)")
    extended_address: str = Field(
        description="Extended address (ex unit apartment/suite, etc), set to empty string if not provided (required)",
        alias="extendedAddress",
    )
    city: str = Field(description="City name (required)")
    state: str = Field(
        description="Two-letter US state abbreviation (e.g., 'CA', 'NY', 'TX') (required)"
    )
    zip: str = Field(description="ZIP code (required)")

    def __str__(self) -> str:
        """Convert to geocoding-compatible address string"""
        return ", ".join(
            [
                p
                for p in [
                    self.street_number,
                    self.street_name,
                    self.city,
                    self.state,
                    self.zip,
                ]
                if p and p != "N/A"
            ]
            + ["USA"]
        )


class DeliveryAddress(BaseDeliveryAddress):
    """Extended delivery address with optional fields that have defaults"""

    lat: float = Field(description="Latitude, set to 0 if not provided", default=0)
    lng: float = Field(description="Longitude, set to 0 if not provided", default=0)
    instruction: str = Field(
        description="Special instructions for the delivery address, set to empty string if not provided",
        default="",
    )
    type_id: int = Field(
        description="Type ID, set to 1 if not provided", default=1, alias="typeId"
    )
    extra_field_1: str = Field(
        description="Extra field 1, set to empty string if not provided",
        default="",
        alias="extraField1",
    )
    extra_field_2: str = Field(
        description="Extra field 2, set to empty string if not provided",
        default="",
        alias="extraField2",
    )

    @computed_field
    @property
    def address(self) -> str:
        """Computed field that combines street_number and street_name"""
        return f"{self.street_number} {self.street_name}"


class ValidateAddressRequest(BaseModel):
    """Request for address validation API"""

    model_config = ConfigDict(populate_by_name=True)

    store_id: str = Field(description="Store ID", alias="storeId")
    lat: float = Field(description="Latitude")
    lng: float = Field(description="Longitude")
    street_no: str = Field(description="Street number", alias="streetNo")
    street_name: str = Field(description="Street name", alias="streetName")
    unit_apt: str = Field(description="Unit/Apartment", alias="unitApt")
    city: str = Field(description="City")
    state: str = Field(description="State")
    zip: str = Field(description="ZIP code")


class ValidateAddressResponse(BaseModel):
    """Response from address validation API"""

    model_config = ConfigDict(populate_by_name=True)

    charge: float = Field(description="Delivery charge")
    minimum_charge: float = Field(description="Minimum charge", alias="minimumCharge")
    type_id: int = Field(description="Type ID", alias="typeId")
    description: str | None = Field(description="Description", default=None)
    delivery_scheduals: str | None = Field(
        description="Delivery schedules", alias="deliveryScheduals", default=None
    )


class ClientCustomerInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str = Field(description="Customer first name, non-empty, required")
    lastname: str = Field(
        description="Customer last name, required, set to via PalonaAI if not provided"
    )
    phone: str = Field(
        description="Customer phone number in format (123) 456-7890, non-empty, required"
    )
    email: str = Field(
        description="Customer email address, required, set to orderingagent@palona.ai if not provided"
    )


class ClientModifier(BaseModel):
    model_config = {"populate_by_name": True}

    id: int = Field(description="Modifier ID, required")
    is_default: bool = Field(
        description="Whether this is a default modifier, required",
        alias="isDefault",
    )
    price: float = Field(
        description="Modifier price, set to 0.0 if not provided", default=0.0
    )
    weight_id: int = Field(
        description="Weight ID for the modifier, set to 0 if not provided",
        default=0,
        alias="weightId",
    )


class ClientGroup(BaseModel):
    model_config = {"populate_by_name": True}

    item_id: int = Field(
        description="Item ID from the menu context. Required. Must match exactly with the item_id provided in the relevant context for the ordered item, must be an integer and cannot be null.",
        alias="itemId",
    )
    size_id: int = Field(
        description="Size ID from the menu context. Required. Cannot be null. Must match exactly with the size_id from the relevant context, must be an integer and cannot be null.",
        alias="sizeId",
    )
    quantity: int = Field(
        description="Item quantity, required, range [1..1000]", ge=1, le=1000
    )
    comment: str | None = Field(
        description="Special instructions or comments, optional, max 250 characters, set to None if not provided",
        default=None,
        max_length=250,
    )
    price: float = Field(
        description="Item price, set to 0.0 if not provided", default=0.0
    )
    modifiers: list[ClientModifier] = Field(
        description="List of modifiers for this item. Only populate if the customer explicitly requested modifications to the item. Leave as empty list if no modifications were specified.",
        default_factory=list,
    )


class ClientItem(BaseModel):
    group: list[ClientGroup] = Field(description="List of item groups, required")


class OrderRequestBase(BaseModel):
    """Base order request with only fields to be extracted by LLM"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    items: list[ClientItem] = Field(description="List of order items, required")
    promise_date_time: str | None = Field(
        description="Promise date and time in ISO date-time format, ex 2019-08-24T14:15:22Z, set to None if not provided (only if customer requests scheduled/future order)",
        default=None,
        alias="promiseDateTime",
    )
    order_comment: str = Field(
        description="Order comment, optional, max 500 characters, set to '(via PalonaAI)' if not specified",
        default="(via PalonaAI)",
        max_length=500,
        alias="orderComment",
    )


class ValidateOrderRequest(BaseModel):
    """Complete order request with delivery address (used for API calls)"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    store_id: str = Field(description="Store ID, non-empty, required", alias="storeId")
    order_type: OrderType = Field(
        description=f"Type of order. Options: {', '.join([e.value for e in OrderType])}",
        alias="OrderType",
    )
    payment_type: PaymentType = Field(
        description=f"Payment type. Options: {', '.join([e.value for e in PaymentType])}",
        alias="paymentType",
    )
    promise_date_time: str | None = Field(
        description="Promise date and time in ISO date-time format, ex 2019-08-24T14:15:22Z, set to None if not provided",
        default=None,
        alias="promiseDateTime",
    )
    customer: ClientCustomerInfo = Field(description="Customer information, required")
    delivery_address: DeliveryAddress | None = Field(
        description="Delivery address (required for delivery orders), set to None if not provided",
        default=None,
        alias="deliveryAddress",
    )
    items: list[ClientItem] = Field(description="List of order items, required")
    order_comment: str = Field(
        description="Order comment, optional, max 500 characters",
        default="(via PalonaAI)",
        max_length=500,
        alias="orderComment",
    )


class ValidateOrderResponse(BaseModel):
    model_config = {"populate_by_name": True}

    key: str | None = Field(
        description="Order key/GUID, set to None if not provided", default=None
    )
    is_payment_required: bool = Field(
        description="Whether payment is required, set to false if not provided",
        alias="isPaymentRequired",
        default=False,
    )
    sub_total: float = Field(
        description="Order subtotal, set to 0.0 if not provided",
        alias="subTotal",
        default=0.0,
    )
    total: float = Field(
        description="Order total, set to 0.0 if not provided", default=0.0
    )
    discount: float = Field(
        description="Total discount amount, set to 0.0 if not provided", default=0.0
    )
    tax_amount: float = Field(
        description="Tax amount, set to 0.0 if not provided",
        alias="taxAmount",
        default=0.0,
    )
    service_charge: float = Field(
        description="Service charge, set to 0.0 if not provided",
        alias="serviceCharge",
        default=0.0,
    )
    delivery_charge: float = Field(
        description="Delivery charge, set to 0.0 if not provided",
        alias="deliveryCharge",
        default=0.0,
    )
    payment_url: str | None = Field(
        description="Payment URL if payment link is required, set to None if not provided",
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
        description=f"Payment type. Options: {', '.join([e.value for e in PaymentType])}. Default is 'PaymentLink' if not specified",
        default=PaymentType.PAYMENT_LINK,
        alias="paymentType",
    )
    guid: str = Field(description="Order GUID from validate order response, required")
    promise_date_time: str | None = Field(
        description="Promise date and time in ISO date-time format, ex 2019-08-24T14:15:22Z, set to None if not provided (only if customer requests scheduled/future order)",
        default=None,
        alias="promiseDateTime",
    )
    customer: ClientCustomerInfo = Field(description="Customer information, required")
    delivery_address: DeliveryAddress | None = Field(
        description="Delivery address (required for delivery orders), set to None if not provided",
        default=None,
        alias="deliveryAddress",
    )
    items: list[ClientItem] = Field(description="List of order items, required")
    payment_details: PaymentDetails = Field(
        description="Payment details including subtotal, tax, and total"
    )
    order_comment: str = Field(
        description="Order comment, optional, max 500 characters, set to '(via PalonaAI)' if not specified",
        default="(via PalonaAI)",
        max_length=500,
        alias="orderComment",
    )


class ProcessOrderResponse(BaseModel):
    model_config = {"populate_by_name": True}

    success: int = Field(description="Success status (0 or 1)")
    order_id: int = Field(
        description="Processed order ID, set to 0 if not provided",
        default=0,
        alias="orderID",
    )
    order_no: int = Field(
        description="Order number, set to 0 if not provided", default=0, alias="orderNo"
    )
    order_date: str | None = Field(
        description="Order date in ISO format, set to None if not provided",
        default=None,
        alias="orderDate",
    )
    customer_id: int = Field(
        description="Customer ID, set to 0 if not provided",
        default=0,
        alias="customerID",
    )
    address_id: int = Field(
        description="Address ID, set to 0 if not provided", default=0, alias="addressID"
    )
    profile_id: int = Field(
        description="Profile ID, set to 0 if not provided", default=0, alias="profileID"
    )
    msg: str | None = Field(
        description="Response message, set to None if not provided", default=None
    )
    prof_updated: int = Field(
        description="Profile updated flag, set to 0 if not provided",
        default=0,
        alias="profUpdated",
    )
    payment_url: str | None = Field(
        description="Payment URL if applicable, set to None if not provided",
        default=None,
        alias="paymentUrl",
    )
