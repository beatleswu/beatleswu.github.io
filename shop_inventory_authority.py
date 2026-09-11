"""Caller-owned atomic authority for consuming ``shop_inventory`` items.

The caller supplies an open transaction and remains responsible for commit or
rollback.  This module owns only the quantity validation and guarded
decrement; it does not inspect, repair, or consolidate any other inventory
store.
"""

from __future__ import annotations

from typing import Any


CONSUME_SQL = (
    "UPDATE shop_inventory SET qty=qty-? "
    "WHERE user_id=? AND item_key=? AND qty>=?"
)


class ShopInventoryConsumeError(RuntimeError):
    """Base class for fail-closed shop-inventory consume failures."""

    def __init__(self, code: str, message: str, **details: Any):
        self.code = code
        self.details = details
        super().__init__(message)


class ShopInventoryInvalidQuantity(ShopInventoryConsumeError):
    """The requested consume quantity is not a positive integer."""

    def __init__(self, quantity: Any):
        super().__init__(
            "INVALID_QUANTITY",
            "shop_inventory consume quantity must be a positive integer",
            quantity=quantity,
        )


class ShopInventoryInsufficient(ShopInventoryConsumeError):
    """The requested item row is absent or has insufficient quantity."""

    def __init__(self, user_id: Any, item_key: Any, quantity: int):
        super().__init__(
            "INSUFFICIENT_QUANTITY",
            "shop_inventory does not contain enough quantity",
            user_id=user_id,
            item_key=item_key,
            quantity=quantity,
            legacy_error="not_owned",
        )


class ShopInventoryUnexpectedRowCount(ShopInventoryConsumeError):
    """The guarded decrement did not produce a valid single-row result."""

    def __init__(self, rowcount: Any):
        super().__init__(
            "UNEXPECTED_ROWCOUNT",
            "shop_inventory consume affected an unexpected number of rows",
            rowcount=rowcount,
        )


def _validate_quantity(quantity: Any) -> int:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ShopInventoryInvalidQuantity(quantity)
    return quantity


def consume_shop_inventory(
    conn: Any,
    user_id: Any,
    item_key: Any,
    quantity: Any = 1,
) -> bool:
    """Consume one positive quantity inside the caller's open transaction.

    The single guarded ``UPDATE`` is the authority for both availability and
    the decrement.  A rowcount of zero is a typed insufficiency/not-owned
    failure.  Any other rowcount apart from exactly one fails closed.  This
    function intentionally never commits or rolls back ``conn``.
    """

    quantity = _validate_quantity(quantity)
    updated = conn.execute(
        CONSUME_SQL,
        (quantity, user_id, item_key, quantity),
    )
    rowcount = getattr(updated, "rowcount", None)
    if type(rowcount) is not int:
        raise ShopInventoryUnexpectedRowCount(rowcount)
    if rowcount == 0:
        raise ShopInventoryInsufficient(user_id, item_key, quantity)
    if rowcount != 1:
        raise ShopInventoryUnexpectedRowCount(rowcount)
    return True


__all__ = [
    "CONSUME_SQL",
    "ShopInventoryConsumeError",
    "ShopInventoryInsufficient",
    "ShopInventoryInvalidQuantity",
    "ShopInventoryUnexpectedRowCount",
    "consume_shop_inventory",
]
