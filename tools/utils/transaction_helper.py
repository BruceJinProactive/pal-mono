"""
Transaction Helper Utilities - DEPRECATED

⚠️  DEPRECATED: This module has been moved to services/transaction_service/

    Please use the following imports instead:
    - from services.transaction_service import save_order
    - from services.transaction_service import update_order_by_order_id
    - from services.transaction_service import reconstruct_order_items

    This file will be removed in a future version.

Shared utilities for tools to easily save transaction data to the database.
This module provides convenience functions that abstract away the complexity
of creating and managing transaction records across different integration providers.

"""

import warnings

# Re-export functions from the new location for backward compatibility
from services.transaction_service import (
    reconstruct_order_items,
    save_order,
    update_order_by_order_id,
)

# Issue deprecation warning when this module is imported
warnings.warn(
    "tools.utils.transaction_helper is deprecated. "
    "Use services.transaction_service instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "save_order",
    "update_order_by_order_id",
    "reconstruct_order_items",
]
