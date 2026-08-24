"""C019 server-side atomic Coin purchase transaction core.

The public entry point, :func:`purchase_with_coins`, is intentionally a
caller-transaction API.  It does not commit or roll back.  The caller must
keep the supplied connection open until the complete purchase succeeds or an
exception causes the surrounding transaction to roll back.

The operation row and all Coin/acquisition/D5A mutations therefore share one
transaction boundary.  The operation table is the exactly-once business
authority; D5A is written as acquisition evidence and D5C is not imported or
used.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Protocol

from event_outbox import append_event
from migrations.coin_purchase_operations_v1 import (
    OPERATION_STATUSES,
    TABLE_NAME,
)
from shop_offer_authority import (
    CoinShopOffer,
    ShopOfferAuthority,
    ShopOfferError,
    ShopOfferNotEligible,
    ShopOfferNotFound,
)


SHOP_SOURCE = "SHOP"
COIN_CURRENCY = "COINS"
AUTHORITY_HOLD_ITEM_IDS = frozenset({"xp_amulet"})
INVENTORY_ONLY_ITEM_IDS = frozenset({"go_stone_black"})
CONSUMABLE_CLASSES = frozenset(
    {"CONSUMABLE", "SPIRIT_CONSUMABLE", "XP_CONSUMABLE"}
)
FUNCTIONAL_EQUIPMENT_CLASSES = frozenset({"WEAPON", "ARMOR", "ACCESSORY"})


class CoinPurchaseError(RuntimeError):
    """Base class for explicit, fail-closed purchase failures."""

    code = "COIN_PURCHASE_FAILED"

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None):
        self.details = dict(details or {})
        super().__init__(message)


class UnknownOffer(CoinPurchaseError):
    code = "UNKNOWN_OFFER"


class OfferNotEligible(CoinPurchaseError):
    code = "OFFER_NOT_ELIGIBLE"


class InsufficientCoins(CoinPurchaseError):
    code = "INSUFFICIENT_COINS"

    def __init__(self, *, balance: int, required: int):
        self.balance = int(balance)
        self.required = int(required)
        super().__init__(
            f"insufficient Coins: balance={self.balance}, required={self.required}",
            details={"balance": self.balance, "required": self.required},
        )


class PurchaseOperationConflict(CoinPurchaseError):
    code = "PURCHASE_OPERATION_CONFLICT"

    def __init__(self, existing: Mapping[str, Any]):
        self.existing = dict(existing)
        super().__init__(
            "purchase operation identity is bound to different purchase semantics",
            details={
                "user_id": self.existing.get("user_id"),
                "purchase_operation_id": self.existing.get("purchase_operation_id"),
                "offer_id": self.existing.get("offer_id"),
            },
        )


class PurchaseOperationInProgress(CoinPurchaseError):
    code = "PURCHASE_OPERATION_IN_PROGRESS"

    def __init__(self, existing: Mapping[str, Any]):
        self.existing = dict(existing)
        super().__init__(
            "purchase operation is unexpectedly still in progress; retry is fail-closed",
            details={
                "user_id": self.existing.get("user_id"),
                "purchase_operation_id": self.existing.get("purchase_operation_id"),
            },
        )


class AcquisitionFailed(CoinPurchaseError):
    code = "ACQUISITION_FAILED"


class OwnershipAuthorityUnavailable(CoinPurchaseError):
    code = "OWNERSHIP_AUTHORITY_UNAVAILABLE"


class SchemaUnavailable(CoinPurchaseError):
    code = "SCHEMA_UNAVAILABLE"


class CoinDebitFailed(CoinPurchaseError):
    code = "COIN_DEBIT_FAILED"


@dataclass(frozen=True)
class CoinBalanceChange:
    coins_before: int
    coins_spent: int
    coins_after: int


@dataclass(frozen=True)
class AcquisitionOutcome:
    """Normalized destination result returned by the scoped acquisition adapter."""

    destination: str
    item_id: str
    quantity: int
    new_quantity: int | None
    ownership_state: str
    is_new: bool | None
    can_equip: bool | None
    can_use: bool | None
    can_wear: bool | None
    presentation_metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "new_quantity": self.new_quantity,
            "ownership_state": self.ownership_state,
            "is_new": self.is_new,
            "can_equip": self.can_equip,
            "can_use": self.can_use,
            "can_wear": self.can_wear,
            "presentation_metadata": dict(self.presentation_metadata),
        }


class AcquisitionAuthority(Protocol):
    def acquire(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
        purchase_operation_id: str,
    ) -> AcquisitionOutcome:
        ...


@dataclass(frozen=True)
class CoinPurchaseResult:
    """Server-committed purchase result; ``replayed`` is delivery metadata."""

    operation_id: str
    offer_id: str
    item_id: str
    quantity: int
    source: str
    destination: str
    coins_before: int
    coins_spent: int
    coins_after: int
    ownership_result: Mapping[str, Any]
    is_new: bool | None
    can_equip: bool | None
    can_use: bool | None
    can_wear: bool | None
    lineage_event_id: str
    offer_version: str
    replayed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "operation_id": self.operation_id,
            "offer_id": self.offer_id,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "source": self.source,
            "destination": self.destination,
            "coins_before": self.coins_before,
            "coins_spent": self.coins_spent,
            "coins_after": self.coins_after,
            "ownership_result": dict(self.ownership_result),
            "is_new": self.is_new,
            "can_equip": self.can_equip,
            "can_use": self.can_use,
            "can_wear": self.can_wear,
            "lineage_event_id": self.lineage_event_id,
            "offer_version": self.offer_version,
            "source_operation_id": self.operation_id,
            "replayed": self.replayed,
        }

    def canonical_payload(self) -> dict[str, Any]:
        """Return the stored result without retry-delivery metadata."""

        payload = self.as_dict()
        payload["replayed"] = False
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        replayed: bool,
    ) -> "CoinPurchaseResult":
        if not isinstance(payload, Mapping) or payload.get("ok") is not True:
            raise SchemaUnavailable("committed purchase result is not recoverable")
        required = (
            "operation_id",
            "offer_id",
            "item_id",
            "quantity",
            "source",
            "destination",
            "coins_before",
            "coins_spent",
            "coins_after",
            "ownership_result",
            "lineage_event_id",
            "offer_version",
        )
        if any(key not in payload for key in required):
            raise SchemaUnavailable("committed purchase result is incomplete")
        return cls(
            operation_id=str(payload["operation_id"]),
            offer_id=str(payload["offer_id"]),
            item_id=str(payload["item_id"]),
            quantity=int(payload["quantity"]),
            source=str(payload["source"]),
            destination=str(payload["destination"]),
            coins_before=int(payload["coins_before"]),
            coins_spent=int(payload["coins_spent"]),
            coins_after=int(payload["coins_after"]),
            ownership_result=dict(payload["ownership_result"]),
            is_new=payload.get("is_new"),
            can_equip=payload.get("can_equip"),
            can_use=payload.get("can_use"),
            can_wear=payload.get("can_wear"),
            lineage_event_id=str(payload["lineage_event_id"]),
            offer_version=str(payload["offer_version"]),
            replayed=replayed,
        )


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _json_parameter(conn: Any, payload: Mapping[str, Any]) -> Any:
    if _is_sqlite(conn):
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    from psycopg2.extras import Json

    return Json(dict(payload))


def _timestamp(conn: Any, value: datetime | None = None) -> Any:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("purchase timestamps must be timezone-aware")
    return value.isoformat() if _is_sqlite(conn) else value


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        result = {str(key): row[key] for key in row.keys()}
    else:
        result = dict(row)
    payload = result.get("result_payload")
    if isinstance(payload, str):
        try:
            result["result_payload"] = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise SchemaUnavailable("purchase result payload is invalid JSON") from exc
    return result


def _normalize_user_and_operation(
    *,
    user_id: Any,
    purchase_operation_id: Any,
    offer_id: Any,
) -> tuple[int, str, str]:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise CoinPurchaseError("user_id must be a positive authenticated integer")
    if not isinstance(purchase_operation_id, str) or not purchase_operation_id.strip():
        raise CoinPurchaseError("purchase_operation_id must be non-empty text")
    if not isinstance(offer_id, str) or not offer_id.strip():
        raise UnknownOffer("offer_id must be non-empty text")
    return user_id, purchase_operation_id.strip(), offer_id.strip()


def _is_missing_schema_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "no such table",
            "does not exist",
            "undefined table",
            "undefined column",
            "relation ",
            "column ",
        )
    )


def _purchase_operation(
    conn: Any,
    *,
    user_id: int,
    purchase_operation_id: str,
) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            f"""SELECT user_id, purchase_operation_id, offer_id,
                        request_fingerprint, offer_version, currency_type,
                        resolved_price, reward_id, reward_quantity,
                        destination, acquisition_class, operation_status,
                        result_payload, lineage_event_id, created_at,
                        updated_at, committed_at
                   FROM {TABLE_NAME}
                  WHERE user_id=? AND purchase_operation_id=?""",
            (user_id, purchase_operation_id),
        ).fetchone()
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("C019 purchase operation schema is unavailable") from exc
        raise
    return _row_to_dict(row)


def _request_fingerprint(offer: CoinShopOffer) -> str:
    encoded = json.dumps(
        offer.canonical_identity(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _replay_or_fail(
    existing: Mapping[str, Any],
    *,
    offer_id: str,
) -> CoinPurchaseResult:
    if str(existing.get("offer_id")) != offer_id:
        raise PurchaseOperationConflict(existing)
    status = existing.get("operation_status")
    if status == "COMMITTED":
        return CoinPurchaseResult.from_payload(
            existing.get("result_payload") or {}, replayed=True
        )
    if status == "IN_PROGRESS":
        raise PurchaseOperationInProgress(existing)
    raise SchemaUnavailable(f"unsupported purchase operation status: {status!r}")


def read_coin_balance(conn: Any, *, user_id: int) -> int:
    """Read the existing ``user_stats.coins`` authority; no ledger is created."""

    try:
        row = conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (user_id,)
        ).fetchone()
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("user_stats.coins authority is unavailable") from exc
        raise
    if row is None:
        raise CoinPurchaseError("authenticated player does not exist", details={"user_id": user_id})
    try:
        return int(row["coins"] if hasattr(row, "keys") else row[0] or 0)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise SchemaUnavailable("user_stats.coins is not readable") from exc


def spend_coins_in_transaction(
    conn: Any,
    *,
    user_id: int,
    amount: int,
    reason: str,
) -> CoinBalanceChange:
    """Transaction-safe adapter over the canonical ``user_stats.coins`` row.

    This deliberately mirrors the existing `_spend_coins` conditional update
    and `currency_log` evidence without introducing a second balance authority.
    """

    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise CoinDebitFailed("Coin debit amount must be a positive integer")
    # This read validates that the authenticated player exists, but it is
    # intentionally not used as the successful result's canonical
    # ``coins_before``.  Another committed transaction may win the row update
    # between this read and the conditional debit.
    read_coin_balance(conn, user_id=user_id)
    try:
        updated = conn.execute(
            "UPDATE user_stats SET coins=COALESCE(coins,0)-? "
            "WHERE user_id=? AND COALESCE(coins,0)>=?",
            (amount, user_id, amount),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("user_stats.coins spend authority is unavailable") from exc
        raise CoinDebitFailed("Coin debit failed") from exc
    if getattr(updated, "rowcount", 0) != 1:
        current = read_coin_balance(conn, user_id=user_id)
        raise InsufficientCoins(balance=current, required=amount)
    coins_after = read_coin_balance(conn, user_id=user_id)
    # The conditional UPDATE owns the row lock through the caller's commit.
    # Reconstruct the actual transition from authoritative post-update state
    # so PostgreSQL READ COMMITTED retries cannot report a stale pre-read.
    coins_before = coins_after + amount
    try:
        conn.execute(
            "INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) "
            "VALUES(?,?,?,?,?)",
            (
                user_id,
                -amount,
                coins_after,
                reason,
                _timestamp(conn),
            ),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("currency_log authority is unavailable") from exc
        raise CoinDebitFailed("Coin debit audit failed") from exc
    return CoinBalanceChange(
        coins_before=coins_before,
        coins_spent=amount,
        coins_after=coins_after,
    )


class SqlAcquisitionAuthority:
    """Scoped adapter for the repository's existing ownership tables.

    It does not create a generic item ledger.  Each supported destination is
    written directly to its current authority: ``shop_inventory`` for
    stackable inventory quantities, ``player_inventory`` for functional or
    inventory-only equipment records, and ``player_wardrobe`` for pure
    cosmetic ownership.
    """

    def acquire(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
        purchase_operation_id: str,
    ) -> AcquisitionOutcome:
        del purchase_operation_id
        if offer.item_id in AUTHORITY_HOLD_ITEM_IDS:
            raise AcquisitionFailed(
                "xp_amulet remains HOLD_FOR_AUTHORITY and cannot be sold by C019"
            )
        if offer.item_id in INVENTORY_ONLY_ITEM_IDS:
            raise AcquisitionFailed(
                "go_stone_black is inventory-only and has no Coin Shop sale authority"
            )
        if offer.destination == "shop_inventory":
            return self._acquire_stackable_inventory(conn, user_id=user_id, offer=offer)
        if offer.destination == "player_inventory":
            return self._acquire_equipment_inventory(conn, user_id=user_id, offer=offer)
        if offer.destination == "player_wardrobe":
            return self._acquire_wardrobe(conn, user_id=user_id, offer=offer)
        raise OwnershipAuthorityUnavailable(
            f"no C019 acquisition adapter for destination {offer.destination!r}"
        )

    def _acquire_stackable_inventory(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
    ) -> AcquisitionOutcome:
        if offer.duplicate_policy != "STACK":
            raise AcquisitionFailed(
                "stackable inventory offer must declare duplicate_policy=STACK"
            )
        try:
            existing = conn.execute(
                "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
                (user_id, offer.item_id),
            ).fetchone()
            old_quantity = int(existing["qty"] if existing else 0)
            conn.execute(
                "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(?,?,?) "
                "ON CONFLICT(user_id,item_key) DO UPDATE SET "
                "qty=shop_inventory.qty+excluded.qty",
                (user_id, offer.item_id, offer.quantity),
            )
            current = conn.execute(
                "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
                (user_id, offer.item_id),
            ).fetchone()
        except Exception as exc:
            if _is_missing_schema_error(exc):
                raise OwnershipAuthorityUnavailable(
                    "shop_inventory ownership authority is unavailable"
                ) from exc
            raise AcquisitionFailed("stackable inventory acquisition failed") from exc
        if current is None:
            raise AcquisitionFailed("stackable inventory result was not recoverable")
        new_quantity = int(current["qty"] if hasattr(current, "keys") else current[0])
        return AcquisitionOutcome(
            destination=offer.destination,
            item_id=offer.item_id,
            quantity=offer.quantity,
            new_quantity=new_quantity,
            ownership_state="QUANTITY_OWNED",
            is_new=old_quantity <= 0,
            can_equip=False,
            can_use=offer.acquisition_class in CONSUMABLE_CLASSES,
            can_wear=False,
            presentation_metadata=offer.presentation_metadata,
        )

    def _acquire_equipment_inventory(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
    ) -> AcquisitionOutcome:
        if offer.acquisition_class not in FUNCTIONAL_EQUIPMENT_CLASSES | {"TROPHY"}:
            raise AcquisitionFailed(
                "player_inventory destination requires equipment or trophy class"
            )
        if offer.quantity != 1:
            raise AcquisitionFailed(
                "player_inventory equipment offers must have quantity=1"
            )
        if offer.duplicate_policy == "UNSPECIFIED":
            raise AcquisitionFailed("equipment offer duplicate policy is undefined")
        try:
            existing = conn.execute(
                "SELECT COUNT(*) AS item_count FROM player_inventory "
                "WHERE user_id=? AND equip_id=?",
                (user_id, offer.item_id),
            ).fetchone()
            existing_count = int(
                existing["item_count"] if hasattr(existing, "keys") else existing[0]
            ) if existing else 0
            if offer.duplicate_policy == "REJECT_IF_OWNED" and existing_count > 0:
                raise AcquisitionFailed(
                    "equipment is already owned; duplicate purchase is unsupported",
                    details={"item_id": offer.item_id},
                )
            if offer.duplicate_policy not in {"ALLOW_DUPLICATE", "REJECT_IF_OWNED"}:
                raise AcquisitionFailed(
                    "equipment offer duplicate policy is unsupported"
                )
            conn.execute(
                "INSERT INTO player_inventory"
                "(user_id,equip_id,equipped,obtained_at,source) "
                "VALUES(?,?,0,?,?)",
                (
                    user_id,
                    offer.item_id,
                    _timestamp(conn),
                    "coin_shop",
                ),
            )
            row = conn.execute(
                "SELECT COUNT(*) AS item_count FROM player_inventory "
                "WHERE user_id=? AND equip_id=?",
                (user_id, offer.item_id),
            ).fetchone()
        except CoinPurchaseError:
            raise
        except Exception as exc:
            if _is_missing_schema_error(exc):
                raise OwnershipAuthorityUnavailable(
                    "player_inventory ownership authority is unavailable"
                ) from exc
            raise AcquisitionFailed("equipment inventory acquisition failed") from exc
        count = int(row["item_count"] if hasattr(row, "keys") else row[0]) if row else 0
        can_equip = (
            offer.acquisition_class in FUNCTIONAL_EQUIPMENT_CLASSES
            and offer.item_id not in AUTHORITY_HOLD_ITEM_IDS
            and offer.item_id not in INVENTORY_ONLY_ITEM_IDS
        )
        return AcquisitionOutcome(
            destination=offer.destination,
            item_id=offer.item_id,
            quantity=offer.quantity,
            new_quantity=count,
            ownership_state="TROPHY_OWNED" if offer.acquisition_class == "TROPHY" else "EQUIPMENT_OWNED",
            is_new=existing_count == 0,
            can_equip=can_equip,
            can_use=False,
            can_wear=False,
            presentation_metadata=offer.presentation_metadata,
        )

    def _acquire_wardrobe(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
    ) -> AcquisitionOutcome:
        if offer.acquisition_class != "COSMETIC":
            raise AcquisitionFailed("player_wardrobe destination requires COSMETIC class")
        if offer.quantity != 1:
            raise AcquisitionFailed(
                "player_wardrobe cosmetic offers must have quantity=1"
            )
        if offer.duplicate_policy != "REJECT_IF_OWNED":
            raise AcquisitionFailed(
                "cosmetic offer must declare duplicate_policy=REJECT_IF_OWNED"
            )
        try:
            inserted = conn.execute(
                "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) "
                "VALUES(?,?,?,?) ON CONFLICT(user_id,item_id) DO NOTHING",
                (user_id, offer.item_id, _timestamp(conn), "coin_shop"),
            )
        except Exception as exc:
            if _is_missing_schema_error(exc):
                raise OwnershipAuthorityUnavailable(
                    "player_wardrobe ownership authority is unavailable"
                ) from exc
            raise AcquisitionFailed("wardrobe acquisition failed") from exc
        if getattr(inserted, "rowcount", 0) != 1:
            raise AcquisitionFailed(
                "cosmetic is already owned; duplicate purchase is unsupported",
                details={"item_id": offer.item_id},
            )
        return AcquisitionOutcome(
            destination=offer.destination,
            item_id=offer.item_id,
            quantity=offer.quantity,
            new_quantity=1,
            ownership_state="COSMETIC_OWNED",
            is_new=True,
            can_equip=False,
            can_use=False,
            can_wear=True,
            presentation_metadata=offer.presentation_metadata,
        )


LineageWriter = Callable[..., Mapping[str, Any]]
CoinSpendFunction = Callable[..., CoinBalanceChange]


def append_shop_acquisition_lineage(
    conn: Any,
    *,
    user_id: int,
    purchase_operation_id: str,
    offer: CoinShopOffer,
    result: CoinPurchaseResult,
) -> Mapping[str, Any]:
    """Append one D5A acquisition event in the caller's transaction."""

    lineage_id = f"coin-purchase:{user_id}:{purchase_operation_id}"
    payload = {
        "operation": "ACQUIRE",
        "source": SHOP_SOURCE,
        "source_operation_id": purchase_operation_id,
        "offer_id": offer.offer_id,
        "offer_version": offer.offer_version,
        "item_id": offer.item_id,
        "quantity": offer.quantity,
        "currency_type": offer.currency_type,
        "resolved_price": offer.price,
        "destination": offer.destination,
        "acquisition_class": offer.acquisition_class,
        "ownership_result": dict(result.ownership_result),
        "coins_spent": result.coins_spent,
        "coins_after": result.coins_after,
        "ownership_authority": offer.destination,
    }
    try:
        return append_event(
            conn,
            event_type="ITEM_ACQUISITION",
            player_id=str(user_id),
            lineage_id=lineage_id,
            source_event_id=f"purchase:{user_id}:{purchase_operation_id}",
            idempotency_key=f"coin-purchase-acquisition:{purchase_operation_id}",
            outcome="SUCCESS",
            payload=payload,
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("D5A acquisition lineage schema is unavailable") from exc
        raise AcquisitionFailed("D5A acquisition lineage append failed") from exc


def _validate_acquisition_outcome(
    outcome: AcquisitionOutcome,
    *,
    offer: CoinShopOffer,
) -> None:
    if not isinstance(outcome, AcquisitionOutcome):
        raise AcquisitionFailed("acquisition authority returned an invalid result")
    if outcome.item_id != offer.item_id or outcome.destination != offer.destination:
        raise AcquisitionFailed("acquisition result does not match resolved offer")
    if outcome.quantity != offer.quantity:
        raise AcquisitionFailed("acquisition result quantity does not match resolved offer")


def purchase_with_coins(
    conn: Any,
    user_id: int,
    purchase_operation_id: str,
    offer_id: str,
    *,
    offer_authority: ShopOfferAuthority,
    acquisition_authority: AcquisitionAuthority | None = None,
    client_price: Any = None,
    spend_coins: CoinSpendFunction | None = None,
    lineage_writer: LineageWriter | None = None,
    now: datetime | None = None,
) -> CoinPurchaseResult:
    """Execute one atomic server-resolved Coin purchase.

    ``client_price`` is accepted only as a compatibility/test probe and is
    intentionally ignored.  The service never trusts client price, quantity,
    reward, destination, or effect data.  All mutations are caller-owned:
    commit the surrounding transaction only after this returns successfully.
    """

    del client_price
    user_id, purchase_operation_id, offer_id = _normalize_user_and_operation(
        user_id=user_id,
        purchase_operation_id=purchase_operation_id,
        offer_id=offer_id,
    )
    if offer_authority is None:
        raise UnknownOffer("server offer authority is unavailable")

    # A committed operation is authoritative even if a later catalog refresh
    # disables or reprices the offer.  This is what makes response-loss replay
    # deterministic, while a different offer_id fails before any new lookup.
    existing = _purchase_operation(
        conn,
        user_id=user_id,
        purchase_operation_id=purchase_operation_id,
    )
    if existing is not None:
        return _replay_or_fail(existing, offer_id=offer_id)

    try:
        offer = offer_authority.resolve(offer_id)
    except ShopOfferNotFound as exc:
        raise UnknownOffer(str(exc)) from exc
    except ShopOfferError as exc:
        raise UnknownOffer("server offer contract is invalid") from exc
    if offer.currency_type != COIN_CURRENCY:
        raise UnknownOffer("C019 accepts only Coin offers")
    if offer.status != "ACTIVE":
        raise UnknownOffer("offer is not active")
    try:
        offer_authority.check_eligibility(conn, user_id=user_id, offer=offer)
    except ShopOfferNotEligible as exc:
        raise OfferNotEligible(str(exc)) from exc
    except ShopOfferError as exc:
        raise OfferNotEligible("offer eligibility check failed") from exc
    except CoinPurchaseError:
        raise
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("offer eligibility authority is unavailable") from exc
        raise OfferNotEligible("offer eligibility check failed") from exc

    request_fingerprint = _request_fingerprint(offer)
    timestamp = _timestamp(conn, now)
    try:
        inserted = conn.execute(
            f"""INSERT INTO {TABLE_NAME}(
                        user_id, purchase_operation_id, offer_id,
                        request_fingerprint, offer_version, currency_type,
                        resolved_price, reward_id, reward_quantity,
                        destination, acquisition_class, operation_status,
                        result_payload, lineage_event_id, created_at,
                        updated_at, committed_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
                    ON CONFLICT(user_id, purchase_operation_id) DO NOTHING""",
            (
                user_id,
                purchase_operation_id,
                offer.offer_id,
                request_fingerprint,
                offer.offer_version,
                offer.currency_type,
                offer.price,
                offer.item_id,
                offer.quantity,
                offer.destination,
                offer.acquisition_class,
                "IN_PROGRESS",
                _json_parameter(conn, {}),
                None,
                timestamp,
                timestamp,
            ),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("C019 purchase operation schema is unavailable") from exc
        raise CoinPurchaseError("purchase operation reservation failed") from exc

    reservation_inserted = getattr(inserted, "rowcount", 0) == 1
    reserved = _purchase_operation(
        conn,
        user_id=user_id,
        purchase_operation_id=purchase_operation_id,
    )
    if reserved is None:
        raise SchemaUnavailable("purchase operation reservation was not recoverable")
    if not reservation_inserted:
        # Another transaction won the unique operation identity gate.  Never
        # run debit/acquisition on this branch.
        if reserved.get("request_fingerprint") != request_fingerprint:
            raise PurchaseOperationConflict(reserved)
        return _replay_or_fail(reserved, offer_id=offer_id)

    spend = spend_coins or spend_coins_in_transaction
    try:
        coin_change = spend(
            conn,
            user_id=user_id,
            amount=offer.price,
            reason=f"coin_purchase:{offer.offer_id}:{purchase_operation_id}",
        )
    except CoinPurchaseError:
        raise
    except Exception as exc:
        raise CoinDebitFailed("Coin debit authority failed") from exc
    if not isinstance(coin_change, CoinBalanceChange):
        raise CoinDebitFailed("Coin debit authority returned an invalid result")

    acquisition = acquisition_authority or SqlAcquisitionAuthority()
    try:
        ownership = acquisition.acquire(
            conn,
            user_id=user_id,
            offer=offer,
            purchase_operation_id=purchase_operation_id,
        )
        _validate_acquisition_outcome(ownership, offer=offer)
    except CoinPurchaseError:
        raise
    except Exception as exc:
        raise AcquisitionFailed("canonical acquisition failed") from exc

    provisional = CoinPurchaseResult(
        operation_id=purchase_operation_id,
        offer_id=offer.offer_id,
        item_id=offer.item_id,
        quantity=offer.quantity,
        source=SHOP_SOURCE,
        destination=offer.destination,
        coins_before=coin_change.coins_before,
        coins_spent=coin_change.coins_spent,
        coins_after=coin_change.coins_after,
        ownership_result=ownership.as_dict(),
        is_new=ownership.is_new,
        can_equip=ownership.can_equip,
        can_use=ownership.can_use,
        can_wear=ownership.can_wear,
        lineage_event_id="",
        offer_version=offer.offer_version,
    )
    writer = lineage_writer or append_shop_acquisition_lineage
    try:
        lineage = writer(
            conn,
            user_id=user_id,
            purchase_operation_id=purchase_operation_id,
            offer=offer,
            result=provisional,
        )
    except CoinPurchaseError:
        raise
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("D5A acquisition lineage authority is unavailable") from exc
        raise AcquisitionFailed("acquisition lineage writer failed") from exc
    lineage_event_id = str((lineage or {}).get("event_id") or "").strip()
    if not lineage_event_id:
        raise AcquisitionFailed("acquisition lineage result has no event_id")

    result = CoinPurchaseResult(
        operation_id=provisional.operation_id,
        offer_id=provisional.offer_id,
        item_id=provisional.item_id,
        quantity=provisional.quantity,
        source=provisional.source,
        destination=provisional.destination,
        coins_before=provisional.coins_before,
        coins_spent=provisional.coins_spent,
        coins_after=provisional.coins_after,
        ownership_result=provisional.ownership_result,
        is_new=provisional.is_new,
        can_equip=provisional.can_equip,
        can_use=provisional.can_use,
        can_wear=provisional.can_wear,
        lineage_event_id=lineage_event_id,
        offer_version=provisional.offer_version,
        replayed=False,
    )
    committed_at = _timestamp(conn, now)
    try:
        updated = conn.execute(
            f"""UPDATE {TABLE_NAME}
                   SET operation_status='COMMITTED', result_payload=?,
                       lineage_event_id=?, updated_at=?, committed_at=?
                 WHERE user_id=? AND purchase_operation_id=?
                   AND operation_status='IN_PROGRESS'""",
            (
                _json_parameter(conn, result.canonical_payload()),
                lineage_event_id,
                committed_at,
                committed_at,
                user_id,
                purchase_operation_id,
            ),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise SchemaUnavailable("C019 purchase operation schema is unavailable") from exc
        raise CoinPurchaseError("purchase result persistence failed") from exc
    if getattr(updated, "rowcount", 0) != 1:
        raise CoinPurchaseError("purchase operation was not committed")
    return result


__all__ = [
    "AUTHORITY_HOLD_ITEM_IDS",
    "AcquisitionFailed",
    "AcquisitionOutcome",
    "AcquisitionAuthority",
    "CoinBalanceChange",
    "CoinDebitFailed",
    "CoinPurchaseError",
    "CoinPurchaseResult",
    "InsufficientCoins",
    "INVENTORY_ONLY_ITEM_IDS",
    "OfferNotEligible",
    "OwnershipAuthorityUnavailable",
    "PurchaseOperationConflict",
    "PurchaseOperationInProgress",
    "SHOP_SOURCE",
    "SchemaUnavailable",
    "SqlAcquisitionAuthority",
    "UnknownOffer",
    "append_shop_acquisition_lineage",
    "purchase_with_coins",
    "read_coin_balance",
    "spend_coins_in_transaction",
]
