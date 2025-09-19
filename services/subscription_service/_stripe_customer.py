from dataclasses import dataclass
from datetime import UTC, datetime

import stripe
from stripe import InvalidRequestError

from utils.log import logger


@dataclass
class CustomerInfo:
    id: str
    name: str | None
    email: str | None
    balance: int | None = None
    currency: str | None = None


def create_stripe_customer(
    account_name: str,
    customer_name: str | None = None,
    customer_email: str | None = None,
    metadata: dict[str, str] | None = None,
) -> CustomerInfo:
    """
    Create a Stripe customer for an account.
    """
    try:
        customer_params = {
            "name": customer_name or account_name,
            "metadata": {
                "account_name": account_name,
                **(metadata or {}),
            },
        }

        if customer_email:
            customer_params["email"] = customer_email

        customer = stripe.Customer.create(**customer_params)

        logger.info(
            "Successfully created Stripe customer",
            extra={
                "account_name": account_name,
                "customer_id": customer.id,
                "customer_name": customer_name,
                "customer_email": customer_email,
            },
        )
        return CustomerInfo(
            id=customer.id,
            name=customer.name,
            email=customer.email,
        )
    except stripe.StripeError as e:
        logger.error(
            f"Failed to create Stripe customer: {e}",
            extra={
                "account_name": account_name,
                "customer_name": customer_name,
                "customer_email": customer_email,
            },
        )
        raise


def get_stripe_customer_info(stripe_customer_id: str) -> CustomerInfo:
    try:
        customer = stripe.Customer.retrieve(stripe_customer_id)
        return CustomerInfo(
            id=customer.id,
            name=customer.name,
            email=customer.email,
            balance=customer.balance,
            currency=customer.currency,
        )
    except stripe.StripeError as e:
        logger.error(
            f"Failed to retrieve Stripe customer: {e}",
            extra={"stripe_customer_id": stripe_customer_id},
        )
        raise


def update_stripe_customer(
    stripe_customer_id: str,
    name: str | None = None,
    email: str | None = None,
) -> CustomerInfo:
    """
    Update a Stripe customer's information.
    """
    try:
        update_params = {}
        if name is not None:
            update_params["name"] = name
        if email is not None:
            update_params["email"] = email

        if not update_params:
            raise ValueError("No fields provided for update")

        customer = stripe.Customer.modify(stripe_customer_id, **update_params)

        logger.info(
            "Successfully updated Stripe customer",
            extra={
                "stripe_customer_id": stripe_customer_id,
                "updated_fields": list(update_params.keys()),
            },
        )
        return CustomerInfo(
            id=customer.id,
            name=customer.name,
            email=customer.email,
            balance=customer.balance,
            currency=customer.currency,
        )
    except stripe.StripeError as e:
        logger.error(
            f"Failed to update Stripe customer: {e}",
            extra={"stripe_customer_id": stripe_customer_id},
        )
        raise


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


def get_credit_grants_history(
    stripe_customer_id: str,
) -> list[dict]:
    try:
        balance_transactions = stripe.Customer.list_balance_transactions(
            stripe_customer_id,
        )

        credit_grants = []
        for txn in balance_transactions.data:
            credit_amount_cents = -txn.amount if txn.amount < 0 else 0
            credit_reduction_cents = txn.amount if txn.amount > 0 else 0

            created_datetime = datetime.fromtimestamp(txn.created, tz=UTC)

            metadata = txn.metadata or {}
            issued_by = metadata.get("issued_by") or "system"
            issued_via = metadata.get("issued_via") or "stripe"
            request_source = metadata.get("request_source") or "unknown"

            credit_grant = {
                "id": txn.id,
                "created": created_datetime,
                "credit_amount_cents": credit_amount_cents,
                "credit_reduction_cents": credit_reduction_cents,
                "currency": txn.currency,
                "description": txn.description,
                "metadata": metadata,
                "ending_balance": -txn.ending_balance if txn.ending_balance else 0,
                "issued_by": issued_by,
                "issued_via": issued_via,
                "request_source": request_source,
            }
            credit_grants.append(credit_grant)

        return credit_grants

    except InvalidRequestError as err:
        logger.error(f"Invalid request when retrieving credit grants: {err}")
        raise ValueError(err)
    except Exception as err:
        logger.error(
            f"Failed to retrieve credit grants for customer: {stripe_customer_id}",
            extra={
                "stripe_customer_id": stripe_customer_id,
                "error": str(err),
            },
        )
        raise err
