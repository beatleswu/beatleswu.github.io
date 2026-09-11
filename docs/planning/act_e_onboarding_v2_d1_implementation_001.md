# ACT-E Onboarding V2 D1 Implementation Handoff

Status: `IMPLEMENTED_DARK`

This handoff is based on the exact canonical tree
`e942e346854ba8397900ee5fa1d824cd2a38967a` at commit
`da531c6da0edabab3c025823ec1157e604d56498`.

The task-provided `BASE_HEAD` had one extra trailing `a` and was not a valid
Git object.  The 40-character commit above is the commit that resolves to the
task-provided `BASE_TREE`.  The dirty canonical checkout was not modified.

## Authority and enablement

The existing `wave2_onboarding_authority.py` remains the single V2 progression
authority.  It was reused unchanged.  Its durable state is dark and its normal
progression is driven only by authenticated calls plus persisted,
context-bound server facts.  Browser events, animation completion, reward
reveal, DOM state, and client correctness claims do not advance it.

No `app.py`, `index.html`, environment flag, rollout setting, production
database, or production reward/battle path was changed by this task.

## V2 schema contract

The existing additive candidate is
`migrations/w2_a1_onboarding_v1.py` (`SCHEMA_VERSION=w2_a1_onboarding_v1`,
`TABLE_NAME=wave2_onboarding_state_v1`).  It creates exactly:

| Column | Contract |
| --- | --- |
| `user_id` | integer primary key |
| `state_version` | non-negative integer, default `0`, CAS version |
| `status` | `NOT_ENROLLED`, `NOT_STARTED`, `IN_PROGRESS`, `SKIPPED`, or `COMPLETED` |
| `current_step` | `start`, `first_context`, `first_question`, `first_review`, `first_combat`, `first_reward`, `first_growth`, or `next_action` |
| `first_context_attempt_id` | nullable server-issued Zone 1 MapBattle attempt id |
| `updated_at` | non-null timestamp with `CURRENT_TIMESTAMP` default |

The candidate is additive, validates an existing table fail-closed, is
idempotent, supports a pure dry run, and never touches legacy tables or
catalog/reward/combat state.  It was not applied to Production.

## Legacy transition contract

`onboarding_v2_transition.py` is a boundary adapter, not a second V2
progression authority.

The legacy chain has Pet, daily, map quiz, curriculum, Hero, Bot, and Shop
tasks.  A stage number does not prove any V2 server-fact frontier, so an
incomplete stage is never projected to a guessed V2 step.  The complete
1--7 matrix is:

| Legacy state | Classification | V2 action | Compatibility |
| --- | --- | --- | --- |
| stage 1, `graduated=0` | `NO_SAFE_MAPPING` | none | `LEGACY_GRANDFATHERED` |
| stage 2, `graduated=0` | `NO_SAFE_MAPPING` | none | `LEGACY_GRANDFATHERED` |
| stage 3, `graduated=0` | `NO_SAFE_MAPPING` | none | `LEGACY_GRANDFATHERED` |
| stage 4, `graduated=0` | `NO_SAFE_MAPPING` | none | `LEGACY_GRANDFATHERED` |
| stage 5, `graduated=0` | `NO_SAFE_MAPPING` | none | `LEGACY_GRANDFATHERED` |
| stage 6, `graduated=0` | `NO_SAFE_MAPPING` | none | `LEGACY_GRANDFATHERED` |
| stage 7, `graduated=0` | `NO_SAFE_MAPPING` | none | `LEGACY_GRANDFATHERED` |
| any valid stage 1--7, `graduated=1` | `DETERMINISTIC_V2_MAPPING` | `COMPLETED`, `next_action`, version `1` | `V2` |

The Owner-provided live inventory of 188 rows and 24 graduated rows therefore
classifies as 24 deterministically mappable and 164 grandfathered, assuming
the stated stage range 1--7 for those rows.  No Production snapshot was read
or mutated by this implementation.

The transition adapter reads legacy state/tasks/events and never writes them.
It is read-only by default.  Terminal materialization requires
`dry_run=False`, `allow_write=True`, and the separate
`GO_PRODUCTION_DB_MIGRATION` gate.  A pre-existing V2 state is preserved; only
a pristine `NOT_ENROLLED/start` placeholder can be promoted to the terminal
projection.  An unmappable row is never reset, and a graduated row is never
restarted.

`legacy_compatibility_retirement_condition()` makes the grandfathering bound
explicit: compatibility is not eligible for future retirement until V2
cutover is enabled, a preservation audit passes, and the legacy state remains
retained.  The adapter reports that condition only; it does not delete or
mutate legacy history.

## New entrant policy

`new_entrant_cutover_contract()` returns `entry_path=V2` and
`legacy_allowed=false` only for a pending account with
`onboarding_required=1`, no `onboarding_path`, and no legacy state row.
Legacy Newbie Quest is not a new-entrant path after cutover.  Existing legacy
rows use the compatibility decision above; grandfathering is not a V2
overlay.

## Server-fact contract

The reused authority accepts this ordered fact contract:

