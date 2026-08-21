# Go Odyssey Wave 2 — Character 20 Production Plan

**Task:** `RPG_WAVE2_CHARACTER_20_CANONICALIZATION_PRODUCTION_READY_001`
**Mode:** Owner precheck correction + parallel production-lane dispatch
**Scope:** canonical roster correction and production readiness; no runtime authority, database, merge, deploy, or Production mutation

## Decision summary

The canonical player target is **20/20 locked canonical characters**: 10 runtime-registered IDs, three previously promoted Batch 1 IDs, and seven newly promoted final-roster IDs. Canonical roster status is no longer an Owner-decision blocker. The seven final-roster IDs remain blocked only by art/reference/runtime conditions, and the current six-character proof set is Owner-passed for this lane.

The current six is:

`apprentice`, `mage`, `paladin`, `trail_apprentice`, `night_runner`, `constellation_apprentice`.

Six default full-body PNG/WebP packages are present for Batch 1. The six one-hand sword pose results are `OWNER_PASS_6_OF_6`; the pose manifest still records the runtime asset as `NOT_CREATED_REVIEW_ONLY`, so this update changes planning status only and does not create a runtime asset.

The long-term production unit is one logical asset per `CHARACTER × WEAPON_FAMILY`. The locked family in this plan is `ONE_HAND_SWORD_POSE`; `wooden_sword`, `iron_sword`, and `fox_fang` must not create three character-specific productions.

## Source-of-truth findings

- Canonical base for this plan: `origin/master` at `ac182ed173620a11e66bebeb6003c121b9ceee95`.
- The canonical runtime registry contains exactly 10 current player IDs in `hero.html`, `js/e9/adapters/player_state.js`, and `app.py`.
- The historical Wave 2 identity registry is `PROPOSAL_FOR_OWNER_GATE1`; this Owner precheck supersedes that planning status for all ten Wave 2 additions. The final seven are canonical in this plan but remain absent from runtime registries until a separate runtime-authority change.
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

`READY` below means final Wave 2 production-ready: default body, required pose family, identity review, compatibility review, and Owner visual gate. `READY_FOR_DEFAULT_ART_PRODUCTION` is independent of the Sword Pose × Armor gate. `READY_FOR_SWORD_POSE_MASS_PRODUCTION` remains zero until the compatibility gate passes.

| Measure | Count | Meaning |
|---|---:|---|
| Target player appearances | 20 | Locked final roster |
| Canonical character IDs | 20 | 10 runtime IDs + 10 promoted Wave 2 IDs |
| Owner-decision-required IDs | 0 | Canonical roster decision is complete |
| READY | 0 | No character has cleared the final plan gates |
| NEEDS_STANDARDIZATION | 6 | All six Batch 1 identities have accepted proof packages and require production standardization only |
| NEEDS_REDRAW | 14 | Seven existing canonical IDs plus the seven promoted final-roster IDs still need default art |
| NEEDS_CANONICAL_DECISION | 0 | No canonical decision remains open |
| RESERVED_ONLY | 0 | No target character remains reserved-only |
| BLOCKED_FOR_ART | 7 | Final-roster IDs require art/identity references; runtime registration remains separate |
| OWNER_APPROVED_CURRENT_6 | 6 | Current six one-hand sword proof identities are Owner-passed |
| READY_FOR_DEFAULT_ART_PRODUCTION | 7 | Batch 2 (4) + Batch 3A (3); no Sword Pose × Armor dependency |
| READY_FOR_SWORD_POSE_MASS_PRODUCTION | 0 | Armor compatibility gate is pending |

The status categories separate roster canon from production readiness. All 20 IDs are canonical. The seven `BLOCKED_FOR_ART` entries are canonical characters that still need approved art/identity references; they are not reserved-only and do not require another canonical decision. Runtime registration remains an independent authority change.

## Current six proof status

