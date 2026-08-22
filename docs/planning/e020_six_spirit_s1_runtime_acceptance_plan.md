# E020-PREP — E10 Six-Spirit S1 Runtime Integration Acceptance Plan

Status: acceptance preparation only

Base: `2fa78d0d8be90da3c5a01571f8d455c2d2780635`

This document defines the integration gate for the next Six-Spirit S1
runtime wave. It does not implement the runtime, create canonical Spirit
IDs, change `app.py`, or authorize merge, deploy, enablement, payment, or a
database migration.

## 1. Evidence boundary and status semantics

The plan separates current evidence from future runtime requirements:

| Status | Meaning |
|---|---|
| `PASS_RUNTIME` | Verified on the current runtime path. |
| `PASS_CONTRACT` | The acceptance contract is explicit and executable, but the target runtime is not yet present. |
| `PASS_FIXTURE` | A fixture or harness proves the contract without claiming target runtime behavior. |
| `PENDING_RUNTIME` | Requires a future lane interface/runtime; it is not a current pass. |
| `BLOCKER` | A known integration/release condition that must be resolved before runtime acceptance. |
| `BLOCKED_INFRA` | Required environment or service is unavailable. |
| `FAIL` | The required invariant is violated. |

`PENDING_RUNTIME` must never be reported as runtime `PASS`.

### Current canonical inputs

| Input | Present | Evidence / current status |
|---|---:|---|
| E019 | YES | Six-Spirit S1 fixture and browser contract harness are present. Current runtime passes cover the existing three and shared status projection; six-slot UI, follower, generic unlock UI, asset-failure runtime, and Owner visual acceptance remain pending. |
| D007 | YES | Lineage and invariant contract is present. `pet_collection` is functional ownership, `user_pets` is the active projection, `player_wardrobe` is cosmetic ownership, and D5A/D5C remain evidence/operation authorities. |
| B021 | YES | Equipment reaches the existing server-authoritative battle settlement; client effect payloads are not authority; `go_stone_black` remains inventory-only. |
| A020 | YES | Owner-approved visual identity evidence exists for slots 4–6. A020 remains the visual authority; runtime registration is consumed from A021A/D008 rather than invented here. |
| A021A | YES | Canonical master now contains the six-Spirit runtime asset package and manifest. The manifest supplies `starpath_antlerling`, `fatty`, and `obsidian_bastion`; D008 must still confirm them as server catalog IDs. |
| B022 | YES | Canonical master now contains the Spirit combat adapter specification. It defines the post-judge boundary and explicitly provides no runtime effect hook yet. |
| F001 | YES | Owner-PASS findings are consumed as a functional-but-fragmented Monster acceptance input; they do not authorize Monster V2 implementation in E020. |
| E014 | YES | Neutral pending presentation precedes E10 in the current first-paint contract. |
| Incident017 | YES | Review-response compatibility and the service-worker cache invalidation lineage are present. |

### Future lane inputs

At R1, canonical master is `8d3c7508d5f91d7ceb41cab5b2137cb9039c18d7`.
A021A and B022 are now canonical inputs. D008 remains blocked on the B023
schema decision, and no committed B023/D008 runtime output is available.
F001 findings are available as Owner-PASS recon evidence, but no unified
Monster interface is available.

| Lane | Required before E020 runtime integration |
|---|---|
| A021A | Canonical asset manifest is available. Still required for runtime integration: D008 ID confirmation, stage-route consumption, release provenance, deterministic missing/404/decode behavior, and responsive evidence. |
| D008 | `BLOCKED_SCHEMA_DECISION until B023 foundation exists`; six server catalog IDs; roster, ownership, active, unlock, feed, train, evolution APIs; operation identity; transaction/concurrency behavior; stage metadata; no automatic Production migration. |
| B022 | Canonical contract is available: judge → B021 equipment → Spirit adapter → Monster/Boss settlement; no second engine; no pre-judge effect; Lord excluded; replay effects zero; D5A/D5C handoff retained. Runtime hook and PostgreSQL execution evidence remain pending. |
| F001 | Owner-PASS findings are consumed below. A unified Monster ID/catalog, reward/item lineage, replay, and adapter interface remain unresolved. |

`A021A_CANONICAL_STATUS=MERGED`, `B022_CANONICAL_INTERFACE_CONSUMED=YES`,
`B023_STATUS=PENDING_NO_COMMITTED_OUTPUT`, and
`D008_STATUS=BLOCKED_SCHEMA_DECISION` are current R1 findings. F001 is
`OWNER_PASS_FINDINGS_CONSUMED=YES`, but its fragmented runtime state remains
a blocker for a unified Spirit/Monster release path.

