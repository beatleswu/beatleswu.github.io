"""Adventure-owned acquisition bridge for Spirit slots 4-6.

The Adventure system owns the milestone fact.  This module only consumes the
already-committed ``adventure_boss_progress.cleared`` projection and binds it
to the existing B023 ``SPIRIT_UNLOCK`` operation authority.  It deliberately
does not import ``app.py`` and does not implement an ownership writer.  The
caller supplies the existing server-owned unlock mutation as a callback so
that Adventure cannot create a second Spirit ownership implementation.

The stable zone keys below are taken from the executable ``ADVENTURE_ZONES``
order (1-based positions 4, 6, and 8), not from display labels.  The mapping
is a D-owned acquisition contract; the Adventure zone catalog remains owned
by the World/Adventure runtime.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

from companion_operations import execute_companion_operation
from spirit_runtime import validate_server_spirit_id


MILESTONE_SOURCE_AUTHORITY = "ADVENTURE_ZONE_MILESTONE"
MILESTONE_FACT = "adventure_boss_progress.cleared=1"
SPIRIT_UNLOCK_OPERATION_TYPE = "SPIRIT_UNLOCK"


class AdventureSpiritAcquisitionError(ValueError):
    """A fail-closed Adventure-to-Spirit contract error."""

    def __init__(self, message: str, *, code: str = "ADVENTURE_SPIRIT_ACQUISITION_REJECTED"):
        self.code = code
        super().__init__(message)


class AdventureSpiritSchemaUnavailable(AdventureSpiritAcquisitionError):
    """The existing World or Spirit ownership schema is unavailable."""


@dataclass(frozen=True)
class AdventureSpiritMilestone:
    """One Owner-approved ordinal-to-stable-key acquisition mapping."""

    zone_number: int
    zone_key: str
    spirit_id: str


@dataclass(frozen=True)
class AdventureSpiritEligibility:
    """Server-derived eligibility evidence for one mapped Adventure zone."""

    user_id: int
    zone_number: int
    zone_key: str
    spirit_id: str
    operation_id: str
    source_authority: str
    source_fact: str
    source_reference: str
    cleared: bool

    @property
    def eligible(self) -> bool:
        return self.cleared

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["eligible"] = self.eligible
        return result


# Owner mapping, bound to exact executable ADVENTURE_ZONES stable keys.
ADVENTURE_SPIRIT_MILESTONES = (
    AdventureSpiritMilestone(4, "k11_15", "starpath_antlerling"),
    AdventureSpiritMilestone(6, "k1_5", "fatty"),
    AdventureSpiritMilestone(8, "d3_4", "obsidian_bastion"),
)

_MILESTONE_BY_ZONE = MappingProxyType(
    {item.zone_key: item for item in ADVENTURE_SPIRIT_MILESTONES}
)
_MILESTONE_BY_NUMBER = MappingProxyType(
    {item.zone_number: item for item in ADVENTURE_SPIRIT_MILESTONES}
)

for _item in ADVENTURE_SPIRIT_MILESTONES:
    # Import-time validation prevents a typo from becoming an ownership
    # mutation target.  No display metadata participates in this check.
    validate_server_spirit_id(_item.spirit_id)


# The supplied callback is the existing server-owned ownership mutation.  It
# receives the server-derived identity, never client-provided Spirit/zone
# fields.  Its return shape matches companion_operations' mutation callback.
UnlockMutation = Callable[
    [Any, int, str, str, str],
    tuple[Mapping[str, Any], int],
]


def _require_user_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdventureSpiritAcquisitionError(
            "user_id must be a positive authenticated integer",
            code="INVALID_AUTHENTICATED_USER",
        )
    return value


def _require_zone_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdventureSpiritAcquisitionError(
            "zone_key must be a non-empty server-resolved string",
            code="INVALID_ADVENTURE_ZONE_KEY",
        )
    return value.strip()


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "keys"):
        return row[key]
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


def _missing_table_error(exc: Exception) -> bool:
    text = str(exc).lower()
    name = exc.__class__.__name__.lower()
    return "no such table" in text or "does not exist" in text or "undefinedtable" in name


def _operation_id(user_id: int, zone_key: str) -> str:
    # B023 validates this format.  It is derived from authenticated user and
    # canonical milestone identity, so retries do not invent a new operation.
    return f"adventure:spirit_unlock:{user_id}:{zone_key}"


def resolve_milestone_for_zone(zone_key: Any) -> AdventureSpiritMilestone:
    """Resolve only the exact Owner-approved stable zone keys."""

    key = _require_zone_key(zone_key)
    milestone = _MILESTONE_BY_ZONE.get(key)
    if milestone is None:
        raise AdventureSpiritAcquisitionError(
            f"zone {key!r} has no Owner-approved Spirit milestone mapping",
            code="UNMAPPED_ADVENTURE_SPIRIT_MILESTONE",
        )
    return milestone


def resolve_milestone_for_number(zone_number: Any) -> AdventureSpiritMilestone:
    """Return the exact stable key for an Owner-approved 1-based zone number."""

    if isinstance(zone_number, bool) or not isinstance(zone_number, int) or zone_number <= 0:
        raise AdventureSpiritAcquisitionError(
            "zone_number must be a positive integer",
            code="INVALID_ADVENTURE_ZONE_NUMBER",
        )
    milestone = _MILESTONE_BY_NUMBER.get(zone_number)
    if milestone is None:
        raise AdventureSpiritAcquisitionError(
            f"zone number {zone_number} has no Spirit acquisition mapping",
            code="UNMAPPED_ADVENTURE_SPIRIT_MILESTONE",
        )
    return milestone


def validate_executable_zone_order(zone_keys: Sequence[str]) -> bool:
    """Validate the mapping against the executable Adventure zone order.

    This helper is intentionally a boundary check, not a second Adventure
    catalog.  It lets an integration test or caller prove that the Owner's
    ordinal wording still resolves to the current stable keys.
    """

    if isinstance(zone_keys, (str, bytes)):
        raise AdventureSpiritAcquisitionError(
            "zone_keys must be the executable Adventure zone sequence",
            code="INVALID_ADVENTURE_ZONE_ORDER",
        )
    try:
        for milestone in ADVENTURE_SPIRIT_MILESTONES:
            if zone_keys[milestone.zone_number - 1] != milestone.zone_key:
                raise AdventureSpiritAcquisitionError(
                    "Owner milestone mapping does not match executable Adventure zone order",
                    code="ADVENTURE_ZONE_ORDER_MISMATCH",
                )
    except IndexError as exc:
        raise AdventureSpiritAcquisitionError(
            "executable Adventure zone order is shorter than the Owner mapping",
            code="ADVENTURE_ZONE_ORDER_MISMATCH",
        ) from exc
    return True


def _read_zone_cleared(conn: Any, *, user_id: int, zone_key: str) -> bool:
    suffix = "" if _is_sqlite(conn) else " FOR UPDATE"
    try:
        cursor = conn.execute(
            "SELECT zone_key, cleared FROM adventure_boss_progress "
            f"WHERE user_id=? AND zone_key=?{suffix}",
            (user_id, zone_key),
        )
    except Exception as exc:
        if _missing_table_error(exc):
            raise AdventureSpiritSchemaUnavailable(
                "adventure_boss_progress schema is unavailable",
                code="ADVENTURE_PROGRESS_SCHEMA_UNAVAILABLE",
            ) from exc
        raise
    row = cursor.fetchone()
    if row is None:
        return False
    stored_zone_key = _row_value(row, "zone_key", 0)
    if stored_zone_key != zone_key:
        raise AdventureSpiritAcquisitionError(
            "Adventure progression returned a mismatched zone identity",
            code="ADVENTURE_ZONE_IDENTITY_MISMATCH",
        )
    return bool(_row_value(row, "cleared", 1))


def _read_owned(conn: Any, *, user_id: int, spirit_id: str) -> bool:
    try:
        row = conn.execute(
            "SELECT pet_key FROM pet_collection WHERE user_id=? AND pet_key=? LIMIT 1",
            (user_id, spirit_id),
        ).fetchone()
    except Exception as exc:
        if _missing_table_error(exc):
            raise AdventureSpiritSchemaUnavailable(
                "pet_collection schema is unavailable",
                code="SPIRIT_OWNERSHIP_SCHEMA_UNAVAILABLE",
            ) from exc
        raise
    return row is not None


def inspect_adventure_spirit_eligibility(
    conn: Any,
    *,
    user_id: int,
    zone_key: str,
) -> AdventureSpiritEligibility:
    """Read one authoritative milestone without mutating any state."""

    user_id = _require_user_id(user_id)
    milestone = resolve_milestone_for_zone(zone_key)
    operation_id = _operation_id(user_id, milestone.zone_key)
    cleared = _read_zone_cleared(conn, user_id=user_id, zone_key=milestone.zone_key)
    return AdventureSpiritEligibility(
        user_id=user_id,
        zone_number=milestone.zone_number,
        zone_key=milestone.zone_key,
        spirit_id=milestone.spirit_id,
        operation_id=operation_id,
        source_authority=MILESTONE_SOURCE_AUTHORITY,
        source_fact=MILESTONE_FACT,
        source_reference=(
            f"adventure_boss_progress:{user_id}:{milestone.zone_key}"
        ),
        cleared=cleared,
    )


def unlock_spirit_from_adventure_milestone(
    conn: Any,
    *,
    user_id: int,
    zone_key: str,
    mutation: UnlockMutation,
) -> dict[str, Any]:
    """Execute one server-derived Adventure Spirit unlock through B023.

    ``mutation`` is the caller's existing server-owned Spirit unlock writer.
    This function never commits or rolls back.  A caller may therefore place
    the authoritative Adventure read, B023 reservation, ownership mutation,
    and any existing reward/lineage work in one transaction.
    """

    if not callable(mutation):
        raise AdventureSpiritAcquisitionError(
            "an existing server-owned Spirit unlock mutation is required",
            code="SPIRIT_UNLOCK_SINK_REQUIRED",
        )
    eligibility = inspect_adventure_spirit_eligibility(
        conn, user_id=user_id, zone_key=zone_key
    )
    result_base = eligibility.as_dict()
    result_base.update(
        {
            "operation_type": SPIRIT_UNLOCK_OPERATION_TYPE,
            "ownership_store": "pet_collection",
            "compensation_count": 0,
            "replacement_count": 0,
            "client_completion_authority": False,
        }
    )
    if not eligibility.eligible:
        result_base.update(
            {
                "status": "NOT_ELIGIBLE",
                "replayed": False,
                "ownership_mutation_count": 0,
                "new_unlock_count": 0,
                "sink_result": None,
            }
        )
        return result_base

    observed = {"before": None, "after": None}

    def invoke_existing_sink(inner_conn: Any, operation_id: str):
        # The no-op is inside the B023 operation callback, so even an already
        # owned Spirit receives a durable, replay-safe operation result without
        # compensation or a second ownership/reward mutation.
        observed["before"] = _read_owned(
            inner_conn, user_id=eligibility.user_id, spirit_id=eligibility.spirit_id
        )
        if observed["before"]:
            body: Mapping[str, Any] = {
                "ok": True,
                "status": "NO_OP",
                "ownership_mutation_count": 0,
                "reward_count": 0,
                "operation_id": operation_id,
            }
            status_code = 200
        else:
            body, status_code = mutation(
                inner_conn,
                eligibility.user_id,
                eligibility.spirit_id,
                eligibility.zone_key,
                operation_id,
            )
        observed["after"] = _read_owned(
            inner_conn, user_id=eligibility.user_id, spirit_id=eligibility.spirit_id
        )
        return body, status_code

    execution = execute_companion_operation(
        conn,
        user_id=eligibility.user_id,
        operation_type=SPIRIT_UNLOCK_OPERATION_TYPE,
        operation_id=eligibility.operation_id,
        spirit_id=eligibility.spirit_id,
        payload={
            "source_authority": MILESTONE_SOURCE_AUTHORITY,
            "source_fact": MILESTONE_FACT,
            "source_reference": eligibility.source_reference,
            "zone_key": eligibility.zone_key,
            "zone_number": eligibility.zone_number,
            "target_spirit_id": eligibility.spirit_id,
            "unlock_kind": "adventure_zone_milestone",
        },
        mutation=invoke_existing_sink,
    )

    sink_result = dict(execution.body)
    result_base["sink_result"] = sink_result
    result_base["replayed"] = bool(execution.replayed)
    result_base["operation_status"] = execution.operation_status

    if execution.operation_status == "FAILED":
        result_base.update(
            {
                "status": "REJECTED",
                "ownership_mutation_count": 0,
                "new_unlock_count": 0,
            }
        )
        return result_base
    if execution.operation_status != "COMPLETED":
        raise AdventureSpiritAcquisitionError(
            "B023 returned a non-terminal Spirit unlock status",
            code="SPIRIT_UNLOCK_NON_TERMINAL",
        )

    owned_after = _read_owned(
        conn, user_id=eligibility.user_id, spirit_id=eligibility.spirit_id
    )
    if not owned_after:
        # The sink reported completion without persisting the mapped ownership
        # row.  Raising leaves the caller's transaction responsible for the
        # rollback and prevents a false successful unlock result.
        raise AdventureSpiritAcquisitionError(
            "Spirit unlock sink completed without mapped pet_collection ownership",
            code="SPIRIT_UNLOCK_OWNERSHIP_NOT_PERSISTED",
        )

    if execution.replayed:
        mutation_count = 0
        status = "REPLAY"
    else:
        mutation_count = int(observed["before"] is False and observed["after"] is True)
        status = "UNLOCKED" if mutation_count else "NO_OP"

    result_base.update(
        {
            "status": status,
            "ownership_mutation_count": mutation_count,
            "new_unlock_count": mutation_count,
        }
    )
    return result_base


def catch_up_adventure_spirit_unlocks(
    conn: Any,
    *,
    user_id: int,
    mutation: UnlockMutation,
) -> tuple[dict[str, Any], ...]:
    """Apply all currently provable mapped milestones in canonical order.

    This is prospective-safe historical catch-up: only persisted
    ``cleared=1`` rows are consumed.  Missing rows remain ``NOT_ELIGIBLE`` and
    no account-creation, selected-zone, or client assertion is inferred.
    """

    user_id = _require_user_id(user_id)
    return tuple(
        unlock_spirit_from_adventure_milestone(
            conn,
            user_id=user_id,
            zone_key=milestone.zone_key,
            mutation=mutation,
        )
        for milestone in ADVENTURE_SPIRIT_MILESTONES
    )


__all__ = [
    "ADVENTURE_SPIRIT_MILESTONES",
    "AdventureSpiritAcquisitionError",
    "AdventureSpiritEligibility",
    "AdventureSpiritMilestone",
    "AdventureSpiritSchemaUnavailable",
    "MILESTONE_FACT",
    "MILESTONE_SOURCE_AUTHORITY",
    "SPIRIT_UNLOCK_OPERATION_TYPE",
    "catch_up_adventure_spirit_unlocks",
    "inspect_adventure_spirit_eligibility",
    "resolve_milestone_for_number",
    "resolve_milestone_for_zone",
    "unlock_spirit_from_adventure_milestone",
    "validate_executable_zone_order",
]
