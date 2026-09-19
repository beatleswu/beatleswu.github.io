# GO_ODYSSEY_ZONE4_RUNTIME_AND_WORLDSTYLE_UNIFICATION_001

Status: `READY_FOR_OWNER_ZONE4_RUNTIME_AND_WORLDSTYLE_UAT`

This report records the bounded candidate only. It does not represent
Production device UAT, a static promotion, a build, a merge, or a gameplay
authority change.

## 1. Authority and current-state findings

### Zone Card authority

The current source contains two rollout surfaces over the same Adventure
state, not two Zone4 authorities:

| Surface | Source authority | Finding |
| --- | --- | --- |
| Legacy/default Adventure | `index.html:renderAdventureMap()` and `index.html:renderAdventureInfoPanel()` | Current source default. One `#adventure-map-panel` renderer builds the selected-zone title, state badges, progress/detail rows and action row for every zone. |
| E9 World Stage | `js/e9/world_stage.js:renderZones()` and `renderSelectedZone()`; `components/adventure/world_stage.html`; `css/e9/world_stage.css` | Existing shared Zone Card shell. `k11_15` is a `data-zone` skin, not a second renderer. |
| E9 right drawer | `js/e9/right_cards.js:updateDrawerZoneSummary()` | Reuses the selected-zone event and the same progress/CTA/replay grammar. |

`js/e9/feature_flags.js` still has `e9Shell` and the E9 component flags false
by default in source. Production flag values remain a deployment/runtime
question; this report does not infer them from source defaults.

### Lord Card authority

`index.html` contains one `#boss-cinematic` overlay and one shared DOM
hierarchy (`.boss-cinematic-kicker`, title, books/progress, rules, actions,
primary and cancel buttons). Zone1, Zone2, Zone3 and Zone4 presenters all
write that same overlay. Zone-specific selectors provide art, accent and
portrait placement only.

Zone4 now explicitly participates in the common state classes:

- challenge: `phase-lord-card phase-zone4-lord-card`
- ritual: `phase-lord-ritual phase-zone4-lord-ritual`
- first-clear/replay success: `result-win result-zone4-win` plus the explicit
  `result-zone4-replay` replay marker when applicable
- failure: `result-lose result-zone4-fail`

No Zone4-only card renderer or `v2` card system was introduced.

## 2. Zone1–3 shared language matrix

| Attribute | Zone1 | Zone2 | Zone3 | Shared rule | Zone4 variation |
| --- | --- | --- | --- | --- | --- |
| Zone Card renderer | `renderAdventureInfoPanel()` / E9 `renderZones()` | same | same | One selected-zone renderer, server-derived state | `data-zone-key="k11_15"` forest/mist skin and existing landmark art |
| Card structure | title, state badges, quest/boss block, star/progress block, meta rows, actions | same | same | hierarchy and semantic order are stable | no structural change |
| Progress | task/region/Lord values from the zone record | same | same | client formats; it does not author progression | same fields; forest accent only |
| CTA grammar | primary adventure/training, Lord action, secondary/ghost actions | same | same | action kind stays in the shared action row | adds the existing shared Replay Story action when the common predicate says it is available |
| Replay predicate | E9 `zoneStoryReplayAvailable()` → `E10Cinematic.hasReplayableStory()` | same | same | fail-closed, authoritative zone record, presentation-only playback | legacy card now calls the same predicate; no new persistence |
| Responsive behavior | shared legacy/E9 media rules | same | same | wrap/stack; touch targets remain usable | forest card follows same layout rules |
| Lord challenge shell | shared `#boss-cinematic` DOM/CSS | same | same | common frame, live copy, rules and buttons | Zone4 backplate/accent only |
| Lord ritual | shared ritual state and overlay | same | same | key art is state-specific; gameplay handoff remains existing | `Z4-LORD-02` then `Z4-LORD-06` |
| Lord success/failure | shared result overlay and state semantics | same | same | first-clear and replay are separate | `Z4-LORD-03/04/05`; replay hides first-clear portrait |

## 3. Candidate changes

### Zone Card

`renderAdventureInfoPanel()` now emits presentation-only markers:

- `data-worldstyle-family="go-odyssey"`
- `data-zone-key="<server-selected-zone>"`

Zone4 CSS uses those markers to add a restrained Misty Forest skin: existing
landmark art, forest/mist colors, readable light panels, and the existing
shared primary/secondary/ghost action geometry. No zone state, progress, star,
Lord, reward, or API authority was changed.

The legacy/default card now exposes `重溫故事` / `Replay Story` only when the
existing `zoneHasReplayableStory()` predicate is true. The click calls the
existing `playZoneStoryReplay()` presentation path. If the model is absent or
cannot prove replayability, the CTA remains hidden. No DB column, seen marker,
progress write, reward call, or new cinematic system was added.