## 2. Future end-to-end journey

The accepted S1 journey is:

```text
LOGIN
  → E10
  → server Spirit roster
  → Hero six-slot view
  → owned / locked / active state
  → select active Spirit
  → persist / reload
  → feed / train
  → Spirit progression
  → evolution
  → Hero refresh
  → World Map follower
  → encounter / question
  → server judge
  → canonical B021 combat
  → approved Spirit effect
  → Monster PvE settlement
  → reward / lineage
  → Backpack / Spirit state refresh
  → repeat
```

Current evidence covers the login/E10 boundary, the existing three-Spirit
projection, the existing judge/B021 foundations, the canonical A021A asset
manifest, the B022 contract, and the lineage contract. The six-slot,
mutation, follower, B022 runtime hook, and Monster settlement steps remain
`PENDING_RUNTIME` or `BLOCKER` until D008/B023 and a unified Monster contract
exist.

## 3. Authority matrix

| Domain | Authoritative owner | Read consumers | Forbidden authority | Gate status |
|---|---|---|---|---|
| Spirit catalog | D008 server catalog/release data | Hero, World Map, Backpack, B022 | Client, asset manifest, presentation | `PENDING_RUNTIME` |
| Functional Spirit ownership | D007/D008 `pet_collection` | All player surfaces and adapters | `user_pets`, localStorage, client `owned` flag | `PASS_CONTRACT` |
| Active Spirit | D007/D008 `user_pets` projection | Hero, World Map, question/battle, Backpack | Follower, presentation, local state | `PASS_CONTRACT` |
| Unlock | D008 server eligibility and ownership transaction | Hero unlock UI | Catalog visibility, client claim, follower | `PENDING_RUNTIME` |
| Feed/train/evolution | D008 validated server mutations | Hero and Backpack | Client progress/stage, replay, scene override | `PENDING_RUNTIME` |
| Spirit visual asset | A021A manifest plus release provenance | Hero, World Map, cinematic | Asset existence creating ownership | `PASS_CONTRACT` |
| World Map follower | Presentation adapter | World Map | DB writes, switch, unlock, reward | `PENDING_RUNTIME` |
| Go correctness | Existing SGF judge | Question/battle settlement | Spirit, client, Monster | `PASS_RUNTIME` |
| Hero equipment | B021 inventory/equipment authority | Battle settlement, Hero | Spirit presentation | `PASS_RUNTIME` |
| Damage/mitigation | B021 and existing battle authority | Settlement/presentation | Client, second combat engine, pre-judge Spirit | `PASS_CONTRACT` |
| Spirit PvE effect | B022 adapter after judge/B021 state | Authoritative settlement | Client magnitude, pre-judge effect, follower | `PASS_CONTRACT` |
| Monster identity/stats/drop | F001 findings; no unified catalog yet | Battle and settlement | Client, Spirit adapter, presentation | `BLOCKER` |
| Reward lineage | D5A | Audit/support/analytics | Analytics, client, presentation | `PASS_CONTRACT` |
| Functional item use | D5C | Server operation/audit | Cosmetic state, client | `PASS_CONTRACT` |
| Presentation | A021A and render adapters | Hero, World Map, cinematic | Ownership, active switch, unlock, reward, combat | `PASS_CONTRACT` |

The non-negotiable invariants are:

- `SINGLE_SPIRIT_OWNERSHIP_AUTHORITY=YES`
- `SINGLE_ACTIVE_SPIRIT_AUTHORITY=YES`
- `SINGLE_COMBAT_AUTHORITY=YES`
- `SINGLE_MONSTER_IDENTITY_AUTHORITY_TARGET=YES`
- `PRESENTATION_IS_AUTHORITY=NO`
- client gameplay, reward, economy, and Premium authority remain `NO`.

## 4. Six-slot roster and identity consistency

The target roster is exactly six logical slots.