| Dimension | Current evidence | Plan status |
|---|---|---|
| `DEFAULT_POSE_STATUS` | Six P1 default packages use the shared player frame and are the accepted Batch 1 default packages | `OWNER_PASS_6_OF_6` |
| `ONE_HAND_SWORD_POSE_STATUS` | Three approved-reference poses plus three Batch 2 poses; aggregate QA is 6/6 | `OWNER_PASS_6_OF_6` |
| `IDENTITY_REFERENCE_STATUS` | Six Batch 1 identities are canonical for this plan | `OWNER_CANONICAL_6_OF_6` |
| `RUNTIME_REGISTRY_STATUS` | Apprentice, Mage, and Paladin are runtime-canonical; the three new canonical IDs remain intentionally unregistered | `3_RUNTIME_CANONICAL + 3_PLAN_CANONICAL_NOT_REGISTERED` |

The current pose manifest says `runtime_asset_status=NOT_CREATED_REVIEW_ONLY`, `pose_selection=PRESENTATION_ONLY`, and `combat_delta=0`. This plan does not reopen or alter that lane.

## Production asset throughput

Counts are logical presentation assets, not per-item variants.

| Asset class | Required | Already complete / Owner-passed | In progress / review-only | Remaining |
|---|---:|---:|---:|---:|
| Default full-body character art | 20 | 6 | 0 | 14 |
| `ONE_HAND_SWORD_POSE` art | 20 | 6 | 0 | 14 |
| Total full-body character presentations | 40 | 12 | 0 | 28 |

The default contract is one accepted PNG master plus a derived WebP runtime file per character. The pose count remains one per character and family; it does not multiply by `wooden_sword`, `iron_sword`, or `fox_fang`. The universal weapon-layer/runtime packaging decision remains behind the current proof Owner gate.

Review planning counts:

- `REVIEW_MATRIX_COUNT=24`: 20 character review rows plus four batch-level review matrices.
- `MOBILE_QA_MATRIX_COUNT=24`: 20 character mobile crops plus four batch-level mobile matrices.
- The current six proof package already contains four batch/final matrix artifacts; those are evidence for the proof gate, not closure of the 20-character program.
- The planned mobile pass is 60 viewport checks: three viewport classes for each of 20 characters, with the 24 matrices used as review evidence.

## Batching plan

The requested 6/4/5/5 shape is retained, but the actual proof set contains three existing IDs and three promoted Batch 1 IDs. Therefore Batch 3 is mixed; it is not truthful to call all five Batch 3 entries “new.”

### Batch 1 — current six proof set

**Characters:** `apprentice`, `mage`, `paladin`, `trail_apprentice`, `night_runner`, `constellation_apprentice`

- Dependencies: current six `ONE_HAND_SWORD_POSE=OWNER_PASS`; weapon-pose/armor compatibility remains the only mass-production gate.
- Identity-reference readiness: six Owner-canonical Batch 1 identities with six accepted default packages.
- Expected full-body redraws: 0 planned; no new Batch 1 default art is requested.
- Expected sword-pose redraws: 0 planned; the six approved poses are not modified.
- Armor compatibility risk: standard overlay candidate only; universal fit is not proven beyond the six Frame-A bodies.
- QA: identity continuity, PNG/WebP provenance, alpha/chroma checks, frame/footline, empty-hand base check, sword grip, face clearance, armor compositing, desktop/tablet/mobile matrices, and focused static-contract tests.
- Owner visual gate: `CURRENT_6_STATUS=OWNER_PASS_6_OF_6`; mass-production Part 2 remains `PENDING_ARMOR_COMPATIBILITY`.

### Batch 2 — four remaining existing canonicals

**Characters:** `apprentice_girl`, `swordsman`, `rogue`, `ranger`

