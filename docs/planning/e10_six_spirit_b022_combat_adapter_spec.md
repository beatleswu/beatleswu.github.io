# E10 Six-Spirit → B021 Canonical Combat Adapter Specification

**Task:** B022
**Status:** read-only architecture specification; no runtime implementation
**Canonical base at audit start:** `2fa78d0d8be90da3c5a01571f8d455c2d2780635`
**Canonical repository:** `D:\go-website`
**Branch:** `codex/go-odyssey-master-lane-b-b022-spirit-combat-adapter-spec`

## 1. Decision summary

B021 already provides the server-authoritative combat boundary that a future
Spirit adapter must extend. The adapter must be a post-judgement,
server-owned modifier stage inside the existing settlement flow. It must not
be a route, a front-end calculator, a replacement for B021, or a second
Monster/combat engine.

The canonical future order is:

```text
Go answer
  → server judge
  → authoritative correctness/result
  → base battle state
  → B021 Hero equipment effects
  → Spirit effect evaluation
  → server-owned Monster/Boss PvE settlement
  → reward/progression handoff
  → presentation
```

The current repository has:

- B021 runtime combat and equipment authority;
- E019 fixture-level Spirit battle ordering and replay boundaries;
- D007 executable Spirit ownership/lineage contracts;
- no current D008 combat projection endpoint;
- no current F001 Monster authority interface;
- no implemented Spirit combat effect evaluator.

Therefore this document defines the handoff contract but does not claim that
Spirit combat is runtime-ready.

## 2. Evidence and authority map

| Concern | Current canonical source | Finding |
| --- | --- | --- |
| Functional equipment ownership | `app.py`, `player_inventory` | Server-owned inventory rows are the source for equipped functional items. |
| Equipped effect definitions | `app.py`, `EQUIPMENT_DEFS` / `_EQUIP_MAP` | Client appearance fields are not consulted for combat power. |
| Shared equipment projection | `app.py::_get_authoritative_combat_stats()` | Reads active server equipment and returns bounded attack, mitigation, crit, counter, and combo values. |
| Legacy Adventure/E10 review combat | `app.py::_equipment_aware_legacy_combat()` → `_update_monster_and_quests()` | Equipment is placed in a server `ContextVar`; the legacy settlement mutates real Monster/player state. |
| Map Battle judge and combat | `map_battle_runtime.py::settle_answer()` | Loads the owner-bound attempt, canonicalizes the answer, judges it, resolves server equipment, calculates combat, then calls persistence settlement. |
| Map Battle damage | `map_battle_runtime.py::calculate_damage()` | Existing shared damage formula; no client damage fields are accepted. |
| Map Battle effect bundle | `map_battle_runtime.py::calculate_combat_effects()` | Current B021 insertion contract for a future Spirit stage; currently returns only Monster damage, player damage, and healing flag. |
| Map Battle persistence | `map_battle_persistence.py::settle_map_battle_submission()` | Caller-owned settlement persistence and retry/revision controls remain authoritative. |
| Monster roster | `app.py::_BATTLEFIELD_ROSTER` / `battlefield_profile()` | Current server-owned roster includes HP, attack, and `normal`/`boss` encounter kind. This is not a new F001 interface. |
| Spirit ownership/current projection | `pet_collection`, `user_pets`, `spirit_lineage.py` | D007 contract: ownership/progression is functional authority; active state is the current projection. |
| Spirit evidence | `spirit_lineage.py`, D5A outbox/D5C operation contracts | Evidence and lineage do not authorize combat or reward mutations. |
| Spirit battle boundary | `tests/fixtures/e019_six_spirit_s1_contract.json` | Fixture contract requires server judge → authoritative settlement → equipment → Spirit adapter → result → presentation. |

### Current implementation boundary

`calculate_combat_effects()` is the semantic adapter point for Map Battle. A
future implementation should extend its result contract or call one shared
Spirit evaluator from this stage before
`settle_map_battle_submission()`. It must not add another `calculate_damage`
implementation.

The legacy review path has a separate existing wrapper around
`_update_monster_and_quests()`. If that path later receives Spirit combat
effects, it must call the same adapter contract after the authoritative
result and equipment profile are known; it must not grow a second formula.