| Slot | Current/approved identity | Role | Canonical machine ID |
|---:|---|---|---|
| 1 | `ink_drop_kelpie` | existing catalog role | existing canonical ID |
| 2 | `whispering_void_kit` | existing catalog role | existing canonical ID |
| 3 | `star_shell_hatchling` | existing catalog role | existing canonical ID |
| 4 | Starpath Antlerling | `EXPLORATION` | `starpath_antlerling` from canonical A021A manifest; D008 confirmation pending |
| 5 | Fatty | `PRECISION` | `fatty` from canonical A021A manifest; D008 confirmation pending |
| 6 | Obsidian Bastion | `SUPPORT` | `obsidian_bastion` from canonical A021A manifest; D008 confirmation pending |

The last three display identities originate in A020, while the machine IDs
are now consumed from the canonical A021A asset manifest. They are not yet
server ownership/catalog authority: D008/B023 must confirm the exact IDs
before runtime integration. The fixture rule remains
`NEW_SPIRIT_CANONICAL_NAMES_IN_TEST_FIXTURES=0` for any future IDs.

The blocking identity check is:

```text
server Spirit ID
== asset manifest Spirit ID
== Hero projection Spirit ID
== World Map follower Spirit ID
== combat adapter Spirit ID
```

Any mismatch blocks integration. A catalog or asset manifest must not
silently normalize an ID from another lane.

## 5. Ownership, active state, and legacy pet quarantine

### Ownership/presentation contract

These are presentation-only and must not create functional ownership:

- asset existence;
- a Hero card or selected detail;
- a World Map follower;
- a cinematic scene override;
- localStorage or other client cache.

The only valid functional ownership source is the server Spirit ledger
defined by D007/D008. An active Spirit must exist in that ownership source.

### Active-state acceptance

The following must all consume one authoritative active projection:

- Hero;
- World Map follower;
- question/battle adapter;
- Backpack;
- reload, navigation, deep links, and device-size changes.

Acceptance must detect stale Hero display, stale follower display, combat
using the previous Spirit after a switch, reload reverting the switch, and
an unowned active identity. Concurrent switches must have one deterministic
server result or an explicit conflict; a client-side last-write-wins visual
state is not acceptable.

Legacy cosmetic IDs remain quarantined and are not deleted:

`pet_cat`, `pet_turtle`, `pet_rabbit`, `pet_fox`, `pet_wolf`, `pet_dragon`,
and `pet_premium` must not enter the six-Spirit functional roster, functional
ownership, or Spirit effect registry.

## 6. Mutation acceptance contracts

All mutation identity must be server-validated or server-generated. A client
nonce/request ID may be proposed, but it is not authority. The server binds
the identity to user, operation type, target, policy/version, and request
fingerprint; replay with the same identity and same fingerprint is safe, while
the same identity with a different fingerprint is a conflict.

### Unlock

Test valid unlock, locked display, claimable-versus-owned state, duplicate
unlock, concurrent unlock, and reload. The server derives eligibility and
inserts ownership once. Expected duplicate ownership and duplicate reward
counts are both zero. The exact milestone source for slots 4–6 remains
pending D008 and must not be invented here.

### Feed

Test success, insufficient resource, double-click, response-loss retry,
concurrent feed, and reload. A successful operation performs one conditional
resource decrement and one progress effect. Expected duplicate consume and
duplicate progress counts are zero.

### Train

Test success, cooldown, daily cap, duplicate submit, response-loss retry,
and cross-device refresh. Daily limits and the mutation must be evaluated in
the same authority transaction. Expected duplicate progress count is zero.

### Evolution

Server thresholds are Stage I Lv1–9, Stage II Lv10–24, Stage III Lv25+.
Acceptance must prove Lv9 remains Stage I, Lv10 transitions once to Stage II,
Lv24 remains Stage II, and Lv25 transitions once to Stage III. The client
cannot force a stage. A presentation/asset failure cannot roll back or
duplicate a committed evolution. Expected duplicate evolution events are
zero.

## 7. Asset and responsive acceptance

### Fail-closed asset behavior

For missing Stage assets, 404s, decode failures, wrong manifest IDs, wrong
stage assets, and transparent/empty images, the runtime must use a neutral
presentation fallback. It must not mutate ownership, active state, progress,
or identity; it must not retry forever or substitute another Spirit.

`ASSET_FAILURE_FAILS_CLOSED=YES` is a release gate.

### Hero six-slot layout

| Viewport | Target |
|---|---|
| Desktop | 3 × 2 |
| Tablet landscape | 3 × 2 |
| iPad portrait | 2 × 3 or a validated equivalent |
| Mobile portrait | 2 × 3 |
| 430 × 932 | 2 × 3 with intentional scroll if required |

