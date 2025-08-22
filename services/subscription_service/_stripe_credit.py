import stripe
from stripe import InvalidRequestError

from utils.log import logger


def grant_credit_balance(
    stripe_customer_id: str,
    amount_cents: int,
    currency: str,
    description: str | None,
):
    """
    Applies a one time credit amount to the customer. This amount will offset their
    future invoice charges.

    The credit amount is in cents.
    - For positive value > 0, a credit is issued.
    - For negative value < 0, a debit is issued.
    """
    if amount_cents == 0:
        raise ValueError("Amount cannot be 0")

    if not description:
        if amount_cents > 0:
            description = "Promotional Credit"
        else:
            description = "Balance Adjustment"

    try:
        stripe.Customer.create_balance_transaction(
            stripe_customer_id,
            amount=-amount_cents,  # A credit reduces balance.
            currency=currency,
            description=description,
        )
    except InvalidRequestError as err:
        logger.error(err)
        raise ValueError(err)
    except Exception as err:
        logger.error(
            f"Failed to adjust credit balance for customer: {stripe_customer_id}",
            extra={
                "amount_in_cents": amount_cents,
            },
        )
        raise err


def get_credit_balance(stripe_customer_id: str) -> tuple[int, str]:
    try:
        customer = stripe.Customer.retrieve(stripe_customer_id)
        credit_balance = -(customer.balance or 0)
        currency = customer.currency or "usd"

        return credit_balance, currency
    except Exception as err:
        logger.error(
            f"Failed to retrieve credit balance for customer: {stripe_customer_id}"
        )
        raise err
