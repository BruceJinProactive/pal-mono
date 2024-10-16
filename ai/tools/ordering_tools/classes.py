from enum import Enum

from pydantic import BaseModel

"""
- This module defines data models in the ordering tools layer.
- These models are designed to be generalized and reusable across different 
  ordering integrations.
- The Pydantic models ensure that the data conforms to the expected schema, 
  providing type validation and serialization capabilities.
"""


class Consumer(BaseModel):
    """
    This is the shape of a consumer that is sent to an integration API at the place_order step.
    """

    first_name: str
    last_name: str
    phone_number: str  # NOTE: phone number must be in (xxx)xxx-xxxx format for compatibility with ALL providers
    email: str


class GenericCoupon(BaseModel):
    """
    This is the shape of a generic coupon that is sent to an integration API at the place_order step.
    """

    coupon: str


class GenericDeliveryAddress(BaseModel):
    """
    This is the shape of a generic delivery address that is sent to an integration API at the place_order step.
    """

    address: str
    city: str
    state: str
    zip_code: str
    # TODO: Consider adding a second address line for suite numbers or other additional address information.


class FulfillmentStrategy(Enum):
    """
    This is an enum representing different fulfillment strategies for an order.
    """

    DELIVERY = "delivery"
    PICKUP = "pickup"
    NA = "N/A"


class LLMFulfillmentStrategy(BaseModel):
    strategy: FulfillmentStrategy


class LLMOrderItem(BaseModel):
    """
    An LLM Order Item is what the LLM outputs when it is asked to parse a cart (see LLMCartInfo).
    """

    item_name: str
    size: str
    quantity: int
    modifications: list[str]


class LLMCartInfo(BaseModel):
    """
    An LLM Cart Info is what the LLM outputs when it is asked to parse a cart.
    """

    cart_items: list[LLMOrderItem]


class LLMOrder(BaseModel):
    """
    The LLM parses the output from save_validate_order to extract the order ID.
    The order_id is then passed into place_order.
    """

    order_id: int


class OrderItem:
    """
    This represents a generic order item that will be passed to an ordering integration.
    This should NOT inherit from Pydantic's BaseModel because it is not used by the LLM.
    """

    def __init__(
        self, item_name: str, size: str, quantity: int, modifications: list[str]
    ):
        self.item_name: str = item_name
        self.size: str = size
        self.quantity: int = quantity
        self.modifications: list[str] = modifications