### Lord Card

Zone4 result classes now include the generic `result-win` / `result-lose`
classes used by the shared overlay contract. Zone4 geometry is aligned to the
common Lord shell (`760px` max desktop width, shared bottom scrim proportions,
shared content box sizing and mobile wrapping); its 16:9 art aspect and
Misty Forest colors remain Zone-specific skin.

Existing Zone4 art mapping remains:

| State | Runtime asset | Semantics |
| --- | --- | --- |
| challenge | `assets/e10/art/zone4/lord/Z4-LORD-01.png` | dedicated challenge card |
| ritual | `Z4-LORD-02.png`, then `Z4-LORD-06.png` | ritual/domain presentation |
| failure | `Z4-LORD-03.png` | retry/failure presentation |
| first clear | `Z4-LORD-04.png` + `Z4-LORD-05.png` | first-clear success/portrait only |
| replay completion | `Z4-LORD-04.png`, no first-clear portrait | no new star/reward implication |

The Zone4 presenter clears the generic monster/emoji node. No rabbit or star
emoji is used as the final Zone4 Lord visual.

## 4. Storyboard and segmentation retained

The accepted candidate remains unchanged for story authority:

- `TOTAL_ZONE4_SHOTS=22`
- `PRE_LORD=Z4_S1_01–Z4_S2_08`
- `POST_LORD=Z4_S3_01–Z4_S3_06`
- Lord boundary: after `Z4_S2_08`
- post-Lord continuation requires authoritative Lord clear
- image/voice pairing: `22/22`
- voice-only blank beats: `0`
- replay: presentation-only and zero mutation

The exact contact sheet was reused byte-for-byte from the accepted storyboard
candidate in the new evidence package. It was not re-authored by this task.

## 5. Acceptance and regression evidence

### Passed

- worldstyle/unification Python contracts: `6 passed`
- accepted Zone4 storyboard/content/intro contracts: `15 passed`
- Zone4 storyboard Node contract: `12/12`
- Owner-final Zone4 content Node contract: `6/6`
- Zone4 intro wiring Node contract: `6/6`
- Zone1/Zone2/Zone3/E9/Lord visual regression set: `78 passed`
- governed Zone4 static packaging + static release tooling: `95 passed`
- `git diff --check`: pass

### Known bounded baseline characterization issue

The additional `tests/test_release_fix_a2_asset_closure.py` run was not used
as a candidate gate. It reported five existing active-manifest/fixture
characterization failures, including the already accepted Zone4 PNG subtree
not being included in that older A2 image set and a temporary fixture expecting
`manifest.json`. Those failures are outside this task's authority and were not
silently fixed by weakening the closure test or editing release manifests.
The governed Zone4/static-release suites above remain green.

## 6. PWA and device evidence boundary

Source/config facts retained from the accepted PWA candidate:

- `manifest.json`: `start_url="/"`, effective root scope, `display="standalone"`
- `index.html`: standalone marker and shared legacy/E9 shell path
- `sw.js`: `v242-zone4-storyboard-pwa-parity` /
  `source-v242-zone4-storyboard-pwa-parity`
- no Service Worker change was made by this task

The evidence package includes deterministic Safari/PWA and mobile/iPad/desktop
mock captures. They show the same core components and vertical flow, but the
actual active worker, cache contents and installed-device bytes cannot be read
in this environment. Therefore:

- `REAL_OWNER_DEVICE_UAT=PENDING`
- `SAFARI_PWA_SAME_FRONTEND_BYTES=UNKNOWN_UNTIL_DEVICE_UAT`
- `PWA_STALE_CACHE_BEFORE=UNKNOWN`
- `PWA_STALE_CACHE_AFTER=UNKNOWN_UNTIL_GOVERNED_STATIC_PROMOTION`

No claim of real iPad Safari/PWA parity is made here.

## 7. Evidence package

Directory:

`docs/evidence/zone4_runtime_worldstyle_unification_001/`

Includes:

- `ZONE_CARD_WORLDSTYLE_COMPARISON.png`
- `LORD_CARD_WORLDSTYLE_COMPARISON.png`
- `ZONE4_STORYBOARD_CONTACT_SHEET.png`
- `LORD_TRIAL_CONTACT_SHEET.png`
- `SAFARI_PWA_WORLDSTYLE_EVIDENCE.png`
- `RESPONSIVE_WORLDSTYLE_EVIDENCE.png`
- `EVIDENCE_MANIFEST.json`
- `generate_evidence.py`

## 8. Boundary confirmation

