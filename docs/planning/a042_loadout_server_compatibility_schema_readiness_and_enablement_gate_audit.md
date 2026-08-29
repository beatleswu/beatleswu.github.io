# A042 Loadout server compatibility, schema readiness, and enablement-gate audit

This is a read-only readiness audit against fresh `origin/master`. It does not
enable Loadout, modify `app.py`, apply B033, query or mutate Production, or
change runtime/static source.

## Identity and reconciliation

```text
TASK=A042_LOADOUT_SERVER_COMPATIBILITY_SCHEMA_READINESS_AND_ENABLEMENT_GATE_AUDIT_001
CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec
BASE_SHA=6829c4c528adf4800326e90534585a32e390ebec
A040_HEAD=0287031118375f5dd0786ff0d41c9420a6a0dd5a
A041_HEAD=b861181fcaee78ac392f90ffd14375b28d0c4074
FRESH_MASTER_RECONCILIATION=PASS
FRESH_MASTER_IS_ANCESTOR=YES
A040_IS_ANCESTOR_OF_FRESH_MASTER=NO
A041_IS_ANCESTOR_OF_FRESH_MASTER=NO
BRANCH=codex/a042-loadout-server-compatibility-schema-readiness-and-enablement-gate-audit-001
LOCAL_HEAD=POST_COMMIT_SHA_REPORTED_IN_TASK_RESULT
REMOTE_HEAD=POST_PUSH_SHA_REPORTED_IN_TASK_RESULT
REMOTE_HEAD_EXACT=YES
```

Fresh master contains the accepted A034--A038 server/equipment contracts and
the A038 tests, but not the A040/A041 commits. A040/A041 changes therefore
remain a dependency reconciliation gate; their accepted browser proof is
referenced as `A041_BROWSER_PROOF=PASS`, not re-created as fresh-master source.

## B033 schema contract

```text
B033_REQUIRED_TABLES=player_inventory
B033_REQUIRED_COLUMNS=id,user_id,equip_id,equipped,obtained_at,source,canonical_slot(nullable)
B033_REQUIRED_INDEXES=idx_inv_user(user_id); uq_player_inventory_user_equipped_slot UNIQUE(user_id,canonical_slot) WHERE equipped=1 AND canonical_slot IS NOT NULL
B033_REQUIRED_CONSTRAINTS=PostgreSQL ck_player_inventory_equipped_requires_slot CHECK(equipped=0 OR canonical_slot IS NOT NULL); SQLite equivalent named INSERT/UPDATE triggers; no ownership uniqueness or user FK is added by B033
```

Evidence classification:

| Dependency | State | Evidence and limitation |
| --- | --- | --- |
| `player_inventory` legacy table | `SOURCE_SCHEMA_DEFINED` | `app.py:init_db` defines the six-column table and `idx_inv_user`; `canonical_slot` is absent there. |
| B033 migration artifact | `MIGRATION_ARTIFACT_EXISTS` | `migrations/equipment_canonical_slot_v1.py` defines additive `canonical_slot`, validation, backfill/preflight, PostgreSQL check/index, SQLite triggers, and advisory lock `773310034`. It does not commit, repair data, or run at application startup. |
| B033 test schema | `TEST_SCHEMA_PROVEN` | Focused SQLite schema/migration tests and loadout-service tests passed. PostgreSQL tests are explicitly skipped without a disposable PostgreSQL URL. |
| Production schema | `PRODUCTION_SCHEMA_UNKNOWN` | No Production query was made; source or disposable-test evidence is not Production evidence. |
| Production schema confirmation | `PRODUCTION_SCHEMA_CONFIRMED=NO` | A separate Owner-gated B033 readiness/migration proof is required. |

The source contract preserves duplicate ownership rows, uses `user_id` as the
ownership key, and uses exact ownership row IDs when a loadout command targets
a copy. B034 requires a valid B033 schema before canonical equip/unequip and
fails closed with `SCHEMA_INVARIANT_UNAVAILABLE` otherwise. The source is
therefore defined and testable, but not Production-ready for Loadout.

## Current equipment authority and locks

The only 15 server-defined functional IDs are:

