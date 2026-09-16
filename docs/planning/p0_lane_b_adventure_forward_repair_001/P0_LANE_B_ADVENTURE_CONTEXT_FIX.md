# P0 Lane B — Adventure Context Fix

Task: `GO_ODYSSEY_P0_LANE_B_ADVENTURE_FORWARD_REPAIR_001`

## Decision

`global` is the existing supported Map Battle V1 mode for ordinary authenticated
Adventure players. No new mode, progression store, historical repair, or MBV1
retirement was introduced.

The repaired client boundary is:

```text
Adventure-originated question
  + Map Battle active       -> Map Battle answer path
  + Map Battle unavailable  -> visible fail-closed state; no answer transport
                              and no Practice fallback
```

## Verified source authority

- `map_battle_persistence.py:19-77` defines
  `E10_MAP_BATTLE_V1_MODE`, the supported values
  `off`, `dark`, `admin`, `allowlist`, `percentage`, `global`, and the
  fail-closed default `off`.
- `map_battle_runtime.py:1285-1302` defines eligibility. `global` returns
  `True` for an authenticated request; `admin` requires server-derived admin
  eligibility.
- `app.py:6154-6163` owns the canonical authentication boundary. All Map
  Battle V1 attempt, resume, nonce, and answer routes use `@login_required`.
- `app.py:15388-15405` performs server-side mode admission. Session claims do
  not replace the database admin status check in `admin` mode.
- `app.py:16147-16172`, `16727`, and `17264-17265` show that successful
  Map Battle progression uses the server-created `mbv1:<submission_id>` marker
  and `FIRST_PASS_ONLY`; public Practice remains `NEVER` for progression.

## Implemented static/client corrective

`index.html` now:

1. Defines `ADVENTURE_UNAVAILABLE_SOURCE_CONTEXT` as the explicit diagnostic
   value `adventure_unavailable`.
2. Makes `_currentReviewMetadata()` select that diagnostic context whenever an
   Adventure question exists but `_mapBattleV1IsActive()` is false.
3. Adds `adventure_failure_mode` for audit visibility.
4. Makes `_incident002ServerPracticeFlow()` require
   `!_isAdventureZonePractice()`. The server-judged Practice transport is now
   structurally unavailable to an Adventure question.
5. Adds `_blockAdventureProgression()` to set a blocked lifecycle state,
   disable battle actions, emit a runtime diagnostic, and show:
   `Adventure is temporarily unavailable; no answer fallback was used.`
6. Blocks `map_battle_v1_disabled`, `map_battle_mode_not_eligible`, missing
   adapter, generic runtime failure, and any post-prepare non-active state.
7. Adds a final guard in `submitSRS()` so a stale/invalid UI cannot submit the
   Adventure question through either Practice or legacy review.

Relevant implementation locations: `index.html:9266-9315`,
`9930-9950`, `10822-10836`, `10907-10964`, and `12519-12534`.

## Failure-state contract

| Adventure state | Client state | `source_context` if metadata is inspected | Answerable as Practice | Result |
|---|---|---|---:|---|
| Map Battle disabled | `disabled` | `adventure_unavailable` | NO | visible fail-closed unavailable state |
| Initialization pending | `pending` | `adventure_unavailable` | NO | no review request is allowed |
| Server mode not eligible | `blocked` with reason `map_battle_mode_not_eligible` | `adventure_unavailable` | NO | visible fail-closed unavailable state |
| Adapter/init/runtime failure | `blocked` | `adventure_unavailable` | NO | visible fail-closed unavailable state |
| Active Map Battle | `active` + valid state | server-created `mbv1:<submission_id>` on settlement | NO | authoritative Map Battle answer path |
| Ordinary Practice | no Adventure question pool | `practice` | YES | existing non-progress-bearing Practice path |

The `adventure_unavailable` value is diagnostic only. It is not the `mbv1:`
server marker, does not mint progression, and is not used to bypass any trusted
reader. If a diagnostic review request is ever observed, the public review
operation still uses `ProgressCreditPolicy.NEVER`; the repaired client does not
submit one in the first place.

## Entry coverage

Both known Adventure entry paths assign `_adventureActiveQuestions` before
calling `loadQuestion()`:

- same-page World Map entry: `index.html:14367-14399`;
- refresh/re-entry path: `index.html:22377`.

This makes the Adventure-origin predicate available before Map Battle
initialization and prevents a failed initialization from inheriting the generic
Practice default.

## Scope boundary

This corrective does not remove MBV1, replace the server progression writer,
alter rewards, migrate historical rows, or touch Production. A later task may
decouple/retire MBV1, but that is explicitly outside this P0 lane.

## Test evidence

- `tests/e2e/run_p0_lane_b_adventure_forward_repair.mjs` executes disabled,
  pending, not-eligible, and runtime-failure representations and asserts
  `practice === false` plus `adventure_unavailable`.
- `tests/test_p0_lane_b_adventure_forward_repair.py` locks the source boundary,
  trusted marker, duplicate guard, and Practice policy.
- `tests/test_map_battle_legacy_adapter.py` adds anonymous, target-mode admin,
  and global non-admin progression/replay cases.

Existing characterization expectations were not rewritten. The old defective
behavior is documented here as the rejected contract:

```text
Adventure + Map Battle failure -> answerable question -> Practice transport
```

That behavior is now permanently rejected by the client and regression tests.