- Dependencies: Current six proof remains Owner-passed; default-pose production is independent of Sword Pose × Armor compatibility.
- Identity-reference readiness: existing canonical art and role briefs are sufficient to start the full-body redraw; new full-body art is still required.
- Expected full-body redraws: 4.
- Expected sword-pose redraws: 4, one per character family variant after default-body acceptance.
- Armor compatibility risk: body-frame subclass review for narrow/hooded/travel silhouettes; do not assume the six-body overlay proof generalizes.
- QA: full identity anchor sheet, frame/alpha, mobile crop, one-hand grip, torso armor, face accessory, and shoulder/back clearance.
- Readiness: `BATCH_2_READY_COUNT=4`, `BATCH_2_BLOCKED_COUNT=0`; these four can enter the default-art queue immediately, without waiting for the armor gate.
- Owner visual gate: batch-specific default-pose visual approval; Sword Pose work remains behind the armor gate.

### Batch 3 — three existing plus two canonical final-roster identities

**Characters:** `berserker`, `guardian`, `sage`, `river_wayfinder`, `stone_caretaker`

- Dependencies: Current six proof remains Owner-passed; three existing identities are ready for default-pose production; two canonical final-roster identities require reference lock.
- Identity-reference readiness: the three existing identities are ready for full-body production; both final-roster IDs remain `ART_REFERENCE_REQUIRED` and `IDENTITY_REFERENCE_REQUIRED`.
- Expected full-body redraws: 5 conditional assets.
- Expected sword-pose redraws: 5 conditional family variants.
- Armor compatibility risk: broad-body, mantle, robe, and age-diverse body-frame subclass risk; special review is mandatory.
- QA: all Batch 2 checks plus broad-shoulder, robe/arm clearance, face-mask occlusion, and silhouette continuity review.
- Readiness: `BATCH_3_READY_COUNT=3`, `BATCH_3_BLOCKED_COUNT=2`.
- Owner visual gate: identity-reference approval plus character-specific visual approval; canonical roster status is already locked.

### Batch 4 — five canonical final-roster identities

**Characters:** `duelist_scout`, `bastion_warden`, `forest_pathfinder`, `archive_scholar`, `worldkeeper`

- Dependencies: Current six proof remains Owner-passed; canonical IDs are locked; face/hair/age/body references remain required.
- Identity-reference readiness: text identity briefs resolve role, palette, costume, and silhouette only; all five remain `ART_REFERENCE_REQUIRED` and `IDENTITY_REFERENCE_REQUIRED`.
- Expected full-body redraws: 5 conditional assets.
- Expected sword-pose redraws: 5 conditional family variants.
- Armor compatibility risk: highest uncertainty; narrow, broad, hooded, layered, and civic-mantle silhouettes require subclass/mask/special review decisions before production.
- QA: full identity reference lock, alpha/frame/footline, mobile silhouette, overlay/mask/shoulder review, then one-hand sword family review.
- Readiness: `BATCH_4_READY_COUNT=0`, `BATCH_4_BLOCKED_COUNT=5`.
- Owner visual gate: identity-reference approval and character-specific visual pass; no canonical decision is pending.

## Identity lock sheets for Batches 2–4

These are production guidance contracts, not finished art and not silent visual canon. For existing IDs, the current canonical asset is the identity reference. For the final seven, fields marked `NOT_CANONICALLY_SPECIFIED` remain art/identity-reference blockers, not canonical-decision blockers.

### Batch 2