`first_context` → `first_question` → `review_accepted` → `combat_result` →
`reward_granted` → `growth_committed` → `next_action`.

The first context is bound to the authenticated user's server-issued Zone 1
(`k26_30`) MapBattle attempt.  Review, combat victory, reward, and growth
facts must be committed and bound to that same attempt/question context.
Duplicate semantic facts are no-ops.  Stale `state_version` advancement is a
409 conflict.  Reward and combat results remain owned by their existing
settlement authorities; onboarding only reads their committed facts.

`resolve_onboarding_question_identity()` is the read-only Puzzle Identity
preflight.  When the identity registry is hot, only `EXACT` active bindings
are attachable.  Missing, cold, unavailable, retired, and ambiguous results
are explicit non-attachable outcomes; no UUID is minted or guessed.  The
client never supplies question correctness or identity authority.

## Frontend bridge

`js/e9/journey_onboarding_view.js` now accepts the optional event
`journey:onboarding-v2-projection` with this exact shape:

```js
{
  enabled: true,
  source: "server_onboarding_v2",
  projection: {
    state: {
      state_version: 4,
      status: "IN_PROGRESS",
      current_step: "first_context"
    }
  }
}
```

If the component has not mounted, App-A may queue the same object in
`window.__GO_JOURNEY_ONBOARDING_V2_PROJECTION_QUEUE__`.  The bridge requires
`enabled=true` and the exact source label, renders the server state as
presentation metadata, and maps V2 steps to existing E9 copy.  Disabled or
terminal projections remain hidden.  Skip/replay controls are hidden until
their server-owned request wiring exists; a DOM click and an E9 presentation
event cannot mutate V2 state.  There is no `fetch`, `localStorage`,
`sessionStorage`, cookie authority, reward logic, battle logic, or durable
client state in the bridge.

## ACT-A exact wiring request

ACT-A may import:

```python
from onboarding_v2_transition import (
    legacy_compatibility_retirement_condition,
    new_entrant_cutover_contract,
    resolve_onboarding_question_identity,
    transition_existing_legacy_user,
)
from wave2_onboarding_authority import (
    advance_from_server_fact,
    finish,
    get_state,
    resume,
    skip,
    start,
)
```

Add authenticated, dark-by-default routes:

* `GET /api/onboarding/v2` — return the server projection or an explicit
  disabled/not-enrolled result; never insert state on a read.
* `POST /api/onboarding/v2/start` — optional body
  `{ "expected_state_version": integer }`; call `start`.
* `POST /api/onboarding/v2/resume` — same CAS body; call `resume`.
* `POST /api/onboarding/v2/skip` — same CAS body; call `skip`.
* `POST /api/onboarding/v2/finish` — same CAS body; call `finish`.

Do not expose a browser-controlled generic fact endpoint.  Existing server
settlement code should first call `resolve_onboarding_question_identity()` for
the authoritative question reference and require its `allowed=true` result
when the identity registry is hot.  It should then call
`advance_from_server_fact()` on the same database connection after its
committed fact is available, passing only server-owned selectors (`attempt_id`,
authoritative question reference, and the expected CAS version).  The caller
must not pass client correctness, damage, reward, XP, or battle outcome as
authority.

Return the authority result shape unchanged: `ok`, `status_code`, `changed`,
`noop`, `reason`, and the `state` projection.  Map authentication to the
existing 401 boundary, malformed CAS input to 400, user mismatch to 403,
stale/out-of-order or missing committed fact to 409, and missing V2 schema to
503.  Keep one transaction: if a domain settlement and V2 advancement share a
connection, the settlement must be committed or rolled back together; the
authority starts/commits its own transaction only when no outer transaction is
active.

Before emitting the projection event, the shell must pass `enabled=false`
unless the separate Owner V2 enablement decision exists.  The current
`_retire_incomplete_legacy_newbie_quest()` behavior must be guarded during the
transition: it must not graduate a `NO_SAFE_MAPPING` user before the
grandfathered compatibility result is selected.  New accounts must never
create a legacy state row.

## ACT-F migration review request

Review the exact existing candidate
`migrations/w2_a1_onboarding_v1.py` and the transition adapter as a dark
package.  Verify:

* additive/idempotent creation and pure dry-run behavior;
* exact six-column V2 contract and checks above;
* no legacy table, catalog, reward, combat, or user-field mutation;
* Puzzle Identity catalog behavior is fail-closed for non-`EXACT` hot-state
  references and never creates catalog rows;
* the 24/164 classification against the Owner-provided 188-row inventory;
* repeated terminal materialization is a no-op and existing V2 progress wins;
* `GO_PRODUCTION_DB_MIGRATION` is a separate required gate.

`GO_PRODUCTION_DB_MIGRATION=NOT_GRANTED`: do not apply the migration or
materialize any Production transition.

## Validation

* `tests/test_act_e_onboarding_v2_d1.py` — 12 passed.
* `tests/e2e/run_act_e_onboarding_v2_bridge.mjs` — PASS, 18 checks.
* Existing V2 authority plus migration tests — 15 passed in the combined
  targeted run.
