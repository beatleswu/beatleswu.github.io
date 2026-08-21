# Go Odyssey Wave 2 — Character Equipment Compatibility Risk Matrix

**Task:** `RPG_WAVE2_CHARACTER_20_PRODUCTION_PLAN_001`
**Purpose:** identify production risk before mass character art; no compatibility implementation is authorized here.

## Guardrails

- The current evidence proves a `PLAYER_FRAME_A_STANDARD_CHIBI` candidate for the six-character proof set only. It does not prove universal wearable fit.
- `TORSO_ARMOR`, `FACE_ACCESSORY`, and `SHOULDER_MANTLE` are visual projection concerns. Functional ownership remains `player_inventory` and functional effects remain server-owned equipment definitions.
- `WEAPON_POSE` is a presentation family. One-hand swords use one `CHARACTER × ONE_HAND_SWORD_POSE` asset, not `CHARACTER × ITEM` assets.
- `Dragon Scale`, `Fox Mask`, `Dragon Eye`, `Void Mantle`, `wooden_sword`, `iron_sword`, and `fox_fang` remain item/family references. No compatibility asset was changed or re-authored by this task.
- No `STAFF_POSE`, `BOW_POSE`, or `HEAVY_WEAPON_POSE` is authorized.

## Counts

These are risk flags, not mutually exclusive work queues.

| Risk flag | Count | Definition |
|---|---:|---|
| `STANDARD_OVERLAY` | 6 | Current six Frame-A bodies only; candidate for standard overlay, not universal proof |
| `BODY_FRAME_SUBCLASS` | 14 | All other target IDs require body-frame measurement/subclass review |
| `CHARACTER_MASK` risk | 7 | Face-occluding accessory could erase identity anchors |
| `SPECIAL_REVIEW` | 10 | Broad shoulders, hoods, capes, robes, back arcs, or age/body exceptions |

Batch readiness after the six-character Owner Pass and 20/20 canonical roster lock:

| Batch | Ready for full-body production | Blocked | Primary blocker |
|---|---:|---:|---|
| Batch 2 | 4 | 0 | No identity or runtime blocker; subclass QA remains |
| Batch 3 | 3 | 2 | `river_wayfinder` and `stone_caretaker`: art/identity reference required |
| Batch 4 | 0 | 5 | Approved face/hair/age/body identity reference required for every final-roster ID |

For Batches 2–4, the risk split is `STANDARD_OVERLAY=0`, `BODY_FRAME_SUBCLASS=14`, `CHARACTER_MASK_RISK=5`, and `SPECIAL_REVIEW=7`. The six Batch 1 bodies retain the six standard-overlay candidate flags, two mask risks, and three special-review flags, producing the program totals above.

## Matrix

