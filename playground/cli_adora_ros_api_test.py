from os import getenv

from ai.tools.integrations.pos.adora_pos.adora_pos_apis import (
    AdoraApiKeyAndSecret,
    AdoraCustomerInfo,
    _get_adora_pos_auth_token,
    calculate_tax_fees_and_total,
    get_adora_pos_consumer_account_info,
    get_adora_pos_store_menu,
    submit_order_and_text_payment_link,
)

# TODO: convert these to unit tests after we add a unit test library
api_key = getenv("ADORA_POS_API_KEY")
api_secret = getenv("ADORA_POS_API_SECRET")

if api_key and api_secret:
    adora_key_and_secret = AdoraApiKeyAndSecret(
        api_key=api_key,
        api_secret=api_secret,
    )

    store_id = "9WHCV"  # NOTE: this is the PizzaMyHeart Test Store ID

    customer: AdoraCustomerInfo = AdoraCustomerInfo(
        first_name="John",
        last_name="smith",
        phone_number="(888)123-4567",
        email="GKvzQ@example.com",
    )

    # test order
    order = {
        "items": [
            {
                "itemId": 4,
                "sizeId": 3,
                "quantity": 1,
                "comment": "item comments here",
                "price": 0,
                "taxes": [],  # can be empty
                "modifiers": [],
            }
        ]
    }

    # test order validation
    order_validation_result = calculate_tax_fees_and_total(
        adora_key_and_secret, store_id, customer, order["items"]
    )
    print(
        "Order Validation Result: "
        + (
            order_validation_result.model_dump_json()
            if order_validation_result
            else "Failure"
        )
    )

    # test order submission
    order_submitted = submit_order_and_text_payment_link(
        adora_key_and_secret, store_id, customer, order["items"]
    )
    print("Order Submitted: " + str(order_submitted) if order_submitted else "Failure")

    # test get menu api
    menu_json_string = get_adora_pos_store_menu(adora_key_and_secret, store_id)
    print("Menu: \n" + menu_json_string if menu_json_string else "Menu API error")

    # test get consumer account info
    user_json_string = get_adora_pos_consumer_account_info(
        adora_key_and_secret, store_id, customer.phone_number
    )
    print("User: \n" + user_json_string if user_json_string else "User not found")

    # test get auth token, and print it for debugging with Postcode if needed
    bearer_token = _get_adora_pos_auth_token(adora_key_and_secret)
    if bearer_token:
        print("Bearer Token: " + bearer_token.access_token)
else:
    print("missing ADORA_POS_API_KEY or ADORA_POS_API_SECRET in environment")