No Spirit runtime hook is implemented by B022.

## 3. Non-negotiable authority boundaries

The following are hard invariants for any future implementation:

| Invariant | Required value |
| --- | --- |
| Spirit effect before Go judge | Forbidden |
| Spirit changes Go correctness | No |
| Spirit changes SGF/native judge | No |
| Spirit changes Map Battle judge | No |
| Spirit auto-corrects an answer | No |
| Client Spirit ID as authority | No |
| Client Spirit stage as authority | No |
| Client effect magnitude as authority | No |
| Client damage/mitigation as authority | No |
| Spirit changes ranked result/leaderboard | No |
| Automatic victory | No |
| Second combat engine | No |
| Scene override replacing active Spirit | No |

Effect configuration failure may skip a Spirit effect or fail the governed
battle transaction according to a future product policy, but it must never
alter the already-derived Go correctness or silently route the battle through
another engine.

## 4. D008 → B022 input contract

### Current status

`D008_INTERFACE_AVAILABLE=NO` as a current runtime combat projection.
The accessible D-side contract is the D007 lineage foundation, and it is
already present on current master with no diff from the accessible D007
lineage commit. D007 establishes the source authorities and operation/evidence
boundaries; it does not expose a battle adapter payload.

`D008_TO_B022_INPUT_CONTRACT=PROPOSED_HANDOFF_NOT_YET_EXPOSED`.

### Proposed server-owned projection

The future B caller should receive a transaction-local, immutable projection
with at least:

```json
{
  "active_spirit_id": "server-owned-id",
  "ownership_validated": true,
  "evolution_stage": "STAGE_I",
  "progression_level": 1,
  "effect_profile_id": "server-owned-profile",
  "effect_policy_version": "E10_SPIRIT_EFFECT_POLICY_V1",
  "enabled": true,
  "source_operation_id": "battle-operation-id"
}
```

The exact profile ID and policy version are future governance values, not
current runtime values. The projection must be derived from the authenticated
user's `pet_collection` ownership and `user_pets` active/current projection,
with D007's ownership and legacy-pet quarantine rules applied. A stale or
missing projection is not replaced by client input.

Required validation:

1. `active_spirit_id` is owned by the authenticated user.
2. The active projection and ownership row are internally consistent.
3. The ID is a functional Spirit, not a legacy cosmetic `pet_*` ID.
4. Stage and level are server-derived.
5. The effect profile and policy version are server-selected.
6. `source_operation_id` is bound to the current authoritative settlement.
7. The projection is read-only for the B evaluator.

`B022_TRUSTS_CLIENT_SPIRIT_STATE=NO`.

## 5. Data-driven Spirit effect registry

The future registry is a data contract, not a Python `if spirit_id` branch.
Minimum fields:

| Field | Rule |
| --- | --- |
| `effect_id` | Globally unique governed effect identity. |
| `spirit_id` / `profile_id` | Catalog/profile identity selected by the server. |
| `trigger` | One supported settlement trigger. |
| `scope` | One allowed effect scope from the matrix below. |
| `condition` | Declarative, server-evaluable condition; no client truth. |
| `effect_type` | Allow-listed operation such as damage modifier, mitigation, shield, or reward modifier. |
| `magnitude` | Server-owned value or formula reference; never request data. |
| `cap` | Explicit per-effect/per-scope cap where applicable. |
| `cooldown` | Server-owned timing policy, if applicable. |
| `stacking_policy` | Explicit `NO_STACK`, `ADDITIVE`, `MULTIPLICATIVE`, `MAX_ONLY`, or exclusive policy. |
| `policy_version` | Immutable balance/semantics version used by settlement. |
| `enabled` | Server-side release switch; no client override. |

The evaluator should return an immutable evaluation record containing the
effect ID, policy version, trigger, condition result, bounded delta, and
settlement operation identity. It must not write ownership, inventory, XP, or
items itself.

`ADDING_NEW_SPIRIT_EFFECT_REQUIRES_NEW_COMBAT_IF_BRANCH=NO`.

New effect types may require a governed evaluator capability, but adding a
new Spirit/profile must be data-only within an already-supported effect type.

## 6. Effect scope matrix

