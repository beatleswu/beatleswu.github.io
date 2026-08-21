# Go Odyssey Wave 2 — Character 20 Production Plan

**Task:** `RPG_WAVE2_CHARACTER_20_PRODUCTION_PLAN_001`
**Mode:** swarm audit + production planning
**Scope:** planning only; no art generation, runtime change, database change, merge, deploy, or Production mutation

## Decision summary

The canonical player target is **20 player appearances**: the 10 runtime-canonical IDs plus 10 Wave 2 candidate IDs. The ten candidates are explicitly proposal-only and are not runtime registered. The current six-character proof set is a review package, not a production or runtime-acceptance gate.

The current six is:

`apprentice`, `mage`, `paladin`, `trail_apprentice`, `night_runner`, `constellation_apprentice`.

The default-art package is `owner_review_candidate`. The six one-hand sword pose results are review-ready, but the pose manifest marks the runtime asset `NOT_CREATED_REVIEW_ONLY`. The current six therefore remain **OWNER_PASS_PENDING**.

The long-term production unit is one logical asset per `CHARACTER × WEAPON_FAMILY`. The locked family in this plan is `ONE_HAND_SWORD_POSE`; `wooden_sword`, `iron_sword`, and `fox_fang` must not create three character-specific productions.

## Source-of-truth findings

- Canonical base for this plan: `origin/master` at `ac182ed173620a11e66bebeb6003c121b9ceee95`.
- The canonical runtime registry contains exactly 10 current player IDs in `hero.html`, `js/e9/adapters/player_state.js`, and `app.py`.
- The ten Wave 2 IDs are in the Wave 2 identity registry with `status=PROPOSAL_FOR_OWNER_GATE1`; they are not runtime roster IDs.
- The P1 visual package covers three existing players and three candidate players, plus two NPCs. NPC assets are excluded from this player plan.
- The six-character pose package uses `PLAYER_FRAME_A_STANDARD_CHIBI`, a 1056×1408 RGBA production frame, and a review-only universal `iron_sword` presentation. It does not change `player_inventory`, combat, selection APIs, the database, or runtime equipment authority.
- The repository has a distinct 20-entry battlefield monster roster. It is not part of this 20-player target.

Supporting source files include:

- `docs/planning/rpg_wave2_lane_a_character_identity_registry_v1.json`
- `docs/planning/rpg_wave2_lane_a_character_production_pack_v1.md`
- `docs/planning/GO_ODYSSEY_RPG_VISUAL_BIBLE.md`
- `docs/planning/rpg_wave2_gate2_character_art_p1_manifest.json`
- `docs/planning/rpg_wave2_gate2_character_art_p1_review.html`
- `docs/planning/rpg_wave2_full_body_weapon_pose_batch2/manifest.json` on `codex/rpg-wave2-one-hand-sword-pose-batch2-001`

## Readiness counts

`READY` below means final Wave 2 production-ready: default body, required pose family, identity review, compatibility review, and Owner visual gate. It does not mean “the current legacy chibi asset exists.”

| Measure | Count | Meaning |
|---|---:|---|
| Target player appearances | 20 | 10 active runtime IDs + 10 candidate slots |
| Existing canonical IDs | 10 | Current runtime and current asset registry |
| New/reserved IDs | 10 | Proposal-only candidates; none runtime registered |
| READY | 0 | No character has cleared the final plan gates |
| NEEDS_STANDARDIZATION | 3 | Existing IDs in the current P1 proof package; Owner acceptance still pending |
| NEEDS_REDRAW | 7 | Existing IDs with current chibi art but no P1 full-body production package |
| NEEDS_CANONICAL_DECISION | 3 | Candidate IDs with P1 art but no Owner Gate 1 decision |
| RESERVED_ONLY | 7 | Candidate IDs with text identity briefs but no tracked character master |
| BLOCKED_FOR_ART | 7 | The seven reserved-only candidates lack sufficient visual identity references |

