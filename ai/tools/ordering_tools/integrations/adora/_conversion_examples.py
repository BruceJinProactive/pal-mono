COUPON_EXAMPLES = """
# EXAMPLE #
EXAMPLE AVAILABLE COUPONS: ["$5 Off", "20% off", "Free Bagel with Purchase of Coffee"]

User: five bucks off
Assistant: $5 Off

User: twenty percent reduced
Assistant: 20% off

User: free bagel coupon
Assistant: Free Bagel with Purchase of Coffee

User: $10 Off
Assistant: N/A

User: 30% off
Assistant: N/A

User: free sandwich
Assistant: N/A
"""

ITEM_ID_EXAMPLES = """
# EXAMPLE #
EXAMPLE MENU: ["Coke", "Sprite"]

User: coke
Assistant: Coke

User: spritw
Assistant: Sprite

User: pepsi
Assistant: N/A

User: coke zero
Assistant: N/A
"""

SIZE_EXAMPLES = """
# EXAMPLE #
EXAMPLE AVAILABLE SIZE OPTIONS: ["Small", "Medium", "Large", "Size 5", "Size 6", "Size 7"]

User: large
Assistant: Large

User: Size5
Assistant: Size 5

User: Size 8
Assistant: N/A

User: size 4
Assistant: N/A

User: extra large
Assistant: N/A
"""

MODIFIER_EXAMPLES = """
# EXAMPLE #
EXAMPLE AVAILABLE MODIFICATION OPTIONS: ["Rainbow Sprinkles", "Gummy Bears", "Whipped Cream", "Peanuts"]
User: rainbow sprinkles
Assistant: Rainbow Sprinkles

User: pnuts
Assistant: peanuts

User: nutella
Assistant: N/A

User: cherries
Assistant: N/A
"""