| Scope | Classification | Boundary |
| --- | --- | --- |
| `SPIRIT_GROWTH` | ALLOWED | D-owned progression authority; not a combat stat shortcut. |
| `LEARNING_PROGRESSION` | ALLOWED_WITH_BALANCE_GATE | Post-judge/reward stage only; final XP remains the existing XP authority. |
| `PVE_DAMAGE` | ALLOWED_WITH_BALANCE_GATE | Only through the B021 damage adapter and server-owned magnitude. |
| `PVE_MITIGATION` | ALLOWED_WITH_BALANCE_GATE | Only through the B021 incoming-damage adapter. |
| `PVE_SHIELD` | ALLOWED_WITH_BALANCE_GATE | Server-consumed shield state; no client HP protection. |
| `PVE_RECOVERY` | ALLOWED_WITH_BALANCE_GATE | Only at an explicit settlement boundary or between encounters. |
| `REWARD_BONUS` | ALLOWED_WITH_BALANCE_GATE | B computes a bounded modifier; D5A/D5C owns persistence/lineage. |
| `MATERIAL_BONUS` | ALLOWED_WITH_BALANCE_GATE | Must flow through canonical acquisition/drop authority. |
| `QUEST_UTILITY` | ALLOWED_WITH_BALANCE_GATE | Utility may change eligibility only through the owning quest authority. |
| `EXPLORATION` | ALLOWED | Must remain server-owned zone/encounter utility. |
| `SUPPORT` | ALLOWED_WITH_BALANCE_GATE | Requires an explicit effect type and cap. |
| Go correctness/answer correction | FORBIDDEN | Cannot affect judge input or result. |
| Ranked result/rating/leaderboard | FORBIDDEN | No paid or Spirit-assisted fake Go skill outcome. |
| Automatic competitive victory | FORBIDDEN | Never a combat adapter output. |

## 7. Equipment + Spirit composition

The future composition order is:

```text
base Hero battle state
  → B021 EQUIPMENT_DEFS effects from player_inventory
  → Spirit effect evaluation from D008 server projection
  → server-owned Monster/Boss modifiers
  → final PvE settlement
```

Equipment is the existing canonical base modifier stage. Spirit effects
extend it; they do not wrap, replace, or recalculate B021. The evaluator must
receive the effective B021 values rather than querying browser state.

### Stacking requirements

- Each effect registry record declares its stacking policy.
- Additive and multiplicative composition are separate typed operations;
  they must not be inferred from a display percentage.
- Equipment and Spirit modifiers cannot silently apply twice through both
  `app.py` and `map_battle_runtime.py`.
- Caps are applied by the canonical adapter after all inputs are bounded and
  before persistence.
- No balance numbers are chosen by B022.
- A policy version must identify the exact order, rounding, caps, and
  stacking semantics used for a settlement.

`EQUIPMENT_SPIRIT_COMPOSITION_ORDER=base → B021 equipment → Spirit adapter → Monster/Boss settlement`.

`STACKING_POLICY_REQUIREMENTS=explicit registry policy per effect; no implicit or duplicate application`.

`CAP_REQUIREMENTS=server-owned per-effect and per-scope caps, versioned with the effect policy; no B022 balance values`.

## 8. Existing three Spirit effects

The current source does contain three catalog abilities and a server-side
legacy XP path, but it does not contain a separate Spirit combat evaluator or
effect registry. `app.py::_pet_player_xp_bonus()` computes a level/affection/
fullness-based XP bonus from `user_pets` and applies it inside
`_srs_review_operation()` after the answer has passed the `grade >= 3` gate.
For public legacy review, the existing grade path remains a separate trust
concern; B022 does not change it.