The status categories are intentionally conservative. The ten current runtime characters are “current-runtime-ready,” but the final production plan still requires full-body contract work and the one-hand sword end state. The seven `BLOCKED_FOR_ART` entries are a readiness flag over the `RESERVED_ONLY` records, not a new runtime category.

## Current six proof status

| Dimension | Current evidence | Plan status |
|---|---|---|
| `DEFAULT_POSE_STATUS` | Six P1 default packages use the shared player frame; manifest status is `owner_review_candidate` | `OWNER_REVIEW_CANDIDATE` |
| `ONE_HAND_SWORD_POSE_STATUS` | Three approved-reference poses plus three Batch 2 poses; aggregate QA is 6/6 review-ready | `6_OF_6_REVIEW_READY_OWNER_PASS_PENDING` |
| `IDENTITY_REFERENCE_STATUS` | Three existing canonical identities and three candidate identities have P1 identity/frame evidence | `6_OF_6_REVIEWABLE; CANDIDATE_GATE1_PENDING` |
| `RUNTIME_REGISTRY_STATUS` | Apprentice, Mage, and Paladin are canonical; the three new IDs are preview-only and not registered | `3_CANONICAL + 3_NOT_REGISTERED` |

The current pose manifest says `runtime_asset_status=NOT_CREATED_REVIEW_ONLY`, `pose_selection=PRESENTATION_ONLY`, and `combat_delta=0`. This plan does not reopen or alter that lane.

## Production asset throughput

Counts are logical presentation assets, not per-item variants.

| Asset class | Required | Already available | In progress / review-only | Remaining after current-six acceptance |
|---|---:|---:|---:|---:|
| Default full-body character art | 20 | 0 final accepted; 10 legacy chibi bases remain current-runtime art | 6 P1 default packages | 14 |
| `ONE_HAND_SWORD_POSE` art | 20 | 0 runtime-accepted | 6 review-ready pose variants | 14 |
| Total full-body character presentations | 40 | 0 final accepted | 12 current-six logical presentations | 28 |

The default contract is one accepted PNG master plus a derived WebP runtime file per character. The pose count remains one per character and family; it does not multiply by `wooden_sword`, `iron_sword`, or `fox_fang`. The universal weapon-layer/runtime packaging decision remains behind the current proof Owner gate.

Review planning counts:

- `REVIEW_MATRIX_COUNT=24`: 20 character review rows plus four batch-level review matrices.
- `MOBILE_QA_MATRIX_COUNT=24`: 20 character mobile crops plus four batch-level mobile matrices.
- The current six proof package already contains four batch/final matrix artifacts; those are evidence for the proof gate, not closure of the 20-character program.
- The planned mobile pass is 60 viewport checks: three viewport classes for each of 20 characters, with the 24 matrices used as review evidence.

## Batching plan

The requested 6/4/5/5 shape is retained, but the actual proof set contains three existing IDs and three candidate IDs. Therefore Batch 3 is mixed; it is not truthful to call all five Batch 3 entries “new.”

### Batch 1 — current six proof set

**Characters:** `apprentice`, `mage`, `paladin`, `trail_apprentice`, `night_runner`, `constellation_apprentice`

- Dependencies: current six `ONE_HAND_SWORD_POSE=OWNER_PASS`; weapon-pose/armor compatibility is Owner-pass or accepted architecture; Gate 1 decisions for the three candidate IDs before they become canonical.
- Identity-reference readiness: six reviewable P1 identity packages; three candidate identities remain Owner-gated.
- Expected full-body redraws: 0 planned after proof acceptance; six are rework candidates if the Owner returns proof feedback.
- Expected sword-pose redraws: 0 planned after proof acceptance; six are rework candidates if the Owner rejects pose/compatibility.
- Armor compatibility risk: standard overlay candidate only; universal fit is not proven beyond the six Frame-A bodies.
- QA: identity continuity, PNG/WebP provenance, alpha/chroma checks, frame/footline, empty-hand base check, sword grip, face clearance, armor compositing, desktop/tablet/mobile matrices, and focused static-contract tests.
- Owner visual gate: `CURRENT_6_CHARACTER_ONE_HAND_SWORD=OWNER_PASS` and `WEAPON_POSE_ARMOR_COMPATIBILITY=OWNER_PASS_OR_ACCEPTED_ARCHITECTURE`.