| Character | Role | Age band | Face anchor | Hair anchor | Body proportion | Palette | Signature costume | Silhouette | Do-not-drift rules | Readiness |
|---|---|---|---|---|---|---|---|---|---|---|
| `apprentice_girl` | Beginner, Newbie Village | Not text-locked; preserve current art read | Current canonical face in shared head anchor `x=.50,y=.16` | Current canonical hair silhouette; no separate measurement | Open beginner frame; shared body `x=.20-.80`, footline `y=.975` | Teal, off-white, clay beige, leather brown, muted brass | Existing beginner costume | Open alternate-beginner silhouette | Preserve alternate beginner identity, face/hair read, open hands, and weapon-free base | `READY_FOR_FULL_BODY_PRODUCTION` |
| `swordsman` | Warrior, village road/training grounds | Not text-locked; preserve current art read | Current focused face in shared face grid | Current dominant hair silhouette; no separate measurement | Compact warrior frame; shared body and footline | Slate blue, rust, warm brown, ivory, brass | Headband and chest trim in large readable shapes | Compact blue upper-body block with hair cue | Preserve focused expression, headband/chest trim, compact warrior read, and no baked weapon | `READY_FOR_FULL_BODY_PRODUCTION` |
| `rogue` | Rogue, forest edge/Goblin Cave | Not text-locked; preserve current art read | Current eye/face plane inside shared head anchor | Current hood identity; no invented hair landmark | Narrow high-contrast frame; retain hand separation | Charcoal, muted violet/teal, warm grey, brown, ivory | Hood and dark close-fitting layers with one face window | Narrow asymmetric profile | Do not merge hood, face, hands, or torso; keep dark identity and cosmetic-only base | `READY_FOR_FULL_BODY_PRODUCTION` |
| `ranger` | Ranger, Misty Forest/frontier routes | Not text-locked; preserve current art read | Current alert face in common eye/brow grid | Current hair/hood separation; no new hairstyle | Lean travel frame; shared body and footline | Forest green, bark brown, mist violet, ivory, muted brass | Mantle and satchel | Lean stance with one large green mantle mass | Preserve green/brown travel identity, mantle/satchel read, alert face, and frame | `READY_FOR_FULL_BODY_PRODUCTION` |

### Batch 3

| Character | Role | Age band | Face anchor | Hair anchor | Body proportion | Palette | Signature costume | Silhouette | Do-not-drift rules | Readiness |
|---|---|---|---|---|---|---|---|---|---|---|
| `berserker` | Warrior, Orc Tribe/arena | Existing age read only; not text-locked | Current face enlarged within common face grid | Preserve current red hair and spike cue | Broad body at shared frame maximum | Ox-blood red, charcoal, leather brown, brass | Fur/leather grouped into three readable masses | Broad shoulders plus red hair spikes | Preserve broad identity, red-hair cue, fur/leather read, footline, and weapon-free base | `READY_FOR_FULL_BODY_PRODUCTION` |
| `guardian` | Knight, village defense/Demon Castle Front | Existing age read only; not text-locked | Current grounded expression in common face grid | Current canonical hair silhouette | Broad protective shoulder/torso blocks | Blue-charcoal, iron grey, brown, muted brass | Dark armor blocks, shoulder/torso block, mantle | Sturdy broad-shouldered protective silhouette | Preserve broad shoulders, torso block, grounded expression; do not assume universal armor fit | `READY_FOR_FULL_BODY_PRODUCTION` |
| `sage` | Scholar/Sage, Sage Tower/ancient records | Older upright read; exact age not text-locked | Beard and glasses inside common facial landmarks | Current canonical hair/face silhouette | Older upright body; do not make youthful | Earth brown, slate, ivory, muted brass | Scholar robe with beard/glasses hierarchy | Older upright scholar with readable robe and face | Preserve age, beard, glasses, robe, and face; remove tiny trim before changing identity | `READY_FOR_FULL_BODY_PRODUCTION` |
| `river_wayfinder` | Adventurer, field guide and route reader | Young adult; broad presentation options | `NOT_CANONICALLY_SPECIFIED`; identity reference required | `NOT_CANONICALLY_SPECIFIED`; identity reference required | Broad options; no measured body lock | Water blue, reed green, warm grey, brass | Hooded rain cape, tall boots, side satchel, rolled-map utility | Asymmetric water-ripple hem with cape/satchel profile | Do not invent face, hair, or body from text; preserve route-reader, rain-cape, satchel, and ripple hem | `ART_REFERENCE_REQUIRED + IDENTITY_REFERENCE_REQUIRED` |
| `stone_caretaker` | Scholar/Village, keeper of local practice and memory | Adult or older adult; age-diverse | `NOT_CANONICALLY_SPECIFIED`; identity reference required | `NOT_CANONICALLY_SPECIFIED`; identity reference required | Broad/grounded older-body direction; no measured lock | Stone grey, cedar brown, ivory, muted gold | Broad sash, layered short robe, dojo workwear/apron, counting cord | Grounded broad/older stance with sash and short-robe mass | Do not invent age, face, hair, or width from text; preserve grounded stance, sash, robe, and cord | `ART_REFERENCE_REQUIRED + IDENTITY_REFERENCE_REQUIRED` |

