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