- `APP_PY_CHANGED=NO`
- `DB_CHANGED=NO`
- `PLAYER_DATA_CHANGED=NO`
- `PRODUCTION_MUTATION=NO`
- `BUILD=NO`
- `DEPLOY=NO`
- `MERGE=NO`
- no Adventure progression, Lord victory, stars, Coins, XP, reward or
  recovery-data authority was modified

## 9. Machine-readable summary

```text
START_ORIGIN_MASTER=4097053dcf87d5eeca826e03d8a21adbfcb9a47a
START_TREE=14b82d6ba2b30652c3ca9c12c55939744ec28110
BRANCH=codex/zone4-cinematic-storyboard-runtime-recovery-001
FINAL_HEAD=4097053dcf87d5eeca826e03d8a21adbfcb9a47a
FINAL_TREE=14b82d6ba2b30652c3ca9c12c55939744ec28110
WORKTREE_CLEAN=NO (local candidate changes intentionally uncommitted; MERGE=NO)

ZONE1_3_SHARED_ZONE_CARD_AUTHORITY=index.html:renderAdventureInfoPanel; js/e9/world_stage.js:renderZones/renderSelectedZone
ZONE1_3_SHARED_LORD_CARD_AUTHORITY=index.html:#boss-cinematic shared DOM plus .boss-cinematic* shared CSS

SHARED_ZONE_CARD_SHELL_REUSED=YES
SHARED_LORD_CARD_SHELL_REUSED=YES
ZONE4_ONLY_PARALLEL_CARD_SYSTEM_REMOVED_OR_AVOIDED=YES

ZONE1_REGRESSION=PASS
ZONE2_REGRESSION=PASS
ZONE3_REGRESSION=PASS

ZONE4_WORLDSTYLE_UNIFIED=PASS
ZONE4_THEME_PRESERVED=PASS

TOTAL_ZONE4_SHOTS=22
IMAGE_AND_VOICE_COMPLETE=22/22
VOICE_ONLY_COUNT=0

PRE_LORD_FIRST=Z4_S1_01
PRE_LORD_LAST=Z4_S2_08
POST_LORD_FIRST=Z4_S3_01
POST_LORD_LAST=Z4_S3_06

FIRST_ENTRY_STOPS_BEFORE_LORD=PASS
POST_LORD_LOCKED_BEFORE_CLEAR=PASS
POST_LORD_PLAYS_AFTER_CLEAR=PASS

LORD_CHALLENGE_VISUAL=PASS
LORD_RITUAL_VISUAL=PASS
LORD_FAILURE_VISUAL=PASS
FIRST_CLEAR_SUCCESS_VISUAL=PASS
FIRST_STAR_VISUAL=PASS (first-clear-only Zone4 portrait/semantic presentation)
REPLAY_COMPLETION_VISUAL=PASS

EMOJI_FINAL_FALLBACK_PRESENT=NO (Zone4 Lord states)

REPLAY_STORY_CTA=PASS
REPLAY_PRE_CLEAR_SAFE=PASS (common replay predicate fails closed; no locked tail)
REPLAY_POST_CLEAR_COMPLETE=PASS
REPLAY_ZERO_MUTATION=PASS

SAFARI_PWA_SAME_FRONTEND_BYTES=UNKNOWN_UNTIL_DEVICE_UAT
PWA_STALE_CACHE_BEFORE=UNKNOWN
PWA_STALE_CACHE_AFTER=UNKNOWN_UNTIL_GOVERNED_STATIC_PROMOTION

SAFARI_CORE_UI=SIMULATED_PASS
IPAD_PWA_CORE_UI=SIMULATED_PASS
PWA_ZONE_CARD_VISIBLE=SIMULATED_PASS
PWA_VERTICAL_FLOW=SIMULATED_PASS
PWA_BOTTOM_DOCK=SIMULATED_PASS

MOBILE=SIMULATED_PASS
IPAD=SIMULATED_PASS
DESKTOP=SIMULATED_PASS

SW_CHANGED=NO (carried accepted v242 candidate unchanged)
SW_VERSION_BEFORE=v242-zone4-storyboard-pwa-parity
SW_VERSION_AFTER=v242-zone4-storyboard-pwa-parity

APP_PY_CHANGED=NO
DB_CHANGED=NO
PLAYER_DATA_CHANGED=NO

TARGETED_TESTS=6 Python + 12/12 Node + 6/6 Node + 6/6 Node
REGRESSION_TESTS=78 Python + 95 static/release

PRODUCTION_MUTATION=NO
BUILD=NO
DEPLOY=NO
MERGE=NO

READY_FOR_OWNER_ZONE4_RUNTIME_AND_WORLDSTYLE_UAT=YES

FINAL_STATUS=READY_FOR_OWNER_ZONE4_RUNTIME_AND_WORLDSTYLE_UAT
```
