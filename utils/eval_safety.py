"""Safety hardening for pal-agents ``Spec`` during eval / test runs.

Auto-applied by :mod:`services.message_service` whenever the underlying
``Conversation.is_test`` flag is ``True`` (set when the first message
carries ``metadata.testing=True``). Ensures eval runs cannot perform
real side-effecting operations (placing orders, charging customers,
etc.) even when the project's ``ProjectIntegration`` config enables them
in production.

Lives in ``utils/`` so both ``services.eval_service`` (eval drivers)
and ``services.message_service`` (chat orchestration) can depend on it
without creating a circular ``services → services`` import.

Kept at the utils layer because the function is pure, depends only on
the external ``pal_agents`` package, and has no internal deps — it
satisfies the ``utils must be isolated`` import-linter contract.
"""

from __future__ import annotations

from pal_agents.spec import Spec


def apply_eval_safety(spec: Spec) -> None:
    """Harden a ``Spec`` in place for eval / test use.

    Current guarantees:

    * **Toast** — forces ``spec.toast.submit_orders = False`` so the
      Toast provider prices orders and generates payment links but
      never issues ``POST /orders``.
    * **Adora** — forces ``spec.adora.force_payment_link = True`` so
      every order's ``payment_type`` is coerced to ``PAYMENT_LINK`` and
      the order is not pushed to the POS with a real payment.

    Any future provider with side-effecting behaviour should extend
    this function — the goal is a single choke point between the
    DB-driven spec builders and the pal-agents engine.

    Args:
        spec: The fully constructed ``Spec`` about to be handed to
            pal-agents. Mutated in place.
    """
    if spec.toast.enabled and spec.toast.submit_orders:
        spec.toast.submit_orders = False

    if spec.adora.enabled and not spec.adora.force_payment_link:
        spec.adora.force_payment_link = True