| Spirit | Current trigger | Current magnitude source | Current authority | Settlement position | Progression implication | Future disposition |
| --- | --- | --- | --- | --- | --- | --- |
| `ink_drop_kelpie` | Legacy review XP path; specialization is always matched | Server-derived base by level, ×1.6 specialization, affection factor, fullness penalty | `user_pets` server row; no client magnitude accepted by this helper | After the current result gate, inside the XP/progression transaction; not a B021 combat hook | Yes: increases player XP/rank-level progression and may add pet XP | `MIGRATE_TO_REGISTRY` after effect-profile approval; preserve behavior during migration |
| `whispering_void_kit` | Legacy review XP path when the mistake record marks prior wrong work (`is_mc`) | Same server-derived legacy formula and condition | `user_pets` + server `mistake_log` context | Same as above; not a separate combat hook | Yes: affects RPG XP/rank-level progression; not a Go match result | `MIGRATE_TO_REGISTRY` after effect-profile approval |
| `star_shell_hatchling` | Legacy review XP path when combo streak is at least 3 | Same server-derived legacy formula and condition | `user_pets` + server combo context | Same as above; not a separate combat hook | Yes: affects RPG XP/rank-level progression; not a Go match result | `MIGRATE_TO_REGISTRY` after effect-profile approval |

Current catalog copy says these are pet-XP/specialization effects, while the
legacy helper also adds a player XP multiplier. That presentation/runtime
relationship should be reconciled by the future owner-approved registry
contract. B022 does not rebalance or change any of the three effects.

`EXISTING_THREE_EFFECT_MATRIX=CURRENT_LEGACY_XP_CONSUMER_PRESENT; NO_CURRENT_SPIRIT_COMBAT_EFFECT_REGISTRY`.

## 9. New Spirits #4–#6

These are architecture domains only. No final gameplay value is assigned.

| Slot | Visual identity | Candidate domain | Candidate adapter surface |
| --- | --- | --- | --- |
| #4 | Starpath Antlerling | `EXPLORATION`, encounter utility, quest utility | Server encounter/zone projection after battle/reward authority; not answer judging. |
| #5 | Fatty | `SUPPORT`, precision/quality cue, bounded reward utility | A post-settlement support/reward modifier; not a client “correctness” or score modifier. |
| #6 | Obsidian Bastion | `PVE_MITIGATION`, `PVE_SHIELD`, `SUPPORT` | B021 incoming-damage adapter after equipment mitigation, subject to balance gate. |

`NEW_SPIRIT_BALANCE_VALUES_LOCKED=NO`.

## 10. Monster-side handoff

No F001-specific interface or canonical F001 branch was available during the
audit. B021 currently exposes the server-owned roster through
`_BATTLEFIELD_ROSTER` and `battlefield_profile()`. B022 does not create a
replacement Monster authority.

`F001_TO_B022_REQUIRED_MONSTER_INPUTS=PROPOSED_HANDOFF_NOT_AVAILABLE`.

When F001 publishes its authority contract, the minimum read-only snapshot
needed by a Spirit PvE evaluator is:

```text
monster_id / server roster identity
monster_type
encounter_kind (normal, elite, boss where supported)
current_hp
max_hp
server_attack
server_defense if the canonical F001 model has it
battle_phase
settlement_status
monster_policy/version reference
drop/reward profile reference (only for reward modifiers)
```

All values must be loaded from the server-owned encounter state. A client
Monster ID, HP, ATK, DEF, type, or phase is a request hint at most and cannot
be used for authority.

## 11. Applicability by battle family

| Battle family | Spirit PvE applicability | Contract |
| --- | --- | --- |
| Normal Monster | YES | Apply supported post-judge PvE scopes through B021 settlement. |
| Elite | ADAPTER_REQUIRED | No canonical elite-specific F001 interface was available. |
| Boss | ADAPTER_REQUIRED | Use server-owned boss profile; no client Boss state. |
| Lord Trial | NO for current B022 scope | Preserve Lord Trial authority; do not invent Lord HP/combat integration. A later explicit Lord adapter may change this. |

`LORD_TRIAL_AUTHORITY_PRESERVED=YES`.

`SPIRIT_EFFECTS_APPLY_TO_LORD_TRIAL=NO_CURRENTLY; Lord Trial does not receive an invented Hero HP/equipment/Spirit combat path in B022`.

## 12. Trigger model

