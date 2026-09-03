# W1_05 Zone 3 vertical-slice acceptance matrix

Task: `W1_05_QUALITY_ZONE3_VERTICAL_SLICE_ACCEPTANCE_HARNESS_002`

Base: `ffcee93aab813d110ce0b70276a101a291f2b508`

This is the bounded Zone 3 extension of the accepted Wave 1 harness. It is a
focused product-acceptance and later static-integration gate, not a substitute
for the repository's whole test suite. The machine-readable source is
[`tests/fixtures/w1_05_zone3_vertical_slice_acceptance_matrix.json`](../../tests/fixtures/w1_05_zone3_vertical_slice_acceptance_matrix.json).

Run the focused selector with:

```text
pytest -q tests/test_w1_05_quality_zone3_vertical_slice_acceptance_harness.py
```

The candidate's canonical Zone 3 identity is:

| Field | Canonical value |
| --- | --- |
| Zone number | 3 |
| Runtime key | `k16_20` |
| English name | Goblin Cave |
| Traditional Chinese name | 哥布林洞穴 |
| Lord identity | `goblin_centurion` / Goblin Centurion |
| E055 normal roster | 13 explicit M-IDs, including protected `M022` presentation |

## Matrix

| ID | Acceptance target | Bounded evidence | Status boundary |
| --- | --- | --- | --- |
| `zone3_canonical_identity` | Zone key, names, landmark, and Lord identity agree across the world map, story metadata, and E055 authority. | Source and authority contract. | Automated evidence. |
| `zone3_visual_asset_presence` | Landmark, 13 server-bound normal-monster assets, and bilingual entry-film files are present, non-empty, and hash-stable. | Explicit fixture manifest and local hash probe. | Automated evidence. |
| `zone3_monster_roster_closure` | Every explicit E055 normal ID resolves to a Zone 3 binding; Lord identity is excluded from normal encounters. | Server-owned registry contract. | Automated evidence. |
| `zone3_encounter_hierarchy` | Common/Monster, Elite, Battlefield Boss, and Lord Trial presentation tiers remain distinct. | Tier and authority source contract. | Automated evidence. |
| `zone3_entry_cinematic` | Four bilingual Goblin Cave entry beats provide image, narration, caption, SFX cue, and a Start Training control. | Static cinematic source/assets contract. | Automated evidence. |
| `zone3_gameplay_handoff` | Entry hands off to the existing server-backed Map Battle route and the server-owned monster projection. | Frontend/backend seam contract. | Automated evidence; live gameplay later. |
| `zone3_onboarding_reachability` | The existing World Stage Beginner Village onboarding spine remains ordered, visible, and actionable before Zone 3. | DOM/CTA contract. | Automated evidence. |
| `zone3_lord_ready_presentation` | Server-backed availability reaches the generic Goblin Centurion Lord card without becoming a normal encounter. | Generic Lord-path contract. | Zone 3-specific art/audio remains candidate-gated. |
| `zone3_lord_trial` | Lord start issues the server-owned attempt/question queue and finish reads the authoritative result. | Generic Lord start/finish seam. | Owner runtime review later. |
| `zone3_authoritative_clear_reward` | Clear, progression, and first-clear reward presentation consume authoritative finish/reward results. | Source contract; no DB or Production writes. | Owner acceptance later. |
| `zone3_post_clear` | Post-victory replay boundary exists, but Zone 3 post-clear content is not falsely claimed present. | Fail-closed replay/source boundary. | Zone 3 content candidate gate. |
| `zone3_zone4_hook` | Screenplay and map topology preserve the forward Zone 3 → Zone 4 hook. | Planning/topology contract. | Runtime promotion is candidate-gated. |
| `zone3_replay_safety` | Replay cannot write clear, unlock, reward, progression, or player-position state. | Source contract, state-delta negative control, and bounded replay runner. | Automated evidence. |
| `zone3_bgm_ambience_candidate` | Zone 3 shot SFX cues are explicit; dedicated BGM/ambience slots remain visibly pending rather than borrowed or claimed complete. | Source boundary contract. | Zone 3 audio candidate gate. |
| `viewport_16_9` | 1920×1080 keeps the stage ratio and shell surfaces bounded. | Browser viewport/CSS contract only. | Physical device later. |
| `viewport_4_3` | 1024×768 enters the bounded tablet layout without relying on horizontal overflow. | Browser viewport/CSS contract only. | Physical device later. |
| `viewport_ipad_landscape` | 1180×820 keeps stage, drawer, and controls bounded. | Browser viewport/CSS contract only. | Physical device later. |
| `viewport_ipad_portrait` | 820×1180 preserves ordered content and reachable controls. | Browser viewport/CSS contract only. | Physical device later. |
| `viewport_mobile_portrait` | 390×844 uses the ordered single-column journey, inline details, and dock-safe spacing. | Browser viewport/CSS contract only. | Physical device later. |
| `reduced_motion` | Reduced-motion users do not depend on required animation or smooth scrolling. | CSS/runtime preference contract. | Automated evidence. |
| `keyboard_focus` | Zone controls are keyboard-activatable and focus-visible; hidden shell regions leave the tab order. | DOM/JS/CSS focus contract. | Automated evidence. |
| `critical_information_not_audio_only` | Zone identity, progress, state, replay, and cinematic context have visible equivalents. | DOM/text/status contract. | Automated evidence; Owner audio-disabled review later. |
| `missing_asset_fail_safe` | Missing/empty paths are detected and component loading exposes a bounded status fallback. | Explicit asset probe and missing-path negative control. | Automated evidence. |
| `static_manifest_validity` | Zone 3 fixture metadata and PWA manifest resolve valid non-empty files with stable declared bytes/hashes. | Bounded manifest/hash probe. | Automated evidence. |
| `shell_static_integration_readiness` | Existing E9 slots, versioned scripts/styles, and static contract marker remain wired. | Static integration and protected-file contract. | Automated evidence. |
| `physical_device_acceptance` | Owner checks actual iPad landscape/portrait and mobile portrait hardware, touch, safe areas, browser chrome, and audio-disabled behavior. | Manual Owner milestone. | Required later; never implied by viewport emulation. |

