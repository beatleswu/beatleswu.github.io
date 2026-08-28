"""F028 Battlefield Boss first-clear Mapping A reward service.

This module is the route-independent acquisition boundary for the current
Adventure/Battlefield Boss flow.  The caller must first obtain the
server-authoritative settlement returned by ``_adventure_boss_record_attempt``;
this service never decides whether a Boss was cleared and never reads client
score, selected-zone, modal, or animation state.

The service composes that first-clear winner with the accepted F027 wardrobe
runtime contract:

    authoritative Boss settlement
        -> locked Mapping A reward identity
        -> existing player_wardrobe ownership row
        -> detached server-authored response result

``player_wardrobe`` is the existing ownership authority.  The unique
``(user_id, item_id)`` constraint and ``INSERT OR IGNORE`` make retries
converge without a second cosmetic ledger.  The caller owns the surrounding
transaction; this module deliberately never commits or rolls back.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Final

from mapping_a_wardrobe_runtime import (
    MAPPING_A_CATALOG,
    MAPPING_A_COMBAT_POWER,
    MAPPING_A_ID_COUNT,
    MappingAWardrobeRuntimeError,
    validate_mapping_a_catalog,
)


F028_REWARD_SERVICE_VERSION: Final[str] = (
    "F028_BATTLEFIELD_BOSS_MAPPING_A_FIRST_CLEAR_V1"
)
WARDROBE_OWNERSHIP_AUTHORITY: Final[str] = "player_wardrobe"
REWARD_SOURCE: Final[str] = "battlefield_boss_first_clear"
GRANT_CONDITION: Final[str] = "BOSS_FIRST_CLEAR"

GRANTED: Final[str] = "GRANTED"
ALREADY_OWNED: Final[str] = "ALREADY_OWNED"
NO_REWARD: Final[str] = "NO_REWARD"

# These are the canonical persisted Adventure zone keys in the same order as
# the current app's ADVENTURE_ZONES registry.  F027's Z1..Z10 identities are
# deliberately reused below; no second item-id list is created here.
BATTLEFIELD_BOSS_ZONE_KEYS: Final[tuple[str, ...]] = (
    "k26_30",
    "k21_25",
    "k16_20",
    "k11_15",
    "k6_10",
    "k1_5",
    "d1_2",
    "d3_4",
    "d5_6",
    "d7_plus",
)

_MAPPING_A_BY_ZONE: Final[Mapping[str, Any]] = MappingProxyType(
    {entry.zone: entry for entry in MAPPING_A_CATALOG}
)
BATTLEFIELD_BOSS_MAPPING_A_ZONE_BY_ZONE: Final[Mapping[str, str]] = MappingProxyType(
    {
        boss_zone: f"Z{position}"
        for position, boss_zone in enumerate(BATTLEFIELD_BOSS_ZONE_KEYS, start=1)
    }
)
BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE: Final[Mapping[str, str]] = MappingProxyType(
    {
        boss_zone: _MAPPING_A_BY_ZONE[mapping_zone].item_id
        for boss_zone, mapping_zone in BATTLEFIELD_BOSS_MAPPING_A_ZONE_BY_ZONE.items()
    }
)

_SETTLEMENT_KEYS: Final[frozenset[str]] = frozenset(
    {"operation_id", "is_replay", "is_first_clear"}
)
_RESULT_STATUSES: Final[frozenset[str]] = frozenset(
    {GRANTED, ALREADY_OWNED, NO_REWARD}
)


class BattlefieldBossRewardError(ValueError):
    """Expected fail-closed F028 validation error."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class BattlefieldBossFirstClearSettlement:
    """Typed handoff from the authoritative Boss progress transition.

    ``operation_id``, ``is_first_clear``, and ``is_replay`` must come from the
    server's ``_adventure_boss_record_attempt`` result.  A raw request mapping
    or an arbitrary reward id cannot be used as this handoff.
    """

    user_id: int
    zone_key: str
    operation_id: str
    passed: bool
    is_first_clear: bool
    is_replay: bool

    def __post_init__(self) -> None:
        if type(self.user_id) is not int or self.user_id <= 0:
            raise BattlefieldBossRewardError(
                "INVALID_AUTHENTICATED_USER",
                "Boss reward settlement requires a positive authenticated user id",
            )
        if (
            type(self.zone_key) is not str
            or not self.zone_key
            or self.zone_key != self.zone_key.strip()
        ):
            raise BattlefieldBossRewardError(
                "MALFORMED_ZONE_KEY",
                "Boss reward settlement requires an exact non-empty zone key",
            )
        if type(self.operation_id) is not str or not self.operation_id:
            raise BattlefieldBossRewardError(
                "MALFORMED_OPERATION_ID",
                "Boss reward settlement requires a server operation id",
            )
        expected_operation_id = (
            f"adventure:first_clear:{self.user_id}:{self.zone_key}"
        )
        if self.operation_id != expected_operation_id:
            raise BattlefieldBossRewardError(
                "OPERATION_ID_MISMATCH",
                "Boss reward operation id is not bound to the authenticated user and zone",
            )
        for name in ("passed", "is_first_clear", "is_replay"):
            if type(getattr(self, name)) is not bool:
                raise BattlefieldBossRewardError(
                    "MALFORMED_SETTLEMENT",
                    f"Boss settlement field {name} must be a boolean",
                )
        if self.is_first_clear and (not self.passed or self.is_replay):
            raise BattlefieldBossRewardError(
                "INVALID_FIRST_CLEAR_SETTLEMENT",
                "a first-clear winner must be a passed, non-replay settlement",
            )

    @classmethod
    def from_authoritative_attempt(
        cls,
        *,
        user_id: int,
        zone_key: str,
        passed: bool,
        attempt_result: Mapping[str, Any],
    ) -> "BattlefieldBossFirstClearSettlement":
        """Build a typed handoff from the existing internal attempt result.

        This factory intentionally accepts exactly the three keys returned by
        ``_adventure_boss_record_attempt``.  In particular, a request-body
        ``reward_id`` or client-provided first-clear flag is rejected rather
        than becoming reward authority.
        """

        if not isinstance(attempt_result, Mapping):
            raise BattlefieldBossRewardError(
                "SETTLEMENT_TYPE_REQUIRED",
                "Boss reward settlement must come from the server attempt result",
            )
        if set(attempt_result.keys()) != _SETTLEMENT_KEYS:
            raise BattlefieldBossRewardError(
                "SETTLEMENT_SHAPE_INVALID",
                "Boss reward settlement has unexpected or missing authority fields",
            )
        return cls(
            user_id=user_id,
            zone_key=zone_key,
            operation_id=attempt_result["operation_id"],
            passed=passed,
            is_first_clear=attempt_result["is_first_clear"],
            is_replay=attempt_result["is_replay"],
        )


