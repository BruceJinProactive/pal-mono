from enum import Enum

from pydantic import BaseModel

from ai.tools.ordering_tools.ordering_classes import OrderItem


class AccessToken(BaseModel):
    access_token: str
    expires_in: int
    token_type: str
    scope: str

    def get_token_header_value(self) -> str:
        return f"{self.token_type} {self.access_token}"


class AdoraHubResponse(BaseModel):
    status: int
    reason: str
    decoded_body: str


class AdoraOrderItem(OrderItem):
    def __init__(
        self,
        item_id: int,
        size_id: int,
        quantity: int,
        comment: str,
        price: 0,
        modifications: list,
    ):
        self.itemId = item_id
        self.sizeId = size_id
        self.quantity = quantity
        self.comment = comment
        self.price = price

        # TODO should taxes field stay here or get moved to constructor param?
        self.taxes = [{"id": 0, "taxAmount": 0}]

        # TODO transform self.modifications into self.modifiers
        # self.modifiers = [{"id": 0, "isDefault": True, "price": 0, "weightId": 0}]
        self.modifiers = modifications


class Consumer(BaseModel):
    """
    NOTE: phone number must be in (xxx)xxx-xxxx format
    NOTE: Placing order will send a text to the phone number
    """

    first_name: str
    last_name: str
    phone_number: str  # NOTE: phone number must be in (xxx)xxx-xxxx format
    email: str


class DeliveryAddress(BaseModel):
    address: str
    extendedAddress: str = (
        ""  # Required by Adora API, used for Apt/Suite number, can be empty string
    )
    city: str
    state: str
    zip: str
    lat: float = 37.230727  # TODO: get this from an address to lat long API
    lng: float = -121.953576  # TODO: get this from an address to lat long API
    instruction: str = ""  # Required by Adora API but can be empty string
    typeId: int = 1  # TODO: get this from address validation API
    extraField1: str = (
        ""  # Required by Adora API but not sure its use and can be empty string
    )
    extraField2: str = (
        ""  # Required by Adora API but not sure its use and can be empty string
    )


class OrderCalculationResult(BaseModel):
    # Key is used on the Adora Pos API side in subsequent API calls to refer to the order.
    Key: str
    IsPaymentRequired: bool
    SubTotal: float
    Total: float
    Discount: float
    TaxAmount: float
    ServiceCharge: float
    DeliveryCharge: float


class OrderType(str, Enum):
    Delivery = "Delivery"
    TakeOut = "TakeOut"


class SavedOrderResult(BaseModel):
    Success: int
    OrderID: int  # this is the important value -- you need this to checkout the order using /textPaymentLink
    OrderNo: int
    CustomerID: int
    AddressID: int
    ProfileID: int
    msg: str
    ProfUpdated: int
