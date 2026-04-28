"""Eval-time Spec safety modifiers.

Hardens a pal-agents ``Spec`` so eval runs cannot perform real side-effecting
operations (placing orders, charging customers, etc.) even when the underlying
``ProjectIntegration`` config enables them in production.

Installed by default on :class:`InProcessDriver`. See
``docs/records/2026-04-28-eval-spec-modifier.md`` for rationale.
"""

from __future__ import annotations

from pal_agents.spec import Spec


def apply_eval_safety(spec: Spec) -> None:
    """Harden a ``Spec`` in place for eval use.

    Current guarantees:

    * **Toast** — forces ``spec.toast.submit_orders = False`` so the Toast
      provider prices orders and generates payment links but never issues
      ``POST /orders``. See ``pal_agents/providers/toast/_implementation.py``.
    * **Adora** — forces ``spec.adora.force_payment_link = True`` so the
      Adora provider coerces every order's ``payment_type`` to
      ``PAYMENT_LINK``. With a payment link in play, the order is not
      pushed to the POS (``processOrder`` is not called with a real
      payment), which makes eval runs safe without any pal-agents changes.
      See ``tools/adora_v2_tool/_implementation.py`` (the
      ``force_payment_link`` branch inside ``fulfill_order``).

    Any future provider with side-effecting behavior should extend this
    function. The goal is a single choke point between the DB-driven spec
    builders and the pal-agents engine.

    Args:
        spec: The fully constructed ``Spec`` about to be handed to pal-agents.
            Mutated in place.
    """
    if spec.toast.enabled and spec.toast.submit_orders:
        spec.toast.submit_orders = False

    if spec.adora.enabled and not spec.adora.force_payment_link:
        spec.adora.force_payment_link = True