@dataclass(frozen=True, slots=True)
class BattlefieldBossMappingAReward:
    """Resolved server-authored reward identity for one persisted Boss zone."""

    zone_key: str
    mapping_a_zone: str
    item_id: str
    slot: str
    display_name: str
    rarity: str | None
    icon: str | None
    presentation: Mapping[str, Any]

    @property
    def combat_power(self) -> int:
        return MAPPING_A_COMBAT_POWER


@dataclass(frozen=True, slots=True)
class BattlefieldBossRewardResult:
    """Detached, server-authored result after one ownership attempt."""

    contract_version: str
    status: str
    user_id: int
    zone_key: str
    operation_id: str
    mapping_a_zone: str
    passed: bool
    first_clear: bool
    replay: bool
    entitlement_consumed: bool
    item_id: str | None
    slot: str | None
    display_name: str | None
    rarity: str | None
    icon: str | None
    presentation: Mapping[str, Any]
    ownership_row_id: int | None
    ownership_source: str | None
    obtained_at: str | None
    reason_code: str | None

    def __post_init__(self) -> None:
        if self.contract_version != F028_REWARD_SERVICE_VERSION:
            raise ValueError("unsupported F028 reward result contract")
        if self.status not in _RESULT_STATUSES:
            raise ValueError(f"unsupported F028 reward status: {self.status}")
        for name in (
            "passed",
            "first_clear",
            "replay",
            "entitlement_consumed",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if self.entitlement_consumed is not self.first_clear:
            raise ValueError("only the authoritative first-clear winner consumes entitlement")
        if self.status in {GRANTED, ALREADY_OWNED}:
            if not self.first_clear or not self.passed or not self.item_id:
                raise ValueError("an acquired reward requires a passed first-clear winner")
            if type(self.ownership_row_id) is not int or self.ownership_row_id <= 0:
                raise ValueError("an acquired reward requires its exact ownership row id")
            if not self.ownership_source or not self.obtained_at:
                raise ValueError("an acquired reward requires persisted ownership metadata")
        else:
            if self.item_id is not None or self.ownership_row_id is not None:
                raise ValueError("a no-reward result cannot expose a persisted grant")

    @property
    def is_new(self) -> bool:
        return self.status == GRANTED

    @property
    def already_owned(self) -> bool:
        return self.status == ALREADY_OWNED

    def as_response(self) -> dict[str, Any]:
        """Return an additive presentation-ready response projection."""

        reward_item = None
        if self.item_id is not None:
            reward_item = {
                "id": self.item_id,
                "item_id": self.item_id,
                "slot": self.slot,
                "display_name": self.display_name,
                "rarity": self.rarity,
                "icon": self.icon,
                "presentation": dict(self.presentation),
                "ownership_authority": WARDROBE_OWNERSHIP_AUTHORITY,
                "ownership_source": WARDROBE_OWNERSHIP_AUTHORITY,
                "source": self.ownership_source,
                "obtained_at": self.obtained_at,
                "ownership_row_id": self.ownership_row_id,
                "grant_id": f"player_wardrobe:{self.ownership_row_id}",
                "source_operation_id": self.operation_id,
                "grant_condition": GRANT_CONDITION,
                "one_time": True,
                "new": self.is_new,
                "already_owned": self.already_owned,
                "duplicate": False,
                "grant_status": "granted" if self.is_new else "already_owned",
                "equipped": False,
                "auto_equipped": False,
                "presentation_only": True,
                "combat_power": MAPPING_A_COMBAT_POWER,
                "mapping_a_zone": self.mapping_a_zone,
                "boss_zone_key": self.zone_key,
            }
        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "passed": self.passed,
            "first_clear": self.first_clear,
            "replay": self.replay,
            "entitlement_consumed": self.entitlement_consumed,
            "entitlement_id": self.operation_id,
            "source_operation_id": self.operation_id,
            "item_id": self.item_id,
            "mapping_a_zone": self.mapping_a_zone,
            "ownership_authority": WARDROBE_OWNERSHIP_AUTHORITY,
            "ownership_persisted": self.ownership_row_id is not None,
            "ownership_row_id": self.ownership_row_id,
            "auto_equip": False,
            "auto_equipped": False,
            "compensation": False,
            "replacement_reward": False,
            "combat_power": MAPPING_A_COMBAT_POWER,
            "reward_item": reward_item,
            "reason_code": self.reason_code,
        }