| Trigger | Future support | Rationale |
| --- | --- | --- |
| `question_settled` | SUPPORTED_WITH_REWARD_BOUNDARY | Safe after server result; useful for legacy learning/growth effects. |
| `review_settled` | SUPPORTED | Natural handoff for the three current legacy XP effects. |
| `battle_started` | SUPPORTED_WITH_BATTLE_CONTEXT | Server-owned encounter snapshot only. |
| `battle_damage_calculated` | SUPPORTED | Canonical point for outgoing PvE damage modifier. |
| `battle_retaliation_calculated` | SUPPORTED | Canonical point for incoming mitigation/shield modifier. |
| `battle_settled` | SUPPORTED | Required boundary for committed effect/reward evidence. |
| `boss_started` | ADAPTER_REQUIRED | Requires F001 boss profile contract. |
| `boss_settled` | ADAPTER_REQUIRED | Requires canonical Boss reward/lineage handoff. |
| `reward_granted` | SUPPORTED_WITH_D_HANDOFF | B may derive a modifier; D owns mutation/lineage. |
| `quest_claimed` | SUPPORTED_WITH_QUEST_AUTHORITY | Quest service remains the eligibility authority. |
| `daily_train` | SUPPORTED_WITH_D_AUTHORITY | D-owned Spirit progression; not a combat write. |

No trigger may execute before the authoritative Go judge result.

## 13. Damage adapter contract

Future shape, not implementation:

```text
SpiritDamageInput {
  settlement_operation_id,
  authenticated_user_id,
  authoritative_judge_result_id,
  base_authoritative_damage,
  b021_effective_combat_stats,
  equipment_effect_evaluations,
  monster_snapshot,
  active_spirit_projection,
  effect_policy_version
}

→ SpiritDamageOutput {
    final_authoritative_damage,
    bounded_effect_evaluations,
    presentation_cues,
    telemetry_facts,
    reward_modifier_handoff,
    inventory_mutations: none
  }
```

Rules:

- `base_authoritative_damage` is computed by B021 from the server judge and
  server equipment.
- Spirit magnitude comes only from the server effect profile.
- The adapter cannot accept client magnitude, grade, answer, damage, or
  Monster state.
- The adapter cannot bypass B021 or call a second damage formula.
- Rounding/caps are deterministic and policy-versioned.
- The output is passed to the existing settlement persistence in the same
  caller-owned transaction.

`SPIRIT_DAMAGE_EFFECT_CAN_USE_CLIENT_MAGNITUDE=NO`.
`SPIRIT_DAMAGE_EFFECT_CAN_BYPASS_B021=NO`.

## 14. Mitigation and shield adapter contract

Recommended future order for incoming PvE damage:

```text
server Monster retaliation
  → B021 Armor mitigation
  → Spirit mitigation/shield adapter
  → final damage taken / KO settlement
```

The exact order must be versioned before implementation. Existing B021
equipment effects, including armor reduction and `void_mantle` counter
negation, must be passed as already-authoritative inputs; Spirit must not
recompute or duplicate them.

Input must include the post-equipment incoming damage, server-owned player
HP/maximum HP, active Spirit projection, and policy version. Output must be a
bounded final damage/shield delta plus a presentation-safe cue. A Spirit
shield cannot be implemented as a client-side HP override.

`SPIRIT_MITIGATION_ADAPTER_CONTRACT=post-equipment B021 incoming damage → server Spirit mitigation/shield → final authoritative damage; no client HP or magnitude`.

## 15. Recovery contract

Recovery is allowed only where the future battle transaction explicitly
models it:

- post-damage within the same uncommitted settlement, or
- between encounters after the prior settlement has committed.

It cannot resurrect a player or undo a committed death after the fact. A
recovery evaluator must be deterministic, bounded, and included in the same
operation identity as the battle settlement.

`RECOVERY_CAN_PREVENT_SERVER_DEATH_AFTER_COMMIT=NO`.

## 16. Reward and item handoff

Spirit combat code stops after deriving a bounded reward/material modifier.
The handoff is:

```text
B021 battle settlement
  → Spirit reward/material modifier
  → owning reward authority
  → D5A evidence / D5C item-use lineage where applicable
  → committed persistence
```

`SPIRIT_COMBAT_ADAPTER_WRITES_INVENTORY_DIRECTLY=NO`.

`B_TO_D_REWARD_HANDOFF=server battle settlement result + bounded Spirit reward modifier + settlement operation_id/policy_version → D-owned reward authority and D5A evidence`.

`B_TO_D_ITEM_HANDOFF=Spirit functional item use, if ever triggered, uses D5C operation identity and ITEM_CONSUME_EFFECT evidence; B does not create a parallel item ledger`.

