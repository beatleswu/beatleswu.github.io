# W2_03_HERO_FULL_FRAME_WEAPON_POSE_VARIANT_VERTICAL_SLICE_007

```
TASK=W2_03_HERO_FULL_FRAME_WEAPON_POSE_VARIANT_VERTICAL_SLICE_007
ASSIGNEE=W1-02_HERO
TASK_CLASS=PRODUCT_VISUAL_ARCHITECTURE
PRIORITY=P1
EXECUTION_MODEL=SINGLE_AGENT
ROLE=SOLE_SOURCE_WRITER
BASE_SOURCE=FRESH_CANONICAL_MASTER
EXPECTED_CURRENT_CANONICAL_HEAD=3dc517bfbf789da378f971b092980fb53e7a5e2f
ARCHITECTURE_DECISION=HYBRID_FULL_FRAME_POSE_VARIANT
SUPERSEDES_FOR_PRODUCTION=TRUE_2D_SKELETAL_RIG_DIRECTION,SEGMENTED_LIMB_PRODUCTION_DIRECTION
SKELETAL_EXPERIMENT_HEAD=d989c15d002820e0eb9e52d9cef4ee8e16105205
SKELETAL_EXPERIMENT_DISPOSITION=RETAIN_AS_EXPERIMENTAL_EVIDENCE_ONLY
DO_NOT_MERGE_SKELETAL_BRANCH=YES
DO_NOT_EXTEND_SKELETAL_ASSETS_1_TO_22=YES
ART_GENERATION_AUTHORITY=NO

OWNER_COORDINATOR_DECISION=APPROVE_HAND_ONLY_V1
DO_NOT_EXPAND_TO_FULL_ARM=YES
DO_NOT_BEGIN_V2_RAISED_ARM=YES
AMENDMENT_1_CANONICAL_OPEN_HAND_REPLACEMENT_SEMANTICS=APPLIED
AMENDMENT_2_FUTURE_SIX_CHARACTER_GRIP_ANCHOR=APPLIED
FINAL_AMENDMENT_1_FIX_R15_SCOPE=APPLIED
FINAL_AMENDMENT_2_DISAMBIGUATE_PALM_VS_GRIP=APPLIED
FINAL_AMENDMENT_3_R10_BACK_LAYER_SEMANTICS=APPLIED
FINAL_AMENDMENT_4_R14_ALPHA_HARD_RGB_DIAGNOSTIC=APPLIED
PREFLIGHT_AMENDMENT_1_R15_NAMING_AND_CUFF_COVERAGE=APPLIED
PREFLIGHT_AMENDMENT_2_DETERMINISTIC_GRIP_AXIS=APPLIED
IMPLEMENTATION_SPEC=APPROVED
DO_NOT_OPEN_OR_MERGE_PR_YET=YES
DO_NOT_MOVE_MASTER=YES
TASK_BRIEF_STATUS=APPROVED_FOR_PLANNING_BRANCH_PUBLICATION
NO_MASTER_MUTATION  NO_MERGE  NO_DEPLOY  NO_PRODUCTION_MUTATION
```

