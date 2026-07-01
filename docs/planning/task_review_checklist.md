# Task Book Review Checklist

## Purpose

This checklist encodes defect patterns found during Phase 12-19 planning reviews.
Apply it to every future Codex task book BEFORE execution.

Usage:
- Plan drafter (ChatGPT/Gemini): self-check the draft against every item before handoff.
- Executor (Codex): re-check items 1-8 during implementation; stop and report on any violation.
- Items marked [BLOCKER] mean: do not execute the task until fixed.

## 1. Context vs Global Confusion [BLOCKER]

Any rule keyed on a move, coordinate, string, or filename must answer:
"Is this property GLOBAL, or does it only hold in a specific puzzle/context?"

- A per-puzzle exception (e.g. B[sd]/T16 candidate-only in GF-003/431.sgf) must
  require puzzle identity context BEFORE the move/coordinate check.
- Never classify by coordinate or string match alone.
- Lesson source: Phase 19 v1 classified T16 as candidate-only on ALL puzzles,
  which would have polluted every future shadow observation.

## 2. Production Data Shape Assumptions [BLOCKER]

Every field a contract requires must exist in production TODAY, or be optional.

- Production puzzle identity is integer question_id (e.g. 29830). Canonical
  UUID v4 aliases do not exist in production yet.
- Contracts touching future production traffic must accept legacy_question_id
  and keep canonical_puzzle_id optional until an alias table exists.
- Ask: "Can the NEXT phase consume this contract with today's production data,
  without waiting for a migration?" If no, redesign.
- Lesson source: Phase 19 v1 required UUID v4, which would have thrown on
  every real production event.

## 3. Observational Paths Must Be Total Functions [BLOCKER]

Shadow / logging / observability code paths must NEVER raise.

- Malformed input becomes a classified error event (e.g. shadow_error),
  not an exception.
- Shadow events must be safe to drop.
- A raise inside an observation path is a production incident, not validation.

## 4. Missing Negative Tests

For every blocking or special-case rule, require the inverse test:

- "X is blocked in context A" requires the test "X is NOT blocked outside A".
- The absence of the inverse test usually marks the exact location of a
  design bug (see item 1).

## 5. Fact Pinning

Every hash, commit id, file path, count, or URL stated in a task book must be
verifiable by a preflight command in the task itself.

- Never trust a full commit hash that no command re-derives.
- Preflight must fail loudly (stop and report), never auto-repair.

## 6. Contract Drift Across Artifacts

When the same rule exists in more than one place (planning doc, test-local
helper, future production code):

- Name the single source of truth explicitly.
- When two artifacts each enumerate the same action/status set, their member
  counts must match; a silent +1 (e.g. an action list growing from 9 to 10
  between Phase 17 and Phase 18) is drift.

## 7. Classification Completeness and Flag Consistency

For enum-driven classifiers:

- Every input combination maps to an explicit classification.
- The fallback else-branch must be an explicit error class; note in the task
  book whether it is intended to be unreachable.
- Derived boolean flags must be consistent with the classification
  (if classification == gf003_safety_blocked then gf003_related must be True).
  Add an invariant test for each such pair.
- Distinguish "source could not judge" from "shadow cannot support":
  legacy_unknown is not shadow_unsupported.

## 8. Test Mechanics

- Parametrized tests must not require kwargs an action does not support.
- The pytest -k filter list must include ALL previous phase keywords;
  dropping one (e.g. phase12) silently removes regression coverage.
- Test-local modules test themselves; they prove contract consistency,
  not production behavior. Say so in the task book, not more.

## 9. Sequencing and Graduation

- Every spike must state how it graduates: import, port, or rewrite.
- A task book whose "next phase" depends on an unresolved external fact
  (e.g. production codebase location) must name that fact as an explicit
  open question and gate, not assume it.

## 10. Windows / Encoding (standing rules)

- UTF-8 without BOM, LF-only, CR=0, no hidden/bidi Unicode controls.
- Write files via Python pathlib with newline="
", never PowerShell
  redirection or here-string pipes.
- No git add . ; add files by explicit path only.

## Maintenance

When a new defect pattern is found in review, append it here in the same
format: rule, then lesson source. This file is the cheap, reusable form of
expensive review judgment. Keep it short enough to actually be read.