| Slot | IDs and authoritative effects |
| --- | --- |
| Weapon | `wooden_sword`: `dmg_bonus=0.05`; `iron_sword`: `dmg_bonus=0.12`; `fox_fang`: `dmg_bonus=0.20`, `fox_dmg_bonus=0.15`; `dragon_claw`: `dmg_bonus=0.35`, `dragon_dmg_bonus=0.20`; `celestial_blade`: `dmg_bonus=0.60`, `combo_multiplier_double=true`. |
| Armor | `cloth_robe`: `player_dmg_reduce=0.08`; `leather_armor`: `player_dmg_reduce=0.15`; `fox_pelt`: `player_dmg_reduce=0.25`, `xp_bonus=0.10`; `dragon_scale`: `player_dmg_reduce=0.40`, `sp_bonus=30`; `void_mantle`: `player_dmg_reduce=0.60`, `negate_counter=true`. |
| Accessory | `lucky_stone`: `loot_bonus=0.10`; `xp_amulet`: `xp_bonus=0.20` but no active new-equip consumer; `fox_mask`: `quest_xp_bonus=0.25`; `dragon_eye`: `crit_multiplier=3`; `go_stone_black`: `first_question_ace=true` in the definition but inventory-only and no active combat effect. |

`EQUIPMENT_DEFS` plus its active-effect allow-list is the server effect
authority. `player_inventory.equipped` is the ownership/equipped-state
authority. `player_appearance.combat_*`, `APPEARANCE_EFFECTS`, and
`hero_combat_gear_v1` are not valid combat authority. The preserved damage
contract is baseline `80`, wooden sword `84`, and iron sword `90`.

## Loadout enablement gate matrix

| Gate | Classification | Finding |
| --- | --- | --- |
| `SERVER_OWNERSHIP_AUTHORITY` | `READY` | B040 writes server-owned `player_inventory` rows with `equipped=0`; exact user/row identity is preserved. |
| `SERVER_EQUIP_AUTHORITY` | `READY` | B034 canonical service is server-owned and exact-row scoped, but the disabled route still has a legacy writer. |
| `SERVER_UNEQUIP_AUTHORITY` | `READY` | Canonical service and bounded legacy recovery both preserve ownership and clear the selected row. |
| `SERVER_REPLACEMENT_AUTHORITY` | `READY` | Canonical slot replacement clears the prior same-slot row and proves final state. |
| `SERVER_EFFECT_AUTHORITY` | `READY` | Combat reads active effects from `player_inventory` plus `EQUIPMENT_DEFS`; appearance fields are excluded. |
| `SERVER_RELOAD_HYDRATION` | `READY` | Inventory and Hero projections read server-owned state; A038/A034--A036 focused tests pass. |
| `HERO_PROJECTION` | `READY` | Accepted A034/A035/A038 projection contract is present on fresh master. |
| `BACKPACK_PROJECTION` | `READY` | Inventory route returns owned/equipped rows and functional metadata. |
| `CLIENT_CACHE_AUTHORITY_REMOVED` | `DEPENDENCY_GATED` | Accepted A040 is not in fresh master; fresh master still has unbounded local `hero_combat_gear_v1` readers/writers. |
| `BROWSER_PROOF` | `READY` | A041 accepted Desktop/iPad landscape/iPad portrait/Mobile browser proof; no physical-device proof. |
| `SCHEMA_SOURCE_READY` | `READY` | B033 artifact and disposable SQLite/test contracts are complete. |
| `PRODUCTION_SCHEMA_VERIFIED` | `PRODUCTION_GATED` | Production remains intentionally unqueried and UNKNOWN. |
| `LEGACY_API_FALLBACK_RETIRED_OR_BOUNDED` | `BLOCKED` | `/api/player/inventory/equip` is reachable while the flag is false and direct-writes `player_inventory.equipped`. |
| `LEGACY_COMBAT_FIELDS_RETIRED_OR_BOUNDED` | `OWNER_GATED` | Eight fields still serve public/profile compatibility readers and have a writer in `/api/skills/character`. |
| `FEATURE_GATE_FAIL_CLOSED` | `BLOCKED` | The UI is disabled, but the API is not route-level fail-closed: false flag selects the legacy functional writer. |
| `ROLLBACK_DISABLE_PATH` | `READY` | `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` defaults false; no gate was changed. |
| `PHYSICAL_DEVICE_PROOF` | `NOT_APPLICABLE` | This server/schema audit uses accepted browser emulation evidence; physical proof is not claimed. |

