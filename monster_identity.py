"""Canonical Monster identity and legacy vocabulary compatibility.

Wave F0 deliberately owns identity only.  It does not calculate combat,
settle an encounter, resolve drops, or write persistence.  The battlefield
roster remains the runtime source for HP/ATK and the adapter binds that
source to stable presentation-independent identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


ENCOUNTER_CLASS_NORMAL = "NORMAL"
ENCOUNTER_CLASS_BATTLEFIELD_BOSS = "BATTLEFIELD_BOSS"

_ENCOUNTER_ALIASES = {
    "normal": ENCOUNTER_CLASS_NORMAL,
    "NORMAL": ENCOUNTER_CLASS_NORMAL,
    "boss": ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    "BOSS": ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    "battlefield_boss": ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    "BATTLEFIELD_BOSS": ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    "chapter_boss": ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    "book_boss": ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
}

# The current taxonomy has one family per stage.  These are compatibility
# values, not a second roster or stat authority.
_BATTLEFIELD_FAMILY_BY_ZONE = (
    ("caterpillar", "caterpillar", "slime_goblin", "slime"),
    ("bee", "bee", "goblin_bat", "cave_bat"),
    ("turtle", "turtle", "orc_soldier", "orc_grunt"),
    ("rabbit", "rabbit", "forest_spirit", "forest_spirit"),
    ("raccoon", "raccoon", "tribal_orc", "tribal_orc"),
    ("wolf", "dragon", "wyvern_deity", "wyvern"),
    ("fox", "fox", "sage_mage_undead", "lich_mage"),
    ("golem", "golem", "knight_chaos", "armored_knight"),
    ("dragon", "dragon", "gods", "storm_deity"),
    ("dragon", "dragon", "ancient_domain", "ancient_idol"),
)


@dataclass(frozen=True)
class CanonicalMonsterIdentity:
    """One stable Monster identity, independent of art and localized text."""

    monster_id: str
    zone_id: str
    roster_slot: int
    encounter_class: str
    family_id: str
    display_name_key: str
    legacy_type: str | None = None
    legacy_name: str | None = None
    taxonomy_battle_type: str | None = None
    legacy_aliases: tuple[str, ...] = ()

    def runtime_fields(self) -> dict[str, Any]:
        """Return safe canonical fields for an existing response payload."""

        return {
            "monster_id": self.monster_id,
            "zone_id": self.zone_id,
            "roster_slot": self.roster_slot,
            "encounter_class": self.encounter_class,
            "family_id": self.family_id,
            "display_name_key": self.display_name_key,
            "monster_identity_resolved": True,
        }


@dataclass(frozen=True)
class MonsterIdentityRegistry:
    entries: tuple[CanonicalMonsterIdentity, ...]
    by_id: Mapping[str, CanonicalMonsterIdentity]
    by_roster_slot: Mapping[int, CanonicalMonsterIdentity]


def _build_specs() -> tuple[CanonicalMonsterIdentity, ...]:
    entries: list[CanonicalMonsterIdentity] = []
    for zone_number, (normal_type, boss_type, family_id, taxonomy_type) in enumerate(
        _BATTLEFIELD_FAMILY_BY_ZONE, start=1
    ):
        zone_id = f"zone_{zone_number:02d}"
        for encounter_index, encounter_class in enumerate(
            (ENCOUNTER_CLASS_NORMAL, ENCOUNTER_CLASS_BATTLEFIELD_BOSS),
            start=0,
        ):
            roster_slot = (zone_number - 1) * 2 + encounter_index + 1
            kind = "normal" if encounter_class == ENCOUNTER_CLASS_NORMAL else "boss"
            legacy_type = normal_type if kind == "normal" else boss_type
            entries.append(
                CanonicalMonsterIdentity(
                    monster_id=f"legacy_bf_{zone_number:02d}_{kind}",
                    zone_id=zone_id,
                    roster_slot=roster_slot,
                    encounter_class=encounter_class,
                    family_id=family_id,
                    display_name_key=(
                        f"monster.battlefield.zone_{zone_number:02d}.{kind}"
                    ),
                    legacy_type=legacy_type,
                    taxonomy_battle_type=taxonomy_type,
                    legacy_aliases=(
                        legacy_type,
                        taxonomy_type,
                        family_id,
                        zone_id,
                        f"LV{zone_number}",
                    ),
                )
            )
    return tuple(entries)


CANONICAL_BATTLEFIELD_IDENTITY_SPECS = _build_specs()
CANONICAL_BATTLEFIELD_MONSTER_COUNT = len(CANONICAL_BATTLEFIELD_IDENTITY_SPECS)


def _registry_from_entries(
    entries: Sequence[CanonicalMonsterIdentity],
) -> MonsterIdentityRegistry:
    entries = tuple(entries)
    by_id = {entry.monster_id: entry for entry in entries}
    by_roster_slot = {entry.roster_slot: entry for entry in entries}
    if len(by_id) != len(entries):
        raise ValueError("canonical Monster IDs must be unique")
    if len(by_roster_slot) != len(entries):
        raise ValueError("canonical Monster roster slots must be unique")
    return MonsterIdentityRegistry(entries, by_id, by_roster_slot)


CANONICAL_MONSTER_IDENTITY_REGISTRY = _registry_from_entries(
    CANONICAL_BATTLEFIELD_IDENTITY_SPECS
)


def build_battlefield_identity_registry(
    roster: Sequence[Sequence[Any]],
    *,
    identity_specs: Sequence[CanonicalMonsterIdentity] | None = None,
) -> MonsterIdentityRegistry:
    """Bind the current server-owned roster to the F0 identity specs.

    This validates the existing roster shape but does not copy or alter its
    HP, ATK, drops, rewards, or persistence behavior.
    """

    specs = tuple(
        CANONICAL_BATTLEFIELD_IDENTITY_SPECS
        if identity_specs is None
        else identity_specs
    )
    if len(roster) != CANONICAL_BATTLEFIELD_MONSTER_COUNT or len(specs) != len(roster):
        raise ValueError(
            "F0 identity mapping requires exactly 20 battlefield roster entries"
        )
    # Validate the candidate identity table before binding any legacy values so
    # duplicate IDs are rejected as an explicit corruption, not overwritten by
    # a dict comprehension.
    _registry_from_entries(specs)

    bound: list[CanonicalMonsterIdentity] = []
    for index, entry in enumerate(roster):
        if len(entry) < 5:
            raise ValueError("battlefield roster entries require five fields")
        spec = specs[index]
        legacy_type, legacy_name, _max_hp, _attack, encounter_kind = entry[:5]
        normalized_kind = normalize_encounter_class(encounter_kind)
        expected_zone_id = f"zone_{index // 2 + 1:02d}"
        expected_roster_slot = index + 1
        expected_kind = (
            ENCOUNTER_CLASS_NORMAL if index % 2 == 0 else ENCOUNTER_CLASS_BATTLEFIELD_BOSS
        )
        expected_id = (
            f"legacy_bf_{index // 2 + 1:02d}_"
            f"{'normal' if index % 2 == 0 else 'boss'}"
        )
        if (
            spec.zone_id != expected_zone_id
            or spec.roster_slot != expected_roster_slot
            or spec.monster_id != expected_id
            or spec.encounter_class != expected_kind
        ):
            raise ValueError(
                f"roster slot {index + 1} has corrupted canonical zone/slot/id/class"
            )
        if legacy_type != spec.legacy_type:
            raise ValueError(
                f"roster slot {index + 1} type mismatch: "
                f"expected {spec.legacy_type}, got {legacy_type}"
            )
        if normalized_kind != spec.encounter_class:
            raise ValueError(
                f"roster slot {index + 1} encounter mismatch: "
                f"expected {spec.encounter_class}, got {encounter_kind}"
            )
        bound.append(
            CanonicalMonsterIdentity(
                **{
                    **spec.__dict__,
                    "legacy_name": str(legacy_name),
                    "legacy_aliases": tuple(
                        dict.fromkeys(
                            (*spec.legacy_aliases, str(legacy_name))
                        )
                    ),
                }
            )
        )
    return _registry_from_entries(bound)


def normalize_encounter_class(value: Any) -> str | None:
    if value is None:
        return None
    return _ENCOUNTER_ALIASES.get(str(value).strip())


def _zone_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_")
    if text.startswith("lv"):
        text = text[2:]
    if text.startswith("zone_"):
        text = text[5:]
    try:
        number = int(text)
    except (TypeError, ValueError):
        return None
    if 1 <= number <= 10:
        return f"zone_{number:02d}"
    return None


def _source_value(source: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = source.get(name)
        if value not in (None, ""):
            return value
    return None


def resolve_monster_identity(
    source: Mapping[str, Any] | None = None,
    *,
    registry: MonsterIdentityRegistry | None = None,
    monster_id: Any = None,
    zone_id: Any = None,
    roster_slot: Any = None,
    monster_idx: Any = None,
    encounter_class: Any = None,
    encounter_type: Any = None,
    family_id: Any = None,
    monster_type: Any = None,
    battle_monster_type: Any = None,
    display_name: Any = None,
    stage: Any = None,
) -> CanonicalMonsterIdentity | None:
    """Resolve legacy identity inputs without guessing ambiguous values.

    ``None`` is an explicit unresolved result.  In particular, a type such as
    ``dragon`` is not enough to select among multiple stages.
    """

    values = dict(source or {})
    registry = registry or CANONICAL_MONSTER_IDENTITY_REGISTRY

    monster_id = monster_id if monster_id is not None else values.get("monster_id")
    zone_id = zone_id if zone_id is not None else _source_value(values, "zone_id", "zone")
    roster_slot = (
        roster_slot if roster_slot is not None else values.get("roster_slot")
    )
    if roster_slot is None and monster_idx is not None:
        try:
            roster_slot = int(monster_idx) + 1
        except (TypeError, ValueError):
            return None
    if roster_slot is None and values.get("monster_idx") is not None:
        try:
            roster_slot = int(values["monster_idx"]) + 1
        except (TypeError, ValueError):
            return None
    encounter_value = (
        encounter_class
        if encounter_class is not None
        else _source_value(values, "encounter_class", "encounter_kind")
    )
    if encounter_value is None:
        encounter_value = encounter_type if encounter_type is not None else values.get("encounter_type")
    normalized_encounter = normalize_encounter_class(encounter_value)
    if encounter_value is not None and normalized_encounter is None:
        # Adventure Boss and Lord Trial are intentionally not converted into
        # ordinary battlefield identities by F0.
        return None

    family_value = (
        family_id
        if family_id is not None
        else _source_value(values, "family_id", "monster_family", "family")
    )
    type_values = {
        str(value).strip()
        for value in (
            monster_type if monster_type is not None else values.get("monster_type"),
            battle_monster_type
            if battle_monster_type is not None
            else values.get("battle_monster_type"),
            values.get("legacy_type"),
        )
        if value not in (None, "")
    }
    display_value = (
        display_name
        if display_name is not None
        else _source_value(values, "display_name", "monster_name", "name")
    )
    requested_zone = _zone_id(
        zone_id if zone_id is not None else _source_value(values, "stage") or stage
    )

    try:
        requested_slot = int(roster_slot) if roster_slot is not None else None
    except (TypeError, ValueError):
        return None

    candidates = list(registry.entries)
    if monster_id not in (None, ""):
        candidates = [entry for entry in candidates if entry.monster_id == str(monster_id)]
    if requested_slot is not None:
        candidates = [entry for entry in candidates if entry.roster_slot == requested_slot]
    if requested_zone is not None:
        candidates = [entry for entry in candidates if entry.zone_id == requested_zone]
    if normalized_encounter is not None:
        candidates = [
            entry
            for entry in candidates
            if entry.encounter_class == normalized_encounter
        ]
    if family_value not in (None, ""):
        family_text = str(family_value).strip()
        candidates = [
            entry
            for entry in candidates
            if family_text in (entry.family_id, entry.taxonomy_battle_type)
        ]
    if type_values:
        candidates = [
            entry
            for entry in candidates
            if type_values.intersection(
                {
                    entry.legacy_type or "",
                    entry.taxonomy_battle_type or "",
                    entry.family_id,
                    *entry.legacy_aliases,
                }
            )
        ]
    if display_value not in (None, ""):
        if not (
            monster_id not in (None, "")
            or requested_slot is not None
            or requested_zone is not None
            or normalized_encounter is not None
            or family_value not in (None, "")
            or type_values
        ):
            # Localized/display text is a validation alias only, never a
            # standalone gameplay identity authority.
            return None
        candidates = [
            entry for entry in candidates if entry.legacy_name == str(display_value)
        ]

    return candidates[0] if len(candidates) == 1 else None


def canonical_battlefield_identity(
    registry: MonsterIdentityRegistry,
    monster_idx: Any,
    *,
    legacy_type: Any = None,
    legacy_name: Any = None,
    encounter_kind: Any = None,
) -> CanonicalMonsterIdentity | None:
    """Resolve one server-owned battlefield row by roster index and validate it."""

    try:
        roster_slot = int(monster_idx) + 1
    except (TypeError, ValueError):
        return None

    return resolve_monster_identity(
        registry=registry,
        roster_slot=roster_slot,
        monster_type=legacy_type,
        display_name=legacy_name,
        encounter_class=encounter_kind,
    )


__all__ = [
    "CANONICAL_BATTLEFIELD_MONSTER_COUNT",
    "CANONICAL_BATTLEFIELD_IDENTITY_SPECS",
    "CANONICAL_MONSTER_IDENTITY_REGISTRY",
    "CanonicalMonsterIdentity",
    "ENCOUNTER_CLASS_BATTLEFIELD_BOSS",
    "ENCOUNTER_CLASS_NORMAL",
    "MonsterIdentityRegistry",
    "build_battlefield_identity_registry",
    "canonical_battlefield_identity",
    "normalize_encounter_class",
    "resolve_monster_identity",
]