### Batch 2 — four remaining existing canonicals

**Characters:** `apprentice_girl`, `swordsman`, `rogue`, `ranger`

- Dependencies: Batch 1 gate; preserve each current identity; measure body frame before redrawing.
- Identity-reference readiness: current art and role briefs exist; most age/body measurements are not text-locked and must be judged from the current art.
- Expected full-body redraws: 4.
- Expected sword-pose redraws: 4, one per character family variant after default-body acceptance.
- Armor compatibility risk: body-frame subclass review for narrow/hooded/travel silhouettes; do not assume the six-body overlay proof generalizes.
- QA: full identity anchor sheet, frame/alpha, mobile crop, one-hand grip, torso armor, face accessory, and shoulder/back clearance.
- Owner visual gate: batch-specific visual approval after the current-six gates remain closed and unchanged.

### Batch 3 — three existing plus two reserved candidates

**Characters:** `berserker`, `guardian`, `sage`, `river_wayfinder`, `stone_caretaker`

- Dependencies: Batch 1 gate; existing identity preservation; Gate 1 canonical decision and full identity references for the two candidates.
- Identity-reference readiness: the three existing identities are referenced; both candidates are text-only and `BLOCKED_FOR_ART` until face/hair/body references are approved.
- Expected full-body redraws: 5 conditional assets.
- Expected sword-pose redraws: 5 conditional family variants.
- Armor compatibility risk: broad-body, mantle, robe, and age-diverse body-frame subclass risk; special review is mandatory.
- QA: all Batch 2 checks plus broad-shoulder, robe/arm clearance, face-mask occlusion, and silhouette continuity review.
- Owner visual gate: candidate Gate 1 plus character-specific visual approval for each newly unblocked candidate.

### Batch 4 — five reserved candidates

**Characters:** `duelist_scout`, `bastion_warden`, `forest_pathfinder`, `archive_scholar`, `worldkeeper`

- Dependencies: Batch 1 gate; five separate Gate 1 canonical decisions; face/hair/age/body references; display-name approval.
- Identity-reference readiness: text briefs only; all five are `BLOCKED_FOR_ART` at planning time.
- Expected full-body redraws: 5 conditional assets.
- Expected sword-pose redraws: 5 conditional family variants.
- Armor compatibility risk: highest uncertainty; narrow, broad, hooded, layered, and civic-mantle silhouettes require subclass/mask/special review decisions before production.
- QA: full identity reference lock, alpha/frame/footline, mobile silhouette, overlay/mask/shoulder review, then one-hand sword family review.
- Owner visual gate: canonical decision, identity-reference approval, and character-specific visual pass.

## Equipment compatibility risk posture

The equipment layer is a presentation projection over server-owned functional equipment. The current evidence proves a Frame-A candidate for six P1 bodies, not a universal overlay system. Risk counts in the matrix are flags and are not mutually exclusive:

- `STANDARD_OVERLAY_COUNT=6`: current six Frame-A bodies only.
- `BODY_FRAME_SUBCLASS_COUNT=14`: every other intended character requires body-frame review before universal overlay claims.
- `CHARACTER_MASK_RISK_COUNT=7`: face-occluding accessories need per-character identity checks.
- `SPECIAL_REVIEW_COUNT=10`: broad shoulders, hoods, capes, robes, back arcs, or age/body exceptions need focused review.