**Baseline verified in-session (2026-09-05):** `origin/master` =
`3dc517bfbf789da378f971b092980fb53e7a5e2f` ("Merge commit `e6655e2a0` into
codex/p0-unified-release-zone3-static-closure-merge-003"). Re-fetched and confirmed. Skeletal head
`d989c15d0` confirmed **not** an ancestor of master; `baae68b58` (wearable replacement) confirmed
**not** an ancestor. Production is unmutated.

Codex must re-verify `EXPECTED_CURRENT_CANONICAL_HEAD` at dispatch time. A second execution line
merges PRs concurrently — if master has moved, **stop and report**, do not silently rebase.

---

## 0. Objective

Make the Hero visibly **hold** a wooden sword, using the full-frame wearable renderer that already
ships in `origin/master`.

- Do not replace the renderer.
- Do not create a skeletal character.
- Do not introduce Live2D or Spine.
- The vertical slice is `apprentice_p1` + `wooden_sword`, and nothing else.

Owner acceptance is a **still image judged by eye**, before any animation and before any second item.

---

## 1. Why the skeletal direction is being retired (evidence)

Verified on `codex/w2-03-hero-true-2d-skeletal-rig-vertical-slice-005r2`:

1. **Cut faces were drawn into the art.** `upper_arm_R.png` / `forearm_R.png` are hollow sleeve
   tubes whose cut ends render the tube's *inner surface*, with the silhouette outline closing
   around the cut. Two such segments butted together seam *by construction*. No pivot hides a
   drawn cut face.
2. **The segments never shared a body proportion.** Integration needed four hand-tuned scales for
   one arm — `upper_arm_R` 0.27, `forearm_R` 0.16, `hand_R_open` 0.22, `hand_R_grip_back` 0.20.
3. **Provenance confirms independent authoring** — five separate ~1254×1254 source images
   (`1-照片-1.jpg` … `5-照片-5.jpg`, five distinct sha256s), each drawn as a standalone object.
4. **The blocker was declared, then ignored.** `apprentice_p1_skeletal_manifest.json` already said
   `production_visual_rig = BLOCKED_WAIT_OWNER_APPROVED_RIG_ART`, `hero_hidden_pixel_blocker = true`,
   and five `art_dependencies` all `WAIT_OWNER_APPROVED_ART` requiring hidden shoulder / sleeve
   underside / wrist underlap pixels. Non-conforming art was integrated anyway.
5. **The gate measured the wrong thing.** 50-loop sampling and joint-underlap assertions passed
   while the composed image read as a severed limb.

**Carried forward:** art non-conformance is rejected mechanically *before* integration, never
absorbed by tuning a transform; and the final gate is the owner's eye on a still.

`js/e9/hero_skeletal_rig.js` is **retained** as experimental evidence (its bone/slot/draw-order
runtime and the proven `grip_back → weapon → grip_front` sandwich concept). What is abandoned is
the **three-segment arm decomposition**, not the file.

---

## 2. The existing render contract is authoritative

Verified facts in `origin/master`:

- `wearable_registry.json`: `player_frame.id = PLAYER_FRAME_A_STANDARD_CHIBI`, `canvas = [1056, 1408]`.
- Measured: `apprentice_p1.png`, `wooden_sword.png`, `apprentice_hair_front.png` are **all exactly
  1056 × 1408**. The full-canvas pre-aligned contract is real and already enforced in shipped assets.
- `js/rpg_wave2_wearable_renderer.js` composes with `position:absolute; inset:0; width:100%;
  height:100%; object-fit:contain` — identity transform, no per-item scaling.
- The front-mask sandwich already ships in production as `HAIR_FRONT_MASK`.
- `scalability.item_character_bespoke_redraws = 0` — one overlay serves all six characters.
- `production_invariants.body_frame_variants = 1`. **The schema already anticipated pose variants.**

Mandatory runtime invariants:

```
RENDER_SCALE=1
RENDER_TRANSLATE_X=0
RENDER_TRANSLATE_Y=0
RENDER_ROTATION=0
```

No per-item correction via scale hacks, viewport offsets, manual CSS transforms, or
screen-coordinate anchors. **If an asset requires transform correction to align:
`ASSET_ACCEPTANCE=FAIL`.**

---

## 3. Measured frame facts — use these, do not re-derive

Measured against `origin/master:assets/hero/characters/wave2_p1/apprentice_p1.png` (1056×1408).
Normalized `0..1`, origin top-left, matching `templates.json` `coordinate_system`.

| Fact | Normalized | Pixels |
|---|---|---|
| Right sleeve cuff — **SLANTED, not a horizontal line** | y 0.489 at x 0.735 → y 0.512 at x 0.648 | — |
| Right hand bounding box (skin) | x 0.692–0.789, y 0.472–0.596 | x 731–833, y 664–839 |
| **`MEASURED_PALM_CENTER_R`** (canonical **open**-hand skin centroid) | **(0.734, 0.542)** | (775, 763) |
| **`GRIP_ANCHOR_R`** | **`DERIVED_FROM_OWNER_ART` — see §3.3** | — |
| `SLEEVE_ENTRY_PRESERVATION_MASK` (§3.4) | ROI ∩ y ≤ 0.478 | x 676–840, y 641–673 |
| **`HAND_CHANGE_REGION_R`** (revised — see §3.1) | **x 0.640–0.795, y 0.455–0.600** | **x 676–840, y 641–845** |
| Body/leg silhouette below the hand (y 0.60–0.95) | x 0.35–0.65 | x 370–686 |
| Existing canonical sword length / width | 0.257 H / 0.294 W | 362 / 310 |
| Right `HAND_ZONE` (existing contract) | x 0.70–0.88, y 0.43–0.60 | x 739–929, y 605–845 |
| `SHOULDER_ZONE` (existing contract) | x 0.18–0.82, y 0.25–0.43 | — |
| `FACE_SAFE_ZONE` (existing contract) | x 0.40–0.60, y 0.085–0.205 | — |

### 3.1 Why the ROI is x 0.640–0.795, y 0.455–0.600 (revised)

An earlier draft used x 0.680–0.810, y 0.470–0.620 with a horizontal "cuff line" at y = 0.490.
**That was wrong, and it would have punched a hole in the sleeve.** Measured:

- **The cuff is slanted.** It runs from y ≈ 0.489 at x 0.735 down to y ≈ 0.512 at x 0.648. Any
  horizontal clear-line at y = 0.490 removes cuff fabric on the left side of the wrist and leaves
  a gap the owner's patch was never asked to fill.
- **The ROI must therefore contain the entire cuff**, so the patch re-supplies it. Top edge
  y = 0.455 sits above the cuff's highest point (0.489) in flat sleeve fabric.
- **Right and bottom edges are fully transparent** — verified: x ≥ 0.795 has zero opaque pixels
  over y 0.46–0.63; y ≥ 0.600 has zero opaque pixels over x 0.64–0.81. Those two borders cannot
  produce a seam at all.
- **Left edge x = 0.640 is the narrowest possible fabric crossing.** At x 0.640 the sleeve is
  opaque only over y 0.460–0.477 (25 px). At x 0.630 the tunic intrudes (58 rows, y 0.460–0.587);
  at x 0.650 the cuff intrudes (58 rows). 0.640 is the minimum.
- **Net: exactly one boundary segment crosses artwork** — the sleeve entering through the
  top-left corner (top edge crossing is x 0.639–0.719, 85 px wide at y 0.455). Every other border
  is in empty space.
- ROI area = 164 × 204 px = **2.25% of canvas**.
- ROI top (0.455) is well below `SHOULDER_ZONE`'s lower bound (0.43), so "shoulder untouched"
  holds automatically.

### 3.3 `GRIP_ANCHOR_R` is derived from the owner's art, not pre-guessed

**Correction of record.** An earlier draft declared `GRIP_ANCHOR_R = (0.734, 0.525)` and called it
the palm centre. That number was a **transcription error**: the underlying measurement was
`(0.7337, 0.5316)`, and 0.5316 was itself the centroid of *all* opaque pixels inside the right
`HAND_ZONE` rect — a figure contaminated by sleeve fabric above the cuff, not a palm centre at all.
Three distinct measurements exist and must never share a label:

| Measurement | Value | What it actually is |
|---|---|---|
| All-opaque centroid in `HAND_ZONE` | (0.734, 0.532) | hand **+ sleeve**; the contaminated figure behind the erroneous 0.525 |
| **`MEASURED_PALM_CENTER_R`** | **(0.734, 0.542)** | skin-only centroid of the whole open hand (palm + fingers) |
| Palm-only centroid (upper 45% of skin extent) | (0.721, 0.512) | palm excluding the splayed fingers |

**None of these is the grip channel**, because the canonical hand is *open* — the fist does not
exist yet. Pre-committing a grip coordinate measured from an open hand is exactly how a 24 px
sword misplacement would enter the renderer contract.

Therefore:

```
MEASURED_PALM_CENTER_R=(0.734,0.542)     STATUS=INFORMATIONAL_ART_TARGETING_HINT
GRIP_ANCHOR_R=DERIVED_FROM_OWNER_ART     STATUS=MEASURED_AFTER_DELIVERY
```

- The art brief gives the owner `MEASURED_PALM_CENTER_R` **only as a targeting hint** for roughly
  where the fist should sit. The owner is not obliged to hit it.
- Once `hand_grip_back` is delivered, Codex **measures** the grip channel centre from that art,
  writes it into `characters.apprentice.grip_anchor_r`, and reports it as
  `GRIP_ANCHOR_R_DERIVED=(x,y)`.
- `wooden_sword_held.png` placement and gate R6 are both evaluated against that **derived** value.
- No numeric grip anchor may be hard-coded in the renderer, tests, or templates ahead of delivery.

### 3.4 `SLEEVE_ENTRY_PRESERVATION_MASK` — and what it deliberately does **not** cover

```
SLEEVE_ENTRY_PRESERVATION_MASK = HAND_CHANGE_REGION_R ∩ (y <= 0.478)
                               = x 0.640–0.795, y 0.455–0.478
```

Verified against the canonical base: that band contains **exactly one** skin-chroma pixel
(a stray antialiasing sample at y 0.4787) out of ~5,400 — continuous hand skin begins at y 0.496.
The band is therefore fabric-or-transparent, and the boundary is set at **0.478** rather than at
the cuff (0.489) precisely so that **no hand pixel can ever fall inside the mask.** That is what
makes R15 safe against rejecting a correctly drawn compact fist.

**Naming correction.** This mask was previously called `SLEEVE_CUFF_PRESERVATION_MASK`, which
overstated its coverage. The measured cuff occupies **y 0.489–0.512** — entirely *below* the mask.
So this mask protects the **sleeve entry only**, not the cuff. Claiming otherwise would leave a
real gap: if the owner's patch tore a transparent hole through the cuff-to-wrist join, a
y ≤ 0.478 mask would not notice.

Protecting the cuff must not be done by skin-versus-cloth RGB classification — the tunic's cream
fabric (≈ rgb 230,200,165) is too close to the skin tone (≈ rgb 252,190,135) for that to be
reliable. It is covered instead by **R16, a pure alpha-topology gate** (see §9), which needs no
colour classification at all. The cuff's *appearance* remains owner visual authority (Q1–Q5).

### 3.5 `GRIP_AXIS` — how `GRIP_ANCHOR_R` is derived, deterministically

`GRIP_ANCHOR_R = DERIVED_FROM_OWNER_ART` is not a specification on its own. "Measure the grip
channel centre" has no unique mathematical answer on a transparent hand image — it could mean the
centroid of the gap between back and front fingers, the thumb-web centre, the palm opening centre,
or the grip-axis midpoint, and nothing fixes the blade direction. Left undefined, the coordinate
would end up eyeballed by a human or by Codex, which is the previous failure wearing a new label.

**Contract: the owner's hand delivery includes grip-axis metadata.** Two coordinate pairs in a
JSON sidecar — **not** a third piece of artwork, and **not** a skeletal pivot. This is ordinary
equipment-socket metadata.

```json
{
  "schema": "go-odyssey.hero-grip-axis.v1",
  "character": "apprentice",
  "frame": "PLAYER_FRAME_A_STANDARD_CHIBI",
  "coordinate_space": "normalized_0_to_1_of_1056x1408",
  "grip_axis_p1": [x1, y1],
  "grip_axis_p2": [x2, y2]
}
```

- `grip_axis_p1` = the **pommel-side** end of the grip channel (nearer the thumb web).
- `grip_axis_p2` = the **blade-side** end. The vector P1 → P2 therefore points along the blade.
  This ordering is normative; swapping the points inverts the sword.

Codex derives, with no judgement calls:

```
GRIP_ANCHOR_R      = midpoint(P1, P2)
GRIP_ORIENTATION_R = degrees(atan2(y2 - y1, x2 - x1))
```

Both are written into `characters.apprentice` and reported. The canonical sword carries its own
one-time axis measurement on its artwork (`equipment.wooden_sword.canonical_grip_axis`, two points
in the same space), and the held overlay is baked by mapping the sword's axis onto the character's
axis.

**The bake is translate + rotate ONLY. Never scale.** The sword must keep its canonical size, so
its opaque pixel count is preserved through the bake (gate R6b). If the character's grip-axis
length disagrees with the sword's grip length, that is an **art mismatch to report**, not something
to fix by resizing the sword — resizing to satisfy a number is exactly the class of correction that
produced the previous failure.

Runtime remains `scale=1 / translate=0 / rotation=0`. All placement is baked once into the asset.

### 3.2 The six characters do NOT share a hand position — measured

Measured palm-skin centroids on the six shipped `wave2_p1` bases (all 1056×1408):

| Character | Right-hand skin bbox | Palm centroid |
|---|---|---|
| `apprentice` | x 0.692–0.789, y 0.474–0.596 | (0.734, 0.542) |
| `paladin` | x 0.660–0.792, y 0.469–0.587 | (0.743, 0.539) |
| `constellation_apprentice` | x 0.709–0.796, y 0.488–0.583 | (0.755, 0.551) |
| `trail_apprentice` | x 0.659–0.753, y 0.498–0.646 | (0.696, 0.567) |
| `night_runner` | x 0.659–0.704, y 0.474–0.641 | (0.677, 0.527) |
| `mage` | x 0.680–0.711, y 0.500–0.503 | (0.700, 0.501) — **unreliable**, only a 4 px skin band found; hand is likely gloved or covered. Requires owner inspection. |

Spread across the five reliable characters: **x 0.677–0.755 (82 px), y 0.527–0.567 (93 px).**

**Consequence:** a single shared held-sword overlay placed at the apprentice anchor would be
misplaced by up to ~80 px on other characters — plainly visible. A common cross-character anchor is
therefore **NOT proven**, and must not be forced.

```
APPRENTICE_GRIP_ANCHOR_R=DERIVED_FROM_OWNER_GRIP_AXIS   STATUS=PENDING_ART   (§3.5)
COMMON_GRIP_ANCHOR_R=NONE                STATUS=SCALABILITY_TARGET_NOT_YET_PROVEN
```

Do not force any future character's anatomy to this coordinate. Visual anatomy outranks an
unproven anchor invariant. Store `grip_anchor_r` **per character** in the registry (the schema in
§7.1 already does).

**How `item_character_bespoke_redraws = 0` is still preserved:** the held sword stays **one
artwork**. Future characters get a Codex-derived *re-placement* of that same canonical sword art at
their own measured anchor (`wooden_sword_held_<character>.png`), never a redraw, and never a
runtime offset. `BESPOKE_SWORD_REDRAW=NO` remains true. Runtime transform stays identity.

---

## 4. DECISION REQUIRED: change the hand only, not the whole arm

This is the one point where this brief **deliberately diverges** from the reviewing proposal, which
asked to replace "right shoulder / arm / forearm / hand".

**Recommendation: V1 changes the HAND ONLY. The arm does not move.**

Grounds, all measured above:

1. **The seam already has a place to hide.** The sleeve cuff is a drawn garment edge at y = 0.490,
   and the hand lies entirely below it. `HAND_CHANGE_REGION_R`'s top edge (y = 0.470) crosses only
   fabric that a cuff line already bounds. A whole-arm ROI instead puts the boundary in the
   **shoulder**, which is the single highest-risk seam location and the only one no garment edge
   protects.
2. **The shoulder is shared with five other overlays.** `SHOULDER_ZONE` (y 0.25–0.43) is occupied
   by `cloth_robe`, `leather_armor`, `fox_pelt`, `dragon_scale`, `void_mantle`. Touching it puts
   all five torso overlays back in scope. Not touching it makes them pose-independent **by
   construction** — which resolves the reviewer's own correction #3 for free.
3. **The ROI is 1.9% of the canvas** (137 × 211 px) instead of roughly a quarter of the figure.
   Smaller ROI = smaller chance of visible drift, and a far smaller art ask.
4. **A lowered sword will not be occluded.** The hand sits at x 0.695–0.793; the body/leg
   silhouette below it spans only x 0.35–0.65. The hand is entirely clear of the body, so a sword
   hanging down from `GRIP_ANCHOR_R` occupies open space beside the figure.
5. **The sword fits the canvas.** It is 0.257 canvas-heights long; from a grip around y 0.54 the tip lands
   at roughly y 0.78 — clear air, above the feet line (~0.95), inside the frame.
6. **`MUST_NOT_REQUIRE_SHOULDER_REDESIGN` then holds trivially** instead of by hope.

Honest trade-off: a lowered sword reads as *carrying* rather than *brandishing*. For a child
apprentice standing in an equipment screen that is the natural, readable pose — but it is less
dynamic than a raised guard.

**If the owner wants a raised or forward sword, that is V2** — a larger ROI including the shoulder,
dispatched only after V1 has proven the pipeline end to end. Do not attempt it first. The cost of
V1 being wrong is one hand; the cost of V2 being wrong is the shoulder plus five torso overlays.

---

## 5. Scope

### IN SCOPE (V1)

- One character: `apprentice`.
- One item: `wooden_sword`.
- One named pose variant: right hand **open → closed grip**. **The arm does not move.**
- Two new render layers: `HELD_WEAPON`, `HAND_FRONT`.
- Registry / templates / visibility-matrix minimal schema extension, presentation-only.
- Renderer pose-variant resolution with fail-closed behaviour.
- Static presentation only.

### STOP LIST — do not produce, do not propose

- ❌ Raised-arm, bent-elbow, or combat pose (that is V2, §4).
- ❌ Any limb segmentation, joint, bone, pivot, or rig manifest.
- ❌ The `#1–#22` asset decomposition list. **Cancelled.**
- ❌ `cloth_robe` sleeve decomposition; `fox_pelt` mantle segmentation.
- ❌ The other five characters, the other four weapons.
- ❌ Animation, breathing, secondary motion, GIF evidence, loop sampling.
- ❌ Any Live2D / Spine / new renderer.
- ❌ Any change to Loadout / ownership / equip / commerce / combat authority. The server-side
  Loadout domain model is **correct and is not being revisited**.
- ❌ Renaming or restructuring unrelated canonical layers.

```
APP_PY_CHANGED=NO
DB_CHANGED=NO
PAYMENT_CHANGED=NO
SHOP_AUTHORITY_CHANGED=NO
LOADOUT_AUTHORITY_CHANGED=NO
ZONE3_CHANGED=NO
PRODUCTION_MUTATED=NO
NO_MERGE
NO_DEPLOY
```

---

## 6. Art authority — Codex may not draw

```
ART_GENERATION_AUTHORITY=NO
```

**Owner supplies the approved artwork. Codex composites and verifies only.**

Codex **may**: mask, alpha-normalize, composite into the canonical full-frame base, derive the held
sword placement, and verify pixel identity outside the ROI.

Codex **may not**: paint, generate, inpaint, upscale, restyle, or generatively reconstruct any
Hero pixel — inside or outside the ROI. If the supplied patch is non-conforming, **reject and
report**; do not repair it.

### Owner deliverable: ONE hand patch, supplied as TWO layers

This reuses the ART_04 / ART_05 split the owner already executed successfully in the 006 slice —
that technique was correct.

| Layer | Content |
|---|---|
| `hand_grip_back` | **The complete opaque content of `HAND_CHANGE_REGION_R`**: the sleeve fragment entering at the top-left, the full slanted cuff, the wrist, and the closed grip hand including the fingers that pass **behind** the sword grip. |
| `hand_grip_front` | **Only** the thumb and the fingers that pass **in front** of the sword grip. Nothing else. No sword pixels, ever. |
| `grip_axis.json` | Two coordinate pairs — `grip_axis_p1` (pommel side) and `grip_axis_p2` (blade side) — in normalized frame space (§3.5). **Metadata, not artwork**: it is what makes the grip socket deterministic instead of eyeballed. |

Both must be delivered on a transparent **1056 × 1408** canvas, positioned in place — not cropped,
not centred, not trimmed. The fist should sit roughly at `MEASURED_PALM_CENTER_R = (0.734, 0.542)`
— **a targeting hint, not a requirement** — with the grip channel oriented for a blade hanging
downward. The authoritative `GRIP_ANCHOR_R` is then *measured from the delivered art* (§3.3), so
the owner draws the most natural fist and the sword is placed to match it, never the reverse.

**Why `hand_grip_back` must cover the whole ROI, cuff included:** the cuff is slanted (§3.1), so
there is no horizontal line that separates "hand" from "sleeve". Rather than ask Codex to guess the
boundary with a colour heuristic — which would be fragile, since the tunic's cream fabric
(≈ rgb 230,200,165) is close to the skin tone (≈ rgb 252,190,135) — the ROI rectangle **is** the
contract: the owner supplies everything inside it, Codex clears all of it, and nothing has to be
classified. Painting the wrist, cuff and fist together is also how the art would naturally be drawn.

Art requirements: skin tone, line weight, outline colour and shading must match the canonical base
exactly — same hand, same character, different finger state. The sleeve fabric must be tonally
continuous with the canonical sleeve **across the ROI's top and left borders** (gate R14).
**No drawn cut face anywhere.** No closed outline across any edge that meets another layer. The
hand must read as a hand with skin, never as an empty glove or garment shell.

### Pose-base construction — CLEAR, then composite (mandatory)

The pose base must **NOT** be produced by alpha-compositing the new grip hand over the canonical
open hand. The canonical open hand is a spread palm; a closed fist is smaller, so old fingers
would remain visible around and below the new grip — a "fist with five extra fingers behind it".

Required deterministic construction, in this exact order:

1. Start from the exact bytes of `assets/hero/characters/wave2_p1/apprentice_p1.png`.
2. **Clear** — set to fully transparent — **every pixel inside `HAND_CHANGE_REGION_R`**
   (x 0.640–0.795, y 0.455–0.600). The whole rectangle, not a colour-selected subset, and not
   everything below a horizontal line.
3. Alpha-composite the owner-approved `hand_grip_back` into that region.
4. Every pixel **outside** the ROI stays untouched.

Runtime composition then remains `CHARACTER_BASE → HELD_WEAPON → HAND_FRONT`.

Because step 2 clears the entire rectangle, the result inside the ROI is *exactly* `hand_grip_back`
— which makes zero residual provable by direct comparison rather than by inspection (gates R2, R3,
R10). No third owner-drawn asset is required for this; clearing is deterministic Codex processing.

### Codex-derived assets (no new art)

| Output | Derivation |
|---|---|
| `assets/hero/characters/wave2_p1/apprentice_p1_weapon_grip.png` | The clear-then-composite construction above. |
| `assets/hero/equipment/wearables/masks/apprentice_p1_weapon_grip_hand_front.png` | `hand_grip_front` alpha-normalized onto the full frame. No opaque pixel outside the ROI. |
| `assets/hero/equipment/wearables/overlays/wooden_sword_held.png` | The **canonical** `wooden_sword.png` artwork, re-placed so its grip centre lands on the **derived** `GRIP_ANCHOR_R` (§3.3), blade downward. `CANONICAL_SWORD_VISUAL_REUSED=YES`, `BESPOKE_SWORD_REDRAW=NO`. Placement is baked once into the asset; runtime stays identity. |
| `characters.apprentice.grip_anchor_r` (registry value) | Measured from the delivered `hand_grip_back`, then written to the registry and reported as `GRIP_ANCHOR_R_DERIVED`. |

The existing waist-sheathed `wooden_sword.png` is **retained unchanged** for the stowed state.

---

## 7. Schema changes (presentation-only, additive)

### 7.1 `assets/hero/equipment/wearables/wearable_registry.json`

**a. `layer_order`** — insert two layers:

```
BACK_WEAPON, BACK_BODY, CHARACTER_BASE, TORSO_ARMOR, FRONT_BODY,
HELD_WEAPON, HAND_FRONT, FRONT_ACCESSORY, HEAD_FACE, HAIR_FRONT_MASK
```

`HELD_WEAPON` after `FRONT_BODY` so a held sword draws in front of torso armour and robes;
`HAND_FRONT` immediately after so fingers wrap the grip.

**b. `characters.apprentice`** — add **named** variants (not a numeric index). `base` is retained
unchanged for backward compatibility:

```json
"base": "/assets/hero/characters/wave2_p1/apprentice_p1.png",
"base_variants": {
  "DEFAULT":       "/assets/hero/characters/wave2_p1/apprentice_p1.png",
  "WEAPON_GRIP_R": "/assets/hero/characters/wave2_p1/apprentice_p1_weapon_grip.png"
},
"hand_front_mask_r": "/assets/hero/equipment/wearables/masks/apprentice_p1_weapon_grip_hand_front.png",
"measured_palm_center_r": [0.734, 0.542],
"grip_axis_r": null,
"grip_anchor_r": null,
"grip_orientation_r_deg": null,
"grip_anchor_status": "DERIVED_FROM_OWNER_GRIP_AXIS",
"hand_change_region_r": [0.640, 0.455, 0.795, 0.600],
"sleeve_entry_preservation_mask": [0.640, 0.455, 0.795, 0.478]
```

`grip_axis_r` is filled from the owner's `grip_axis.json`; `grip_anchor_r` and
`grip_orientation_r_deg` are then **computed** from it by the closed formula in §3.5 — never typed
in by hand, never eyeballed. All three ship as `null` and become `HARD_CONTRACT` for `apprentice`
only once written from real art. `measured_palm_center_r` is informational and must never be used
as the sword anchor.

**f. `equipment.wooden_sword`** also gains a one-time axis measurement on its own canonical
artwork, so the bake has something to map *from*:

```json
"canonical_grip_axis": [[x1, y1], [x2, y2]]
```

Same coordinate space, same P1 = pommel / P2 = blade ordering.

`grip_anchor_r` is stored **per character**, never globally. Add alongside it, at registry root:

```json
"common_grip_anchor_r": {
  "value": null,
  "status": "SCALABILITY_TARGET_NOT_YET_PROVEN",
  "note": "measured palm centroids differ by up to 82px x / 93px y across the six shipped bases; do not force future character anatomy to this coordinate"
}
```

The other five characters get **no** `base_variants` key. Their absence must resolve fail-closed (§8.3).

**c. `equipment.wooden_sword`** — add the held presentation alongside the retained waist fields.
Do not remove or alter existing fields:

```json
"held_presentation": {
  "template_id": "WEAPON_HELD",
  "layer": "HELD_WEAPON",
  "asset": "/assets/hero/equipment/wearables/overlays/wooden_sword_held.png",
  "requires_base_variant": "WEAPON_GRIP_R",
  "requires_hand_front": "hand_front_mask_r",
  "grip_anchor": null,
  "grip_anchor_source": "characters.<character>.grip_anchor_r (derived, §3.5)",
  "production_status": "OWNER_REVIEW_PENDING"
}
```

**d.** `player_frame.body_frame_variants`: `1` → `2`.
**e.** `scalability.body_frame_variants`: `1` → `2`. `item_character_bespoke_redraws` stays `0`.

### 7.2 `docs/planning/rpg_modular_2d_equipment/templates.json`

This file currently **forbids** what this task introduces. Amend it explicitly — do not bypass it.

- `zones.HAND_ZONE.default_rule` is currently `"never_fake_a_grip;
  use_carry_or_forearm_presentation"`. Replace with a rule permitting a grip **only** when backed
  by a declared pose variant, e.g. `"grip permitted only via a declared WEAPON_GRIP_R base variant
  plus HAND_FRONT sandwich; never a floating weapon over an open hand"`.
- `templates.WEAPON_WAIST.occlusion_rule` retains `no_hand_grip_pose` — correct for the sheathed
  template. **Leave it alone.**
- Add an 11th template `WEAPON_HELD`:
  - `anchor: "hand_right"`, `anchor_point: null` — resolved per character from the derived
    `grip_anchor_r` (§3.5); **no literal coordinate may be written into the template**
  - `bounding_box` containing the sword art; must not intersect `FACE_SAFE_ZONE` or `NECK_ZONE`
  - `front_back_layer: ["HELD_WEAPON", "HAND_FRONT"]`
  - `requires_base_variant: "WEAPON_GRIP_R"`
  - `occlusion_rule: "hand back in base variant, weapon above, thumb/fingers above weapon"`
  - `shoulder_limit: "MUST_NOT_REQUIRE_SHOULDER_REDESIGN"` — still holds; the arm does not move
- `production_invariants.body_frame_variants`: `1` → `2`
- `production_invariants.static_sword_mode`: extend `WAIST_SHEATHED` to record both modes, e.g.
  `"WAIST_SHEATHED | HAND_HELD_WHEN_POSE_VARIANT_DECLARED"`

### 7.3 `docs/planning/rpg_modular_2d_equipment/visibility_matrix.json`

Add the held presentation for `wooden_sword` using the existing `visibility_policy` vocabulary.
Until owner acceptance it must be `VISIBLE_IF_SUPPORTED`, **never** `VISIBLE_WEARABLE`. Update
`counts` consistently.

---

## 8. Renderer changes — `js/rpg_wave2_wearable_renderer.js`

Must remain presentation-only: consumes the server's equipped projection, writes no inventory,
equipment, selection, or combat state. No new renderer. `NEW_RENDERER_CREATED=NO`.

### 8.1 Pose-variant resolution

In `render()`, resolve the base in this precedence order:

1. `opts.baseAsset` — **must keep winning**, unchanged (existing callers and tests depend on it).
2. `WEAPON_GRIP_R` — **only if all four hold**: an equipped item declares `held_presentation`; and
   `character.base_variants.WEAPON_GRIP_R` exists; and
   `character[item.held_presentation.requires_hand_front]` exists; and the held overlay asset is declared.
3. `base_variants.DEFAULT`.
4. `character.base` (legacy field).

Resolution must key on the **semantic variant name**, never on an array index.

### 8.2 Layer append order

Extend the existing hardcoded sequence in `render()`:

```
appendEntries('BACK_WEAPON')
appendEntries('BACK_BODY')
appendLayer(resolvedBase, 'character-base')
appendEntries('TORSO_ARMOR')
appendEntries('FRONT_BODY')
appendHeldWeapon()        // NEW — only in WEAPON_GRIP_R state
appendHandFrontMask()     // NEW — only in WEAPON_GRIP_R state
appendEntries('FRONT_ACCESSORY')
appendEntries('HEAD_FACE')
appendHairFrontMask()     // existing, unchanged, stays last
```

`appendHandFrontMask()` follows the existing conditional-append pattern used for `HAIR_FRONT_MASK`.
Every new layer uses the same `rpg-wearable-layer` class and therefore the same identity transform.
**No new CSS transform, scale, offset, or per-item positioning may be introduced.**

### 8.3 Fail-closed rules (mandatory)

- If the `WEAPON_GRIP_R` variant is missing, the held weapon and hand-front layers **must not
  render at all**, and the item falls back to its existing `BACK_WEAPON` waist presentation. A
  weapon floating beside an open hand is a **worse** failure than a sheathed weapon and must be
  structurally impossible.
- If either the held overlay or the hand-front mask fails to load, drop the **entire** held
  presentation and fall back to waist. Never render a partial sandwich.
- `stage.dataset` must record the resolved state — `data-base-variant="WEAPON_GRIP_R"`,
  `data-held-weapon="wooden_sword"` — so QA asserts state without pixel guessing.
- `renderSafe()` error behaviour unchanged.

### 8.4 Slot semantics

`normalizeEquipped()` already dedupes one item per `slot`, and both presentations are slot `weapon`.
The held/waist choice is a **presentation** decision derived from variant availability. Do not add
a second weapon slot. Which weapon is equipped stays server authority.

---

## 9. Hard machine rejection gates

Run **before** integration. Any failure = reject the art and stop. **Fixing a failure by adjusting
a transform is forbidden** — that is exactly the defect that produced the previous failure.

| # | Check | Reject if |
|---|---|---|
| R1 | Dimensions of all deliverables and supplied layers | not exactly 1056 × 1408 |
| R2 | `apprentice_p1_weapon_grip.png` vs `apprentice_p1.png`, all pixels **outside** `HAND_CHANGE_REGION_R` | `OUTSIDE_HAND_CHANGE_REGION_PIXEL_DIFF_COUNT != 0` (RGBA) |
| R3 | Same file **inside** the ROI | identical to canonical base (nothing actually changed) |
| R4 | Required integration transform | anything but identity — any scale ≠ 1, translate ≠ 0, rotation ≠ 0 |
| R5 | `wooden_sword_held.png` opaque bbox | intersects `FACE_SAFE_ZONE` or `NECK_ZONE` |
| R6 | `wooden_sword_held.png` grip centre | further than 2% of canvas from `GRIP_ANCHOR_R` |
| R7 | `apprentice_p1_weapon_grip_hand_front.png` | contains any sword pixel, or any opaque pixel outside the ROI |
| R8 | Alpha | any deliverable has an opaque background, or a matte/halo fringe from white-background extraction |
| R9 | Canvas integrity | any deliverable cropped, trimmed, or re-centred rather than full-frame |
| **R10** | **`apprentice_p1_weapon_grip.png` inside the ROI vs `hand_grip_back` inside the ROI (RGBA)** | **not byte-identical.** Since the ROI was fully cleared, the composite inside it must equal the supplied **back** layer exactly. Formally: `POSE_BASE_RGBA_INSIDE_HAND_CHANGE_REGION_R == OWNER_HAND_GRIP_BACK_RGBA`. This is the authoritative residual-open-hand proof: `OLD_OPEN_HAND_RESIDUAL_PIXEL_COUNT = 0`. **`hand_grip_front` must NOT be baked into the pose base** — it stays a separate runtime layer, in front of the weapon (§8.2). If any front-finger pixel appears in the pose base, R10 fails |
| R11 | Closed outlined cut surface at shoulder / elbow / wrist | present |
| R12 | Hollow sleeve-tube presentation (visible inner tube surface) | present |
| R13 | `SHOULDER_ZONE` (y 0.25–0.43) pixels | modified — V1 must not touch the shoulder. `SHOULDER_ZONE_PIXEL_DIFF_COUNT != 0` |
| **R14a** | **ROI border alpha continuity — HARD GATE.** At the sleeve crossing (top edge x 0.639–0.719; left edge y 0.460–0.477): wherever the canonical base is opaque immediately *outside* the border, the patch must be opaque immediately *inside*, and wherever it is transparent outside, the patch must not bleed opaque inside | any alpha mismatch across the border. This is the structural test that the arm is not severed at the ROI edge |
| R14b | **ROI border RGB seam metric — DIAGNOSTIC ONLY.** Mean per-channel delta between the 1-px ring inside and outside the border, at the sleeve crossing | *nothing.* **Reported, not blocking.** A provisional reference value of 8/255 is recorded for observation. It may be promoted to a hard gate **only after** its tolerance has been calibrated against a known-good conforming patch — an uncalibrated RGB threshold would false-reject normal antialiasing and shading, which is the same "pretty number measuring the wrong thing" failure as the 50-loop gate |
| **R15** | **`R15_SLEEVE_ENTRY_PRESERVATION` — scoped to `SLEEVE_ENTRY_PRESERVATION_MASK` only** (ROI ∩ y ≤ 0.478, §3.4). Within that mask: `ORIGINAL_OPAQUE_AND_NEW_TRANSPARENT_COUNT` | `!= 0`. **This rule must NOT be applied to the whole `HAND_CHANGE_REGION_R`.** Canonical open-hand finger pixels *are expected and permitted to disappear* — a correct closed grip is more compact than a spread palm, so a broad "no opaque may become transparent" rule would reject correct art. This gate protects **the sleeve entry only**; it does not reach the cuff (y 0.489–0.512) — that is R16's job |
| **R16** | **`CUFF_TO_WRIST_ALPHA_CONTINUITY` — HARD GATE, pure alpha topology, no colour classification.** On the composed pose base, restricted to the ROI: **(a) connectivity** — flood-fill 4-connected through opaque pixels, seeded from the opaque pixels at the sleeve-entry border crossing (top edge x 0.639–0.719 at y 0.455; left edge y 0.460–0.477 at x 0.640); every opaque pixel in the ROI must belong to that single component. **(b) enclosed-hole detection** — flood-fill 4-connected through *transparent* pixels seeded from the ROI border; any transparent pixel not reached is enclosed by opaque pixels and is a hole | (a) any opaque pixel in the ROI is not connected to the sleeve entry → a detached fist / floating hand / stray island; or (b) `ENCLOSED_TRANSPARENT_HOLE_PIXEL_COUNT != 0` → a tear through the cuff-to-wrist join. This is what actually guarantees the arm is one continuous piece from sleeve through cuff to fist, and it needs no skin-versus-cloth judgement |
| **R6b** | **Sword bake preserves canonical size.** Opaque pixel count of `wooden_sword_held.png` vs canonical `wooden_sword.png` | differs by more than antialiasing tolerance (0.5%). Proves the bake was translate + rotate only, never scale (§3.5) |
| R17 | `grip_axis` metadata validity: both points inside the ROI; `midpoint(P1,P2)` falls on an opaque pixel of `hand_grip_back`; `\|P2 − P1\|` ≥ 1% of canvas diagonal | any condition fails. A degenerate or out-of-region axis makes `GRIP_ORIENTATION_R` numerically unstable |

**Load-bearing gates.** R2 + R13 make "different body, different scale, different character,
shoulder drift" mechanically impossible — the exact class of defect that reached the owner's screen
last time. R10 makes leftover open-hand fingers impossible. R14a makes a severed arm at the ROI
border impossible. R15 protects the sleeve entry **without** rejecting a correct fist. **R16 is the
one that actually guarantees a continuous arm** — sleeve → cuff → wrist → fist as a single opaque
component with no enclosed tear — and it does so on alpha topology alone, so no fragile
skin-versus-cloth colour test ever enters a release gate.

**Deliberately not blockers:** R14b (RGB seam average, pending calibration) and cuff *aesthetics*.
Hard-thresholding an RGB average before calibration is how gates start measuring their own
arithmetic instead of the picture. Whether the cuff *looks* right is owner visual authority
(§12), not a numeric gate. What the gates guarantee is structural: nothing is severed, nothing is
holed, nothing drifted, nothing was resized.

---

## 10. Tests

Additive. Do not weaken or delete existing tests.

`tests/test_w2_03_hero_full_frame_weapon_pose_variant_vertical_slice_007.py`
- R1–R17 as executable checks against the real asset bytes.
- **Explicitly asserts the pose base was built by clear-then-composite, not alpha-over**: inside
  the ROI, `apprentice_p1_weapon_grip.png` must equal `hand_grip_back` byte-for-byte (R10). A test
  fixture must additionally prove the naive alpha-over construction **fails** this assertion, so
  the gate is known to be live rather than vacuously true.
- Asserts `grip_anchor_r` is per-character and `common_grip_anchor_r.status ==
  "SCALABILITY_TARGET_NOT_YET_PROVEN"`.
- **Asserts R15 is scoped, not broad**: a fixture in which the fist correctly vacates canonical
  open-finger pixels **outside** `SLEEVE_ENTRY_PRESERVATION_MASK` must PASS, and a fixture that
  leaves a hole **inside** the mask must FAIL. Both directions must be exercised, so the scope fix
  is proven live rather than assumed.
- Asserts no literal grip-anchor coordinate is hard-coded in the renderer, templates, or tests;
  the value must be read from the registry after derivation.
- Asserts R14a (alpha continuity) blocks and R14b (RGB delta) does not.
- **R16 both directions**: a fixture with a transparent tear through the cuff-to-wrist join must
  FAIL; a fixture with a correct continuous arm must PASS; a fixture with a fist detached from the
  sleeve must FAIL on connectivity. Asserts the implementation contains **no** RGB/chroma test.
- **Grip derivation is a closed formula**: given a `grip_axis.json` fixture, the computed
  `grip_anchor_r` and `grip_orientation_r_deg` must equal `midpoint(P1,P2)` and
  `atan2(P2−P1)` exactly. Asserts no literal anchor constant exists in renderer, templates or tests.
- **R6b**: a fixture where the sword was scaled during the bake must FAIL.
- Registry schema: `layer_order` contains `HELD_WEAPON` and `HAND_FRONT` in the specified
  positions; `body_frame_variants == 2`; `item_character_bespoke_redraws == 0`;
  `base_variants` keyed by **name**; `wooden_sword.held_presentation` well-formed; existing waist
  fields unchanged.
- `templates.json` has `WEAPON_HELD`; revised `HAND_ZONE.default_rule` no longer forbids a
  variant-backed grip; `WEAPON_WAIST` untouched.
- The five characters without `base_variants` resolve to `DEFAULT` and emit **no** `HELD_WEAPON` /
  `HAND_FRONT` layer.
- Fail-closed: with the variant absent, the projection falls back to `BACK_WEAPON`.
- `opts.baseAsset` still wins over variant resolution.

`tests/e2e/run_w2_03_hero_full_frame_weapon_pose_variant_vertical_slice_007.mjs`
- Renders the real page at desktop, iPad landscape, iPad portrait, mobile portrait.
- Asserts DOM layer order matches §8.2 exactly.
- Asserts every `img.rpg-wearable-layer` has identical computed geometry — proves no per-layer
  transform crept in.
- Asserts `data-base-variant` / `data-held-weapon`.
- **Still PNGs only.** No GIFs, no loop sampling, no animation assertions.

Regression, must stay green:
`tests/test_rpg_modular_2d_equipment_contract.py`,
`tests/test_rpg_wave2_gate2_p3_wearable_production_runtime.py`,
`tests/test_a051_wooden_sword_equip_to_hero_projection_vertical_slice.py`,
`tests/test_a038_fresh_master_hero_equipment_inventory_final_integration_closure.py`,
`tests/test_b034_equipment_loadout_service.py`.

---

## 11. Evidence

`docs/evidence/w2_03_hero_full_frame_weapon_pose_variant_vertical_slice_007/`

Still PNGs only. Four viewports (desktop, iPad landscape, iPad portrait, mobile portrait) ×:

| State | Equipped | Gating? |
|---|---|---|
| `A_default` | nothing | yes |
| `B_held` | `wooden_sword` | yes |
| `C_closeup` | `wooden_sword`, cropped to shoulder / elbow / wrist / hand / grip | yes |
| `D_held_cloth` | `wooden_sword` + `cloth_robe` | **NO — observational only** |

State D costs zero new art and gives early warning of a torso-occlusion problem. It is
**explicitly not an acceptance criterion**, and this task **must not claim** `cloth_robe`
pose-compatibility either way. Record what is observed; that is all. Torso-armour compatibility is
a separate follow-up task.

Plus `browser-results.json` and `reject_conditions.json` recording measured R1–R17 per deliverable.

**No GIF. No 50-loop sampling.** If the still is wrong, animation cannot save it.

---

## 12. Acceptance gate

1. R1–R17 all PASS, recorded in `reject_conditions.json`.
2. All §10 tests PASS.
3. **Owner static visual acceptance.** Owner views the gating stills and answers:

```
Q1_CONTINUOUS_ARM           Does the arm read as one continuous, natural arm?
Q2_REALISTIC_GRIP           Does the hand genuinely appear to hold the sword?
Q3_CANONICAL_HERO_PRESERVED Does the Hero look exactly like canonical Apprentice outside the hand?
Q4_PRODUCTION_QUALITY       Does it look production quality?
Q5_NO_FLOATING_OVERLAY_LOOK Is there zero flat-overlay / floating-weapon impression?
```

All five must PASS. Engineering PASS counts do **not** substitute for step 3. Codex must report
these as `PENDING_OWNER` and must not self-certify them.

If step 3 fails, report it as an art-conformance failure and **stop** — do not tune transforms, do
not add layers, do not expand scope.

Only after step 3 passes may these be proposed, **each as its own task**:
- the remaining five characters' `WEAPON_GRIP_R` variants (same anchor, same ROI discipline),
- the remaining three sword-grip weapons (`iron_sword`, `fox_fang`, `celestial_blade`) — one
  overlay PNG each, reusing `GRIP_ANCHOR_R`,
- torso-armour pose compatibility (starting with one item),
- whole-stage idle breathing — a single CSS transform on `.rpg-wearable-stage`, so hero and
  equipment move together **by construction**; no articulated bones, no joint motion,
- V2 raised-arm pose (§4), if the owner wants a more dynamic silhouette,
- promotion from `VISIBLE_IF_SUPPORTED` to `VISIBLE_WEARABLE`.

---

## 13. Governance

- Branch from `origin/master` at `3dc517bfbf789da378f971b092980fb53e7a5e2f`; re-verify at dispatch.
  If master has moved, **stop and report** — do not silently rebase (a concurrent execution line
  merges PRs).
- Do not commit to `master` (ADR-0001). Merge and deploy are separate owner-gated operations; a
  merged PR is not a deployed PR.
- Do not modify `app.py`, `.env`, or any untracked artifact. Do not inspect secrets.
- Do not touch `sgf_engine` or vendored code.
- No destructive git operations.

---

## 14. Required report

```
TASK=W2_03_HERO_FULL_FRAME_WEAPON_POSE_VARIANT_VERTICAL_SLICE_007
BASE_HEAD=                          BASE_TREE=
HEAD=                               TREE=
BRANCH=                             REMOTE_HEAD=        REMOTE_MATCH=
EXPECTED_CANONICAL_HEAD_MATCHED=    (3dc517bfb… ; STOP if NO)

EXISTING_FULL_FRAME_RENDERER_REUSED=
NEW_RENDERER_CREATED=NO
ART_GENERATION_AUTHORITY=NO         CODEX_DREW_PIXELS=NO
POSE_VARIANT_MODEL=NAMED            VARIANT_NAMES=DEFAULT,WEAPON_GRIP_R
BODY_FRAME_VARIANTS_BEFORE=1        BODY_FRAME_VARIANTS_AFTER=2
BESPOKE_REDRAWS=0

POSE_BASE_PATH=
POSE_BASE_1056x1408=                POSE_BASE_TRUE_ALPHA=
POSE_BASE_CONSTRUCTION=CLEAR_ROI_THEN_COMPOSITE   (alpha-over-only is a FAIL)
HAND_CHANGE_REGION_R=x0.640-0.795,y0.455-0.600
OUTSIDE_HAND_CHANGE_REGION_PIXEL_DIFF_COUNT=      (must be 0)
SHOULDER_ZONE_PIXEL_DIFF_COUNT=                   (must be 0)
OLD_OPEN_HAND_RESIDUAL_PIXEL_COUNT=               (must be 0)
POSE_BASE_ROI_RGBA_EQUALS_OWNER_HAND_GRIP_BACK=   (must be YES)
HAND_FRONT_BAKED_INTO_POSE_BASE=NO                (YES is a FAIL)
R14a_BORDER_ALPHA_CONTINUITY=                     (HARD; must be PASS)
R14b_BORDER_RGB_MEAN_DELTA=                       (DIAGNOSTIC ONLY; not blocking)
R15_SLEEVE_ENTRY_MASK=x0.640-0.795,y0.455-0.478
R15_ORIGINAL_OPAQUE_AND_NEW_TRANSPARENT_COUNT=    (must be 0, within mask only)
R15_APPLIED_TO_WHOLE_ROI=NO                       (YES is a spec violation)
R15_CLAIMS_TO_COVER_CUFF=NO                       (it does not; cuff is R16)
R16_CUFF_TO_WRIST_ALPHA_CONTINUITY=               (HARD; must be PASS)
R16_ROI_OPAQUE_NOT_CONNECTED_TO_SLEEVE_ENTRY=     (must be 0)
R16_ENCLOSED_TRANSPARENT_HOLE_PIXEL_COUNT=        (must be 0)
R16_USED_RGB_CLASSIFICATION=NO                    (YES is a spec violation)
MEASURED_PALM_CENTER_R=(0.734,0.542)              STATUS=INFORMATIONAL
GRIP_AXIS_P1_R=                GRIP_AXIS_P2_R=    (from owner grip_axis.json)
GRIP_ANCHOR_R_DERIVED=                            (= midpoint(P1,P2), computed)
GRIP_ORIENTATION_R_DEG=                           (= atan2(P2-P1), computed)
GRIP_ANCHOR_DERIVATION=CLOSED_FORMULA             (EYEBALLED is a FAIL)
GRIP_ANCHOR_R_HARDCODED_AHEAD_OF_DELIVERY=NO
SWORD_BAKE_OPS=TRANSLATE_ROTATE_ONLY              (any scale is a FAIL)
R6b_SWORD_OPAQUE_PIXEL_COUNT_DELTA=               (must be <= 0.5%)
COMMON_GRIP_ANCHOR_R_STATUS=SCALABILITY_TARGET_NOT_YET_PROVEN
FORCED_FUTURE_CHARACTER_TO_COMMON_ANCHOR=NO
CHARACTER_SPECIFIC_DERIVED_HELD_OVERLAY=YES       (expected, not a defect)

HAND_FRONT_PATH=                    HAND_FRONT_1056x1408=    HAND_FRONT_TRUE_ALPHA=
HELD_SWORD_PATH=                    HELD_SWORD_1056x1408=    HELD_SWORD_TRUE_ALPHA=
CANONICAL_SWORD_VISUAL_REUSED=YES   BESPOKE_SWORD_REDRAW=NO

RUNTIME_TRANSFORM_IDENTITY=
WEAPON_HELD_PRESENTATION_CLASS=     WEAPON_WAIST_PRESERVED=
LAYER_ORDER=
FAIL_CLOSED_VERIFIED=               (missing variant -> waist fallback, no floating weapon)
REJECT_CONDITIONS=R1..R13 per file

DESKTOP_STATIC_EVIDENCE=            IPAD_LANDSCAPE_STATIC_EVIDENCE=
IPAD_PORTRAIT_STATIC_EVIDENCE=      MOBILE_PORTRAIT_STATIC_EVIDENCE=
GRIP_CLOSEUP_EVIDENCE=
CLOTH_ROBE_OBSERVATION=             (observational only; no compatibility claim)

TESTS=<n> passed / <n> failed       REGRESSION=<n> passed
Q1_CONTINUOUS_ARM=PENDING_OWNER
Q2_REALISTIC_GRIP=PENDING_OWNER
Q3_CANONICAL_HERO_PRESERVED=PENDING_OWNER
Q4_PRODUCTION_QUALITY=PENDING_OWNER
Q5_NO_FLOATING_OVERLAY_LOOK=PENDING_OWNER
OWNER_STATIC_VISUAL_ACCEPTANCE=PENDING

ANIMATION_IMPLEMENTED=NO
APP_PY_CHANGED=NO   DB_CHANGED=NO   ZONE3_CHANGED=NO
PRODUCTION_MUTATED=NO   MERGED=NO   DEPLOYED=NO

STATUS=PASS_W2_03_FULL_FRAME_WEAPON_POSE_VARIANT_READY_FOR_OWNER_STATIC_REVIEW
     | ART_REJECTED(<R#>)
     | STOP_CANONICAL_HEAD_MOVED
```

---

## Appendix A — 007 vs the abandoned direction

| | 005R2 / 006 (abandoned) | 007 (this task) |
|---|---|---|
| Arm | 3 rigid segments + 2 hand states | untouched, inside one illustration |
| Joints to hide | shoulder, elbow, wrist | **none** |
| Shoulder touched | yes | **no** (R13 enforces) |
| Hidden-geometry art required | 5 packages × 6 characters | **none** |
| Owner-drawn pieces for the slice | 22 planned | **1 hand, in 2 layers** |
| Codex-derived pieces | — | 3 |
| Integration transforms | 4 hand-tuned scales | **identity only** |
| Seam risk | 3 drawn cut faces | 1 ROI edge, hidden at an existing sleeve cuff |
| New weapon cost | segment art per weapon | 1 overlay PNG |
| Torso overlays in scope | 5 (shoulder shared) | **0** (shoulder untouched) |
| Gate | 50-loop geometry PASS | R1–R17 + **owner's eye on a still** |

## Appendix B — divergences from the reviewing proposal, and why

| Reviewer said | This brief | Reason |
|---|---|---|
| Replace right shoulder + arm + forearm + hand | **Hand only**; arm and shoulder untouched | Measured: cuff garment edge at y 0.490 already hides the ROI boundary; hand is clear of the body (x 0.695–0.793 vs body 0.35–0.65) so a lowered sword is unoccluded; shoulder is shared with 5 torso overlays. §4 |
| Owner supplies the weapon-arm patch | Owner supplies **one hand, as back + front layers** | Reuses the ART_04/ART_05 split already executed successfully in 006; the front-finger decision is an art decision, not a masking decision |
| Don't touch `cloth_robe` at all in slice 1 | No `cloth_robe` **art or claim**; one **non-gating** screenshot | Free early warning at zero art cost; compatibility is explicitly not asserted. §11 |
| `body_frame_variants=2` needs named variants | Adopted verbatim — `DEFAULT` / `WEAPON_GRIP_R`, resolution keyed on name, index resolution forbidden | Agreed |
| `ART_GENERATION_AUTHORITY=NO` | Adopted verbatim, plus explicit "reject, do not repair" | Agreed — this is the right guard |
| Owner eye is the highest gate | Adopted, with reviewer's Q1–Q5 verbatim and `PENDING_OWNER` mandated in the report | Agreed |
| `EXPECTED_CURRENT_CANONICAL_HEAD=3dc517bf…` | **Verified correct in-session** and retained, with a STOP rule if master moves | Confirmed: `origin/master` = `3dc517bfbf789da378f971b092980fb53e7a5e2f` |
| Amendment 1: clear the old open hand before compositing, don't alpha-over | **Adopted, and the clear rule corrected.** Clearing "everything in the ROI below the cuff" would have punched a hole in the sleeve, because the cuff is **slanted** (y 0.489 at x 0.735 → y 0.512 at x 0.648). Rule is now: clear the **entire ROI rectangle**; the owner's patch re-supplies sleeve fragment + cuff + fist. Gates R10 (residual = 0), R15 (no hole), R14 (no visible rectangle edge). ROI revised to x 0.640–0.795, y 0.455–0.600. §3.1, §6 |
| Final amendment 1: R15 as written would reject a correct fist | **Accepted — this was a real logic bug in my gate.** A closed grip is more compact than a spread palm, so open-hand finger pixels *must* be allowed to vanish. R15 is now scoped to `SLEEVE_ENTRY_PRESERVATION_MASK` (ROI ∩ y ≤ 0.478) only, with the boundary measured so no hand pixel can fall inside it. §3.4, R15 |
| Final amendment 2: two different apprentice Y values | **Accepted, and the cause found: 0.525 was my transcription error** of the measurement 0.5316 — which was itself a sleeve-contaminated figure, not a palm centre. Three measurements are now separately labelled, and `GRIP_ANCHOR_R` is `DERIVED_FROM_OWNER_ART` rather than pre-guessed, because the canonical hand is open and the fist does not exist yet. §3.3 |
| Final amendment 3: R10 must name the back layer | **Adopted verbatim.** R10 compares the pose base ROI against `hand_grip_back` only; baking `hand_grip_front` into the pose base is an explicit FAIL, since it must stay a runtime layer in front of the weapon |
| Preflight amendment 1: R15's mask sits above the cuff, so it cannot claim to preserve it | **Accepted — the name overstated the coverage.** Measured cuff is y 0.489–0.512; the mask is y ≤ 0.478. Renamed to `R15_SLEEVE_ENTRY_PRESERVATION` with the same safe cloth-only mask, and the cuff is now covered by **R16 `CUFF_TO_WRIST_ALPHA_CONTINUITY`** — pure alpha topology (single connected component from sleeve entry to fist, plus enclosed-hole detection), explicitly no skin/cloth RGB classification. Cuff aesthetics stay owner authority. §3.4, R16 |
| Preflight amendment 2: `DERIVED_FROM_OWNER_ART` needs an actual algorithm | **Accepted — without one it was an eyeballed coordinate with a better name.** Owner now supplies `grip_axis_p1` (pommel) / `grip_axis_p2` (blade) as JSON metadata, not artwork. Codex computes `GRIP_ANCHOR_R = midpoint(P1,P2)` and `GRIP_ORIENTATION_R = atan2(P2−P1)` by closed formula. Two points also fix the blade angle, which the brief previously left as prose ("hanging downward"). Bake is **translate + rotate only**, never scale (R6b), runtime stays identity. §3.5 |
| Final amendment 4: alpha continuity hard, RGB threshold not a blocker yet | **Adopted.** Split into R14a (hard, alpha) and R14b (diagnostic, RGB). An uncalibrated 8/255 average would false-reject antialiasing and shading — the same "measuring its own arithmetic" failure mode as the 50-loop gate |
| Amendment 2: common six-character anchor is not yet proven | **Adopted, and now empirically confirmed.** Measured palm centroids on all six shipped bases differ by up to 82 px x / 93 px y; `mage` could not even be measured reliably. `grip_anchor_r` is stored per character; `common_grip_anchor_r.status = SCALABILITY_TARGET_NOT_YET_PROVEN`. Reuse is preserved by Codex re-*placing* the one canonical sword artwork per character, never redrawing it. §3.2 |