### Batch 4

| Character | Role | Age band | Face anchor | Hair anchor | Body proportion | Palette | Signature costume | Silhouette | Do-not-drift rules | Readiness |
|---|---|---|---|---|---|---|---|---|---|---|
| `duelist_scout` | Warrior, frontier roads/training grounds | Teen or young adult; any presentation | `NOT_CANONICALLY_SPECIFIED`; identity reference required | `NOT_CANONICALLY_SPECIFIED`; identity reference required | Narrow shoulders; no measured lock | Slate blue, rust red, ivory, leather brown | Light travel cloth, reinforced cuffs, split shoulder panel | Narrow asymmetric coat and long leg line | Do not invent face, hair, or body from text; preserve observation role, narrow coat, cuffs, and split panel | `ART_REFERENCE_REQUIRED + IDENTITY_REFERENCE_REQUIRED` |
| `bastion_warden` | Knight/Guardian, village defense/Demon Castle Front | Adult; varied body widths | `NOT_CANONICALLY_SPECIFIED`; identity reference required | `NOT_CANONICALLY_SPECIFIED`; identity reference required | Broad mantle and stable vertical torso; no measured lock | Blue-charcoal, stone grey, muted gold, brown | Layered guard cloth and padded mantle | Rounded shoulder mantle and strong shoulder arc | Do not invent broad body or face from text; preserve calm defender role, mantle, and shoulder arc | `ART_REFERENCE_REQUIRED + IDENTITY_REFERENCE_REQUIRED` |
| `forest_pathfinder` | Ranger, Misty Forest | Teen or adult; neutral/androgynous options | `NOT_CANONICALLY_SPECIFIED`; identity reference required | `NOT_CANONICALLY_SPECIFIED`; identity reference required | Neutral body options; no measured lock | Forest green, mist violet, bark brown, ivory | Weathered cloak, layered travel cloth, tall boots | Leaf-like mantle and long hood profile | Do not invent face, hair, or body from text; preserve patient-guide role, leaf hood, cloak, and back arc | `ART_REFERENCE_REQUIRED + IDENTITY_REFERENCE_REQUIRED` |
| `archive_scholar` | Scholar/Sage, Sage Tower/ancient records | Adult or older adult; age-diverse | `NOT_CANONICALLY_SPECIFIED`; identity reference required | `NOT_CANONICALLY_SPECIFIED`; identity reference required | Broad age-diverse options; no measured lock | Warm umber, slate, parchment ivory, muted teal | Tall collar, archive layers, cloth tabs, practical sleeves, satchel | Straight robe line with tall collar and folio clasp | Do not invent age, face, hair, or width from text; preserve researcher role, archive layers, and readable folio cue | `ART_REFERENCE_REQUIRED + IDENTITY_REFERENCE_REQUIRED` |
| `worldkeeper` | Sage/Guardian, endgame world stage | Broad age/body presentation; no fixed gender cue | `NOT_CANONICALLY_SPECIFIED`; identity reference required | `NOT_CANONICALLY_SPECIFIED`; identity reference required | Broad presentation; no measured lock | Deep indigo, ivory, cedar brown, restrained gold | Civic mantle over practical travel base | Long stable mantle and strong vertical center | Do not invent face, hair, age, or body from text; preserve quiet steward role, civic mantle, and paired waystone motif | `ART_REFERENCE_REQUIRED + IDENTITY_REFERENCE_REQUIRED` |

