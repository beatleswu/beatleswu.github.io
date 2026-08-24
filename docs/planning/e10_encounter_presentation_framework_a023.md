# E10 Encounter Presentation Framework V1 — A023

## Status

Presentation-only implementation and visual prototype. The framework is
cardinality-agnostic: the future Monster roster size is undecided and no
Monster-per-Zone or total-roster count is encoded.

## Current encounter truth

The current player-facing encounter surface is concentrated in `index.html`:

| Surface | Current DOM / route | Role | Authority boundary |
|---|---|---|---|
| Encounter arena | `#monster-panel` on `/` | Player/Monster identity, HP, feedback and SP | Existing server battle/review result |
| Adventure boss summary | `.adventure-quest-boss-card` on `/?adventure=1` | Zone context, readiness and entry CTA | Adventure bootstrap projection |
| Lord Trial cinematic | `#boss-cinematic` on `/` | Lord intro, ritual, result and progression context | Lord Trial controller; separate from generic Monsters |
| Feedback layers | `#impact-flash`, `#monster-speech`, victory/KO/result overlays | Transient hit, attack, defeat and reward/drop presentation slots | Committed result only |

`CURRENT_ENCOUNTER_SURFACE_COUNT=4`. There are three identifiable render
duplication points in the current arena: the `updateMonsterUI` path, the direct
`/api/monster/status` path, and the next-Monster write in the kill transition.
A023 decorates those existing paths; it does not replace their server or
settlement behavior.

The existing server taxonomy currently exposes `normal`, `chapter_boss`, and
`book_boss`. A023 normalizes those presentation inputs as Common, Elite, and
Battlefield Boss respectively. Rare remains available only when explicit
metadata supplies it. This is a presentation mapping, not a roster or combat
classification change.

## Framework hierarchy

`EncounterPresentationV1` provides one contract for:

- Common — solid standard frame, `✦` badge, standard HP and a short entrance.
- Rare — double frame, `◇` badge, restrained accent and a slightly longer
  entrance without a Boss interruption.
- Elite — reinforced geometry, `✧` badge, stronger silhouette emphasis and
  differentiated HP treatment while remaining an ordinary Monster settlement.
- Battlefield Boss — heavy frame, `✹` badge, largest generic treatment, a
  bounded warning beat and the strongest generic HP presentation.

The hierarchy is not color-only. Each tier has a visible text label, symbol,
frame geometry and scale/HP treatment. A player can distinguish the tier when
color is removed.

Lord Trial is deliberately not one of the generic presentation tiers. If a
Lord Trial authority marker reaches the normalizer, it is marked
`lord_trial` / `lordTrialAuthority=separate`; the existing Lord Trial
controller and cinematic remain authoritative.

## Scalable art-production model

The presentation contract is:

```text
Base Creature Family → Variant Identity → Encounter Presentation
```

Variants can change meaningful identity axes such as silhouette, gear,
headgear, accessory, posture, proportion, markings, texture, aura or carried
prop. A hue-only change is not accepted as a distinct Monster identity. The
model allows one base family to support controlled variants without requiring
fully unique art for every future Monster. A023 creates no Monster catalog and
locks no final count.

## HP, feedback and rewards

There is one reusable HP presentation framework. It consumes current/max HP
already projected by the server, clamps only for safe display, and shows a
neutral dash when values are unavailable. It never calculates damage.

Feedback states are reusable: correct attack, Monster damaged, future special
placeholder, Monster attack, and Monster defeated. The caller must identify a
committed result before applying a feedback class. Presentation cannot
authorize correctness, damage, defeat, reward or drop truth.

Reward/drop UI is limited to future visual slots for Coins, equipment,
appearance/cosmetic, and no-drop. F006/server settlement remains the source of
truth.

## Responsive contract

The review fixture is validated at desktop, iPad landscape, iPad portrait,
390px, 375px and 360px. Desktop uses a four-column hierarchy; tablet collapses
to two columns; portrait/mobile uses one bounded card column. The live battle
surface remains the existing player/Monster arrangement and receives only
presentation decoration. Art uses bounded `object-fit`/container sizing; the
framework does not assume a fixed Monster aspect ratio.

## Prototype evidence

`tests/e2e/fixtures/a023_encounter_presentation_showcase.html` renders four
review-only prototypes using existing Monster art. It is not a player route,
does not load APIs, and is not a runtime roster. The same shared JS/CSS module
is linked by the existing `index.html` encounter surface and by the fixture.

## Explicit boundary

`app.py`, schema/DB, Monster selector/roster, HP/attack/equipment effects,
drop/reward values, Spirit, Lord progression, payment, Service Worker and
Production are outside A023. No runtime asset files were added.
