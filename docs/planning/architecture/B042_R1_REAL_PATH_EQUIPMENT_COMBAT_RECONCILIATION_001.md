# B042-R1 Real-Path Equipment Combat Reconciliation

## Provenance

- Task: `B042_R1_REAL_PATH_EQUIPMENT_COMBAT_RECONCILIATION_001`
- Current origin/master at start: `95e8156d87540d4d027bd215e5db5dfc6ab70b44`
- B042 source proof: `715a237ae77937ceeea335530dbab7d6b218e224`
- R1 base: `95e8156d87540d4d027bd215e5db5dfc6ab70b44`
- `app.py` changed by R1: **NO**
- Schema/migration changed by R1: **NO**
- Production queried or mutated: **NO**

## Real-path failure and root cause

The Owner-cited test was reproduced exactly:

```text
tests/test_rpg_wave1_lane_a_combat_equipment.py::
test_equipped_armor_reduces_retaliation_and_unequip_restores_baseline
```

Before the narrow test repair, current master produced:

```text
baseline=2
armor equipped=1
armor unequipped=2
```

The failing historical expectation of `20` was stale. The current path is:

```text
_update_monster_and_quests
  -> _get_or_create_battlefield
  -> resolve_monster_combat_profile(..., context=LEGACY_BATTLEFIELD)
  -> profile.attack
  -> _mitigate_authoritative_retaliation
  -> result['monster']['player_dmg']
```

The test fixture supplies `q_info['monster_atk']=20`, but the current
runtime deliberately does not use question-side attack data on this path.
Legacy Battlefield roster slot 0 resolves through the server F004 profile to
attack `2`. The existing positive-retaliation minimum rule then produces:

```text
no armor:       2
cloth_robe 8%:  1
unequipped:     2
```

This is not double mitigation, an Equipment ordering bug, or a leaked
modifier. It is the intended current server Monster-stat authority plus the
existing integer retaliation rule. The old test contract was updated only to
those canonical values.

To prove the armor differential is not merely a low-damage rounding artifact,
R1 uses a server-authoritative persisted Monster fixture whose current F004
resolution is `legacy_bf_09_normal`, attack `28`:

```text
no armor:       28
cloth_robe 8%:  26
unequipped:     28
```

## Equipment real-path results

The current real-path Weapon test remains green and proves:

```text
baseline=80
wooden_sword=84
iron_sword=90
iron_sword unequipped=80
```

The R1 real-path accessory fixture proves the server-defined `dragon_eye`
effect reaches grade-five Combat:

```text
baseline=136
dragon_eye=408
crit_multiplier=3.0
```

This is intentionally an at-least-one statement. It does not claim every
Accessory is a Combat modifier:

- `dragon_eye`: canonical Combat critical multiplier;
- `lucky_stone`: loot only;
- `fox_mask`: non-Combat quest-XP effect;
- `xp_amulet`: `HOLD_FOR_AUTHORITY`;
- `go_stone_black`: Trophy/inventory-only.

## Map Battle and current-master drift

The existing B021 Map Battle settlement tests continue to use the same
server-derived projection through:

```text
combat_stats_resolver
  -> app._get_authoritative_combat_stats
  -> map_battle_runtime.calculate_combat_effects
  -> canonical Map Battle settlement
```

Weapon outgoing, armor incoming, and `dragon_eye` critical effects remain
server-derived. Client Combat stats and client slots are not consumed.

The current-master delta after B042 was inspected. D025 and F018 add their
separate acquisition/reward result modules. E030-R1 changes Shop/equipment
grant and loadout integration seams, but the delta contains no changes to:

```text
_get_authoritative_combat_stats
_get_active_equip_effect
_calc_damage
_mitigate_authoritative_retaliation
_update_monster_and_quests
map_battle_runtime.calculate_damage
```

Therefore E030-R1 does not replace the current Combat authority.

## Malformed post-B033 protection

R1 adds executable evidence for the canonical protection model:

1. B033 SQLite validity enforcement rejects `equipped=1` with
   `canonical_slot IS NULL`.
2. B033 partial uniqueness rejects more than one equipped row for the same
   `(user_id, canonical_slot)`.
3. B034 rejects malformed equipped pre-state before mutation, including
   duplicate effective slot state.

The pre-B033 legacy Combat fixture does not require `canonical_slot`; it
continues to prove compatibility with the legacy six-column inventory shape.
No arbitrary malformed-row winner is introduced.

## Required conclusions

```text
KNOWN_ARMOR_REAL_PATH_FAILURE_REPRODUCED=YES
ARMOR_FAILURE_ROOT_CAUSE=STALE_TEST_EXPECTATION; CURRENT F004 PROFILE ATTACK AUTHORITY
OLD_TEST_CONTRACT_STALE=YES
ARMOR_REAL_PATH_MODIFIER_CONSUMED=YES
WEAPON_REAL_PATH_MODIFIER_CONSUMED=YES
DRAGON_EYE_REAL_PATH_MODIFIER_CONSUMED=YES
AT_LEAST_ONE_CANONICAL_ACCESSORY_HAS_COMBAT_EFFECT=YES
MAP_BATTLE_EQUIPMENT_PROJECTION=PASS
MALFORMED_POST_B033_PROOF=PASS
EQUIPMENT_COMBAT_LOOP_ALREADY_CLOSED=YES
IMPLEMENTATION_REQUIRED=NO
APP_PY_FIX_REQUIRED=NO
CLIENT_COMBAT_STAT_AUTHORITY=NO
CLIENT_SLOT_AUTHORITY=NO
```

R1 therefore repairs proof and stale test expectation only. It does not add
another Combat authority or change gameplay values.
