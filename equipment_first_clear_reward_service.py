"""EQ-F functional Equipment first-clear acquisition authority.

This service composes the already-authoritative Adventure Boss clear with the
existing ``player_inventory`` ownership writer.  It deliberately owns no
transaction boundary, no judging, no cosmetic F028 mapping, and no Shop
price.  The cleared Boss row is locked and the durable ownership row is the
idempotent convergence record; no second reward ledger or schema is created.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Final

from equipment_ownership_service import (
    EquipmentOwnershipError,
    grant_equipment_ownership,
)
from equipment_portfolio_registry import (
    EQ_F_ZONE_EQUIPMENT_BY_ZONE,
)


REWARD_SOURCE: Final[str] = "adventure_first_clear"
GRANTED: Final[str] = "GRANTED"
ALREADY_OWNED: Final[str] = "ALREADY_OWNED"
NO_REWARD: Final[str] = "NO_REWARD"

_ZONE_TO_ITEM: Final[Mapping[str, str]] = MappingProxyType(
    dict(EQ_F_ZONE_EQUIPMENT_BY_ZONE)
)
_ZONE_KEYS: Final[tuple[str, ...]] = tuple(_ZONE_TO_ITEM)
_REQUIRED_ATTEMPT_KEYS: Final[frozenset[str]] = frozenset(
    {"operation_id", "is_replay", "is_first_clear"}
)


class EquipmentFirstClearRewardError(ValueError):
    """Expected fail-closed validation or authority failure."""

    def __init__(self, code: str, message: str, **details: Any):
        self.code = code
        self.details = details
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class EquipmentFirstClearSettlement:
    """Typed handoff from the server's authoritative Boss attempt result."""

    user_id: int
    zone_key: str
    source_operation_id: str
    passed: bool
    is_first_clear: bool
    is_replay: bool

    @property
    def operation_id(self) -> str:
        return f"adventure:first_clear_equipment:{self.user_id}:{self.zone_key}"

    @classmethod
    def from_authoritative_attempt(
        cls,
        *,
        user_id: Any,
        zone_key: Any,
        passed: Any,
        attempt_result: Mapping[str, Any],
    ) -> "EquipmentFirstClearSettlement":
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise EquipmentFirstClearRewardError(
                "INVALID_AUTHENTICATED_USER",
                "functional first-clear reward requires an authenticated user",
            )
        normalized_zone = str(zone_key or "").strip()
        if normalized_zone not in _ZONE_TO_ITEM:
            raise EquipmentFirstClearRewardError(
                "UNKNOWN_EQUIPMENT_REWARD_ZONE",
                "functional first-clear reward zone is not canonical",
                zone_key=normalized_zone,
            )
        if not isinstance(attempt_result, Mapping):
            raise EquipmentFirstClearRewardError(
                "INVALID_AUTHORITATIVE_ATTEMPT",
                "functional first-clear reward requires the server attempt result",
            )
        missing = _REQUIRED_ATTEMPT_KEYS - set(attempt_result)
        if missing:
            raise EquipmentFirstClearRewardError(
                "INVALID_AUTHORITATIVE_ATTEMPT",
                "server attempt result is missing settlement fields",
                missing=sorted(missing),
            )
        try:
            source_operation_id = str(attempt_result["operation_id"]).strip()
            is_replay = bool(attempt_result["is_replay"])
            is_first_clear = bool(attempt_result["is_first_clear"])
        except Exception as exc:
            raise EquipmentFirstClearRewardError(
                "INVALID_AUTHORITATIVE_ATTEMPT",
                "server attempt result fields are malformed",
            ) from exc
        if not source_operation_id:
            raise EquipmentFirstClearRewardError(
                "INVALID_AUTHORITATIVE_ATTEMPT",
                "server attempt operation identity is required",
            )
        return cls(
            user_id=user_id,
            zone_key=normalized_zone,
            source_operation_id=source_operation_id,
            passed=bool(passed),
            is_first_clear=is_first_clear,
            is_replay=is_replay,
        )


