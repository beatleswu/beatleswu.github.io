# Incident 003I — packaging / provenance corrective

BASE=928f1d47f612e8b3463b19a69b3936e100bfe0c9 (Incident 003G candidate, tree ed891312ddde0dbd7c2760e2e6b1a16757a7218f)
SCOPE=packaging/provenance only. No SRS, Practice, Map Battle, Zone4, app.py domain, or schema change.

## The blocker

Independent review 003H returned BLOCKED_INCIDENT_003H_PACKAGING_OR_PROVENANCE for one deterministic reason: the two runtime modules Incident 003G introduces are packaged (Dockerfile, build manifest) but have no record in the governed runtime provenance manifest. Every one of the 106 existing records was fresh, so the existing suite passed — the omission was invisible because the validator's expected governed set was also still 106.

## What was independently verified before changing anything

Rather than trusting the review's table, each claim was re-derived from the candidate's own bytes and git objects:

| claim | verified |
|---|---|
| `srs_scheduling_core.py` sha256 `4fd9465f…0606a1`, 7115 bytes | matches candidate blob `8a22825e` exactly |
| `practice_answer_authority.py` sha256 `11f0eb39…76dba`, 16543 bytes | matches candidate blob `01da1aa5` exactly |
| first source commit `b1b17e77e` (Stage A) | exists, ancestor of candidate, byte-identical blob, subject/date confirmed |
| first source commit `12294e9ae` (Stage B) | exists, ancestor of candidate, byte-identical blob, subject/date confirmed |
| these are the *first* such commits | each path is touched by exactly one commit in the candidate's ancestry |

Scope was also re-derived rather than assumed. Diffing the candidate against canonical master shows 003G adds exactly two non-test runtime modules — the same two. Of the runtime files 003G *modifies*, every one that was already governed (`app.py`, `community_leaderboard_rewards.py`, `index.html`, `srs.js`, `js/game/review_transport.js`) already carries a fresh Stage B record. `adventure_progress_compatibility.py` and `srs_review_authority.py` have no record, but they had none on canonical master either — pre-existing governance scope, untouched here.

One nuance worth recording for the next reviewer: the runtime *dependency closure* is 160 modules while the governed manifest holds 108. Completeness here does **not** mean "closure ⊆ manifest" (126 closure modules legitimately have no record). The manifest's own schema note scopes it to recovered sources plus explicitly governed newly-authored modules, which is exactly why these two — and only these two — required entries.

## The change

Two files, 53 lines added, 0 removed. Purely additive.

1. `deploy/runtime-source-provenance.json` — two records appended, each with every field the manifest contract requires, computed from candidate bytes. All 106 pre-existing entries are byte-identical (verified by structural comparison, not eyeball); LF policy and trailing newline preserved.
2. `tests/deployment/test_runtime_dependency_provenance.py` — the governed expected set extended 106 → 108 via a new `INCIDENT_003G_GOVERNED_RUNTIME_PATHS` group, mirroring the existing `EQ_F_GOVERNED_RUNTIME_PATHS` convention, plus a matching exactness/disjointness test. This is what makes a future omission fail closed instead of passing on a stale count. Nothing was loosened, skipped, or xfailed.

## Verification

- Provenance + closure suites: 51 passed, 3 skipped, 0 failed.
- Independent completeness check: 0 runtime modules newly added by 003G absent from the manifest; 0 manifest entries pointing at a nonexistent file.
- Invariants re-derived at source: `srs_cards` writers = 1 (`srs_scheduling_core.py` only), SM-2 implementations = 1, app.py direct `srs_cards` SQL = 0.
- Targeted incident regression (Practice authority, Map Battle runtime/persistence/legacy adapter, Zone4 004/005, Lord behavioural gate): 124 passed, 3 skipped, 0 failed.
- Diff review: no product source, no Zone4 asset, no `.py`/`.js`/`.html` runtime file touched outside `tests/`.

## One pre-existing failure, classified

`tests/test_e10_backend_review_service_v1a2.py::test_update_monster_and_quests_body_only_adds_retaliation_mitigation` fails on this branch. It is **not** caused by this corrective and **not** caused by 003G:

- It fails identically on the untouched 003G base (928f1d47f, clean worktree).
- It fails identically on pristine canonical master (5442904c5) — confirmed by execution, not inference.
- The test compares app.py's `_update_monster_and_quests` against a baseline frozen at `554a86f5c` (2026-08-17). Master's signature has since gained `settlement_id` / `battlefield_shadow_events` / `battlefield_catalog_profile`; the candidate's copy of that function is byte-identical to master's. The drift is canonical's, against a stale frozen baseline, in battlefield/settlement code unrelated to this incident.

This is a separate pre-existing characterization-baseline defect and is deliberately left alone, consistent with the known order-dependent test-infrastructure defects that remain their own tasks.

## Boundaries

MERGE=NO · DEPLOY=NO · PRODUCTION_MUTATION=NO · DB_MIGRATION=NO · SCHEMA_CHANGED=NO · ZONE4_OWNER_APPROVED_CONTENT_CHANGED=NO

A PASS here does not authorize merge. The corrected candidate still requires final independent admission verification before it can return to the Owner GO_MERGE decision point.
