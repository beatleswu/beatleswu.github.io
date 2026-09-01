"""Compatibility for pre-E055 Adventure Zone 3 Map Battle state.

Zone 3 Map Battles created before E055 were written with the generic legacy
provenance ``legacy-adventure-map`` / ``map-battle-v1``.  Those rows carry no
Monster identity at all: the legacy path persisted only HP, and the Monster
was re-derived from the *question* on each request.  E055 made Zone 3 Monster
identity server-owned and persisted it in the battle row, and
``decode_zone3_binding`` correctly refuses any Zone 3 battle that does not
carry that binding.

The result in Production is a permanent lockout rather than a one-off error.
``/api/map-battle/start`` looks up the player's OPEN battle for the zone
before creating a new one, so a single pre-E055 OPEN Zone 3 battle makes
every subsequent Zone 3 request fail closed with
``Adventure Zone 3 Monster binding is unavailable``.  The player can never
reach a battle that *would* be bound correctly.

There is deliberately no reconciliation from legacy state to an E055 binding.
A legacy row records no Monster identity, so any mapping would have to invent
one -- from the currently requested question, or from a default -- and that
invented identity would then own drops, rewards and presentation.  The
mapping is not mechanically unambiguous, so this module does not attempt it.

Instead the stranded battle is retired.  ``EXPIRED`` is an existing, already
modelled terminal state for ``map_battles``; it settles nothing.  Retiring
frees the zone so the next request creates a properly bound E055 battle.

What retirement deliberately does not do:

* it never touches a ``COMPLETED`` battle, so no settlement is replayed and
  no reward, drop, coin, star or Boss clear can be minted twice;
* it never writes ``completed_at``, so the row cannot be mistaken for a clear;
* it never converts a battle in another zone, or one already carrying an
  E055 binding -- a Zone 3 battle with corrupt or unrecognised E055
  provenance still fails closed, because that is tampering or corruption
  rather than legacy state.

The only thing lost is transient in-battle Monster HP for an unfinished
battle.  That is combat scratch state, not settled progress; the alternative
is a player who can never enter Zone 3 again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from adventure_zone3_monster_authority import ZONE3_KEY


# The exact provenance pair written by the pre-E055 Adventure Map Battle
# path.  Recognition is exact: a partial or unknown match is not legacy
# state and must keep failing closed.
LEGACY_MAP_BATTLE_MIGRATION_SOURCE = "legacy-adventure-map"
LEGACY_MAP_BATTLE_MIGRATION_VERSION = "map-battle-v1"

LEGACY_ZONE3_RETIREMENT_STATE = "EXPIRED"


def is_legacy_zone3_battle(battle: Any) -> bool:
    """Return whether *battle* is exactly a pre-E055 Zone 3 battle row."""

    if not isinstance(battle, Mapping):
        return False
    if str(battle.get("zone_key") or "") != ZONE3_KEY:
        return False
    if str(battle.get("migration_source") or "") != LEGACY_MAP_BATTLE_MIGRATION_SOURCE:
        return False
    return (
        str(battle.get("migration_version") or "")
        == LEGACY_MAP_BATTLE_MIGRATION_VERSION
    )


def legacy_zone3_battle_is_retirable(battle: Any) -> bool:
    """Return whether *battle* is legacy Zone 3 state safe to retire.

    Only an ``OPEN`` battle qualifies.  A ``COMPLETED`` legacy battle has
    already settled; it is left exactly as it is.
    """

    if not is_legacy_zone3_battle(battle):
        return False
    return str(battle.get("state") or "") == "OPEN"


def retire_legacy_zone3_battle(conn: Any, *, user_id: int, battle: Any) -> bool:
    """Retire one stranded legacy Zone 3 battle; return whether it was retired.

    The UPDATE repeats every admission condition in its WHERE clause, so a
    concurrent settlement that completed the battle first cannot be
    overwritten: such a request simply retires nothing and returns ``False``.
    """

    if not legacy_zone3_battle_is_retirable(battle):
        return False
    battle_id = str(battle.get("id") or "").strip()
    if not battle_id:
        return False
    updated = conn.execute(
        """UPDATE map_battles
              SET state=?
            WHERE id=? AND user_id=? AND zone_key=? AND state='OPEN'
              AND completed_at IS NULL
              AND migration_source=? AND migration_version=?""",
        (
            LEGACY_ZONE3_RETIREMENT_STATE,
            battle_id,
            int(user_id),
            ZONE3_KEY,
            LEGACY_MAP_BATTLE_MIGRATION_SOURCE,
            LEGACY_MAP_BATTLE_MIGRATION_VERSION,
        ),
    )
    return getattr(updated, "rowcount", 0) == 1


__all__ = [
    "LEGACY_MAP_BATTLE_MIGRATION_SOURCE",
    "LEGACY_MAP_BATTLE_MIGRATION_VERSION",
    "LEGACY_ZONE3_RETIREMENT_STATE",
    "is_legacy_zone3_battle",
    "legacy_zone3_battle_is_retirable",
    "retire_legacy_zone3_battle",
]