@dataclass(frozen=True, slots=True)
class EquipmentFirstClearRewardResult:
    status: str
    user_id: int
    zone_key: str
    item_id: str | None
    operation_id: str
    first_clear: bool
    backfill: bool
    ownership_row_id: int | None = None
    already_owned: bool = False
    reason_code: str | None = None

    def as_response(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "item_id": self.item_id,
            "zone_key": self.zone_key,
            "operation_id": self.operation_id,
            "first_clear": self.first_clear,
            "backfill": self.backfill,
            "ownership_authority": "player_inventory",
            "ownership_persisted": self.ownership_row_id is not None or self.already_owned,
            "ownership_row_id": self.ownership_row_id,
            "already_owned": self.already_owned,
            "equipped": False,
            "auto_equip": False,
            "auto_equipped": False,
            "reason_code": self.reason_code,
        }


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _definitions(
    equipment_defs: Iterable[Mapping[str, Any]] | None,
) -> tuple[Mapping[str, Any], ...]:
    if equipment_defs is None:
        from app import CANONICAL_EQUIPMENT_DEFS

        equipment_defs = CANONICAL_EQUIPMENT_DEFS
    definitions = tuple(equipment_defs)
    by_id = {str(item.get("id")): item for item in definitions}
    for item_id in _ZONE_TO_ITEM.values():
        definition = by_id.get(item_id)
        if definition is None:
            raise EquipmentFirstClearRewardError(
                "EQUIPMENT_DEFINITION_MISSING",
                "canonical first-clear Equipment definition is unavailable",
                item_id=item_id,
            )
        if definition.get("slot") not in {"weapon", "armor", "accessory"}:
            raise EquipmentFirstClearRewardError(
                "EQUIPMENT_DEFINITION_INVALID",
                "canonical first-clear Equipment slot is unsupported",
                item_id=item_id,
            )
    return definitions


def _progress_row(conn: Any, user_id: int, zone_key: str) -> Any:
    suffix = "" if _is_sqlite(conn) else " FOR UPDATE"
    try:
        row = conn.execute(
            "SELECT user_id, zone_key, cleared FROM adventure_boss_progress "
            f"WHERE user_id=? AND zone_key=?{suffix}",
            (user_id, zone_key),
        ).fetchone()
    except Exception as exc:
        raise EquipmentFirstClearRewardError(
            "PROGRESS_SCHEMA_UNAVAILABLE",
            "authoritative Adventure clear state is unavailable",
        ) from exc
    if row is None:
        raise EquipmentFirstClearRewardError(
            "CLEAR_NOT_CONFIRMED",
            "functional first-clear reward requires a persisted Boss clear",
            zone_key=zone_key,
        )
    if not bool(_row_value(row, 2, "cleared")):
        raise EquipmentFirstClearRewardError(
            "CLEAR_NOT_CONFIRMED",
            "functional first-clear reward requires cleared=1",
            zone_key=zone_key,
        )
    return row


def _owned_row(conn: Any, user_id: int, item_id: str) -> Any:
    try:
        return conn.execute(
            "SELECT id, equipped FROM player_inventory "
            "WHERE user_id=? AND equip_id=? ORDER BY id LIMIT 1",
            (user_id, item_id),
        ).fetchone()
    except Exception as exc:
        raise EquipmentFirstClearRewardError(
            "OWNERSHIP_SCHEMA_UNAVAILABLE",
            "player_inventory ownership authority is unavailable",
            item_id=item_id,
        ) from exc


def _result(
    settlement: EquipmentFirstClearSettlement,
    *,
    status: str,
    item_id: str | None,
    backfill: bool,
    ownership_row_id: int | None = None,
    already_owned: bool = False,
    reason_code: str | None = None,
) -> EquipmentFirstClearRewardResult:
    return EquipmentFirstClearRewardResult(
        status=status,
        user_id=settlement.user_id,
        zone_key=settlement.zone_key,
        item_id=item_id,
        operation_id=settlement.operation_id,
        first_clear=settlement.is_first_clear,
        backfill=backfill,
        ownership_row_id=ownership_row_id,
        already_owned=already_owned,
        reason_code=reason_code,
    )


