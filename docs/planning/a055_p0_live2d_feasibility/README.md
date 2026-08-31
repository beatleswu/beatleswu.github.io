# A055-P0 Live2D single-character weapon-grip feasibility

This is an isolated feasibility spike for `apprentice` holding a
`wooden_sword`, with an `iron_sword` swap test. It is not a Go Odyssey runtime
integration and it does not replace Paper Doll or A054.

## Result at a glance

`LIVE2D_RUNTIME_EXECUTION=BLOCKED_BY_SDK_AVAILABILITY`

No authorized Live2D Cubism SDK/runtime, model binary, or package reference was
available in the repository or development environment. The committed viewer is
therefore a lawful `DESIGN_MOCKUP`, not an actual Live2D renderer. It uses the
existing apprentice identity art and existing functional sword SVGs as visual
references, plus an explicit semantic socket and grip geometry model. Every
viewer panel is labelled so that design evidence cannot be mistaken for runtime
output.

The spike still answers the maintainability question at the contract level:
both weapons attach to the same `RIGHT_HAND_WEAPON_SOCKET`, use the same
`apprentice_live2d_candidate_rig_v0` and the same right-hand rig, and vary only
weapon grip metadata. The separate closed-hand/forearm reference is used as a
layer reference; it is not claimed to be deformed by Cubism.

## Art decomposition and rig contract

The proposed drawable/deformer split is:

```text
ROOT
├─ LOWER_BODY
├─ TORSO
│  ├─ RIGHT_UPPER_ARM
│  │  └─ RIGHT_FOREARM
│  │     └─ RIGHT_HAND
│  │        └─ RIGHT_HAND_WEAPON_SOCKET
│  └─ LEFT_UPPER_ARM
│     └─ LEFT_FOREARM
│        └─ LEFT_HAND
└─ HEAD
   ├─ FACE
   ├─ EYES
   ├─ MOUTH
   ├─ HAIR_BACK
   └─ HAIR_FRONT
```

The minimum parameter set is recorded in [`rig-model.json`](rig-model.json):
body X/Y, right-arm, right-forearm, right-wrist, right-hand grip, breath, and
two eye-open parameters. The weapon transform is derived from the socket and
the weapon's `gripPoint`, `gripAxis`, and `gripWidth`; it is not an unexplained
absolute x/y placement.

The true-grip target is explicit: the handle passes into the palm, fingers
wrap the handle, the thumb opposes the fingers, and the forearm/wrist remains
continuous. The close-up in the viewer is a geometry mockup of that target and
is marked `NOT FINAL ART`.

## Viewer and evidence

Open [`demo/index.html`](demo/index.html) through a local static HTTP server.
The viewer provides:

- apprentice identity reference with the weapon as a separate attachment;
- wooden/iron swap using the same rig/socket IDs;
- parameter controls and a small mock idle/breathing loop;
- grip close-up, socket/axis diagram, and decomposition map;
- measured mock viewer first-render time, request bytes, and animation-loop FPS
  when the browser exposes them;
- responsive layouts for desktop, iPad landscape/portrait, and 390x844 mobile.

The viewer's `MODEL_BYTES` is intentionally `NOT_APPLICABLE`: no Cubism model
was available. Its JS and referenced texture bytes measure the design mock only.
`APPROX_MEMORY` is not fabricated when the browser does not expose a supported
memory API.

One local Chromium run on 2026-08-31 measured: `rig-model.json` **4,568 B**;
mock viewer JS **11,484 B**; referenced identity/grip/weapon art **560,475 B**
(about **547.3 KiB**); first render **3.9 ms** on the 390x844 run; mock
`requestAnimationFrame` loop **57.2 FPS**; and exposed JS heap **28.34 MB**.
The run reported no horizontal overflow at 1440x900, 1024x768, 768x1024, or
390x844. These values are machine/browser-run observations for this mock only,
not a Cubism runtime benchmark; the real model, texture atlas, official runtime
bytes, and physical-device performance remain unmeasured.

## Existing source references

The prototype references, without modifying, these existing assets:

- `assets/hero/characters/wave2_p1/apprentice_p1.webp`
- `assets/hero/equipment/functional/wooden_sword.svg`
- `assets/hero/equipment/functional/iron_sword.svg`
- `docs/planning/rpg_wave2_modular_2d_handheld_sword_prototype/pose_layers/apprentice_grip_forearm.png`

The last file is an existing Paper Doll grip/forearm reference. It is not a
Live2D mesh, and the old Paper Doll composite is not used as proof of a Live2D
runtime.

## Narrow engineering comparison

| Dimension | Live2D candidate | Current Paper Doll | A054 split-weapon Paper Doll |
| --- | --- | --- | --- |
| Grip quality potential | High if layers, mesh, and corrective poses are authored well | Limited by static pose/layer alignment | Better than overlay; still pose/raster based |
| Weapon swap | Low per weapon after socket contract | Asset/pose composition work | Universal weapon plus reusable grip pose |
| Character setup | High: decomposition, mesh, deformers, QA | Lower | Medium: reusable grip/forearm source |
| Weapon setup | Low to medium: grip metadata and art fit | Medium to high by pose | Low after universal asset contract |
| Motion capability | Strong | Limited | Limited/basic pose motion |
| Browser complexity | High: licensed runtime, model loading, WebGL/runtime QA | Low | Low to medium |
| Asset size | Model + atlas + runtime overhead | Raster assets | Raster assets plus matrices/review artifacts |
| Mobile risk | Unverified here; runtime/memory risk is real | Lower | Lower than a runtime rig |
| Maintenance burden | High, especially for 20 characters | Medium | Medium and bounded |
| Licensing/dependency burden | High and currently blocked | Existing project assets | Existing project assets |

The spike does not recommend migration. The correct next decision remains an
Owner comparison with A054: `KEEP_PAPER_DOLL`, `ADOPT_SPLIT_WEAPON_PAPER_DOLL`,
`RUN_LIVE2D_PHASE_1`, or `HYBRID_APPROACH`.

## 20-character scale estimate

Assumptions: one experienced artist/technical artist, a shared one-hand weapon
socket convention, no full facial-animation library, and no physics-heavy
clothing/hair in the first pass.

- Character decomposition: roughly **2–5 artist-days per character** → **40–100
  days** for 20 characters.
- Initial rig setup and per-character QA: **1–3 days each** → **20–60 days**.
- New one-hand weapon attachment after the socket contract: **0.25–1 day per
  weapon**, subject to grip correction art.
- Shared idle/motion parameter setup: **1–3 days initially**, then reuse with
  per-character tuning.
- Unique character exceptions: **0.5–3 days per exception**; unusual sleeves,
  hand poses, silhouettes, or two-hand weapons can exceed this range.

These are planning ranges, not measured production capacity. SDK licensing,
runtime integration, atlas optimization, browser QA, and mobile profiling are
additional work not represented by the art-day totals.

## Scope firewall

`APP_PY_CHANGED=NO`; no routes, server authority, combat, equipment authority,
flags, payment, schema, SW/static release, current Hero renderer, or Production
asset was changed. A054's worktree/branch was not modified. Owner visual
acceptance remains `NOT_GRANTED`.