```text
LOADOUT_READY_FOR_ENABLEMENT=NO
```

## Legacy equip API fallback

```text
LEGACY_EQUIP_FALLBACK=app.py:equip_item, POST /api/player/inventory/equip; direct player_inventory.equipped branch selected when EQUIPMENT_CANONICAL_LOADOUT_ENABLED is false
LEGACY_EQUIP_FALLBACK_REACHABLE=YES
LEGACY_EQUIP_FALLBACK_FUNCTIONAL_AUTHORITY=YES (server-side functional writer; not client authority)
RECOMMENDED_FALLBACK_CLOSURE=FAIL_CLOSED for new action=equip while the flag is false; retain only explicitly bounded legacy unequip recovery if Owner policy requires it, and route all enabled mutations through B034
```

The route first scopes the requested row by `id AND user_id` and rejects the
known locks, but the false-flag branch still performs slot clearing and an
`equipped=1` update directly. A future app.py patch must reject new equip
before this branch when Loadout is disabled, preserve a stable 4xx/no-mutation
response, and ensure the enabled path is the sole functional writer. A042
does not apply that patch.

## `player_appearance.combat_*` compatibility fields

```text
COMBAT_COMPATIBILITY_FIELD_COUNT=8
COMBAT_COMPATIBILITY_FIELDS=combat_armor,combat_weapon,combat_cape,combat_offhand,combat_hat,combat_pet,combat_aura,combat_acc
```

All eight have the same authority classification unless noted in the reader
column. None is consulted by `_get_authoritative_combat_stats`.

| Field | Current readers | Current writers | Gameplay authority | Cosmetic compatibility | Stop writing | Stop reading | Data migration | Owner decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `combat_armor` | `_get_appearance_effects`; `/api/player/appearance`; `_row_loadout`; community/friends/leaderboard/badges/messages projections; bot/legacy avatar | `/api/skills/character` | `NO` | `YES` | `NO` | `NO` | `NO` | `YES` |
| `combat_weapon` | Same public/profile compatibility readers; bot/community/messages avatar layers | `/api/skills/character` | `NO` | `YES` | `NO` | `NO` | `NO` | `YES` |
| `combat_cape` | Same public/profile compatibility readers; bot/community/messages avatar layers | `/api/skills/character` | `NO` | `YES` | `NO` | `NO` | `NO` | `YES` |
| `combat_offhand` | Same public/profile compatibility readers; bot/community/messages avatar layers | `/api/skills/character` | `NO` | `YES` | `NO` | `NO` | `NO` | `YES` |
| `combat_hat` | `_get_appearance_effects`; public compatibility avatar projections; community/messages | `/api/skills/character` | `NO` | `YES` | `NO` | `NO` | `NO` | `YES` |
| `combat_pet` | `_get_appearance_effects`; public compatibility avatar projections; community/messages | `/api/skills/character` | `NO` | `YES` | `NO` | `NO` | `NO` | `YES` |
| `combat_aura` | `_get_appearance_effects`; public compatibility avatar projections; community/messages | `/api/skills/character` | `NO` | `YES` | `NO` | `NO` | `NO` | `YES` |
| `combat_acc` | `_get_appearance_effects`; character writer compatibility input; not present in the seven-field `_row_loadout` public projection | `/api/skills/character` | `NO` | `YES` | `NO` | `NO` | `NO` | `YES` |

The `NO` stop-writing/reading classifications are deliberate: the current
public compatibility window has not been retired by its Owner. The accepted
A040 client migration would reduce Hero/Index/Curriculum/Bot dependence, but
that source is not on fresh master. No field or data was removed or migrated.

## Appearance/effect compatibility

```text
APPEARANCE_EFFECTS_FUNCTIONAL_COMBAT_AUTHORITY=NO
APPEARANCE_EFFECTS_READERS=app._get_appearance_effects (used by /api/skills/profile compatibility response); /api/skills/profile appearance item effects; premium_v1_revenue presentation projection; battlefield_boss_reward_service cosmetic-reward validation; related compatibility tests
APPEARANCE_EFFECTS_RETIREMENT=NEEDS_COMPATIBILITY_WINDOW
```