No staff, bow, heavy-weapon, or other weapon pose family is authorized by this plan. They remain future decisions.

## Exact mass-production start gate

`MASS_CHARACTER_PRODUCTION` may begin only when both conditions are true:

1. `CURRENT_6_CHARACTER_ONE_HAND_SWORD=OWNER_PASS`
2. `WEAPON_POSE_ARMOR_COMPATIBILITY=OWNER_PASS_OR_ACCEPTED_ARCHITECTURE`

After both conditions pass, proceed into the batches without reopening the architecture for each character. Stop only for a real identity, art, or compatibility blocker. A candidate still requires its own canonical/identity decision; the mass-production gate does not silently register candidates or grant runtime authority.

## Authority and exclusions

- Character art is cosmetic and presentation-only.
- `player_inventory` remains the functional equipment authority.
- No character art may imply ownership, attack, defense, class, or combat effect.
- No current Sword Pose asset, Dragon Scale compatibility asset, runtime registry, player inventory, combat path, database, merge, deployment, or Production state was changed by this planning task.

## Swarm reconciliation

- `SWARM_F1`: found 10 existing asset-backed runtime IDs; three P1 candidate assets; seven candidate art gaps.
- `SWARM_F2`: confirmed the 10 runtime IDs and that all ten candidates are not runtime registered; identified legacy compatibility aliases as non-canonical.
- `SWARM_F3`: mapped identity anchors and marked seven text-only candidates `BLOCKED_FOR_ART`; identified age/body reference gaps in the existing roster.
- `SWARM_F4`: supplied the 6/4/5/5 throughput shape and exposed the proof-set mismatch; lead reconciled Batch 3 as mixed.
- `SWARM_F5`: confirmed six-body Frame-A overlay evidence, 14 subclass risks, seven face-mask risks, ten special-review flags, and family-level sword pose multiplication.

## Return values

```text
TASK=RPG_WAVE2_CHARACTER_20_PRODUCTION_PLAN_001
BASE_HEAD=ac182ed173620a11e66bebeb6003c121b9ceee95
BRANCH=codex/rpg-wave2-character-20-production-plan-001
HEAD_AFTER=<set after commit>
TARGET_CHARACTER_COUNT=20
EXISTING_CHARACTER_COUNT=10
NEW_OR_RESERVED_CHARACTER_COUNT=10
READY_CHARACTER_COUNT=0
NEEDS_STANDARDIZATION_COUNT=3
NEEDS_REDRAW_COUNT=7
NEEDS_CANONICAL_DECISION_COUNT=3
BLOCKED_FOR_ART_COUNT=7
CURRENT_6_STATUS=6/6 pose review-ready; Owner Pass pending; 3 canonical + 3 preview-only
BATCH_1=current six proof set
BATCH_2=apprentice_girl, swordsman, rogue, ranger
BATCH_3=berserker, guardian, sage, river_wayfinder, stone_caretaker
BATCH_4=duelist_scout, bastion_warden, forest_pathfinder, archive_scholar, worldkeeper
DEFAULT_FULL_BODY_ART_REQUIRED=20
ONE_HAND_SWORD_POSE_ART_REQUIRED=20
TOTAL_FULL_BODY_CHARACTER_ART_REQUIRED=40
STANDARD_OVERLAY_COUNT=6
BODY_FRAME_SUBCLASS_COUNT=14
CHARACTER_MASK_RISK_COUNT=7
SPECIAL_REVIEW_COUNT=10
MASS_PRODUCTION_GATE=DEFINED
FILES_CHANGED=4
TESTS=JSON validation planned after artifact creation; no application tests required
TASK_INTRODUCED_FAILURES=NONE_OBSERVED
DB_MIGRATION=NO
MERGE=NO
DEPLOY=NO
PRODUCTION_MUTATION=NO
FINAL_STATUS=READY_FOR_OWNER_CHARACTER_20_PRODUCTION_PLAN_REVIEW
```
