from . import _implementation


def create_checkout_session(
    account_name: str,
    customer_email: str,
    price_id: str,
    redirect_url_prefix: str,
    quantity: int = 1,
):
    """
    Creates a checkout session to collect payment for the intended product's price ID.
    """
    return _implementation.create_checkout_session(
        account_name, customer_email, price_id, redirect_url_prefix, quantity
    )


def unpack_checkout_session(session_id: str):
    """
    Unpacks the checkout session data from the Stripe webhook.
    Returns a dictionary with the account name, customer id, and subscription id.
    """
    return _implementation.unpack_checkout_session(session_id)


def cancel_subscription(subscription_id: str):
    """
    Cancels a Stripe subscription by subscription ID.
    """
    return _implementation.cancel_subscription(subscription_id)
