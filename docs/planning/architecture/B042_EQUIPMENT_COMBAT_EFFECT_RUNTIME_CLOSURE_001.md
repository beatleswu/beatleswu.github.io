# B042 Equipment Combat Effect Runtime Closure

## Candidate provenance

- Task: `B042_EQUIPMENT_COMBAT_EFFECT_RUNTIME_CLOSURE_001`
- Current origin/master at start: `e10735cf580fb5074e07811f76ab60445562760c`
- Candidate base: `e10735cf580fb5074e07811f76ab60445562760c`
- Runtime implementation required: **NO**
- `app.py` changed: **NO**
- Schema or migration changed: **NO**
- Production accessed or mutated: **NO**

## Finding

The functional Equipment → Combat loop is already closed on current master.
No second Equipment combat authority is required.

The canonical path is:

```text
player_inventory.equipped
  -> app._get_authoritative_combat_stats
  -> server EQUIPMENT_DEFS and _FUNCTIONAL_EFFECT_ACTIVE_KEYS
  -> legacy app._calc_damage / retaliation mitigation
```

Map Battle consumes the same server-derived combat projection:

```text
map_battle_runtime.settle_answer
  -> combat_stats_resolver
  -> map_battle_runtime.calculate_combat_effects
  -> map_battle_persistence.settle_map_battle_submission
```

The Spirit adapter is downstream of Equipment in the existing Map Battle
ordering. B042 does not change Spirit policy or settlement.

## Authority map

| Concern | Current authority | Evidence |
| --- | --- | --- |
| Owned/equipped Equipment identity | `player_inventory` | `app._get_authoritative_combat_stats` and `_get_active_equip_effect` query only rows with `equipped=1`. |
| Functional slot/effect definition | `app.EQUIPMENT_DEFS` | Weapon, armor, and accessory definitions contain the server effect data. |
| Effect activation boundary | `app._FUNCTIONAL_EFFECT_ACTIVE_KEYS` | Only effects with an explicit server consumer contribute; `xp_amulet` and `go_stone_black` are empty. |
| Outgoing damage | `app._calc_damage`, then Map Battle `calculate_damage` | Both consume the resolved `attack_bonus` and `crit_multiplier`. |
| Incoming damage | `app._mitigate_authoritative_retaliation`, then Map Battle `calculate_damage` | Both consume resolved armor/counter fields. |
| Loadout mutation | B034 `equipment_loadout_service.py` | B033 schema required; server slot projection; no commit/rollback; malformed state fails closed. |
| Exact ownership-row targeting | B041 extension of B034 | Optional `ownership_row_id` targets one `player_inventory.id`; item-identity mode remains compatible. |
| Spirit | Existing B027 policy/runtime | Consumed separately after the Equipment combat projection. |

## Runtime proof

Current server definitions include functional combat consumers:

- Weapons: `dmg_bonus`, with monster-specific bonuses where defined.
- Armor: `player_dmg_reduce`, plus existing counter-negation behavior.
- Accessory: `dragon_eye.crit_multiplier` is a canonical Combat effect.
- Non-combat or held definitions remain separate from Combat. `lucky_stone`
  affects loot, `fox_mask` affects quest XP, `xp_amulet` is held, and
  `go_stone_black` is inventory-only.

The existing B021 real-path regression suite already proves the closed loop
for legacy Combat and Map Battle. The focused B042 proof adds direct current-
master assertions for:

1. baseline → equipped weapon → unequipped weapon damage;
2. baseline → equipped armor → unequipped armor retaliation;
3. server-defined `dragon_eye` critical damage;
4. duplicate ownership where only the exact equipped row contributes;
5. held/inventory-only items contributing no unauthorized Combat effect; and
6. malformed duplicate equipped state being rejected by the B034 loadout
   authority before mutation.

## B033 and malformed-state boundary

In canonical post-B033 storage, the database validity rule requires
`equipped=false OR canonical_slot IS NOT NULL`, and the partial unique index
allows at most one equipped row per `(user_id, canonical_slot)`. B034 also
requires the accepted B033 schema and rejects duplicate or otherwise
malformed equipped state before changing it.

The legacy Combat reader remains compatible with pre-B033 fixtures because it
reads the existing `equipped` state and does not require a migration column.
Production migration/preflight and the B034 command boundary remain the
authoritative protection against malformed post-B033 storage; B042 does not
invent a second combat-state validator or silently select a malformed row.

## Required conclusions

```text
DO_EQUIPPED_WEAPONS_CHANGE_OUTGOING_DAMAGE=YES
DO_EQUIPPED_ARMOR_CHANGE_INCOMING_DAMAGE=YES
DO_EQUIPPED_ACCESSORIES_HAVE_CANONICAL_COMBAT_EFFECT=YES
EQUIPMENT_COMBAT_LOOP_ALREADY_CLOSED=YES
IMPLEMENTATION_REQUIRED=NO
CLIENT_COMBAT_STAT_AUTHORITY=NO
CLIENT_SLOT_AUTHORITY=NO
SPIRIT_AUTHORITY_CHANGED=NO
```

`DO_EQUIPPED_ACCESSORIES_HAVE_CANONICAL_COMBAT_EFFECT=YES` means that at
least one current server-defined accessory (`dragon_eye`) has a live Combat
consumer. It does not mean every accessory is a Combat modifier.

## Compatibility and exclusions

- `player_appearance.combat_*` is not read by the canonical Combat stats
  resolver.
- Client-supplied stats, slots, and presentation/inventory fields are not
  Combat authority.
- Pre-B033 legacy rows remain readable by the existing Combat path. B033 is
  still required for canonical slot enforcement and B034 loadout commands.
- `xp_amulet` remains `HOLD_FOR_AUTHORITY` and contributes no new Combat
  effect.
- `go_stone_black` remains a Trophy/inventory-only item and contributes no
  Combat effect.
- Spirit policy, Equipment definitions, Monster stats, and settlement logic
  were not modified.

## B042 changed-surface decision

This is a proof-only candidate. The only intended changes are this document
and the focused regression test. No runtime implementation is needed because
the canonical Equipment combat loop is already present and covered by the
current B021/B025/B026-era settlement path.
