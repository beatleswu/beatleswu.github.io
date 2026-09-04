"""Fail-closed Zone 4 Adventure authority boundary for W2-01.

The current repository has Zone 4 art/planning identities and a Battlefield
anchor, but no Adventure M-ID/profile/persistence authority for M034-M045.
This registry records that fact explicitly.  It exposes the Battlefield Boss
and Lord as separate read-only references and refuses to promote presentation
art into Adventure combat authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adventure_zone4_misty_forest_content import load_zone4_manifest


ZONE4_KEY = "k11_15"
ZONE4_BATTLEFIELD_ZONE_KEY = "zone_04"
ZONE4_LORD_ID = "misty_phantom_rabbit_king"
ZONE4_BATTLEFIELD_BOSS_ID = "legacy_bf_04_boss"
ZONE4_NORMAL_IDS: tuple[str, ...] = tuple(f"M{n:03d}" for n in range(34, 46))


class Zone4AuthorityGap(LookupError):
    """Raised when a requested Zone 4 Adventure binding is not authoritative."""


@dataclass(frozen=True)
class Zone4EncounterCandidate:
    monster_id: str
    asset_path: str | None
    asset_status: str
    runtime_status: str
    runtime_id: str | None


@dataclass(frozen=True)
class Zone4BattlefieldBossReference:
    monster_id: str
    zone_key: str
    asset_path: str
    authority_scope: str


@dataclass(frozen=True)
class Zone4LordReference:
    lord_id: str
    zone_key: str
    asset_path: str | None
    authority_scope: str


def _normal_candidates() -> tuple[Zone4EncounterCandidate, ...]:
    manifest = load_zone4_manifest()
    return tuple(
        Zone4EncounterCandidate(
            monster_id=str(entry["id"]),
            asset_path=entry.get("assetPath"),
            asset_status=str(entry["assetStatus"]),
            runtime_status=str(entry["runtimeStatus"]),
            runtime_id=entry.get("runtimeId"),
        )
        for entry in manifest["encounters"]["normal"]
    )


ZONE4_NORMAL_CANDIDATES = _normal_candidates()
ZONE4_ADVENTURE_NORMAL_AUTHORIZED_IDS: tuple[str, ...] = tuple(
    candidate.monster_id
    for candidate in ZONE4_NORMAL_CANDIDATES
    if candidate.runtime_status == "ADVENTURE_NORMAL_AUTHORIZED"
)


def get_zone4_encounter_candidate(monster_id: Any) -> Zone4EncounterCandidate | None:
    if monster_id in (None, ""):
        return None
    normalized = str(monster_id).strip()
    return next((candidate for candidate in ZONE4_NORMAL_CANDIDATES if candidate.monster_id == normalized), None)


def require_zone4_adventure_normal(monster_id: Any) -> Zone4EncounterCandidate:
    candidate = get_zone4_encounter_candidate(monster_id)
    if candidate is None or candidate.runtime_status != "ADVENTURE_NORMAL_AUTHORIZED":
        raise Zone4AuthorityGap("Zone 4 Adventure normal authority is not available")
    return candidate


def resolve_battlefield_anchor(monster_id: Any) -> Zone4EncounterCandidate:
    candidate = get_zone4_encounter_candidate(monster_id)
    if candidate is None or candidate.runtime_status != "BATTLEFIELD_ONLY":
        raise Zone4AuthorityGap("Zone 4 Battlefield anchor is not this identity")
    if candidate.runtime_id != "legacy_bf_04_normal":
        raise Zone4AuthorityGap("Zone 4 Battlefield anchor identity is invalid")
    return candidate


def battlefield_boss_reference() -> Zone4BattlefieldBossReference:
    boss = load_zone4_manifest()["encounters"]["battlefieldBoss"]
    return Zone4BattlefieldBossReference(
        monster_id=str(boss["id"]),
        zone_key=str(boss["zoneKey"]),
        asset_path=str(boss["assetPath"]),
        authority_scope="BATTLEFIELD_ONLY",
    )


def lord_reference() -> Zone4LordReference:
    lord = load_zone4_manifest()["encounters"]["lord"]
    return Zone4LordReference(
        lord_id=str(lord["id"]),
        zone_key=str(lord["zoneKey"]),
        asset_path=lord.get("assetPath"),
        authority_scope="LORD_ONLY",
    )


def authority_snapshot() -> dict[str, Any]:
    boss = battlefield_boss_reference()
    lord = lord_reference()
    return {
        "zone_key": ZONE4_KEY,
        "normal_candidate_count": len(ZONE4_NORMAL_CANDIDATES),
        "adventure_normal_authorized_count": len(ZONE4_ADVENTURE_NORMAL_AUTHORIZED_IDS),
        "battlefield_boss_id": boss.monster_id,
        "lord_id": lord.lord_id,
        "battlefield_boss_equals_lord": boss.monster_id == lord.lord_id,
        "client_mutation_allowed": False,
        "progression_authority": "EXISTING_SERVER_RUNTIME",
    }


__all__ = [
    "ZONE4_ADVENTURE_NORMAL_AUTHORIZED_IDS",
    "ZONE4_BATTLEFIELD_BOSS_ID",
    "ZONE4_BATTLEFIELD_ZONE_KEY",
    "ZONE4_KEY",
    "ZONE4_LORD_ID",
    "ZONE4_NORMAL_CANDIDATES",
    "ZONE4_NORMAL_IDS",
    "Zone4AuthorityGap",
    "Zone4BattlefieldBossReference",
    "Zone4EncounterCandidate",
    "Zone4LordReference",
    "authority_snapshot",
    "battlefield_boss_reference",
    "get_zone4_encounter_candidate",
    "lord_reference",
    "require_zone4_adventure_normal",
    "resolve_battlefield_anchor",
]
