class OrderItem:
    def __init__(
        self, item_name: str, size: str, quantity: int, modifications: list[str]
    ):
        self.item_name: str = item_name
        self.size: str = size
        self.quantity: int = quantity
        self.modifications: list[str] = modifications
