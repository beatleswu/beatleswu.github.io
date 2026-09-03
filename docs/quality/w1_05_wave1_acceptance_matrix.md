# W1_05 Wave 1 acceptance matrix

Task: `W1_05_QUALITY_WAVE1_ACCEPTANCE_HARNESS_001`

This is a bounded product-acceptance gate for the Wave 1 presentation and integration lanes. It is intentionally not a replacement for the repository's approximately 4,900-test suite.

The machine-readable source is [`tests/fixtures/w1_05_wave1_acceptance_matrix.json`](../../tests/fixtures/w1_05_wave1_acceptance_matrix.json). The focused executable selector is:

```text
pytest -q tests/test_w1_05_quality_wave1_acceptance_harness.py
```

## Acceptance matrix

| ID | Acceptance target | Bounded evidence | Physical-device status |
| --- | --- | --- | --- |
| `zone_presentation_presence` | World Stage has a real map frame, route, zone nodes, status, details, and CTA surfaces. | Static DOM/JS/CSS contract. | Not applicable. |
| `missing_fallback_asset_detection` | Referenced Wave 1 assets resolve to non-empty local files; component failure has a safe fallback. | Explicit path resolver and loader fallback checks, including a missing-file negative control. | Not applicable. |
| `zone_entry_clear_replay` | Zone selection/entry and cleared-zone replay remain on the existing lifecycle seams. | Source contract; the existing generic replay behavioral runner remains a separate focused gate. | Not applicable. |
| `boss_lord_distinction` | Normal training, first-clear Lord challenge, and cleared-zone Lord replay remain distinct actions. | CTA-state and routing contract. | Not applicable. |
| `replay_no_reward` | Replay presentation cannot mark progression, unlocks, seen state, or rewards. | Presentation-only source contract and replay-delta negative control. | Not applicable. |
| `onboarding_reachability` | First-stop Beginner Village copy, ordered steps, and a usable CTA are reachable from the world stage; the existing naming/tour entry remains present. | DOM spine and handoff contract. | Not applicable. |
| `mobile_portrait` | The 390x844 contract uses a single-column flow, inline zone details, and dock-safe bottom padding. | CSS breakpoint contract for a browser viewport. | Required later; viewport emulation is not physical-device acceptance. |
| `tablet_portrait` | The 768x1024 contract exposes the portrait detail action and keeps the supporting drawer bounded. | CSS breakpoint/orientation contract. | Required later; viewport emulation is not physical-device acceptance. |
| `tablet_landscape` | The 1024x768 contract keeps the stage and support regions in a bounded responsive grid/overlay. | CSS breakpoint/grid contract. | Required later; viewport emulation is not physical-device acceptance. |
| `reduced_motion` | Reduced-motion users receive no required animation or smooth-scroll dependency. | CSS and runtime preference contract. | Not applicable. |
| `keyboard_focus` | Zone nodes are keyboard-activatable, focus-visible, and hidden shell roots are removed from tab order. | DOM/JS/CSS focus contract. | Not applicable. |
| `audio_not_only_information` | Zone state, replay, progress, and cinematic context have visible text/status/control equivalents. | DOM and runtime text contract. | Not applicable. |
| `static_asset_manifest_validity` | PWA icons and the Wave 1 E10 UI/art package paths, sizes, and hashes are valid. | Bounded manifest/file validation. | Not applicable. |
| `shell_static_integration_readiness` | E9 slots, versioned component scripts/styles, and the static contract marker are wired. | Static integration contract. | Not applicable. |
| `physical_device_acceptance` | Owner reviews actual phone/tablet portrait and landscape behavior, touch targets, browser chrome, safe areas, and audio-disabled operation. | Manual Owner milestone only. | Required. |

The three viewport rows deliberately say “browser viewport/CSS contract only.” Passing them must never be reported as passing the physical-device milestone.

## Known debt classifications preserved

| Known item | Classification |
| --- | --- |
| A019 stale assertion | `TEST_STALE` |
| Jade Ring changed-path base-ref issue | `HARNESS_DEBT` |
| Whole-suite shared-state/setup errors | `HARNESS_DEBT / TEST_ISOLATION_SHARED_STATE` |

These are recorded for reporting and are not repaired by this task unless they prevent this focused selector from running.

## Gate boundary

This harness is read-only with respect to product/runtime behavior. It does not modify `app.py`, `index.html`, `i18n.js`, `sw.js`, runtime Economy, payment, or production state. It is static/source-level evidence for later static integration; it does not merge, deploy, mutate Production, or certify a physical device.
