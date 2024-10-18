from enum import Enum

from pydantic import BaseModel

from ai.tools.ordering_tools.classes import OrderItem


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


class AdoraCoupon(BaseModel):
    """
    This is the shape of a coupon, part of a response from the Adora API when you list all coupons.
    """

    id: int
    name: str
    description: str


class AdoraCouponList(BaseModel):
    """
    This is the shape of a list of coupons, a response from the Adora API when you list all coupons.
    """

    coupons: list[AdoraCoupon]


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


class AdoraHubResponse(BaseModel):
    """
    This is the response shape from the Adora API when you make a request to the OrderHub.
    """

    status: int
    reason: str
    decoded_body: str


class AdoraOrderCalculationResult(BaseModel):
    """
    This is the response shape from the Adora API when you request an order calculation at the validate_order step.
    """

    # Key is used on the Adora Pos API side in subsequent API calls to refer to the order.
    Key: str
    IsPaymentRequired: bool
    SubTotal: float
    Total: float
    Discount: float
    TaxAmount: float
    ServiceCharge: float
    DeliveryCharge: float


class AdoraOrderItem(OrderItem):
    """
    This is the shape of an order item that is sent to the Adora API at the add_to_order step.
    """

    def __init__(
        self,
        item_id: int,
        size_id: int,
        quantity: int,
        comment: str,
        price: int,
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


class AdoraOrderType(str, Enum):
    Delivery = "Delivery"
    TakeOut = "TakeOut"


class AdoraSavedOrderResult(BaseModel):
    """
    This is the shape of the response from the Adora API at the save_validate_order step.
    """

    Success: int
    OrderID: int  # this is the important value -- you need this to checkout the order using /textPaymentLink
    OrderNo: int
    CustomerID: int
    AddressID: int
    ProfileID: int
    msg: str
    ProfUpdated: int


class AdoraValidatedAddress(BaseModel):
    """
    This is the shape of the response from the Adora API at the validate_address step, part of AdoraValidatedAddressList.
    """

    charge: float
    minimumCharge: float
    typeId: int
    description: str


class AdoraValidatedAddressList(BaseModel):
    """
    This is the shape of the response from the Adora API at the validate_address step.
    """

    addresses: list[AdoraValidatedAddress]