| Character ID | Torso armor | Face accessory | Shoulder mantle | Weapon pose | Risk flags | Production implication |
|---|---|---|---|---|---|---|
| `apprentice` | `STANDARD_OVERLAY` candidate | Standard anchor check | Standard anchor check | Six-proof `OWNER_PASS` | — | Use current-six gate; preserve beginner face and open-hand base |
| `apprentice_girl` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Standard anchor check | Not started | — | Ready for full-body production; measure body during redraw |
| `swordsman` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Standard anchor check | Not started | — | Ready for full-body production; preserve headband/chest trim and verify hands |
| `rogue` | `BODY_FRAME_SUBCLASS` | `CHARACTER_MASK` | Standard anchor check | Not started | `CHARACTER_MASK` | Hood and face opening must not erase identity |
| `ranger` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Subclass review | Not started | `SPECIAL_REVIEW` | Mantle/satchel/back arc can exceed standard overlay safe area |
| `berserker` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Subclass review | Not started | `SPECIAL_REVIEW` | Broad body and strong shoulder silhouette need measured frame |
| `guardian` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Subclass review | Not started | `SPECIAL_REVIEW` | Broad shoulders are an explicit universal-fit risk |
| `paladin` | `STANDARD_OVERLAY` candidate | Standard anchor check | Standard anchor check | Six-proof `OWNER_PASS` | — | Revalidate armor projection only at the pending compatibility gate |
| `mage` | `STANDARD_OVERLAY` candidate | Standard anchor check | Standard anchor check | Six-proof `OWNER_PASS` | — | Robe and sleeve clearance must remain readable |
| `sage` | `BODY_FRAME_SUBCLASS` | `CHARACTER_MASK` | Standard anchor check | Not started | `CHARACTER_MASK` | Beard/glasses and robe layers require face clearance |
| `trail_apprentice` | `STANDARD_OVERLAY` candidate | Standard anchor check | Subclass review | Six-proof `OWNER_PASS` | `SPECIAL_REVIEW` | Pack/scarf and travel silhouette need back/neck checks |
| `river_wayfinder` | `BODY_FRAME_SUBCLASS` | `CHARACTER_MASK` | Subclass review | Not started | `CHARACTER_MASK` | Canonical final-roster ID; rain cape/satchel identity reference required |
| `stone_caretaker` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Subclass review | Not started | `SPECIAL_REVIEW` | Canonical final-roster ID; grounded broad/older identity reference required |
| `duelist_scout` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Standard anchor check | Not started | — | Canonical final-roster ID; narrow coat/cuff hand clearance requires identity reference |
| `bastion_warden` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Subclass review | Not started | `SPECIAL_REVIEW` | Canonical final-roster ID; broad mantle/shoulder identity reference required |
| `forest_pathfinder` | `BODY_FRAME_SUBCLASS` | `CHARACTER_MASK` | Subclass review | Not started | `CHARACTER_MASK`, `SPECIAL_REVIEW` | Canonical final-roster ID; hood/cloak/back arc and face opening need identity review |
| `night_runner` | `STANDARD_OVERLAY` candidate | `CHARACTER_MASK` | Subclass review | Six-proof `OWNER_PASS` | `CHARACTER_MASK`, `SPECIAL_REVIEW` | P1 hood/face opening and diagonal silhouette are review-sensitive |
| `constellation_apprentice` | `STANDARD_OVERLAY` candidate | `CHARACTER_MASK` | Subclass review | Six-proof `OWNER_PASS` | `CHARACTER_MASK`, `SPECIAL_REVIEW` | Asymmetric sleeve/hood lines need pose and overlay clearance |
| `archive_scholar` | `BODY_FRAME_SUBCLASS` | `CHARACTER_MASK` | Standard anchor check | Not started | `CHARACTER_MASK` | Canonical final-roster ID; layered robe/satchel and face accessory need identity review |
| `worldkeeper` | `BODY_FRAME_SUBCLASS` | Standard anchor check | Subclass review | Not started | `SPECIAL_REVIEW` | Canonical final-roster ID; civic mantle and broad age/body presentation require identity review |

## Gate interpretation

`STANDARD_OVERLAY` is a candidate classification, not permission to implement a universal renderer. `BODY_FRAME_SUBCLASS` means the character must receive measured body-frame evidence before an overlay can be reused. `CHARACTER_MASK` means a face accessory must be checked against face, hair, age, and silhouette anchors. `SPECIAL_REVIEW` means the character needs an explicit review sheet before approval.

The seven final canonical character blockers are now narrowed to explicit codes:

- `ART_REFERENCE_REQUIRED`: all seven lack an approved final art/reference package.
- `IDENTITY_REFERENCE_REQUIRED`: all seven lack approved face, hair, age, and measured body identity evidence.
- `DEFAULT_ART_MISSING`: all seven still need a complete default-pose presentation.
- `RUNTIME_NOT_REGISTERED`: all seven are canonical but intentionally absent from runtime authority; this task does not register them.
- Role, costume, palette, and silhouette direction are resolved from the canonical text identity registry and carried into the Final 7 identity lane.

The only current family-level weapon decision is `ONE_HAND_SWORD_POSE`. The current six pose package uses a review-only universal `iron_sword` presentation and reports runtime composition still requires the universal weapon layer. No item-specific character redraws are planned.

## Required evidence before each character passes

1. Approved identity reference with face, hair, age, body proportion, palette, signature clothing, silhouette, and role.
2. Default full-body master with the shared canvas, foot baseline, alpha, and safe-area contract.
3. Overlay/mask/mantle compositing review at desktop, tablet, and mobile sizes.
4. One-hand sword family pose review where the character is allowed to wield one-handed swords.
5. Owner visual pass; no runtime, database, equipment ownership, combat, merge, or deployment mutation.