Existing D007 contracts require operation identity, lineage ID, server-derived
fields, and `analytics_is_source_of_truth=false`. D5A outbox records evidence;
they do not decide eligibility or correctness.

## 17. Operation identity, randomness, and replay

`SPIRIT_EFFECT_OPERATION_IDENTITY_SOURCE=the existing authoritative battle/review settlement operation identity; use Map Battle submission/settlement identity where present and the caller's canonical review identity otherwise; do not introduce a Spirit-specific idempotency system`.

The Spirit evaluation identity must include the authenticated user, source
settlement ID, effect ID, target/encounter identity, and policy version. The
same operation and policy must return the original evaluation, not execute a
new random outcome.

### Randomness

`CLIENT_RANDOMNESS_AUTHORITY=NO`.

If a future effect needs chance, derive a deterministic server seed from the
settlement operation identity, effect identity, target identity, and policy
version. Store or return the resulting evaluation as part of the committed
settlement evidence. Never use a client-provided random value. B022 does not
implement an RNG.

### Replay boundary

| Replay outcome | Required delta |
| --- | ---: |
| `REPLAY_SPIRIT_COMBAT_EFFECT` | 0 new functional effects |
| `REPLAY_SPIRIT_REWARD_EFFECT` | 0 new rewards/items |
| `REPLAY_SPIRIT_DROP_EFFECT` | 0 new drops |

Replay may reproduce the original authoritative result and presentation cue,
but must not reroll, re-grant, re-level, or reapply functional state.

`REPLAY_EFFECT_BOUNDARY=original committed evaluation/result may be replayed; new Spirit mutation is forbidden`.

## 18. Scene override boundary

E019's scene override is presentation-only. It may select a visual Spirit
cue for a narrative scene, but it cannot:

- apply a combat effect;
- replace the active server Spirit;
- change ownership, progression, zone progress, or reward eligibility.

`SCENE_OVERRIDE_CAN_APPLY_COMBAT_EFFECT=NO`.
`SCENE_OVERRIDE_CAN_REPLACE_ACTIVE_SPIRIT_AUTHORITY=NO`.

## 19. Policy versioning and telemetry

Each effect evaluation must carry:

```text
effect_id
spirit_id/profile_id
policy_version
trigger
source_settlement_id
operation_id
condition_inputs_version
bounded_delta
evaluation_outcome
```

The historical policy version must be sufficient for support to explain a
past battle. B022 does not add an audit table; D-owned evidence/lineage can
carry the committed event when a later implementation is authorized.

Suggested non-authoritative telemetry:

- `spirit_effect_evaluated`
- `spirit_effect_triggered`
- `spirit_damage_bonus`
- `spirit_mitigation`
- `spirit_reward_modifier`

Telemetry may be emitted after or with committed truth, but cannot retry,
authorize, or override a business mutation.

`TELEMETRY_IS_COMBAT_AUTHORITY=NO`.

## 20. Presentation contract

After settlement, E/A presentation may receive only the minimum safe cue:

```text
effect_triggered
effect_id or localized presentation key
spirit_id
visual_cue_key
safe delta amount, only where product disclosure allows it
```

Do not expose hidden caps, internal seeds, untrusted inputs, or policy data
that would create an attack surface. Presentation must consume the committed
server result, never recalculate combat.

## 21. Failure behavior

| Failure | Required behavior |
| --- | --- |
| Missing Spirit projection/profile | Skip the optional effect and record a non-authoritative error, or abort the governed effect transaction if the future product contract marks it mandatory. Never use client fallback. |
| Unknown Spirit ID | Fail the Spirit evaluation closed; preserve Go correctness and do not create a combat branch. |
| Missing effect config | No effect; no reward/item mutation; support-visible error/evidence. |
| Invalid effect type | Reject configuration/evaluation; no client-supplied substitute. |
| Evaluator exception | Roll back the governed settlement if the effect is mandatory; otherwise skip with explicit status. The policy must be chosen before enabling the effect. |
| Unsupported Monster type | Skip the unsupported optional effect or fail the battle effect stage according to the versioned policy; never invent Monster stats. |

In all cases:

