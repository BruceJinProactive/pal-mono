import stripe

from utils import secret
from utils.log import logger


def create_checkout_session(
    account_name: str,
    customer_email: str,
    price_id: str,
    redirect_url_prefix: str,
    quantity: int = 1,
):
    stripe.api_key = secret.get_server_secret("STRIPE_API_KEY")

    try:
        redirect_url_prefix = redirect_url_prefix.rstrip("/")
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price": price_id,
                    "quantity": quantity,
                },
            ],
            client_reference_id=account_name,
            customer_email=customer_email,
            success_url=f"{redirect_url_prefix}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{redirect_url_prefix}/cancel",
        )
        return session
    except Exception as e:
        logger.error(f"Failed to create checkout session with stripe due to error: {e}")
        return None


def unpack_checkout_session(session_id: str):
    stripe.api_key = secret.get_server_secret("STRIPE_API_KEY")

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if not session:
            return None
        return {
            "account_name": session.client_reference_id,
            "customer_id": session.customer,
            "subscription_id": session.subscription,
            "customer_email": session.customer_email,
        }
    except Exception as e:
        logger.error(
            f"Failed to retrieve checkout session with stripe due to error: {e}"
        )
        return None
