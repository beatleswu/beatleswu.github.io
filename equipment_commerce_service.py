"""Source-level Coin purchase service for functional Equipment.

This is a route-independent C043-C adapter. It consumes already server-owned
Shop facts, lets C025/C029 normalize the catalog and price, and delegates the
atomic Coin debit, C019 operation identity, D5A lineage, and result replay to
``coin_purchase_authority.purchase_with_coins``. The acquisition adapter uses
the existing B040 ownership writer to create exactly one unequipped
``player_inventory`` row.

The service intentionally has no HTTP, environment, schema-migration, payment,
loadout, or Production behavior. It never imports ``app.py``. Callers must
provide the real server catalog facts and the real server Equipment definition
snapshot; test fixtures may provide disposable equivalents.

Purchase and acquisition are not equip operations: no loadout service is
imported or called, and B040 always persists ``equipped=0``. A successful call
returns the unchanged C019 ``CoinPurchaseResult``. The caller owns commit and
rollback of the surrounding transaction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from typing import Any, Protocol, TypeAlias

from coin_purchase_authority import (
    AcquisitionFailed,
    AcquisitionOutcome,
    CoinBalanceChange,
    CoinPurchaseError,
    CoinPurchaseResult,
    OwnershipAuthorityUnavailable,
    purchase_with_coins,
)
from equipment_ownership_service import (
    EquipmentOwnershipError,
    EquipmentOwnershipResult,
    grant_equipment_ownership,
)
from question_idempotency import IdempotencyIdentityError, normalize_identity
from shop_offer_authority import (
    CoinShopOffer,
    ShopOfferAuthority,
    ShopOfferContractError,
    ShopOfferNotFound,
    StaticShopOfferAuthority,
)
from shop_offer_identity_projection import (
    OfferNotReady,
    ServerShopOfferFacts,
    ShopOfferIdentityError,
    normalize_shop_offer,
)


COIN_CURRENCY = "COINS"
EQUIPMENT_OFFER_PREFIX = "shop.static."
EQUIPMENT_DESTINATION = "player_inventory"
FUNCTIONAL_EQUIPMENT_CLASSES = frozenset({"WEAPON", "ARMOR", "ACCESSORY"})
EQUIPMENT_DUPLICATE_POLICIES = frozenset({"REJECT_IF_OWNED", "ALLOW_DUPLICATE"})
_EQUIPMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

ServerEquipmentOfferFact: TypeAlias = ServerShopOfferFacts | Mapping[str, Any]
CoinSpendFunction = Callable[..., CoinBalanceChange]
LineageWriter = Callable[..., Mapping[str, Any]]


class EquipmentCommerceError(CoinPurchaseError):
    """Base class for explicit, fail-closed Equipment purchase failures."""

    code = "EQUIPMENT_COMMERCE_FAILED"


class EquipmentPurchaseValidationError(EquipmentCommerceError):
    code = "INVALID_EQUIPMENT_PURCHASE"


class EquipmentOfferNotFound(EquipmentCommerceError):
    code = "UNKNOWN_EQUIPMENT_OFFER"


class EquipmentOfferInvalid(EquipmentCommerceError):
    code = "INVALID_EQUIPMENT_OFFER"


class EquipmentOfferNotReady(EquipmentCommerceError):
    code = "EQUIPMENT_OFFER_NOT_READY"


class EquipmentAlreadyOwned(AcquisitionFailed):
    """A unique Equipment offer was already owned before this operation."""

    code = "EQUIPMENT_ALREADY_OWNED"

    def __init__(self, *, user_id: int, equipment_id: str):
        self.user_id = user_id
        self.equipment_id = equipment_id
        super().__init__(
            "Equipment is already owned",
            details={
                "user_id": user_id,
                "equipment_id": equipment_id,
                "ownership_state": "EQUIPMENT_OWNED",
            },
        )


class EquipmentOfferAuthority(Protocol):
    """Resolve one current server-owned Shop fact by Equipment identity."""

    def resolve(self, equipment_id: str) -> ServerEquipmentOfferFact:
        """Return server facts; never accept client price or offer fields."""


class ServerFactEquipmentOfferAuthority:
    """Index an existing server-fact snapshot without copying its authority.

    The input is normally the existing Shop/catalog boundary's output. This
    helper only indexes ``item_id``/``item_key`` so the purchase service can
    request one fact. C025/C029 still perform the executable normalization and
    price validation when the fact is resolved.
    """

    def __init__(self, facts: Iterable[ServerEquipmentOfferFact]):
        by_identity: dict[str, ServerShopOfferFacts] = {}
        for raw in facts:
            try:
                fact = (
                    raw
                    if isinstance(raw, ServerShopOfferFacts)
                    else ServerShopOfferFacts.from_mapping(raw)
                )
            except ShopOfferIdentityError as exc:
                raise EquipmentOfferInvalid(
                    "server Equipment offer facts are invalid"
                ) from exc
            identities = {
                str(value).strip()
                for value in (fact.item_id, fact.item_key)
                if isinstance(value, str) and value.strip()
            }
            for identity in identities:
                if identity in by_identity:
                    raise EquipmentOfferInvalid(
                        "server Equipment offer identity is ambiguous",
                        details={"equipment_id": identity},
                    )
                by_identity[identity] = fact
        self._facts = by_identity

    def resolve(self, equipment_id: str) -> ServerShopOfferFacts:
        fact = self._facts.get(equipment_id)
        if fact is None:
            raise EquipmentOfferNotFound(
                "active server Equipment offer was not found",
                details={"equipment_id": equipment_id},
            )
        return fact


def _validate_equipment_id(value: Any) -> str:
    if not isinstance(value, str):
        raise EquipmentPurchaseValidationError(
            "equipment_id must be a server Equipment identity"
        )
    equipment_id = value.strip()
    if not _EQUIPMENT_ID_RE.fullmatch(equipment_id):
        raise EquipmentPurchaseValidationError(
            "equipment_id must contain only canonical identity characters"
        )
    return equipment_id


def _validate_user_and_operation(user_id: Any, operation_id: Any) -> tuple[int, str]:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise EquipmentPurchaseValidationError(
            "user_id must be a positive authenticated integer"
        )
    try:
        normalized_operation_id, _generated = normalize_identity(
            operation_id,
            field="purchase_operation_id",
            generate_if_missing=False,
        )
    except IdempotencyIdentityError as exc:
        raise EquipmentPurchaseValidationError(str(exc)) from exc
    return user_id, normalized_operation_id


def _server_fact_to_offer(
    raw_fact: ServerEquipmentOfferFact,
    *,
    equipment_id: str,
) -> CoinShopOffer:
    if isinstance(raw_fact, ServerShopOfferFacts):
        fact = raw_fact
    else:
        try:
            fact = ServerShopOfferFacts.from_mapping(raw_fact)
        except ShopOfferIdentityError as exc:
            raise EquipmentOfferInvalid(
                "server Equipment offer facts are invalid"
            ) from exc

    try:
        normalized = normalize_shop_offer(fact)
    except OfferNotReady as exc:
        raise EquipmentOfferNotReady(
            "server Equipment offer is not ready for C019",
            details={"equipment_id": equipment_id, "status": exc.status},
        ) from exc
    except ShopOfferIdentityError as exc:
        raise EquipmentOfferInvalid(
            "server Equipment offer cannot be normalized"
        ) from exc

    try:
        offer = CoinShopOffer.from_mapping(normalized.as_c019_mapping())
    except ShopOfferContractError as exc:
        raise EquipmentOfferInvalid(
            "normalized Equipment offer violates the C019 contract"
        ) from exc

    expected_offer_id = f"{EQUIPMENT_OFFER_PREFIX}{equipment_id}"
    if offer.offer_id != expected_offer_id:
        raise EquipmentOfferInvalid(
            "Equipment offer identity is not the canonical static Shop identity",
            details={
                "expected_offer_id": expected_offer_id,
                "offer_id": offer.offer_id,
            },
        )
    if offer.item_id != equipment_id:
        raise EquipmentOfferInvalid(
            "Equipment offer item identity does not match the requested Equipment",
            details={"equipment_id": equipment_id, "item_id": offer.item_id},
        )
    if offer.offer_type != "FIXED_ITEM":
        raise EquipmentOfferInvalid(
            "functional Equipment purchases must use a static fixed-item offer"
        )
    if offer.currency_type != COIN_CURRENCY:
        raise EquipmentOfferInvalid("Equipment purchase currency must be COINS")
    if offer.destination != EQUIPMENT_DESTINATION:
        raise EquipmentOfferInvalid(
            "Equipment purchase destination must be player_inventory"
        )
    if offer.acquisition_class not in FUNCTIONAL_EQUIPMENT_CLASSES:
        raise EquipmentOfferInvalid(
            "Equipment purchase requires a functional Equipment class"
        )
    if offer.quantity != 1:
        raise EquipmentOfferInvalid("Equipment purchase quantity must be one")
    if offer.duplicate_policy not in EQUIPMENT_DUPLICATE_POLICIES:
        raise EquipmentOfferInvalid(
            "Equipment purchase requires an explicit duplicate policy"
        )
    return offer


class _LazyEquipmentShopOfferAuthority:
    """Expose a C019 authority while preserving committed-operation replay."""

    def __init__(
        self,
        catalog_authority: EquipmentOfferAuthority,
        *,
        equipment_id: str,
        offer_id: str,
    ) -> None:
        self._catalog_authority = catalog_authority
        self._equipment_id = equipment_id
        self._offer_id = offer_id
        self._delegate: StaticShopOfferAuthority | None = None

    def _delegate_authority(self) -> StaticShopOfferAuthority:
        if self._delegate is None:
            try:
                raw_fact = self._catalog_authority.resolve(self._equipment_id)
            except EquipmentCommerceError:
                raise
            except (KeyError, LookupError) as exc:
                raise EquipmentOfferNotFound(
                    "server Equipment offer was not found",
                    details={"equipment_id": self._equipment_id},
                ) from exc
            except Exception as exc:
                raise EquipmentOfferNotFound(
                    "server Equipment offer authority failed"
                ) from exc
            offer = _server_fact_to_offer(
                raw_fact,
                equipment_id=self._equipment_id,
            )
            self._delegate = StaticShopOfferAuthority({offer.offer_id: offer})
        return self._delegate

    def resolve(self, offer_id: str) -> CoinShopOffer:
        if offer_id != self._offer_id:
            raise ShopOfferNotFound("Equipment offer identity does not match request")
        return self._delegate_authority().resolve(offer_id)

    def check_eligibility(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
    ) -> None:
        self._delegate_authority().check_eligibility(
            conn,
            user_id=user_id,
            offer=offer,
        )


class EquipmentInventoryAcquisitionAuthority:
    """Adapt B040's exact ownership writer to the C019 acquisition protocol."""

    def __init__(self, equipment_defs: Iterable[Mapping[str, Any]]):
        if equipment_defs is None:
            raise EquipmentPurchaseValidationError(
                "server Equipment definitions must be explicitly bound"
            )
        self._equipment_defs = tuple(equipment_defs)
        if not self._equipment_defs:
            raise EquipmentPurchaseValidationError(
                "server Equipment definitions must not be empty"
            )

    @staticmethod
    def _existing_count(conn: Any, *, user_id: int, equipment_id: str) -> int:
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS item_count FROM player_inventory "
                "WHERE user_id=? AND equip_id=?",
                (user_id, equipment_id),
            ).fetchone()
        except Exception as exc:
            raise OwnershipAuthorityUnavailable(
                "player_inventory ownership authority is unavailable"
            ) from exc
        if row is None:
            return 0
        try:
            return int(row["item_count"] if hasattr(row, "keys") else row[0])
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            raise OwnershipAuthorityUnavailable(
                "player_inventory ownership count is not readable"
            ) from exc

    def acquire(
        self,
        conn: Any,
        *,
        user_id: int,
        offer: CoinShopOffer,
        purchase_operation_id: str,
    ) -> AcquisitionOutcome:
        del purchase_operation_id
        if offer.destination != EQUIPMENT_DESTINATION:
            raise AcquisitionFailed(
                "Equipment acquisition must target player_inventory"
            )
        if offer.acquisition_class not in FUNCTIONAL_EQUIPMENT_CLASSES:
            raise AcquisitionFailed("Equipment acquisition class is unsupported")
        if offer.quantity != 1:
            raise AcquisitionFailed("Equipment acquisition quantity must be one")
        if offer.duplicate_policy not in EQUIPMENT_DUPLICATE_POLICIES:
            raise AcquisitionFailed("Equipment duplicate policy is unsupported")

        existing_count = self._existing_count(
            conn,
            user_id=user_id,
            equipment_id=offer.item_id,
        )
        if offer.duplicate_policy == "REJECT_IF_OWNED" and existing_count:
            raise EquipmentAlreadyOwned(
                user_id=user_id,
                equipment_id=offer.item_id,
            )

        try:
            ownership: EquipmentOwnershipResult = grant_equipment_ownership(
                conn,
                user_id,
                offer.item_id,
                "coin_shop",
                equipment_defs=self._equipment_defs,
            )
        except EquipmentOwnershipError as exc:
            raise AcquisitionFailed(
                f"canonical Equipment ownership failed: {exc.code}",
                details={"equipment_id": offer.item_id, "ownership_error": exc.code},
            ) from exc

        if ownership.equipped is not False:
            raise AcquisitionFailed("Equipment purchase attempted to equip an item")
        if ownership.equip_id != offer.item_id or ownership.user_id != user_id:
            raise AcquisitionFailed(
                "canonical Equipment ownership result does not match purchase"
            )

        return AcquisitionOutcome(
            destination=offer.destination,
            item_id=offer.item_id,
            quantity=offer.quantity,
            new_quantity=existing_count + 1,
            ownership_state="EQUIPMENT_OWNED",
            is_new=existing_count == 0,
            can_equip=True,
            can_use=False,
            can_wear=False,
            presentation_metadata=offer.presentation_metadata,
            ownership_reference=f"player_inventory:{ownership.row_id}",
        )