def grant_equipment_first_clear_reward(
    conn: Any,
    settlement: EquipmentFirstClearSettlement,
    *,
    equipment_defs: Iterable[Mapping[str, Any]] | None = None,
    obtained_at: Any = None,
    backfill: bool = False,
) -> EquipmentFirstClearRewardResult:
    """Grant the mapped functional item exactly once in the caller's tx."""

    if not isinstance(settlement, EquipmentFirstClearSettlement):
        raise EquipmentFirstClearRewardError(
            "INVALID_SETTLEMENT",
            "functional first-clear reward requires a typed settlement",
        )
    item_id = _ZONE_TO_ITEM.get(settlement.zone_key)
    if item_id is None:
        raise EquipmentFirstClearRewardError(
            "UNKNOWN_EQUIPMENT_REWARD_ZONE",
            "functional first-clear reward zone is not canonical",
        )
    definitions = _definitions(equipment_defs)
    if not settlement.is_first_clear:
        return _result(
            settlement,
            status=NO_REWARD,
            item_id=None,
            backfill=backfill,
            reason_code=("REPLAY_ALREADY_CLEARED" if settlement.is_replay else "BOSS_NOT_FIRST_CLEAR"),
        )
    if not settlement.passed or settlement.is_replay:
        raise EquipmentFirstClearRewardError(
            "INVALID_FIRST_CLEAR_SETTLEMENT",
            "only a passed non-replay first-clear winner can grant Equipment",
        )

    _progress_row(conn, settlement.user_id, settlement.zone_key)
    existing = _owned_row(conn, settlement.user_id, item_id)
    if existing is not None:
        return _result(
            settlement,
            status=ALREADY_OWNED,
            item_id=item_id,
            backfill=backfill,
            ownership_row_id=int(_row_value(existing, 0, "id")),
            already_owned=True,
            reason_code="ALREADY_OWNED",
        )

    try:
        ownership = grant_equipment_ownership(
            conn,
            settlement.user_id,
            item_id,
            REWARD_SOURCE,
            equipment_defs=definitions,
        )
    except EquipmentOwnershipError as exc:
        raise EquipmentFirstClearRewardError(
            f"OWNERSHIP_{exc.code}",
            "canonical first-clear Equipment ownership failed",
            item_id=item_id,
        ) from exc
    if ownership.equipped:
        raise EquipmentFirstClearRewardError(
            "AUTO_EQUIP_FORBIDDEN",
            "first-clear functional Equipment must remain unequipped",
            item_id=item_id,
        )
    return _result(
        settlement,
        status=GRANTED,
        item_id=item_id,
        backfill=backfill,
        ownership_row_id=ownership.row_id,
        reason_code="FIRST_CLEAR_GRANTED" if not backfill else "HISTORICAL_BACKFILL_GRANTED",
    )


def backfill_cleared_equipment(
    conn: Any,
    user_id: Any,
    *,
    equipment_defs: Iterable[Mapping[str, Any]] | None = None,
    obtained_at: Any = None,
) -> tuple[EquipmentFirstClearRewardResult, ...]:
    """Converge all authoritative historical ``cleared=1`` rows for one user."""

    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise EquipmentFirstClearRewardError(
            "INVALID_AUTHENTICATED_USER",
            "historical Equipment backfill requires an authenticated user",
        )
    definitions = _definitions(equipment_defs)
    try:
        rows = conn.execute(
            "SELECT zone_key FROM adventure_boss_progress "
            "WHERE user_id=? AND cleared=1 ORDER BY zone_key",
            (user_id,),
        ).fetchall()
    except Exception as exc:
        raise EquipmentFirstClearRewardError(
            "PROGRESS_SCHEMA_UNAVAILABLE",
            "authoritative Adventure clear state is unavailable",
        ) from exc

    results: list[EquipmentFirstClearRewardResult] = []
    for row in rows:
        zone_key = str(_row_value(row, 0, "zone_key") or "").strip()
        if zone_key not in _ZONE_TO_ITEM:
            # Historical rows outside the locked canonical mapping are not
            # allowed to mint an invented product.
            continue
        settlement = EquipmentFirstClearSettlement(
            user_id=user_id,
            zone_key=zone_key,
            source_operation_id=f"adventure:first_clear:{user_id}:{zone_key}",
            passed=True,
            is_first_clear=True,
            is_replay=False,
        )
        results.append(
            grant_equipment_first_clear_reward(
                conn,
                settlement,
                equipment_defs=definitions,
                obtained_at=obtained_at or datetime.now(timezone.utc).isoformat(),
                backfill=True,
            )
        )
    return tuple(results)


__all__ = [
    "ALREADY_OWNED",
    "EquipmentFirstClearRewardError",
    "EquipmentFirstClearRewardResult",
    "EquipmentFirstClearSettlement",
    "GRANTED",
    "NO_REWARD",
    "REWARD_SOURCE",
    "backfill_cleared_equipment",
    "grant_equipment_first_clear_reward",
]
