import stripe
from stripe import InvalidRequestError

from utils.log import logger


def grant_credit_balance(
    stripe_customer_id: str,
    amount_cents: int,
    currency: str,
    description: str | None,
    metadata: dict[str, str] | None = None,
    idempotency_key: str | None = None,
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
        balance_transaction_params = {
            "amount": -amount_cents,
            "currency": currency,
            "description": description,
        }

        if metadata:
            sanitized_metadata = {}
            existing_keys = set()
            for orig_k, v in metadata.items():
                base = str(orig_k)
                key = base[:40]
                i = 1
                while key in existing_keys:
                    suffix = f"_{i}"
                    key = (base[: 40 - len(suffix)]) + suffix
                    i += 1
                existing_keys.add(key)
                sanitized_metadata[key] = ("" if v is None else str(v))[:500]
            balance_transaction_params["metadata"] = sanitized_metadata

        if idempotency_key:
            balance_transaction_params["idempotency_key"] = idempotency_key

        txn = stripe.Customer.create_balance_transaction(
            stripe_customer_id,
            **balance_transaction_params,
        )
        return txn
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