### Final 7 canonical identity-reference cards

The seven final-roster characters are canonical. No canonical decision is pending. Their remaining work is to approve exact face/hair/body identity references and to produce default art; runtime registration remains a separate authority change. `RUNTIME_NOT_REGISTERED` is a tracked boundary, not permission to edit runtime registries in this task.

- `IDENTITY-F7-river_wayfinder`: lock face/hair/body reference; then review rain-cape, satchel, and water-ripple hem.
- `IDENTITY-F7-stone_caretaker`: lock age/face/hair/body reference; then review broad grounded robe/sash fit.
- `IDENTITY-F7-duelist_scout`: lock face/hair/body reference; then review narrow coat, cuffs, and hand clearance.
- `IDENTITY-F7-bastion_warden`: lock face/hair/body reference; then review broad mantle and shoulder arc.
- `IDENTITY-F7-forest_pathfinder`: lock face/hood/hair/body reference; then review mask, cloak, and back arc.
- `IDENTITY-F7-archive_scholar`: lock age/face/hair/body reference; then review robe, satchel, and face accessory.
- `IDENTITY-F7-worldkeeper`: lock face/hair/age/body reference; then review civic mantle and subclass fit.

## Equipment compatibility risk posture

The equipment layer is a presentation projection over server-owned functional equipment. The current evidence proves a Frame-A candidate for six P1 bodies, not a universal overlay system. Risk counts in the matrix are flags and are not mutually exclusive. Default-pose production may proceed while the Sword Pose × Armor gate is pending:

- `STANDARD_OVERLAY_COUNT=6`: current six Frame-A bodies only.
- `BODY_FRAME_SUBCLASS_COUNT=14`: every other intended character requires body-frame review before universal overlay claims.
- `CHARACTER_MASK_RISK_COUNT=7`: face-occluding accessories need per-character identity checks.
- `SPECIAL_REVIEW_COUNT=10`: broad shoulders, hoods, capes, robes, back arcs, or age/body exceptions need focused review.

No staff, bow, heavy-weapon, or other weapon pose family is authorized by this plan. They remain future decisions.

## Exact mass-production start gate

`MASS_CHARACTER_PRODUCTION` may begin only when both conditions are true:

1. `CURRENT_6_CHARACTER_ONE_HAND_SWORD=OWNER_PASS`
2. `WEAPON_POSE_ARMOR_COMPATIBILITY=OWNER_PASS_OR_ACCEPTED_ARCHITECTURE`

`CURRENT_6_CHARACTER_ONE_HAND_SWORD=OWNER_PASS` is now satisfied. `WEAPON_POSE_ARMOR_COMPATIBILITY=OWNER_PASS_OR_ACCEPTED_ARCHITECTURE` remains pending. Batch 2 and Batch 3A default-pose production can start immediately; Sword Pose mass production remains blocked until Part 2 passes. The final seven require identity references, not canonical decisions, and no lane silently registers runtime IDs.

## Parallel work dispatched

- `RPG_WAVE2_CHARACTER_DEFAULT_POSE_BATCH2_001`: `apprentice_girl`, `swordsman`, `rogue`, `ranger`; complete DEFAULT_POSE only, with no Sword Pose or armor changes.
- `RPG_WAVE2_CHARACTER_DEFAULT_POSE_BATCH3A_001`: `berserker`, `guardian`, `sage`; complete DEFAULT_POSE only, with Smith Elder / Eastern Guardian / Archmage confusion gates.
- `RPG_WAVE2_CHARACTER_IDENTITY_UNBLOCK_FINAL7_001`: the seven canonical final-roster IDs; produce identity contracts and Owner-review reference sheets, not final runtime art or runtime registration.

The first two lanes are independent of Sword Pose × Armor compatibility. Their asset edits and review sheets are isolated by lane; the Final 7 lane owns only identity-reference evidence.