`APPEARANCE_EFFECTS` is a cosmetic/read-model registry. It may produce legacy
presentation metadata and cosmetic-reward validation, but current SRS combat
settlement uses server equipment effects instead. Removing it now would
break response/public compatibility shape; retirement needs consumer inventory
and Owner/C049 coordination. It must not be converted into equipment combat
authority.

## `hero_combat_gear_v1` compatibility

```text
HERO_COMBAT_GEAR_V1_FUNCTIONAL_AUTHORITY=NO (accepted A040 target; fresh master is pre-A040 and still violates this target until reconciliation)
HERO_COMBAT_GEAR_V1_REMAINING_READERS=hero.html _combatGear initialization and selection; index.html heroCombatState and adventure-avatar projection; curriculum.html getGuildCombatGear; bot.html localBotHeroGear and setMyPcAvatar
HERO_COMBAT_GEAR_V1_REMAINING_WRITERS=hero.html selection/save/account cleanup; index.html character selection/save/account cleanup; curriculum.html storage/focus refresh; no server combat writer
HERO_COMBAT_GEAR_V1_RECOMMENDATION=TIMEBOXED_COMPATIBILITY, with A040 bounded guard as the accepted first cut and later retirement after the compatibility window
```

The fresh-master readers can still override or supply functional-looking gear
on those surfaces. This is the exact A040 reconciliation dependency; A042 does
not copy A040 runtime files or alter them.

## Flag and disabled-state security

```text
LOADOUT_FLAG_DEFAULT=false
LOADOUT_ENABLED=NO
LOADOUT_FLAG_EFFECT_MATRIX=UI: inventory functional Equip control is hard-coded disabled and Hero legacy loadout is false; API: /api/player/inventory/equip remains reachable; routing: no route-level disabled fail-closed; canonical service: selected only when flag is true and requires B033; legacy fallback: selected when flag is false; reads: inventory/Hero projections remain available; Shop: separate default-off flag
```

The server-side services and route tests prove the following fail-closed
contracts, independent of the disabled UI:

```text
UNOWNED_EQUIP=FAIL_CLOSED
INVALID_ITEM_EQUIP=FAIL_CLOSED
INVALID_SLOT_EQUIP=FAIL_CLOSED
CROSS_USER_EQUIP=FAIL_CLOSED
```

The false-flag legacy writer is still a separate enablement blocker even
though it validates these inputs.

## Permanent boundaries

```text
BASELINE_DAMAGE=80
WOODEN_SWORD_DAMAGE=84
IRON_SWORD_DAMAGE=90
SERVER_DAMAGE_AUTHORITY=YES
CLIENT_DAMAGE_AUTHORITY=NO
COSMETIC_COMBAT_POWER=0
GO_STONE_BLACK_COMBAT_POWER=0
XP_AMULET_NEW_EQUIP=NO
XP_AMULET_LEGACY_UNEQUIP=YES
PURCHASE_AUTO_EQUIP=NO
ACQUIRE_AUTO_EQUIP=NO
LOADOUT_ENABLED=NO
SHOP_ENABLED=NO
GO_ENABLE_CONSUMED=NO
```

`go_stone_black` remains an inventory/trophy identity with no active combat
effect. `xp_amulet` ownership and legacy unequip recovery remain allowed, but
new equip remains held. Purchase/acquisition services persist `equipped=0`
and do not call loadout.

## Browser and dependency evidence

```text
A041_BROWSER_PROOF=PASS
PHYSICAL_DEVICE_PROOF=NO
DESKTOP=PASS (A041 accepted browser proof)
IPAD_LANDSCAPE=PASS (A041 accepted browser proof)
IPAD_PORTRAIT=PASS (A041 accepted browser proof)
MOBILE=PASS (A041 accepted browser proof)
```

The accepted browser evidence is not claimed as fresh-master source proof;
A040/A041 remain unmerged dependencies. B057 packaging remains outside this
task and is untouched.

## Focused tests