Each viewport must prove no horizontal overflow, CTA collision, portrait
clipping, unreadable stage labels, inaccessible locked state, or unusable
keyboard/touch behavior. Selected details must remain readable. Automated
checks are engineering evidence; Owner visual acceptance remains separate.

### World Map follower

The future interface is:

```text
authoritative active Spirit
  → presentation adapter
  → follower
```

The adapter may carry `spirit_id`, `evolution_stage`, `art_manifest`,
`animation_manifest`, and `presentation_state`. It must not write the DB,
change active Spirit, unlock, or grant rewards. Test follower updates after a
switch, reload consistency, zone transition, small-screen positioning, Hero
layer priority, and non-occlusion of zone nodes.

## 8. Combat, Monster, Lord, and equipment integration

The required order is:

```text
SERVER_JUDGE
  → B021 authoritative battle state
  → equipment effect
  → approved B022 Spirit effect adapter
  → authoritative settlement
  → presentation
```

Spirit effects before the judge, a second combat engine, and client effect
magnitude authority are forbidden. B021 remains the combat owner. Composition
tests must cover weapon only, Spirit only, weapon plus Spirit, armor only,
Spirit mitigation only, armor plus Spirit mitigation, unequip, Spirit switch,
and reload; exact balance values are outside E020-PREP.

The canonical B022 contract is consumed here: equipment feeds the Spirit
adapter, and the adapter feeds Monster/Boss settlement only after the
authoritative judge. Lord Trial is explicitly excluded and preserved as a
separate authority. Replay Spirit effects are zero, scene overrides are
presentation-only, and reward/item mutations hand off to D5A/D5C rather than
being authored by the adapter. B022 supplies a contract, not an implemented
runtime hook.

F001 is Owner PASS, but its actual state is
`FUNCTIONAL_BUT_FRAGMENTED`. Acceptance must keep the following explicit
blockers visible rather than inventing Monster V2:

- two real Monster combat paths and no unified `monster_id`/catalog;
- server-owned HP/ATK, with Map Battle field mismatch
  `battle_monster_type` versus `monster_type`;
- no Elite runtime, no Monster skill/AI, and no multi-Monster runtime;
- Lord Trial is a separate runtime and authority;
- Monster reward D5A integration is missing;
- Monster item D5C integration is partial/missing;
- replay behavior is fragmented;
- equipment-drop source and reachable Monster roster do not fully agree.

The future Spirit/Monster adapter must run post-settlement and before
reward/audit lineage. The Lord Trial regression must preserve existing
answer/review authority, introduce no fake Monster HP, prevent Spirit from
overriding a Lord result, and apply equipment/Spirit behavior only where
explicitly supported.

## 9. Replay and scene override

Story, Boss, and cinematic replay may show a Spirit model, reaction, or cue,
but must produce zero:

- Spirit XP;
- Spirit item grants;
- Spirit unlock progress;
- Spirit evolution;
- Monster drops;
- zone progress.

A scene-specific Spirit is a presentation override only. It must not change
active ownership, active selection, progression, item state, or combat
effect. The normal active Spirit must remain authoritative after the scene.

## 10. D5A and D5C lineage gates

Every functional Spirit reward that the final runtime supports—unlock, Spirit
XP, evolution, Monster/Boss reward, or quest reward—must have the required
D5A lineage. A reward without required lineage is a failing test, not an
analytics warning.

Every functional Spirit consumable must use D5C operation identity for
exactly-once consumption/effect, persisted operation state, response-loss
retry, and changed-payload conflict. Purely cosmetic state is out of scope
unless the final architecture requires it.

The D007 read-only auditor and analytics are evidence only; neither can
authorize a mutation.

## 11. PostgreSQL and forgery gates

SQLite may supplement but cannot replace PostgreSQL for:

- concurrent unlock;
- concurrent feed/train/switch;
- operation identity replay/conflict;
- D5A lineage;
- D5C item use;
- DB-sensitive B021/B022 settlement;
- DB-sensitive Monster reward settlement.

Client inputs are classified as follows:

| Input | Classification |
|---|---|
| `owned=true` | `SERVER_OWNED` |
| active Spirit ID | `SERVER_VERIFIED` |
| stage/progress | `SERVER_OWNED` |
| unlock request | `SERVER_VERIFIED` |
| feed quantity | `SERVER_VERIFIED` |
| effect ID | `SERVER_VERIFIED` |
| effect magnitude | `SERVER_OWNED` |
| Monster stats | `SERVER_OWNED` |
| damage/mitigation | `SERVER_OWNED` |
| reward result | `SERVER_OWNED` |

