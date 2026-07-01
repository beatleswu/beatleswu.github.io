# Phase 19A-B: SGF Engine Shadow Judging Readiness Spike

## Status

Accepted as Phase 19A-B test-local readiness baseline.

## Purpose

`sgf_engine` value is not fully realized until it observes real judging traffic.
Phase 19A-B prepares the contract for future no-user-impact shadow judging.
Shadow judging must never alter user-facing judgement in this phase.
Shadow judging must produce clean observation data, not global coordinate false positives.

## Scope

Phase 19A-B is test-local only.
Phase 19A-B creates shadow judging event and comparison classifier contracts.
Phase 19A-B does not add production hooks.
Phase 19A-B does not log production traffic.
Phase 19A-B does not modify Flask, app.py, API, frontend, DB, or runtime.

## Non-Goals

No production shadow judging hook.
No app.py change.
No Flask route change.
No API change.
No frontend change.
No DB schema.
No persistence.
No SQLAlchemy.
No Alembic.
No SGF byte change.
No READY_IDS change.
No override activation.
No GF-003 activation.
No judging semantics change.

## Shadow Judging Principle

Legacy/current production judgement remains authoritative.
SGF engine judgement is observational only in future shadow mode.
Shadow disagreement must create review evidence, not user-facing judgement.
Shadow events must be safe to drop.
Shadow classifier and event builder must not throw on malformed production-like input.
Shadow errors must be represented as shadow_error events.
Shadow events must not require production DB persistence in Phase 19A-B.

## Shadow Event Shape

Conceptual fields:

- `event_id`
- `legacy_question_id`
- `canonical_puzzle_id`
- `source_judgement`
- `shadow_judgement`
- `classification`
- `player_color`
- `player_move_sgf`
- `player_move_gtp_or_board_coordinate`
- `legacy_reason`
- `shadow_reason`
- `review_recommended`
- `owner_decision_required`
- `candidate_only_detected`
- `gf003_related`
- `invalid_identity`
- `legacy_unknown`
- `user_facing_judgement_changed`
- `created_at`

`legacy_question_id` is a production source locator, not canonical identity.
`canonical_puzzle_id` is optional in Phase 19A-B because production may not yet have UUID aliases.
`canonical_puzzle_id`, when present, must be valid UUID v4.
Invalid or missing identity must not crash shadow classification.
These are conceptual test-local fields only.
No production schema is created.
No production logging sink is added.

## Identity Compatibility

Future production traffic may initially provide legacy integer question_id only.
Phase 19A-B therefore accepts `legacy_question_id` and optional `canonical_puzzle_id`.
`legacy_question_id` must never become canonical puzzle identity.
`canonical_puzzle_id` remains the future stable ingestion-generated UUID v4.
If `canonical_puzzle_id` is missing, shadow event may still be created using `legacy_question_id`.
If `canonical_puzzle_id` is invalid, classify as `shadow_error` instead of raising.
If both `canonical_puzzle_id` and `legacy_question_id` are missing, classify as `shadow_error` instead of raising.

## Comparison Classifications

Required classifications:

- `agreement_accept`
- `agreement_reject`
- `legacy_accepts_shadow_rejects`
- `legacy_rejects_shadow_accepts`
- `legacy_accepts_shadow_off_tree`
- `legacy_rejects_shadow_off_tree`
- `shadow_unsupported`
- `shadow_error`
- `legacy_unknown`
- `candidate_only_blocked`
- `gf003_safety_blocked`

`legacy_accepts_shadow_rejects` and `legacy_rejects_shadow_accepts` require review.
`legacy_rejects_shadow_accepts` requires owner decision because shadow accepted something legacy rejected.
`legacy_unknown` is distinct from `shadow_unsupported`.
Off-tree classifications require review evidence, not automatic correction.
`candidate_only_blocked` must never promote candidate-only answers.
`gf003_safety_blocked` must preserve GF-003 disabled state.
Any `gf003_safety_blocked` event must have `gf003_related=True`.
`shadow_error` means the shadow path could not safely classify but must not affect user-facing judgement.

## GF-003 Candidate-Only Scope

`B[sd]` / `T16` is candidate-only only in GF-003 / 431.sgf context.
`T16` is not globally candidate-only.
`B[sd]` is not globally candidate-only.
GF-003 candidate-only detection requires puzzle identity context first.
In Phase 19A-B, `puzzle_id_hint == "GF-003"` is the only recognized GF-003 identity hint.
A shadow result of `gf003_blocked` is treated as GF-003-related safety evidence even if `puzzle_id_hint` is missing.
Future production integration may replace this with a `canonical_puzzle_id` or `legacy_question_id` alias table.
Non-GF-003 `B[sd]` / `T16` must be classified by normal legacy-vs-shadow comparison rules.

## Review Queue Integration Readiness

Shadow disagreement events are future inputs to review queue.
`review_recommended=True` means teacher/admin review is useful.
`owner_decision_required=True` means normal teacher UI cannot resolve the issue.
Phase 19A-B does not create review queue persistence or UI.

## Production Hook Boundary

Future production hook must be no-user-impact.
Future production hook must not change user-facing result.
Future production hook must be behind explicit owner authorization.
Future production hook is C-level and out of scope for Phase 19A-B.

## Production Codebase Location Open Question

Before Phase 20 production hook work, the production codebase location and deployment source of truth must be resolved.
Phase 19A-B does not inspect or modify production app.py, Dockerfile, deploy scripts, or any checkout outside D:\go-website-testing-baseline-clean.
If production Flask/app.py is not present in this checkout, Phase 20 must first establish where the hook can be implemented safely.

## GF-003 / Override Safety Boundary

GF-003 remains disabled.
`B[sd]` / `T16` remains candidate-only only for GF-003 context.
`B[sf]` / `T14` remains the canonical SGF answer for GF-003.
`gf003_safety_blocked` events are review evidence only, not activation.
No runtime override is added.
No production override is added.
`puzzle_variation_overrides.json` remains unchanged.
READY_IDS remains unchanged.
No SGF bytes are changed.
No judging semantics are changed.

## Future C-Level Trigger

Any of the following must be future owner-authorized C-level work:

- Production codebase location resolution for hook implementation.
- Production shadow judging hook.
- Production logging sink.
- DB persistence for shadow events.
- API endpoint for shadow event review.
- Frontend review UI for shadow events.
- Runtime sgf_engine integration into Flask.
- Changing user-facing judgement.
- Promoting READY_IDS.
- Enabling GF-003.
- Activating `B[sd]` / `T16`.
- Adding runtime override.
- Adding production override.
- Changing SGF bytes.
- Changing judging semantics.

## Test Contract

Phase 19A-B tests use test-local constants and pure Python classifiers.
Tests must not import production `sgf_engine`.
Tests must not import SQLAlchemy.
Tests must not import Alembic.
Tests must not connect to DB.
Tests must not create physical DB files.
Classifier and event builder must be total functions that return `shadow_error` or `legacy_unknown` instead of throwing on malformed production-like inputs.
Any `gf003_safety_blocked` classification must set `gf003_related=True`.
Future C-level production shadow hook must intentionally update this contract.