```text
SERVER_EQUIPMENT_REGRESSION=PASS (core A034-A038, B033/B034/B036/B040/B041/B042: 109 passed, 8 controlled PostgreSQL skips)
SCHEMA_CONTRACT_TESTS=PASS (included in the core run)
LOADOUT_DISABLED_REGRESSION=PASS (A038 gate/contract tests)
COMPATIBILITY_CONTRACT_TESTS=PASS for the A038/B050 and cosmetic suites, with one unrelated pre-existing A019 assertion failure
TESTS=109 passed/8 skipped core; 97 passed commerce/inventory/combat; 53 passed compatibility/public/cosmetic; 1 pre-existing A019 failure
TASK_INTRODUCED_FAILURES=0
PRE_EXISTING_FAILURES=1: tests/test_a019_revenue_launch_presentation_polish.py::test_a019_does_not_reintroduce_functional_or_commerce_authority; its stale assertion rejects the canonical master `player_inventory` commerce marker already present in shop.html
```

No disposable PostgreSQL URL was supplied, so PostgreSQL-specific B033 tests
were skipped by their explicit guard. No Production endpoint was contacted.

## Enablement decision packet

```text
READY_NOW=server ownership/effect/equip-service contracts; source B033 artifact and disposable test proof; accepted A041 browser evidence; default-off rollback path
OWNER_DECISION_REQUIRED=retirement/bounding of eight combat compatibility fields and APPEARANCE_EFFECTS; compatibility window for hero_combat_gear_v1; future GO_ENABLE
APP_PY_IMPLEMENTATION_REQUIRED=YES for the exact false-flag legacy equip closure in app.py (C049/Owner writer boundary)
PRODUCTION_SCHEMA_VERIFICATION_REQUIRED=YES
PRODUCTION_DB_MIGRATION_REQUIRED=YES if the Owner-approved B033 preflight confirms the deployed schema lacks the candidate invariant; A042 did not run it
PHYSICAL_DEVICE_REQUIRED=NO for this audit; no physical-device proof is claimed
```

Recommended future sequence:

1. `A043`: Owner/C049-approved server route closure: fail closed for new
   equip while disabled and canonicalize the enabled mutation path; preserve
   only explicitly approved legacy unequip recovery.
2. `A044`: compatibility-window decision and bounded retirement plan for
   `player_appearance.combat_*`, `APPEARANCE_EFFECTS`, and remaining social
   readers; no deletion without Owner approval.
3. `A045`: B033 deployed-schema readiness preflight, malformed-row audit,
   migration/quiescence plan, and rollback evidence; Production remains
   Owner-gated.
4. `A046`: final Loadout enablement preflight after A040/A041/B057/C049 and
   schema gates reconcile; consume GO_ENABLE only with explicit authorization.

```text
RECOMMENDED_NEXT_A_TASKS=A043 legacy equip fallback closure; A044 combat-appearance compatibility retirement decision; A045 B033 deployed-schema readiness/migration preflight; A046 final Loadout enablement preflight
```

## Scope and result

```text
APP_PY_CHANGED=NO
FUTURE_APP_PY_REQUIREMENT=YES: /api/player/inventory/equip must fail closed for new equip when EQUIPMENT_CANONICAL_LOADOUT_ENABLED=false; do not apply in A042
RUNTIME_SOURCE_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
B057_SCOPE_TOUCHED=NO
C049_SCOPE_TOUCHED=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
PRODUCTION_DB_MIGRATION=NO
DEPLOY=NO
GO_ENABLE_CONSUMED=NO
MASTER_MERGE=NO
UNEXPECTED_FILES=0 before this planning document
```

```text
RESULT=PASS_LOADOUT_SERVER_COMPATIBILITY_SCHEMA_READINESS_AND_ENABLEMENT_GATE_AUDIT
READY_FOR_COORDINATOR_A042_REVIEW=YES
```

The audit passes because all requested source contracts and blockers are
classified and the focused evidence is recorded. Loadout itself remains
`LOADOUT_READY_FOR_ENABLEMENT=NO`: fresh-master client/cache reconciliation,
legacy false-flag writer closure, compatibility ownership decisions, and
Production B033 schema verification are still required.