def _reject(code: str, message: str) -> BattlefieldBossRewardError:
    return BattlefieldBossRewardError(code, message)


def _canonical_timestamp(value: Any) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise _reject("TIMESTAMP_MUST_BE_TIMEZONE_AWARE", "reward timestamp must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    if not isinstance(value, str) or not value or value != value.strip():
        raise _reject("MALFORMED_REWARD_TIMESTAMP", "reward timestamp must be a non-empty string")
    return value


def _pure_cosmetic_definition(
    item_id: str,
    definition: Mapping[str, Any],
    *,
    presentation_registry: Mapping[str, Mapping[str, Any]] | None,
    appearance_effects: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    """Reject a Mapping A identity that could become functional equipment."""

    if definition.get("functional_equipment") is True:
        raise _reject("MAPPING_A_FUNCTIONAL_ITEM", f"Mapping A item is functional: {item_id}")
    if definition.get("functional") is True:
        raise _reject("MAPPING_A_FUNCTIONAL_ITEM", f"Mapping A item is functional: {item_id}")
    if definition.get("combat_power") not in (None, False, 0):
        raise _reject("MAPPING_A_COMBAT_POWER_FORBIDDEN", f"Mapping A item has combat power: {item_id}")
    if definition.get("effects") not in (None, {}, [], (), ""):
        raise _reject("MAPPING_A_EFFECT_FORBIDDEN", f"Mapping A item has effects: {item_id}")
    if appearance_effects is not None and appearance_effects.get(item_id) not in (None, {}, [], (), ""):
        raise _reject("MAPPING_A_EFFECT_FORBIDDEN", f"Mapping A appearance effect is non-empty: {item_id}")

    presentation: Mapping[str, Any] = MappingProxyType(
        {
            "item_id": item_id,
            "slot": definition.get("slot"),
            "presentation_only": True,
            "combat_authority": "NO",
        }
    )
    if presentation_registry is not None:
        raw_presentation = presentation_registry.get(item_id)
        if not isinstance(raw_presentation, Mapping):
            raise _reject(
                "MAPPING_A_PRESENTATION_MISSING",
                f"Mapping A presentation metadata is missing: {item_id}",
            )
        if (
            raw_presentation.get("pure_presentation") is not True
            or raw_presentation.get("functional_effect_count") != 0
            or raw_presentation.get("combat_authority") != "NO"
        ):
            raise _reject(
                "MAPPING_A_PRESENTATION_NOT_COSMETIC",
                f"Mapping A presentation metadata is not pure cosmetic: {item_id}",
            )
        presentation = MappingProxyType(
            {
                **dict(raw_presentation),
                "item_id": item_id,
                "slot": definition.get("slot"),
                "presentation_only": True,
                "combat_authority": "NO",
            }
        )
    return presentation


def resolve_battlefield_boss_mapping_a_reward(
    zone_key: str,
    *,
    appearance_definitions: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None = None,
    presentation_registry: Mapping[str, Mapping[str, Any]] | None = None,
    appearance_effects: Mapping[str, Any] | None = None,
) -> BattlefieldBossMappingAReward:
    """Resolve one exact persisted Boss zone to the accepted F027 item.

    The caller cannot supply an item id.  The only identity input is the
    server-owned persisted zone key, and the item catalog is validated through
    F027's accepted runtime module.
    """

    if type(zone_key) is not str or not zone_key or zone_key != zone_key.strip():
        raise _reject("MALFORMED_ZONE_KEY", "Boss reward requires an exact zone key")
    mapping_a_zone = BATTLEFIELD_BOSS_MAPPING_A_ZONE_BY_ZONE.get(zone_key)
    if mapping_a_zone is None:
        raise _reject("UNKNOWN_ZONE", f"no Mapping A reward is authorized for zone {zone_key!r}")
    if MAPPING_A_ID_COUNT != 10 or len(MAPPING_A_CATALOG) != 10:
        raise _reject("MAPPING_A_CARDINALITY_INVALID", "F027 Mapping A must contain exactly ten ids")

    try:
        catalog = validate_mapping_a_catalog(appearance_definitions)
    except MappingAWardrobeRuntimeError as exc:
        raise _reject(exc.code, str(exc)) from exc

    entry = _MAPPING_A_BY_ZONE.get(mapping_a_zone)
    if entry is None:
        raise _reject("MAPPING_A_IDENTITY_MISSING", f"F027 mapping zone is missing: {mapping_a_zone}")
    definition = catalog.get(entry.item_id)
    if definition is None:
        raise _reject(
            "MISSING_MAPPING_ITEM",
            f"canonical Mapping A item is missing: {entry.item_id}",
        )
    if definition.get("id") != entry.item_id or definition.get("slot") != entry.slot:
        raise _reject(
            "MALFORMED_REWARD_IDENTITY",
            f"canonical Mapping A item identity is malformed: {entry.item_id}",
        )
    presentation = _pure_cosmetic_definition(
        entry.item_id,
        definition,
        presentation_registry=presentation_registry,
        appearance_effects=appearance_effects,
    )
    return BattlefieldBossMappingAReward(
        zone_key=zone_key,
        mapping_a_zone=mapping_a_zone,
        item_id=entry.item_id,
        slot=entry.slot,
        display_name=str(definition.get("name") or entry.item_id),
        rarity=definition.get("rarity"),
        icon=definition.get("emoji", definition.get("icon")),
        presentation=presentation,
    )


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _ownership_row(conn: Any, user_id: int, item_id: str) -> Any:
    return conn.execute(
        "SELECT id, item_id, obtained_at, source "
        "FROM player_wardrobe WHERE user_id=? AND item_id=?",
        (user_id, item_id),
    ).fetchone()


def _result(
    settlement: BattlefieldBossFirstClearSettlement,
    reward: BattlefieldBossMappingAReward,
    status: str,
    *,
    row: Any = None,
    reason_code: str | None = None,
) -> BattlefieldBossRewardResult:
    row_id = _row_value(row, "id")
    if row is not None and (type(row_id) is not int or row_id <= 0):
        raise RuntimeError("persisted wardrobe row did not expose an exact positive id")
    item_id = reward.item_id if row is not None else None
    reward_metadata = reward.presentation if row is not None else MappingProxyType({})
    ownership_source = _row_value(row, "source") if row is not None else None
    obtained_at = _row_value(row, "obtained_at") if row is not None else None
    return BattlefieldBossRewardResult(
        contract_version=F028_REWARD_SERVICE_VERSION,
        status=status,
        user_id=settlement.user_id,
        zone_key=settlement.zone_key,
        operation_id=settlement.operation_id,
        mapping_a_zone=reward.mapping_a_zone,
        passed=settlement.passed,
        first_clear=settlement.is_first_clear,
        replay=settlement.is_replay,
        entitlement_consumed=settlement.is_first_clear,
        item_id=item_id,
        slot=reward.slot if row is not None else None,
        display_name=reward.display_name if row is not None else None,
        rarity=reward.rarity if row is not None else None,
        icon=reward.icon if row is not None else None,
        presentation=reward_metadata,
        ownership_row_id=row_id,
        ownership_source=ownership_source,
        obtained_at=obtained_at,
        reason_code=reason_code,
    )


def grant_battlefield_boss_first_clear_reward(
    conn: Any,
    settlement: BattlefieldBossFirstClearSettlement,
    *,
    appearance_definitions: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None = None,
    presentation_registry: Mapping[str, Mapping[str, Any]] | None = None,
    appearance_effects: Mapping[str, Any] | None = None,
    obtained_at: Any = None,
) -> BattlefieldBossRewardResult:
    """Apply one server-authoritative first-clear cosmetic ownership grant.

    The operation is intentionally caller-transactional.  If the ownership
    insert raises, the exception is allowed to reach the caller; no success
    response is manufactured and the caller's transaction can roll back the
    Boss clear together with the attempted grant.
    """

    if type(settlement) is not BattlefieldBossFirstClearSettlement:
        raise _reject(
            "SETTLEMENT_TYPE_REQUIRED",
            "F028 reward service requires a typed server settlement",
        )
    reward = resolve_battlefield_boss_mapping_a_reward(
        settlement.zone_key,
        appearance_definitions=appearance_definitions,
        presentation_registry=presentation_registry,
        appearance_effects=appearance_effects,
    )

    if not settlement.is_first_clear:
        reason = "REPLAY_ALREADY_CLEARED" if settlement.is_replay else "BOSS_NOT_FIRST_CLEAR"
        return _result(settlement, reward, NO_REWARD, reason_code=reason)
    if not settlement.passed:
        return _result(
            settlement,
            reward,
            NO_REWARD,
            reason_code="BOSS_NOT_PASSED",
        )

    source = f"{REWARD_SOURCE}:{settlement.zone_key}"
    existing = _ownership_row(conn, settlement.user_id, reward.item_id)
    if existing is not None:
        return _result(settlement, reward, ALREADY_OWNED, row=existing)

    timestamp = _canonical_timestamp(obtained_at)
    # Existing schema authority: UNIQUE(user_id, item_id).  db.py translates
    # INSERT OR IGNORE to PostgreSQL ON CONFLICT DO NOTHING.  No commit occurs
    # here; the Boss finish caller owns the clear+reward transaction.
    inserted_cursor = conn.execute(
        "INSERT OR IGNORE INTO player_wardrobe "
        "(user_id, item_id, obtained_at, source) VALUES (?,?,?,?)",
        (settlement.user_id, reward.item_id, timestamp, source),
    )
    rowcount = int(getattr(inserted_cursor, "rowcount", 0) or 0)
    if rowcount not in (0, 1):
        raise RuntimeError("wardrobe ownership insert returned an invalid row count")
    persisted = _ownership_row(conn, settlement.user_id, reward.item_id)
    if persisted is None:
        raise RuntimeError("wardrobe ownership insert completed without a readable row")
    inserted_row_id = _row_value(persisted, "id")
    if type(inserted_row_id) is not int or inserted_row_id <= 0:
        raise RuntimeError("wardrobe ownership row did not expose an exact id")

    # Whether this call inserted or converged on a concurrent/retried row, the
    # durable outcome is one ownership row.  The first-clear transition itself
    # remains the entitlement-consumption authority.
    return _result(
        settlement,
        reward,
        GRANTED if rowcount == 1 else ALREADY_OWNED,
        row=persisted,
    )


__all__ = [
    "ALREADY_OWNED",
    "BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE",
    "BATTLEFIELD_BOSS_MAPPING_A_ZONE_BY_ZONE",
    "BATTLEFIELD_BOSS_ZONE_KEYS",
    "BattlefieldBossFirstClearSettlement",
    "BattlefieldBossMappingAReward",
    "BattlefieldBossRewardError",
    "BattlefieldBossRewardResult",
    "F028_REWARD_SERVICE_VERSION",
    "GRANTED",
    "NO_REWARD",
    "REWARD_SOURCE",
    "WARDROBE_OWNERSHIP_AUTHORITY",
    "grant_battlefield_boss_first_clear_reward",
    "resolve_battlefield_boss_mapping_a_reward",
]
