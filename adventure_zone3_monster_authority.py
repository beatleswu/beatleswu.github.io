"""Server-owned Adventure Normal monster authority for Zone 3.

E055 deliberately keeps this binding separate from the Battlefield catalog.
The module is a small, explicit content/profile registry for the Goblin Cave
slice.  It owns the server-side identity that is persisted with an Adventure
Map Battle, while presentation helpers expose only a read-only projection to
the browser.

The drop and reward registries referenced here are the existing settlement
registries.  They are references, not a second settlement implementation.
Likewise, the normal combat values are the current Map Battle server defaults
until a separately governed Adventure balance authority exists; they are
stored explicitly in each versioned binding and never calculated by Zone.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from monster_combat_profiles import MonsterCombatProfile
from monster_drop_profiles import CANONICAL_DROP_PROFILE_REGISTRY
from monster_profiles import (
    CanonicalMonsterProfile,
    MonsterDropProfile as FoundationDropProfile,
    MonsterPresentationProfile,
    MonsterProfileRegistry,
    MonsterRewardProfile as FoundationRewardProfile,
    MonsterStatProfile,
)
from monster_reward_profiles import CANONICAL_REWARD_PROFILE_REGISTRY


ZONE3_KEY = "k16_20"
ZONE3_DISPLAY_KEY = "adventure.zone3.goblin_cave"
ZONE3_LORD_ID = "goblin_centurion"
ZONE3_LORD_CLASSIFICATION = "LORD_ONLY"
ZONE3_ENCOUNTER_CLASS = "NORMAL"
ZONE3_BINDING_SOURCE = "adventure-zone3-monster-catalog"
ZONE3_BINDING_VERSION = "e055.zone3.binding.v1"
ZONE3_PROFILE_VERSION = "e055.zone3.normal.v1"

# These are the currently deployed Map Battle server defaults.  They are
# copied into explicit Adventure profiles rather than inherited at runtime;
# a future balance task may replace this version with an owner-approved
# Adventure profile set.
ZONE3_NORMAL_MAX_HP = 100
ZONE3_NORMAL_ATTACK = 8

ZONE3_NORMAL_IDS: tuple[str, ...] = (
    "M022",
    "M023",
    "M024",
    "M025",
    "M026",
    "M027",
    "M028",
    "M029",
    "M030",
    "M031",
    "M032",
    "M033",
    "M060",
)

# M022 is the protected legacy asset.  The other Zone 3 presentation assets
# are canonical art paths admitted by the current master; no art filename is
# used to derive identity or select gameplay.
ZONE3_PRESENTATION_ASSET_FILENAMES: tuple[str, ...] = (
    "M023_coppercap_goblin.png",
    "M024_echo_bat.png",
    "M025_pickaxe_moleworker.png",
    "M026_fungus_lantern_imp.png",
    "M027_rope_ladder_lizard.png",
    "M028_ironbucket_beetle.png",
    "M029_crevice_snake.png",
    "M030_cartcap_crawler.png",
    "M031_crystal_ore_gob.png",
    "M032_cavern_slinger.png",
    "M033_stalactite_tortoise.png",
    "M060_crystalhorn_lizard.png",
)

_ZONE3_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    ("M022", "洞穴獸人", "Cave Orc Grunt", "orc", "/assets/monsters/orc_grunt_chibi.png"),
    ("M023", "銅帽哥布林", "Coppercap Goblin", "goblin", "/art/monsters/M023_coppercap_goblin.png"),
    ("M024", "回音蝙蝠", "Echo Bat", "bat", "/art/monsters/M024_echo_bat.png"),
    ("M025", "鎬工鼴鼠", "Pickaxe Moleworker", "mole", "/art/monsters/M025_pickaxe_moleworker.png"),
    ("M026", "菌燈小鬼", "Fungus Lantern Imp", "imp", "/art/monsters/M026_fungus_lantern_imp.png"),
    ("M027", "繩梯蜥蜴", "Rope-Ladder Lizard", "lizard", "/art/monsters/M027_rope_ladder_lizard.png"),
    ("M028", "鐵桶甲蟲", "Ironbucket Beetle", "beetle", "/art/monsters/M028_ironbucket_beetle.png"),
    ("M029", "裂隙蛇", "Crevice Snake", "snake", "/art/monsters/M029_crevice_snake.png"),
    ("M030", "礦車爬蟲", "Cartcap Crawler", "crawler", "/art/monsters/M030_cartcap_crawler.png"),
    ("M031", "晶礦哥布林", "Crystal Ore Gob", "goblin", "/art/monsters/M031_crystal_ore_gob.png"),
    ("M032", "洞窟投石手", "Cavern Slinger", "goblin", "/art/monsters/M032_cavern_slinger.png"),
    ("M033", "鐘乳石巨龜", "Stalactite Tortoise", "tortoise", "/art/monsters/M033_stalactite_tortoise.png"),
    ("M060", "晶角蜥蜴", "Crystalhorn Lizard", "lizard", "/art/monsters/M060_crystalhorn_lizard.png"),
)


class Zone3MonsterAuthorityError(ValueError):
    """Raised when a persisted Zone 3 identity/profile binding is invalid."""


@dataclass(frozen=True)
class AdventureZone3MonsterBinding:
    """One immutable server-owned Normal encounter binding."""

    monster_id: str
    roster_slot: int
    zone_key: str
    encounter_class: str
    taxonomy_family: str
    display_name: str
    display_name_en: str
    presentation_asset: str
    profile_id: str
    profile_version: str
    max_hp: int
    attack: int
    drop_profile_id: str
    reward_profile_id: str

    def to_presentation_payload(
        self,
        *,
        hp: int | None = None,
        defeated: bool = False,
    ) -> dict[str, Any]:
        """Return fields safe for rendering; no settlement authority leaks."""

        current_hp = self.max_hp if hp is None else max(0, min(self.max_hp, int(hp)))
        return {
            "monster_id": self.monster_id,
            "name": self.display_name,
            "name_en": self.display_name_en,
            "avatar": self.presentation_asset,
            "zone_key": self.zone_key,
            "encounter_class": self.encounter_class,
            "role": "NORMAL",
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "hp": current_hp,
            "max_hp": self.max_hp,
            "defeated": bool(defeated or current_hp == 0),
        }


def _build_registry() -> tuple[
    MonsterProfileRegistry,
    dict[str, AdventureZone3MonsterBinding],
]:
    if tuple(spec[0] for spec in _ZONE3_SPECS) != ZONE3_NORMAL_IDS:
        raise ValueError("Zone 3 explicit roster does not match approved IDs")

    stat_profiles: dict[str, MonsterStatProfile] = {}
    drop_profiles: dict[str, FoundationDropProfile] = {}
    reward_profiles: dict[str, FoundationRewardProfile] = {}
    presentation_profiles: dict[str, MonsterPresentationProfile] = {}
    profiles: list[CanonicalMonsterProfile] = []
    bindings: dict[str, AdventureZone3MonsterBinding] = {}

    for roster_slot, (monster_id, name, name_en, family, asset) in enumerate(
        _ZONE3_SPECS,
        start=1,
    ):
        profile_id = f"adventure_z3_normal_{monster_id}"
        stat_id = f"stat_{profile_id}"
        drop_id = "drop_legacy_goblin"
        reward_id = "reward_battlefield_legacy"
        presentation_id = f"presentation_{profile_id}"
        stat_profiles[stat_id] = MonsterStatProfile(
            profile_id=stat_id,
            max_hp=ZONE3_NORMAL_MAX_HP,
            attack=ZONE3_NORMAL_ATTACK,
        )
        # These foundation references intentionally point at the existing
        # settlement vocabulary; the actual authoritative registries are
        # supplied to settle_monster_defeat by the caller.
        drop_profiles.setdefault(
            drop_id,
            FoundationDropProfile(
                profile_id=drop_id,
                legacy_monster_type="goblin",
                source_ref="monster_drop_profiles.CANONICAL_DROP_PROFILE_REGISTRY",
            ),
        )
        reward_profiles.setdefault(
            reward_id,
            FoundationRewardProfile(
                profile_id=reward_id,
                source_ref="monster_reward_profiles.CANONICAL_REWARD_PROFILE_REGISTRY",
            ),
        )
        presentation_profiles[presentation_id] = MonsterPresentationProfile(
            profile_id=presentation_id,
            display_key=f"{ZONE3_DISPLAY_KEY}.{monster_id}",
            source_ref="E055 canonical presentation binding",
        )
        profiles.append(
            CanonicalMonsterProfile(
                monster_id=monster_id,
                roster_slot=roster_slot,
                zone_key=ZONE3_KEY,
                encounter_class=ZONE3_ENCOUNTER_CLASS,
                taxonomy_family=family,
                display_key=f"{ZONE3_DISPLAY_KEY}.{monster_id}",
                stat_profile_id=stat_id,
                drop_profile_id=drop_id,
                reward_profile_id=reward_id,
                presentation_profile_id=presentation_id,
                enabled=True,
                legacy_aliases=(),
                boss_role=None,
            )
        )
        bindings[monster_id] = AdventureZone3MonsterBinding(
            monster_id=monster_id,
            roster_slot=roster_slot,
            zone_key=ZONE3_KEY,
            encounter_class=ZONE3_ENCOUNTER_CLASS,
            taxonomy_family=family,
            display_name=name,
            display_name_en=name_en,
            presentation_asset=asset,
            profile_id=profile_id,
            profile_version=ZONE3_PROFILE_VERSION,
            max_hp=ZONE3_NORMAL_MAX_HP,
            attack=ZONE3_NORMAL_ATTACK,
            drop_profile_id=drop_id,
            reward_profile_id=reward_id,
        )

    registry = MonsterProfileRegistry(
        profiles=tuple(profiles),
        by_id={profile.monster_id: profile for profile in profiles},
        by_roster_slot={profile.roster_slot: profile for profile in profiles},
        stat_profiles=stat_profiles,
        drop_profiles=drop_profiles,
        reward_profiles=reward_profiles,
        presentation_profiles=presentation_profiles,
    )
    return registry, bindings


ZONE3_MONSTER_PROFILE_REGISTRY, _ZONE3_BINDINGS = _build_registry()
ZONE3_DROP_PROFILE_REGISTRY = CANONICAL_DROP_PROFILE_REGISTRY
ZONE3_REWARD_PROFILE_REGISTRY = CANONICAL_REWARD_PROFILE_REGISTRY
ZONE3_BINDING_COUNT = len(_ZONE3_BINDINGS)


# An explicit stable-key selector map makes the selection policy inspectable;
# it does not derive identity from art, array position, or display text.
_ZONE3_SELECTION_BUCKET_TO_ID: Mapping[int, str] = {
    0: "M022",
    1: "M023",
    2: "M024",
    3: "M025",
    4: "M026",
    5: "M027",
    6: "M028",
    7: "M029",
    8: "M030",
    9: "M031",
    10: "M032",
    11: "M033",
    12: "M060",
}


def get_zone3_binding(monster_id: Any) -> AdventureZone3MonsterBinding | None:
    """Resolve an exact canonical M-ID; unknown values fail closed."""

    if monster_id in (None, ""):
        return None
    return _ZONE3_BINDINGS.get(str(monster_id).strip())


def require_zone3_binding(monster_id: Any) -> AdventureZone3MonsterBinding:
    binding = get_zone3_binding(monster_id)
    if binding is None:
        raise Zone3MonsterAuthorityError("unknown Zone 3 Monster identity")
    return binding


def select_zone3_binding(question_id: Any) -> AdventureZone3MonsterBinding:
    """Select a deterministic server-owned Monster for one question identity."""

    try:
        question_key = str(int(question_id))
    except (TypeError, ValueError) as exc:
        raise Zone3MonsterAuthorityError("question identity is invalid") from exc
    if int(question_key) <= 0:
        raise Zone3MonsterAuthorityError("question identity is invalid")
    digest = hashlib.sha256(f"{ZONE3_KEY}:{question_key}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % len(_ZONE3_SELECTION_BUCKET_TO_ID)
    return require_zone3_binding(_ZONE3_SELECTION_BUCKET_TO_ID[bucket])


def zone3_combat_profile(binding: AdventureZone3MonsterBinding) -> MonsterCombatProfile:
    """Build the explicit profile consumed by the existing combat runtime."""

    if not isinstance(binding, AdventureZone3MonsterBinding):
        raise Zone3MonsterAuthorityError("Zone 3 binding is invalid")
    return MonsterCombatProfile(
        canonical_monster_id=binding.monster_id,
        zone_key=binding.zone_key,
        roster_slot=binding.roster_slot,
        encounter_class=binding.encounter_class,
        max_hp=binding.max_hp,
        attack=binding.attack,
        profile_id=binding.profile_id,
        stat_source="E055_ADVENTURE_ZONE3_MONSTER_CATALOG",
        compatibility_mode="ADVENTURE_ZONE3_EXPLICIT_PROFILE",
        profile_version=binding.profile_version,
        provenance=(
            ("source", ZONE3_BINDING_SOURCE),
            ("monster_id", binding.monster_id),
            ("profile_id", binding.profile_id),
        ),
    )


def encode_zone3_binding(binding: AdventureZone3MonsterBinding) -> str:
    """Encode only server-created binding fields into an existing DB column."""

    if not isinstance(binding, AdventureZone3MonsterBinding):
        raise Zone3MonsterAuthorityError("Zone 3 binding is invalid")
    return ":".join(
        (
            ZONE3_BINDING_VERSION,
            binding.monster_id,
            binding.profile_id,
            binding.profile_version,
        )
    )


def decode_zone3_binding(
    battle: Mapping[str, Any],
) -> AdventureZone3MonsterBinding:
    """Recover a persisted binding and validate every authority component."""

    if str(battle.get("zone_key") or "") != ZONE3_KEY:
        raise Zone3MonsterAuthorityError("battle is not a Zone 3 encounter")
    if str(battle.get("migration_source") or "") != ZONE3_BINDING_SOURCE:
        raise Zone3MonsterAuthorityError("Zone 3 binding source is missing")
    parts = str(battle.get("migration_version") or "").split(":")
    if len(parts) != 4 or parts[0] != ZONE3_BINDING_VERSION:
        raise Zone3MonsterAuthorityError("Zone 3 binding version is invalid")
    binding = require_zone3_binding(parts[1])
    if binding.profile_id != parts[2] or binding.profile_version != parts[3]:
        raise Zone3MonsterAuthorityError("Zone 3 profile binding does not match")
    return binding


def zone3_presentation_for_battle(
    battle: Mapping[str, Any],
) -> dict[str, Any]:
    binding = decode_zone3_binding(battle)
    return binding.to_presentation_payload(
        hp=int(battle.get("monster_hp") or 0),
        defeated=str(battle.get("state") or "") == "COMPLETED"
        and int(battle.get("monster_hp") or 0) == 0,
    )


def resolve_zone3_binding_for_battle(
    battle: Mapping[str, Any],
) -> AdventureZone3MonsterBinding:
    return decode_zone3_binding(battle)


__all__ = [
    "AdventureZone3MonsterBinding",
    "ZONE3_BINDING_SOURCE",
    "ZONE3_BINDING_VERSION",
    "ZONE3_DISPLAY_KEY",
    "ZONE3_DROP_PROFILE_REGISTRY",
    "ZONE3_ENCOUNTER_CLASS",
    "ZONE3_KEY",
    "ZONE3_LORD_CLASSIFICATION",
    "ZONE3_LORD_ID",
    "ZONE3_MONSTER_PROFILE_REGISTRY",
    "ZONE3_NORMAL_ATTACK",
    "ZONE3_NORMAL_IDS",
    "ZONE3_NORMAL_MAX_HP",
    "ZONE3_PRESENTATION_ASSET_FILENAMES",
    "ZONE3_PROFILE_VERSION",
    "ZONE3_REWARD_PROFILE_REGISTRY",
    "ZONE3_BINDING_COUNT",
    "Zone3MonsterAuthorityError",
    "decode_zone3_binding",
    "encode_zone3_binding",
    "get_zone3_binding",
    "require_zone3_binding",
    "resolve_zone3_binding_for_battle",
    "select_zone3_binding",
    "zone3_combat_profile",
    "zone3_presentation_for_battle",
]
