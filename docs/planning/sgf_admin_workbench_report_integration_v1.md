# SGF Admin Workbench and Report Integration

## Purpose

The existing `/admin/sgf-answer-review` board-first queue remains the review
surface for SGF quality work. The additive Admin Workbench projection joins
player reports, findings made during authorized Admin play, and future corpus
scanner findings without creating a second inbox or changing SGF judging.

## Current primitives audited

- Player reports are still stored in `question_problem_reports` and
  `question_alternative_reports`; historical rows and their audit records are
  preserved.
- The existing `corpus_review_queue` and `/admin/sgf-answer-review` route remain
  available for the prior detector/review workflow and its responsive WGo.js
  board.
- Existing SGF repair batch and content-release tooling remains the only batch
  handoff/publish path. Workbench batches are evidence/manifests only and set
  `production_mutation=false`.

## Unified workbench contract

`sgf_workbench_reports` stores immutable observations. The semantic grouping key
binds question identity, record identity, issue class, candidate move, SGF/node
identity, and board evidence. Therefore identical reports aggregate while
different candidate moves or positions remain separate. Individual source rows
remain underneath each grouped item.

Sources are `PLAYER_REPORT`, `ADMIN_PLAY`, and `CORPUS_SCAN` (the latter is
schema-ready for a future scanner). Review statuses are `OPEN`, `STAGED`,
`NEEDS_RESEARCH`, `REJECTED`, `PUBLISHED`, and `STALE`.

Authorized Admin endpoints can create a staged repair for add-alternative,
remove-accepted, replace-answer, disable-broken, or needs-research actions.
Rejection and research resolution preserve the original evidence. The staged
record stores original/proposed state, reviewer, source item, baseline hash,
candidate move, reason, and provenance.

## Active play and retest

The shared report widget receives context from the real question runtimes on
Main Practice, Rating Test, Daily Challenge, Mistakes, and the friend-facing
shell. It submits only untrusted evidence; it never changes answers. The
Admin Workbench flag and repair endpoints are server-authorized and use the
existing review CSRF token.

An Admin can retest a staged item through the workbench endpoint. The response
contains both the production verdict (the existing resolver) and the staged
overlay verdict. The overlay is Admin-scoped and never enters player traffic,
Map Battle, Daily, Rating, Friend Challenge, or canonical content.

## Responsive parity and safety

The existing board-first page remains usable on desktop and iPad portrait or
landscape. Workbench controls use touch-safe targets and responsive grids; no
hover interaction is required. Desktop and iPad call the same server routes,
identities, aggregation, staging, and audit paths.

## Batch handoff

Multiple `STAGED` repairs can be turned into one deterministic, hash-addressed
workbench batch. The manifest explicitly hands off to
`tools/sgf_answer_repair_batch.py` and the merged PR318 content-release
validator. This Sprint does not apply `questions.json`, publish content, or
deploy Production; predecessor/rollback gates remain owned by the existing
release infrastructure.