## Authority and exclusions

- Character art is cosmetic and presentation-only.
- `player_inventory` remains the functional equipment authority.
- No character art may imply ownership, attack, defense, class, or combat effect.
- No current Sword Pose asset, Dragon Scale compatibility asset, runtime registry, player inventory, combat path, database, merge, deployment, or Production state was changed by this planning task.

## Swarm reconciliation

- `SWARM_F1`: reconciled the product decision to a locked 20/20 canonical roster; seven final-roster IDs remain art/identity/runtime blocked only.
- `SWARM_F2`: confirmed Batch 2 has four identity-ready canonical characters and dispatched independent DEFAULT_POSE production.
- `SWARM_F3`: confirmed Batch 3A has three identity-ready canonical characters and dispatched independent DEFAULT_POSE production.
- `SWARM_F4`: converted the former Batch 3/4 reserved concepts into canonical final-seven identity-reference work; no canonical decision remains.
- `SWARM_F5`: split readiness into `READY_FOR_DEFAULT_ART_PRODUCTION=7` and `READY_FOR_SWORD_POSE_MASS_PRODUCTION=0` pending armor compatibility; dispatched Final 7 identity unblock.

## Return values

```text
TASK=RPG_WAVE2_CHARACTER_20_CANONICALIZATION_PRODUCTION_READY_001
OWNER_PRECHECK=PASS_WITH_GOVERNANCE_CORRECTION
BASE_HEAD=12f5b7f08cba4958d4f40f537acef18438166319
BRANCH=codex/rpg-wave2-character-governance-correction-001
HEAD_AFTER=CONTINUATION_BRANCH_HEAD_REPORTED_IN_TASK_RETURN
TARGET_CHARACTER_COUNT=20
CANONICAL_CHARACTER_COUNT=20
OWNER_DECISION_REQUIRED_COUNT=0
ART_REFERENCE_BLOCKED_COUNT=7
CURRENT_6_STATUS=OWNER_PASS_6_OF_6
END_STATE_DEFAULT_ART_COUNT=20
END_STATE_ONE_HAND_SWORD_POSE_COUNT=20
END_STATE_TOTAL_FULL_BODY_ART_COUNT=40
DEFAULT_ART_ALREADY_COMPLETE=6
DEFAULT_ART_REMAINING=14
SWORD_POSE_ALREADY_COMPLETE=6
SWORD_POSE_REMAINING=14
TOTAL_NEW_FULL_BODY_ART_REMAINING=28
OWNER_APPROVED_CURRENT_6=6
READY_FOR_DEFAULT_ART_PRODUCTION=7
READY_FOR_SWORD_POSE_MASS_PRODUCTION=0
BATCH_2_READY_COUNT=4
BATCH_2_BLOCKED_COUNT=0
BATCH_3_READY_COUNT=3
BATCH_3_BLOCKED_COUNT=2
BATCH_4_READY_COUNT=0
BATCH_4_BLOCKED_COUNT=5
MASS_PRODUCTION_GATE_PART_1=PASS
MASS_PRODUCTION_GATE_PART_2=PENDING_ARMOR_COMPATIBILITY
NEEDS_STANDARDIZATION_COUNT=6
NEEDS_REDRAW_COUNT=14
NEEDS_CANONICAL_DECISION_COUNT=0
STANDARD_OVERLAY_COUNT=6
BODY_FRAME_SUBCLASS_COUNT=14
CHARACTER_MASK_RISK_COUNT=7
SPECIAL_REVIEW_COUNT=10
FILES_CHANGED=4
TESTS=JSON validation, roster/batch coverage checks, dispatch scope checks
TASK_INTRODUCED_FAILURES=NONE_OBSERVED
DB_MIGRATION=NO
MERGE=NO
DEPLOY=NO
PRODUCTION_MUTATION=NO
FINAL_STATUS=OWNER_ACCEPTED_CHARACTER_MASS_PRODUCTION_PRECHECK
```