`EFFECT_CONFIG_FAILURE_CHANGES_GO_CORRECTNESS=NO`.
`EFFECT_CONFIG_FAILURE_CREATES_SECOND_COMBAT_PATH=NO`.

## 22. Security / forgery matrix

| Client attempt | Future server behavior |
| --- | --- |
| Submit Spirit ID | `SERVER_IGNORED` for authority; load active/owned Spirit from D source. |
| Submit evolution stage | `SERVER_IGNORED`; derive from server progression/policy. |
| Submit effect ID/profile | `SERVER_IGNORED`; resolve from server registry. |
| Submit effect magnitude | `SERVER_IGNORED`; use server config. |
| Submit damage bonus | `SERVER_IGNORED`; use B021 + Spirit adapter calculation. |
| Submit mitigation | `SERVER_IGNORED`; use server Monster/Armor/Spirit stages. |
| Submit reward multiplier | `SERVER_IGNORED`; derive bounded modifier and send to D authority. |
| Submit Monster type/HP/ATK | `SERVER_IGNORED` for authority; load F001/B021 server snapshot. |
| Submit scene override | `SERVER_VERIFIED` only as a presentation request against allow-listed catalog data; it cannot mutate combat authority. |

## 23. Future test matrix

The future runtime task must add deterministic tests for:

1. Judge-before-effect invariant: effect evaluator cannot receive or mutate
   an unjudged answer.
2. Client Spirit-state forgery: ID, stage, profile, and magnitude are
   ignored/rejected.
3. Client combat forgery: damage, mitigation, Monster state, and reward
   multiplier cannot alter settlement.
4. Equipment + Spirit composition: B021 equipment is applied once, then the
   Spirit adapter once.
5. Weapon + Spirit outgoing damage: server result changes only through the
   canonical adapter.
6. Armor + Spirit mitigation/shield: order, caps, and no duplicate reduction.
7. Normal Monster and Boss server snapshots.
8. Elite unsupported/adapter-required behavior.
9. Lord Trial exclusion and preservation.
10. Retry determinism and same-operation replay.
11. Replay creates no combat/reward/drop effects.
12. Scene override isolation.
13. D5A/D5C reward/item handoff and no direct inventory write.
14. Unknown effect/config failure closes safely.
15. Policy-version reconstruction.
16. PostgreSQL transaction integration and concurrent settlement identity.
17. Existing legacy three-effect compatibility against approved values.
18. No second combat engine/static contract check.

## 24. Swarm interface status

| Interface | Available at audit start | Evidence / consequence |
| --- | --- | --- |
| D008 Spirit runtime combat projection | No | D008 branch/ref resolves to current master; no new runtime projection is present. Use the proposed handoff above, not a claimed implementation. |
| D007 lineage foundation | Yes | `spirit_lineage.py`, `spirit_lineage_auditor.py`, and `docs/planning/e10_six_spirit_s1_lineage_contract_v1.md`; no diff from the accessible D007 lineage commit to current master for these files. |
| F001 Monster authority interface | No | No F001-specific branch/file/interface was found. Use B021 roster evidence only and wait for the F001 handoff. |
| E019 boundary harness | Yes | Fixture contract and focused harness define post-judgement order, scene isolation, single active source, and replay-zero deltas. |

`D008_INTERFACE_AVAILABLE=LINEAGE_ONLY; COMBAT_PROJECTION=NO`.
`F001_INTERFACE_AVAILABLE=NO`.
`SWARM_INTERFACE_COLLISION=NO`.

No collision was found because no newer D008/F001 runtime contract is
available to contradict this proposed adapter boundary. If either lane later
publishes a different canonical interface, B implementation must stop and
reconcile the contract before adding hooks.

## 25. B022 scope proof

This task changes no runtime behavior. The only permitted tracked artifact is
this architecture/spec document.

```text
APP_PY_CHANGED=NO
MAP_BATTLE_RUNTIME_CHANGED=NO
SPIRIT_RUNTIME_CHANGED=NO
MONSTER_RUNTIME_CHANGED=NO
DB_MIGRATION=NO
PRODUCTION_MUTATION=NO
PAYMENT_CHANGED=NO
PRICING_CHANGED=NO
REVENUE_CHANGED=NO
MERGE=NO
DEPLOY=NO
```
