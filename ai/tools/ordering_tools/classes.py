from pydantic import BaseModel

"""
- This module defines data models in the ordering tools layer.
- These models are designed to be generalized and reusable across different 
  ordering integrations.
- The Pydantic models ensure that the data conforms to the expected schema, 
  providing type validation and serialization capabilities.
"""


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


class OrderItem(BaseModel):
    """
    This represents a generic order item that will be passed to an ordering integration.
    """

    item_name: str
    size: str
    quantity: int
    modifications: list[str]