The matrix covers all requested dimensions: `FUNCTIONAL`, `CONTENT`,
`VISUAL`, `ANIMATION`, `SFX`, `BGM_AMBIENCE`, `ONBOARDING`, `UX`,
`RESPONSIVE`, `ACCESSIBILITY`, `INTEGRATION`, and `TEST`.

## Vertical-slice boundaries

The accepted path is intentionally split into evidence layers:

1. Zone identity, landmark, E055 roster/binding, bilingual entry package, and
   World Stage handoff are directly checked against current source and files.
2. The generic Lord path is checked for server-issued start state and
   authoritative finish/reward consumption. Zone 3 must not be represented as
   a separate reward or progression authority.
3. The generic cinematic model exposes `POST_CLEAR` and `POST_CLEAR_HOOK`
   ordering, but current later-zone content remains candidate-gated. The
   harness records this boundary so a future Zone 3 content candidate must add
   and prove those timelines instead of inheriting a silent Zone 1/2 claim.
4. Browser viewport cases are repeatable layout evidence only. They do not
   certify iPad or mobile hardware, touch behavior, safe areas, browser chrome,
   media policy, or physical audio behavior.

## Negative controls

The focused selector intentionally proves that it rejects:

- an injected missing Zone 3 static path;
- a replay state delta that increments protected reward/progression state; and
- a matrix row that incorrectly labels a browser viewport as physical-device
  acceptance.

## Known debt classifications preserved

| Known item | Classification |
| --- | --- |
| A019 stale assertion | `TEST_STALE` |
| Jade Ring changed-path base-ref issue | `HARNESS_DEBT` |
| Whole-suite shared-state/setup errors | `HARNESS_DEBT / TEST_ISOLATION_SHARED_STATE` |

These classifications are recorded for reporting and are not repaired by this
task. No merge, deploy, Production mutation, database migration, or runtime
product-file change is authorized here.
