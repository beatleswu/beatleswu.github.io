# Teacher Admin MVP Implementation Map

## Scope

This planning note records a future implementation map for a teacher-admin MVP built
on the current SGF testing baseline.

This is docs-only groundwork.

This is not an implementation spec.

This PR does not implement teacher admin.

This PR does not add DB, API, backend, or frontend UI.

This PR does not add fake app.py.

This PR does not define final canonical puzzle identity.

This PR does not implement review queue.

This PR does not implement feedback queue.

This PR does not change SGF bytes.

This PR does not promote READY_IDS.

This PR does not activate GF-003.

This PR does not activate production overrides.

This PR does not change runtime behavior.

## Current Repo Implementation Surface

Bounded repo discovery was limited to `docs`, `tests`, and `sgf_engine`.

Within that bounded discovery scope:

- Flask or backend entrypoint: Absent in the allowed discovery surface
- frontend or template entrypoint: Absent in the allowed discovery surface
- WGo.js integration surface: Absent in the allowed discovery surface
- teacher admin route: Absent in the allowed discovery surface
- review queue route: Absent in the allowed discovery surface
- DB, schema, or migration structure: Absent in the allowed discovery surface
- API tests for teacher admin: Absent
- UI tests for teacher admin: Absent

The repository does contain planning and test baselines that describe future teacher
admin behavior, but no suitable implementation target was found in this branch for a
safe C-level teacher admin implementation.

Future C-level implementation must first define the app, API, and UI structure.

## MVP Implementation Slices

The future C-level teacher-admin MVP is best treated as separable slices:

1. Canonical puzzle identity contract
2. Teacher review queue data model
3. Teacher-facing status taxonomy
4. Visual SGF review card payload
5. WGo.js review UI integration
6. Feedback or issue-report ingestion
7. Teacher decision trace and audit log
8. Low-risk batch operations
9. High-risk confirmation flow
10. Permission and admin role model

These slices are future C-level implementation slices only.

This PR does not implement any slice.

## Recommended Technical Dependency Order

Recommended technical dependency order for future C-level work:

1. Canonical puzzle identity contract
2. Review queue read model
3. Visual SGF review card payload
4. Teacher-facing status taxonomy
5. Feedback issue report ingestion
6. Teacher decision trace
7. WGo.js review UI
8. Low-risk teacher actions
9. High-risk guarded actions
10. Permission model hardening

This is a technical dependency order, not a product priority commitment.

## C-Level Readiness Gates

The following still need explicit owner decisions before implementation:

- canonical puzzle identity contract
- teacher or admin permission model
- status transition rules
- review queue state model
- feedback issue reason list
- domain taxonomy initial tag list
- difficulty grouping final confirmation
- Visual SGF payload shape
- WGo.js integration target
- DB, API, and frontend implementation surface
- audit and owner decision trace model

## Canonical Identity Requirement

Any future review queue, feedback queue, or active admin review action must bind
strongly to a stable canonical puzzle identity.

The formal canonical puzzle identity definition remains a future C-level identity and
API decision.

The following are not canonical puzzle identity:

- `source_path`
- `fixture_path`
- `gold_fixture_id`
- temporary review item ID
- transient runtime state

This PR only allows `source_path`, `fixture_path`, and `gold_fixture_id` to appear as
traceability metadata.

No future review or feedback flow should treat file paths, fixture references, or
temporary runtime identifiers as canonical puzzle identity.

## Explicit Non-Actions

This PR does not implement teacher admin.

This PR does not add DB, API, backend, or frontend UI.

This PR does not add fake app.py.

This PR does not define final canonical puzzle identity.

This PR does not implement review queue.

This PR does not implement feedback queue.

This PR does not change SGF bytes.

This PR does not promote READY_IDS.

This PR does not activate GF-003.

This PR does not activate production overrides.

This PR does not change runtime behavior.
