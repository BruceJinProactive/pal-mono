"""Backward-compat shim for ``apply_eval_safety``.

The canonical implementation now lives at :mod:`utils.eval_safety` so
both ``services.eval_service`` and ``services.message_service`` can
import it without creating a circular ``services → services`` cycle.

Existing callers (``InProcessDriver``, tests) continue to work via this
re-export. New code should import from ``utils.eval_safety`` directly.
"""

from utils.eval_safety import apply_eval_safety

__all__ = ["apply_eval_safety"]
