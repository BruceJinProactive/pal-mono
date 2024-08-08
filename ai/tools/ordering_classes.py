from typing import List


class OrderItem:
    def __init__(
        self, item_name: str, size: str, quantity: int, modifications: List[str]
    ):
        self.item_name: str = item_name
        self.size: str = size
        self.quantity: int = quantity
        self.modifications: List[str] = modifications