Any accepted client value in a server-owned field is a release blocker.

## 12. Browser, device, and accessibility matrix

The future real-browser journey set contains 15 journeys:

1. fresh login;
2. existing player;
3. existing-three owner;
4. new six-slot player;
5. active Spirit switch;
6. feed;
7. train;
8. evolution;
9. reload after mutation;
10. World Map follower;
11. battle;
12. deep link;
13. logout/re-login;
14. asset failure;
15. story/Boss replay.

Each is required on the applicable desktop, iPad landscape, iPad portrait,
mobile portrait, and 430 × 932 narrow portrait surfaces. The matrix covers
Hero, World Map, roster, selected details, battle cue, and asset fallback.
Unimplemented journeys are not executed or reported as passes in E020-PREP.

Accessibility checks include keyboard focus, touch targets, screen-reader
labels, non-color-only state, modal focus trap/restore, Escape behavior where
supported, and reduced-motion behavior where supported.

## 13. Observability

Useful non-authoritative signals include Spirit hydration failure, asset
failure, active-state mismatch across surfaces, effect evaluation failure,
lineage failure, duplicate operation conflict, replay mutation attempt, and
client-forgery rejection. Observability supports diagnosis only; it cannot
grant ownership, settle combat, authorize rewards, or repair state.

## 14. Regression and release blockers

The future E020 gate must include:

- E019 harness;
- D007 lineage and PostgreSQL contracts;
- B021 equipment combat loop;
- A020/A021 visual and identity evidence;
- D008 runtime after the B023 schema decision;
- B022 canonical adapter contract plus runtime hook when implemented;
- F001 fragmented-Monster blocker tests and later unified settlement tests;
- Incident017 response compatibility;
- E014 first-paint behavior;
- Boss/Lord and Map Battle compatibility;
- Revenue default-off regression if shared `app.py` changes occur.

Release-blocking categories are:

1. duplicate ownership, active, combat, Monster, or other authority;
2. accepted client forgery;
3. duplicate unlock/feed/train/evolution/item-use/reward operation;
4. missing D5A lineage or D5C functional-operation identity;
5. pre-judge Spirit effect or second combat engine;
6. stale active state after reload/navigation/deep link/device change;
7. replay mutation;
8. six-slot overflow, duplicate ID, or cross-lane ID mismatch;
9. missing/wrong canonical asset or non-failing-closed asset behavior;
10. browser console error affecting the journey;
11. PostgreSQL concurrency failure;
12. `MONSTER_IDENTITY_SPLIT_BLOCKER` or an unconfirmed Monster authority boundary;
13. `MAP_BATTLE_MONSTER_TYPE_FIELD_MISMATCH` not reconciled at the adapter boundary;
14. `MONSTER_REWARD_D5A_GAP`;
15. `MONSTER_D5C_GAP`;
16. `MONSTER_REPLAY_CONTRACT_GAP`;
17. `DROP_ROSTER_REACHABILITY_GAP`;
18. treating the separate Lord Trial runtime as ordinary Monster combat.

## 15. E019 extension plan

`E019_REUSED=YES` and `PARALLEL_ACCEPTANCE_HARNESS_CREATED=NO`.

E020 should extend E019 in place conceptually rather than replace it:

1. retain E019 fixtures and strict status semantics;
2. add D008 server snapshots and operation-identity fixtures;
3. bind A021A manifest IDs/stages to D008 catalog IDs;
4. consume the canonical B022 post-settlement contract, then add runtime probes without changing B021;
5. keep F001 fragmentation blockers as failing integration gates until a unified Monster interface exists;
6. extend browser journeys from the existing three to the six-slot runtime;
7. run PostgreSQL concurrency gates before any runtime release gate;
8. keep Owner visual acceptance separate from automated/fixture passes.

The existing three Spirits, legacy cosmetic-pet quarantine, E014 neutral-to-
E10 first paint, Incident017 compatibility, and B021 equipment authority are
non-regression requirements throughout.

## 16. Zero-change boundary and final gate

This preparation changes no runtime source, route, service worker, database,
payment, Revenue behavior, or Production state. It does not merge or deploy.
The only intended files are this plan and its machine-readable matrix.

The next implementation wave is ready for Owner review only after the future
lane interfaces are available and the pending contracts above are executed
against the actual runtime.
