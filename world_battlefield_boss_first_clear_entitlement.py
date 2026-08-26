"""F022 Battlefield Boss first-clear entitlement authority.

F015 records every consumed Battlefield Boss settlement.  This module owns a
different question: whether the first dedicated reward for one user and Zone
has already been consumed.  It is intentionally separate from World
progression, Lord state, Quest state, wardrobe ownership, and D5A lineage.

The service accepts a validated F012 defeated fact and performs one
caller-owned transactional insert.  The database primary key
``(user_id, zone_key)`` is the authority for the lifetime V1 entitlement;
``reward_policy_version`` is retained as provenance and is never part of that
uniqueness key.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Final, Iterable

from migrations.world_battlefield_boss_first_clear_entitlement_v1 import (
    SOURCE_AUTHORITY,
    SOURCE_CONTRACT_VERSION,
    SOURCE_EVENT_TYPE,
    TABLE_NAME,
    validate_schema,
)
from world_monster_boundary_contract import (
    BATTLEFIELD_BOSS_CLASS,
    BattlefieldBossDefeatedFact,
)


POLICY_VERSION: Final[str] = "F022_BATTLEFIELD_BOSS_FIRST_CLEAR_MAPPING_A_V1"
MAPPING_A: Final[Mapping[str, str]] = MappingProxyType(
    {
        "zone_01": "back_pack",
        "zone_02": "hat_cloth",
        "zone_03": "hat_bamboo",
        "zone_04": "robe_crane",
        "zone_05": "hat_onihorns",
        "zone_06": "robe_dragon",
        "zone_07": "acc_dragon_pendant",
        "zone_08": "back_cloak",
        "zone_09": "hat_dragon_horn",
        "zone_10": "hat_celestial_crown",
    }
)

RECORDED: Final[str] = "RECORDED"
REPLAYED: Final[str] = "REPLAYED"
ALREADY_CLAIMED: Final[str] = "ALREADY_CLAIMED"
CONFLICT: Final[str] = "CONFLICT"
_STATUSES: Final[frozenset[str]] = frozenset(
    {RECORDED, REPLAYED, ALREADY_CLAIMED, CONFLICT}
)

_TEXT_LIMIT: Final[int] = 256
_PERSISTED_COLUMNS: Final[tuple[str, ...]] = (
    "user_id",
    "zone_key",
    "source_settlement_id",
    "source_encounter_operation_id",
    "source_monster_id",
    "eligibility_reference",
    "intent_replay_fingerprint",
    "source_authority",
    "source_event_type",
    "source_contract_version",
    "reward_item_id",
    "reward_policy_version",
    "claimed_at",
)
_IMMUTABLE_COLUMNS: Final[tuple[str, ...]] = _PERSISTED_COLUMNS[:-1]


class FirstClearEntitlementError(RuntimeError):
    """Base class for explicit F022 entitlement failures."""


class FirstClearEntitlementSchemaUnavailable(FirstClearEntitlementError):
    """The additive F022 schema is not present on the caller connection."""


class FirstClearEntitlementValidationError(
    ValueError,
    FirstClearEntitlementError,
):
    """A claim did not contain the required trusted F012/F022 facts."""


def _fail(code: str, message: str) -> None:
    raise FirstClearEntitlementValidationError(f"{code}: {message}")


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _execute(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    values = tuple(params)
    if hasattr(conn, "execute"):
        return conn.execute(sql, values)
    cursor = conn.cursor()
    cursor.execute(sql.replace("?", "%s"), values)
    return cursor


def _fetchone(
    conn: Any,
    sql: str,
    params: Iterable[Any] = (),
) -> Any:
    cursor = _execute(conn, sql, params)
    try:
        return cursor.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _require_positive_user_id(value: Any) -> int:
    if type(value) is not int or value <= 0:
        _fail("invalid_user_id", "user_id must be a positive integer")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail("invalid_text", f"{field} must be a non-empty trimmed string")
    if len(value) > _TEXT_LIMIT:
        _fail("text_too_long", f"{field} exceeds {_TEXT_LIMIT} characters")
    return value


def _timestamp(value: Any) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            _fail("invalid_timestamp", "claimed_at must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    return _require_text(value, "claimed_at")


def reward_item_for_zone(
    zone_key: str,
    *,
    reward_policy_version: str = POLICY_VERSION,
) -> str:
    """Resolve the server-owned Mapping A item for one canonical Zone."""

    _require_text(zone_key, "zone_key")
    _require_text(reward_policy_version, "reward_policy_version")
    if reward_policy_version != POLICY_VERSION:
        _fail(
            "unsupported_reward_policy",
            "F022 only authorizes the immutable Mapping A V1 policy",
        )
    item_id = MAPPING_A.get(zone_key)
    if item_id is None:
        _fail("unsupported_zone", f"no F022 reward mapping exists for {zone_key!r}")
    return item_id


def validate_mapping_a_against_catalog(
    *,
    presentation_registry: Mapping[str, Mapping[str, Any]],
    appearance_defs: Mapping[str, Mapping[str, Any]] | None = None,
    appearance_effects: Mapping[str, Mapping[str, Any]] | None = None,
    premium_item_ids: Collection[str] = (),
    shop_item_ids: Collection[str] = (),
    quest_exclusive_item_ids: Collection[str] = (),
) -> None:
    """Validate Mapping A against injected canonical presentation sources.

    The service deliberately does not import ``app.py`` or copy its catalog.
    A release/test preflight injects the existing canonical registries here so
    content validation remains an explicit check against the source of truth.
    """

    if not isinstance(presentation_registry, Mapping):
        raise FirstClearEntitlementValidationError(
            "invalid_catalog: presentation_registry must be a mapping"
        )
    missing = sorted(set(MAPPING_A.values()) - set(presentation_registry))
    if missing:
        raise FirstClearEntitlementValidationError(
            f"mapping_missing_items: {missing}"
        )
    premium = set(premium_item_ids)
    shop = set(shop_item_ids)
    quest = set(quest_exclusive_item_ids)
    effects = appearance_effects or {}
    definitions = appearance_defs or {}
    for item_id in MAPPING_A.values():
        presentation = presentation_registry[item_id]
        if presentation.get("pure_presentation") is not True:
            raise FirstClearEntitlementValidationError(
                f"not_pure_cosmetic: {item_id}"
            )
        if presentation.get("functional_effect_count") != 0:
            raise FirstClearEntitlementValidationError(
                f"functional_cosmetic: {item_id}"
            )
        if presentation.get("combat_authority") != "NO":
            raise FirstClearEntitlementValidationError(
                f"combat_cosmetic: {item_id}"
            )
        if item_id in premium:
            raise FirstClearEntitlementValidationError(
                f"premium_conflict: {item_id}"
            )
        if item_id in shop:
            raise FirstClearEntitlementValidationError(
                f"shop_conflict: {item_id}"
            )
        if item_id in quest:
            raise FirstClearEntitlementValidationError(
                f"quest_conflict: {item_id}"
            )
        if effects.get(item_id):
            raise FirstClearEntitlementValidationError(
                f"appearance_effect_conflict: {item_id}"
            )
        if appearance_defs is not None and item_id not in definitions:
            raise FirstClearEntitlementValidationError(
                f"appearance_definition_missing: {item_id}"
            )


@dataclass(frozen=True, slots=True)
class BattlefieldBossFirstClearEntitlementResult:
    """Detached claim result; it contains no World-progression decision."""

    status: str
    user_id: int
    zone_key: str
    requested_settlement_id: str
    entitlement_settlement_id: str
    entitlement_encounter_operation_id: str
    reward_item_id: str
    reward_policy_version: str
    recorded: bool
    replayed: bool
    already_claimed: bool

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError(f"unsupported F022 status: {self.status}")
        if type(self.recorded) is not bool:
            raise ValueError("recorded must be boolean")
        if type(self.replayed) is not bool:
            raise ValueError("replayed must be boolean")
        if type(self.already_claimed) is not bool:
            raise ValueError("already_claimed must be boolean")
        if self.status == RECORDED and not self.recorded:
            raise ValueError("RECORDED requires recorded=True")
        if self.status == REPLAYED and not self.replayed:
            raise ValueError("REPLAYED requires replayed=True")
        if self.status == ALREADY_CLAIMED and not self.already_claimed:
            raise ValueError("ALREADY_CLAIMED requires already_claimed=True")
        if self.status == CONFLICT and (
            self.recorded or self.replayed or self.already_claimed
        ):
            raise ValueError("CONFLICT cannot report a successful claim flag")


def _existing_row(
    conn: Any,
    *,
    user_id: int,
    zone_key: str,
    lock: bool = False,
) -> Any:
    table = TABLE_NAME if _is_sqlite(conn) else f"public.{TABLE_NAME}"
    suffix = " FOR UPDATE" if lock and not _is_sqlite(conn) else ""
    return _fetchone(
        conn,
        f"SELECT {', '.join(_PERSISTED_COLUMNS)} FROM {table} "
        "WHERE user_id=? AND zone_key=?" + suffix,
        (user_id, zone_key),
    )


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        name: _row_value(row, index, name)
        for index, name in enumerate(_PERSISTED_COLUMNS)
    }


def _result(
    row: Any,
    *,
    requested_settlement_id: str,
    status: str,
) -> BattlefieldBossFirstClearEntitlementResult:
    values = _row_dict(row)
    return BattlefieldBossFirstClearEntitlementResult(
        status=status,
        user_id=int(values["user_id"]),
        zone_key=str(values["zone_key"]),
        requested_settlement_id=requested_settlement_id,
        entitlement_settlement_id=str(values["source_settlement_id"]),
        entitlement_encounter_operation_id=str(
            values["source_encounter_operation_id"]
        ),
        reward_item_id=str(values["reward_item_id"]),
        reward_policy_version=str(values["reward_policy_version"]),
        recorded=status == RECORDED,
        replayed=status == REPLAYED,
        already_claimed=status == ALREADY_CLAIMED,
    )


def _validate_fact_and_claim(
    *,
    fact: Any,
    user_id: Any,
    zone_key: Any,
    source_settlement_id: Any,
    reward_item_id: Any,
    reward_policy_version: Any,
) -> dict[str, Any]:
    if type(fact) is not BattlefieldBossDefeatedFact:
        _fail(
            "fact_type_required",
            "claim requires a validated BattlefieldBossDefeatedFact",
        )
    normalized_user_id = _require_positive_user_id(user_id)
    normalized_zone_key = _require_text(zone_key, "zone_key")
    normalized_settlement_id = _require_text(
        source_settlement_id,
        "source_settlement_id",
    )
    normalized_reward_item_id = _require_text(reward_item_id, "reward_item_id")
    normalized_policy = _require_text(
        reward_policy_version,
        "reward_policy_version",
    )
    if fact.user_id != normalized_user_id:
        _fail("user_binding_mismatch", "claim user does not match the F012 fact")
    if fact.zone_key != normalized_zone_key:
        _fail("zone_binding_mismatch", "claim Zone does not match the F012 fact")
    if fact.settlement_id != normalized_settlement_id:
        _fail(
            "settlement_binding_mismatch",
            "claim settlement does not match the F012 fact",
        )
    metadata = fact.metadata
    if metadata.get("operation_binding_verified") is not True:
        _fail("operation_binding_required", "F014 operation binding evidence is required")
    if not isinstance(metadata.get("eligibility_reference"), str) or not metadata[
        "eligibility_reference"
    ].strip():
        _fail("eligibility_reference_required", "World eligibility evidence is required")
    if not isinstance(metadata.get("intent_replay_fingerprint"), str) or not metadata[
        "intent_replay_fingerprint"
    ].strip():
        _fail(
            "intent_fingerprint_required",
            "intent replay fingerprint evidence is required",
        )
    if metadata.get("settlement_event_type") != SOURCE_EVENT_TYPE:
        _fail("settlement_event_required", "MONSTER_DEFEATED evidence is required")

    return {
        "user_id": normalized_user_id,
        "zone_key": normalized_zone_key,
        "source_settlement_id": normalized_settlement_id,
        "source_encounter_operation_id": fact.encounter_operation_id,
        "source_monster_id": fact.monster_id,
        "eligibility_reference": metadata["eligibility_reference"],
        "intent_replay_fingerprint": metadata["intent_replay_fingerprint"],
        "source_authority": fact.source_authority,
        "source_event_type": SOURCE_EVENT_TYPE,
        "source_contract_version": fact.contract_version,
        "reward_item_id": normalized_reward_item_id,
        "reward_policy_version": normalized_policy,
    }


def _validate_current_reward_policy(values: Mapping[str, Any]) -> None:
    expected_item = reward_item_for_zone(
        str(values["zone_key"]),
        reward_policy_version=str(values["reward_policy_version"]),
    )
    if values["reward_item_id"] != expected_item:
        _fail(
            "reward_mapping_mismatch",
            "reward item does not match the server-owned Mapping A policy",
        )


def _conflicts(existing: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return any(existing[name] != expected[name] for name in _IMMUTABLE_COLUMNS)


def claim_battlefield_boss_first_clear_entitlement(
    conn: Any,
    *,
    fact: BattlefieldBossDefeatedFact,
    user_id: int,
    zone_key: str,
    source_settlement_id: str,
    reward_item_id: str,
    reward_policy_version: str = POLICY_VERSION,
    claimed_at: Any = None,
) -> BattlefieldBossFirstClearEntitlementResult:
    """Claim the one lifetime Mapping A reward entitlement for a user/Zone.

    The caller owns the transaction.  This function never commits, rolls
    back, opens a second connection, grants a wardrobe item, appends D5A, or
    changes World/Lord/Quest state.
    """

    schema_status = validate_schema(conn)
    if not schema_status.get("valid"):
        raise FirstClearEntitlementSchemaUnavailable(
            f"{TABLE_NAME} schema is not available: {schema_status.get('missing')}"
        )
    values = _validate_fact_and_claim(
        fact=fact,
        user_id=user_id,
        zone_key=zone_key,
        source_settlement_id=source_settlement_id,
        reward_item_id=reward_item_id,
        reward_policy_version=reward_policy_version,
    )
    claimed_value = _timestamp(claimed_at)
    table = TABLE_NAME if _is_sqlite(conn) else f"public.{TABLE_NAME}"

    # A read is useful for replay/reporting and permits a future policy
    # version to return ALREADY_CLAIMED without becoming an implicit regrant.
    # It is not the authority: the following INSERT's primary-key conflict is
    # what serializes concurrent first claims.
    existing = _existing_row(
        conn,
        user_id=values["user_id"],
        zone_key=values["zone_key"],
        lock=True,
    )
    if existing is not None:
        existing_values = _row_dict(existing)
        if existing_values["source_settlement_id"] != values["source_settlement_id"]:
            return _result(
                existing,
                requested_settlement_id=values["source_settlement_id"],
                status=ALREADY_CLAIMED,
            )
        if _conflicts(existing_values, values):
            return _result(
                existing,
                requested_settlement_id=values["source_settlement_id"],
                status=CONFLICT,
            )
        return _result(
            existing,
            requested_settlement_id=values["source_settlement_id"],
            status=REPLAYED,
        )

    # Only a new lifetime entitlement must match the currently authorized
    # Mapping A policy.  If a future policy version is presented after an
    # entitlement already exists, the existing-row branches above return
    # ALREADY_CLAIMED or CONFLICT and cannot create a second entitlement.
    _validate_current_reward_policy(values)

    columns = _PERSISTED_COLUMNS
    marker = ", ".join("?" for _ in columns)
    insert_values = tuple(
        values[name] if name != "claimed_at" else claimed_value
        for name in columns
    )
    cursor = _execute(
        conn,
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marker}) "
        "ON CONFLICT (user_id, zone_key) DO NOTHING",
        insert_values,
    )
    inserted = int(getattr(cursor, "rowcount", 0)) == 1
    row = _existing_row(
        conn,
        user_id=values["user_id"],
        zone_key=values["zone_key"],
        lock=False,
    )
    if row is None:
        raise FirstClearEntitlementError(
            "entitlement insert completed without a readable projection row"
        )
    row_values = _row_dict(row)
    if inserted:
        return _result(
            row,
            requested_settlement_id=values["source_settlement_id"],
            status=RECORDED,
        )
    if row_values["source_settlement_id"] != values["source_settlement_id"]:
        return _result(
            row,
            requested_settlement_id=values["source_settlement_id"],
            status=ALREADY_CLAIMED,
        )
    if _conflicts(row_values, values):
        return _result(
            row,
            requested_settlement_id=values["source_settlement_id"],
            status=CONFLICT,
        )
    return _result(
        row,
        requested_settlement_id=values["source_settlement_id"],
        status=REPLAYED,
    )


__all__ = [
    "ALREADY_CLAIMED",
    "CONFLICT",
    "MAPPING_A",
    "POLICY_VERSION",
    "RECORDED",
    "REPLAYED",
    "BattlefieldBossFirstClearEntitlementResult",
    "FirstClearEntitlementError",
    "FirstClearEntitlementSchemaUnavailable",
    "FirstClearEntitlementValidationError",
    "claim_battlefield_boss_first_clear_entitlement",
    "reward_item_for_zone",
    "validate_mapping_a_against_catalog",
]
