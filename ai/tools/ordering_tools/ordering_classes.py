from pydantic import BaseModel


class LLMOrderItem(BaseModel):
    item_name: str
    size: str
    quantity: int
    modifications: list[str]


class LLMCartInfo(BaseModel):
    cart_items: list[LLMOrderItem]


class OrderItem:
    def __init__(
        self, item_name: str, size: str, quantity: int, modifications: list[str]
    ):
        self.item_name: str = item_name
        self.size: str = size
        self.quantity: int = quantity
        self.modifications: list[str] = modifications


class ParsedAdoraOrder(BaseModel):
    order_id: int