def purchase_equipment_with_coins(
    conn: Any,
    user_id: Any,
    purchase_operation_id: Any,
    equipment_id: Any,
    *,
    catalog_authority: EquipmentOfferAuthority,
    equipment_defs: Iterable[Mapping[str, Any]],
    acquisition_authority: EquipmentInventoryAcquisitionAuthority | None = None,
    spend_coins: CoinSpendFunction | None = None,
    lineage_writer: LineageWriter | None = None,
    now: Any = None,
) -> CoinPurchaseResult:
    """Purchase one server-catalogued Equipment item with Coins.

    The operation identity is required and is bound to the authenticated user
    by C019's existing primary key. The static C029 offer identity is derived
    from the validated Equipment identity; price, quantity, destination, slot,
    and duplicate policy come only from the resolved server facts. A committed
    retry is replayed by C019 before the catalog authority is consulted, so a
    later catalog refresh cannot cause a second debit or acquisition.
    """

    if catalog_authority is None:
        raise EquipmentPurchaseValidationError(
            "server Equipment catalog authority is required"
        )
    user_id, operation_id = _validate_user_and_operation(
        user_id,
        purchase_operation_id,
    )
    equipment_id = _validate_equipment_id(equipment_id)
    offer_id = f"{EQUIPMENT_OFFER_PREFIX}{equipment_id}"
    offer_authority: ShopOfferAuthority = _LazyEquipmentShopOfferAuthority(
        catalog_authority,
        equipment_id=equipment_id,
        offer_id=offer_id,
    )
    acquisition = acquisition_authority or EquipmentInventoryAcquisitionAuthority(
        equipment_defs
    )
    return purchase_with_coins(
        conn,
        user_id,
        operation_id,
        offer_id,
        offer_authority=offer_authority,
        acquisition_authority=acquisition,
        spend_coins=spend_coins,
        lineage_writer=lineage_writer,
        now=now,
    )


__all__ = [
    "COIN_CURRENCY",
    "EQUIPMENT_DESTINATION",
    "EQUIPMENT_DUPLICATE_POLICIES",
    "EQUIPMENT_OFFER_PREFIX",
    "FUNCTIONAL_EQUIPMENT_CLASSES",
    "EquipmentAlreadyOwned",
    "EquipmentCommerceError",
    "EquipmentInventoryAcquisitionAuthority",
    "EquipmentOfferAuthority",
    "EquipmentOfferInvalid",
    "EquipmentOfferNotFound",
    "EquipmentOfferNotReady",
    "EquipmentPurchaseValidationError",
    "ServerEquipmentOfferFact",
    "ServerFactEquipmentOfferAuthority",
    "purchase_equipment_with_coins",
]
