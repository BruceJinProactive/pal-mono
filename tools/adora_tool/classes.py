"""
Data model templates to be used by Instructor to extract ordering data from user's
chat history.

[Instructor](https://github.com/instructor-ai/instructor)
"""

from typing import List, Optional

from pydantic import BaseModel, Field


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


class CustomerInfo(BaseModel):
    first_name: Optional[str] = Field(description="Customer's first name")
    last_name: Optional[str] = Field(description="Customer's last name")
    phone: Optional[str] = Field(
        description="Customer's phone number",
        pattern=r"^\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})$",
    )
    email: Optional[str] = Field(description="Customer's email address")


# US Address Data Model
class DeliveryAddress(BaseModel):
    street_no: Optional[str] = Field(description="Street number")
    address: Optional[str] = Field(description="Street address")
    city: Optional[str] = Field(description="City name")
    state: Optional[str] = Field(description="State abbreviation")
    zip: Optional[str] = Field(description="ZIP code")


class Modification(BaseModel):
    name: str = Field(
        description="Modification name", examples=["Onions", "Bacon", "Cheese"]
    )
    price: float = Field(description="Price of the modification")
    quantity: int = Field(description="Quantity of the modification")


class OrderItem(BaseModel):
    id: str = Field(description="Item ID")
    name: str = Field(description="Item name")
    quantity: int = Field(description="Quantity")
    price: float = Field(description="Price per unit")
    modifications: List[Modification] = Field(description="List of modifications")


class Order(BaseModel):
    store_id: str = Field(description="Store ID")
    order_type: str = Field(description="Order type")
    customer: CustomerInfo = Field(description="Customer information")
    items: List[OrderItem] = Field(description="List of order items")
    delivery_address: DeliveryAddress = Field(description="Delivery address")
