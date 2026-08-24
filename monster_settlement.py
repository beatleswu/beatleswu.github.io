"""F006 authoritative Monster defeat, reward, and lineage seam.

This module is deliberately cardinality-agnostic.  It consumes one already
committed server decision (``monster_hp_before > 0`` and
``monster_hp_after == 0``), resolves F004/F005 profiles, records one durable
``MONSTER_DEFEATED`` event, and lets the existing ownership writers grant the
result inside the caller's transaction.

The module does not create schema, calculate combat, update Quest progress,
or own ``player_inventory``, ``player_wardrobe``, or Coins.  Those remain
caller-owned authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Callable, Mapping, Sequence

from event_outbox import (
    DuplicateOutboxEvent,
    append_event,
    get_event_by_idempotency_key,
)
from monster_drop_profiles import (
    DROP_STATUS_REACHABLE,
    MonsterDropProfile,
    get_drop_profile,
)
from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    CanonicalMonsterProfile,
    MonsterProfileRegistry,
    get_monster_profile,
)
from monster_reward_profiles import (
    MonsterRewardProfile,
    get_reward_profile,
)


MONSTER_DEFEATED_EVENT_TYPE = "MONSTER_DEFEATED"


class MonsterSettlementRejected(RuntimeError):
    """Raised when a server settlement cannot resolve a safe profile."""


@dataclass(frozen=True)
class MonsterDefeatedEvent:
    settlement_id: str
    user_id: int
    monster_id: str
    zone_id: str | None
    roster_slot: int | None
    encounter_class: str
    family_id: str | None
    hp_before: int
    hp_after: int


@dataclass(frozen=True)
class MonsterSettlementProfiles:
    monster: CanonicalMonsterProfile
    drop: MonsterDropProfile
    reward: MonsterRewardProfile


@dataclass(frozen=True)
class MonsterSettlementResult:
    event_record: Mapping[str, Any]
    duplicate: bool
    monster_id: str
    functional_drop_id: str | None
    functional_drop_quantity: int
    appearance_drop_id: str | None
    coins_granted: int | None
    functional_lineage_count: int
    wardrobe_lineage_count: int
    functional_payload: Mapping[str, Any] | None
    appearance_payload: Mapping[str, Any] | None
    quest_event: Mapping[str, Any]


def build_monster_defeated_event(
    *,
    settlement_id: Any,
    user_id: Any,
    monster_id: Any,
    hp_before: Any,
    hp_after: Any,
    zone_id: Any = None,
    roster_slot: Any = None,
    encounter_class: Any = "NORMAL",
    family_id: Any = None,
) -> MonsterDefeatedEvent:
    """Build the only accepted Monster defeat transition.

    A client result, kill flag, or drop claim is never enough.  The caller
    must provide the server-owned before/after HP values from its committed
    settlement boundary.
    """

    settlement_text = str(settlement_id or "").strip()
    if not settlement_text:
        raise MonsterSettlementRejected("settlement identity is required")
    try:
        uid = int(user_id)
        before = int(hp_before)
        after = int(hp_after)
    except (TypeError, ValueError) as exc:
        raise MonsterSettlementRejected("invalid Monster settlement values") from exc
    monster_text = str(monster_id or "").strip()
    if not monster_text or uid <= 0 or before <= 0 or after != 0:
        raise MonsterSettlementRejected("Monster defeat transition is not authoritative")
    try:
        slot = int(roster_slot) if roster_slot is not None else None
    except (TypeError, ValueError) as exc:
        raise MonsterSettlementRejected("invalid Monster roster slot") from exc
    return MonsterDefeatedEvent(
        settlement_id=settlement_text,
        user_id=uid,
        monster_id=monster_text,
        zone_id=str(zone_id) if zone_id not in (None, "") else None,
        roster_slot=slot,
        encounter_class=str(encounter_class or "NORMAL"),
        family_id=str(family_id) if family_id not in (None, "") else None,
        hp_before=before,
        hp_after=after,
    )


def resolve_monster_settlement_profiles(
    monster_id: Any,
    *,
    monster_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
    drop_registry: Mapping[str, MonsterDropProfile] | None = None,
    reward_registry: Mapping[str, MonsterRewardProfile] | None = None,
) -> MonsterSettlementProfiles | None:
    """Resolve one Monster through the F004 profile and F005 references."""

    monster = get_monster_profile(monster_id, registry=monster_registry)
    if monster is None or not monster.enabled:
        return None
    if drop_registry is None:
        from monster_drop_profiles import CANONICAL_DROP_PROFILE_REGISTRY

        drop_registry = CANONICAL_DROP_PROFILE_REGISTRY
    if reward_registry is None:
        from monster_reward_profiles import CANONICAL_REWARD_PROFILE_REGISTRY

        reward_registry = CANONICAL_REWARD_PROFILE_REGISTRY
    drop = get_drop_profile(monster.drop_profile_id, registry=drop_registry)
    reward = get_reward_profile(monster.reward_profile_id, registry=reward_registry)
    if drop is None or reward is None or not drop.enabled or not reward.enabled:
        return None
    return MonsterSettlementProfiles(monster=monster, drop=drop, reward=reward)


def roll_functional_drop(
    profile: MonsterDropProfile,
    *,
    loot_bonus: float = 0.0,
    random_source: Any = None,
) -> tuple[str | None, int]:
    """Roll the exact F005 functional drop values once.

    ``gate_chance`` and relative entry weights come from F005.  No new
    rarity, pity, quantity, or balance rule is introduced.
    """

    if profile.status != DROP_STATUS_REACHABLE or not profile.entries:
        return None, 0
    rng = random_source or random
    chance = profile.gate_chance + float(loot_bonus or 0.0)
    if rng.random() > chance:
        return None, 0
    entries = tuple(profile.entries)
    selected = rng.choices(
        entries,
        weights=[entry.relative_weight for entry in entries],
        k=1,
    )[0]
    return selected.item_id, int(selected.quantity)


def next_roster_entry(
    roster: Sequence[Sequence[Any]],
    current_index: Any,
) -> tuple[int | None, Sequence[Any] | None]:
    """Select the next data entry without encoding a roster cardinality."""

    entries = tuple(roster)
    if not entries:
        return None, None
    try:
        index = int(current_index)
    except (TypeError, ValueError):
        return None, None
    next_index = (index + 1) % len(entries)
    return next_index, entries[next_index]


def _event_key(event: MonsterDefeatedEvent) -> str:
    return f"monster-defeated:{event.settlement_id}"


def _event_payload(
    event: MonsterDefeatedEvent,
    profiles: MonsterSettlementProfiles,
    *,
    functional_drop_id: str | None,
    functional_drop_quantity: int,
    appearance_drop_id: str | None,
) -> dict[str, Any]:
    return {
        "settlement_id": event.settlement_id,
        "monster_id": event.monster_id,
        "zone_id": event.zone_id,
        "roster_slot": event.roster_slot,
        "encounter_class": event.encounter_class,
        "family_id": event.family_id,
        "hp_before": event.hp_before,
        "hp_after": event.hp_after,
        "drop_profile_id": profiles.monster.drop_profile_id,
        "reward_profile_id": profiles.monster.reward_profile_id,
        "functional_drop_id": functional_drop_id,
        "functional_drop_quantity": functional_drop_quantity,
        "appearance_drop_id": appearance_drop_id,
        "coins_requested": int(profiles.reward.coins or 0),
    }


def _assert_existing_event_matches(
    existing: Mapping[str, Any],
    event: MonsterDefeatedEvent,
) -> Mapping[str, Any]:
    payload = existing.get("payload") or {}
    if (
        str(payload.get("settlement_id") or "") != event.settlement_id
        or str(payload.get("monster_id") or "") != event.monster_id
        or payload.get("hp_after") is None
        or int(payload.get("hp_after")) != 0
    ):
        raise MonsterSettlementRejected("Monster settlement idempotency conflict")
    return payload


def _replay_result(
    existing: Mapping[str, Any],
    event: MonsterDefeatedEvent,
) -> MonsterSettlementResult:
    payload = _assert_existing_event_matches(existing, event)
    return MonsterSettlementResult(
        event_record=existing,
        duplicate=True,
        monster_id=event.monster_id,
        functional_drop_id=payload.get("functional_drop_id"),
        functional_drop_quantity=int(payload.get("functional_drop_quantity") or 0),
        appearance_drop_id=payload.get("appearance_drop_id"),
        coins_granted=payload.get("coins_granted"),
        functional_lineage_count=0,
        wardrobe_lineage_count=0,
        functional_payload=None,
        appearance_payload=None,
        quest_event={
            "event_type": MONSTER_DEFEATED_EVENT_TYPE,
            "event_id": existing.get("event_id"),
            "settlement_id": event.settlement_id,
            "duplicate": True,
        },
    )


def settle_monster_defeat(
    conn: Any,
    event: MonsterDefeatedEvent,
    *,
    monster_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
    drop_registry: Mapping[str, MonsterDropProfile] | None = None,
    reward_registry: Mapping[str, MonsterRewardProfile] | None = None,
    loot_bonus: float = 0.0,
    appearance_roll: Callable[[str], Any] | None = None,
    grant_coins: Callable[[int, str], int] | None = None,
    grant_functional_item: Callable[[str, int, str], Mapping[str, Any]] | None = None,
    grant_wardrobe_item: Callable[[str, str], Mapping[str, Any]] | None = None,
    random_source: Any = None,
) -> MonsterSettlementResult:
    """Settle one committed defeat inside the caller's transaction.

    The durable Monster event is the idempotency gate.  Its payload stores the
    single random result, so retries replay rather than reroll.  Ownership and
    currency callbacks remain the existing server authorities.
    """

    profiles = resolve_monster_settlement_profiles(
        event.monster_id,
        monster_registry=monster_registry,
        drop_registry=drop_registry,
        reward_registry=reward_registry,
    )
    if profiles is None:
        raise MonsterSettlementRejected("Monster profile resolution failed closed")

    idempotency_key = _event_key(event)
    existing = get_event_by_idempotency_key(
        conn,
        player_id=str(event.user_id),
        event_type=MONSTER_DEFEATED_EVENT_TYPE,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return _replay_result(existing, event)

    functional_drop_id, functional_drop_quantity = roll_functional_drop(
        profiles.drop,
        loot_bonus=loot_bonus,
        random_source=random_source,
    )
    appearance_value = (
        appearance_roll(profiles.drop.legacy_monster_type)
        if appearance_roll is not None
        else None
    )
    appearance_drop_id = (
        appearance_value.get("id")
        if isinstance(appearance_value, Mapping)
        else str(appearance_value) if appearance_value else None
    )
    payload = _event_payload(
        event,
        profiles,
        functional_drop_id=functional_drop_id,
        functional_drop_quantity=functional_drop_quantity,
        appearance_drop_id=appearance_drop_id,
    )
    try:
        event_record = append_event(
            conn,
            event_type=MONSTER_DEFEATED_EVENT_TYPE,
            player_id=str(event.user_id),
            lineage_id=f"monster-settlement:{event.settlement_id}",
            source_event_id=event.settlement_id,
            idempotency_key=idempotency_key,
            outcome="SUCCESS",
            payload=payload,
        )
    except DuplicateOutboxEvent as duplicate:
        return _replay_result(duplicate.existing_event, event)

    coins_granted = 0
    if profiles.reward.coins and grant_coins is not None:
        coins_granted = int(
            grant_coins(int(profiles.reward.coins), "monster_kill") or 0
        )

    functional_lineage_count = 0
    functional_payload = None
    if functional_drop_id and grant_functional_item is None:
        raise MonsterSettlementRejected(
            "functional drop resolved without an ownership writer"
        )
    if functional_drop_id:
        grant = grant_functional_item(
            functional_drop_id,
            functional_drop_quantity,
            "drop",
        )
        grant_id = str(grant.get("grant_id") or "").strip()
        if not grant_id:
            raise MonsterSettlementRejected("functional item grant identity missing")
        append_event(
            conn,
            event_type="ITEM_ACQUISITION",
            player_id=str(event.user_id),
            lineage_id=grant_id,
            source_event_id=str(event_record["event_id"]),
            idempotency_key=f"item-acquisition:{grant_id}",
            outcome="SUCCESS",
            payload={
                "operation": "GRANT",
                "grant_id": grant_id,
                "item_id": functional_drop_id,
                "quantity": functional_drop_quantity,
                "acquisition_source": "MONSTER_DROP",
                "source_reference": event.settlement_id,
                "ownership_authority": "player_inventory",
                "ownership_committed": True,
            },
        )
        functional_lineage_count = 1
        functional_payload = grant.get("payload")

    wardrobe_lineage_count = 0
    appearance_payload = None
    if appearance_drop_id and grant_wardrobe_item is None:
        raise MonsterSettlementRejected(
            "appearance drop resolved without a wardrobe ownership writer"
        )
    if appearance_drop_id:
        grant = grant_wardrobe_item(appearance_drop_id, "drop")
        if grant.get("new"):
            grant_id = str(grant.get("grant_id") or "").strip()
            if not grant_id:
                raise MonsterSettlementRejected("wardrobe grant identity missing")
            append_event(
                conn,
                event_type="ITEM_ACQUISITION",
                player_id=str(event.user_id),
                lineage_id=grant_id,
                source_event_id=str(event_record["event_id"]),
                idempotency_key=f"item-acquisition:{grant_id}",
                outcome="SUCCESS",
                payload={
                    "operation": "GRANT",
                    "grant_id": grant_id,
                    "item_id": appearance_drop_id,
                    "quantity": 1,
                    "acquisition_source": "MONSTER_DROP",
                    "source_reference": event.settlement_id,
                    "ownership_authority": "player_wardrobe",
                    "ownership_committed": True,
                },
            )
            wardrobe_lineage_count = 1
        appearance_payload = grant.get("payload")

    payload["coins_granted"] = coins_granted
    return MonsterSettlementResult(
        event_record={**event_record, "payload": payload},
        duplicate=False,
        monster_id=event.monster_id,
        functional_drop_id=functional_drop_id,
        functional_drop_quantity=functional_drop_quantity,
        appearance_drop_id=appearance_drop_id,
        coins_granted=coins_granted,
        functional_lineage_count=functional_lineage_count,
        wardrobe_lineage_count=wardrobe_lineage_count,
        functional_payload=functional_payload,
        appearance_payload=appearance_payload,
        quest_event={
            "event_type": MONSTER_DEFEATED_EVENT_TYPE,
            "event_id": event_record.get("event_id"),
            "settlement_id": event.settlement_id,
            "monster_id": event.monster_id,
            "duplicate": False,
        },
    )


__all__ = [
    "MONSTER_DEFEATED_EVENT_TYPE",
    "MonsterDefeatedEvent",
    "MonsterSettlementProfiles",
    "MonsterSettlementRejected",
    "MonsterSettlementResult",
    "build_monster_defeated_event",
    "next_roster_entry",
    "resolve_monster_settlement_profiles",
    "roll_functional_drop",
    "settle_monster_defeat",
]
