import json
from dataclasses import dataclass

from ai.tools.pizza_demo_ordering_tools.adapters.mock_cart import (
    convert_order_item_to_adora,
)
from ai.tools.pizza_demo_ordering_tools.ordering_classes import OrderItem


# False means propagate failure, True means expected result in message.
@dataclass
class ConversionResult:
    success: bool
    message: str


if __name__ == "__main__":
    """For testing
    Item names: Pesto, Big Sur, Little Sur, Chicken Wings
    Sizes: small, medium, large, 12", 14", 18"
    Quantity: -1, 0, 101, 1, 2
    Modifications: White Sauce,
    """
    item_names = ["big sur"]
    sizes = ['18"', "medium"]
    quantities = [1]
    modifications = [
        [],
        ["White Sauce"],
        ["Anchovy"],
        ["White Sauce", "Anchovy"],
        ["Spell my name on it"],
        ["Lime Aioli"],
    ]

    with open("conversion.txt", "w") as f:
        f.write("")

    for item_name in item_names:
        for size in sizes:
            for quantity in quantities:
                for modification in modifications:
                    order_item = OrderItem(item_name, size, quantity, modification)
                    with open("conversion.txt", "a") as f:
                        f.write(
                            "Order Item: "
                            + item_name
                            + " "
                            + size
                            + " "
                            + str(quantity)
                            + " "
                            + str(modification)
                            + "\n"
                        )
                        res = convert_order_item_to_adora(order_item)
                        if res.success:
                            f.write(json.dumps(json.loads(res.message), indent=4))
                        else:
                            f.write("\n" + res.message + "\n")
                        f.write("\n-----------------------------\n")
