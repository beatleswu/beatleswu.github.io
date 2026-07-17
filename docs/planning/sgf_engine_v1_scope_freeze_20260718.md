# SGF Engine V1 Scope Freeze

Status: **FROZEN FOR INDEPENDENT ROLLOUT AUDIT**

Date: 2026-07-18

SGF Engine V1 is the Shadow Observation Foundation completed in PR #156. It
does not change player-facing judgement and does not make Shadow authoritative.

## V1 included scope

SGF Engine V1 includes:

- the `shadow-v4` observation envelope;
- the existing eligible Shadow entrypoints;
- Legacy-authoritative judging;
- bounded JSONL storage;
- rotation, retention, and locking;
- dashboard budgets and truncation metadata;
- Candidate Class A/B classification;
- fail-closed Shadow configuration;
- governed enable, disable, rollback, and kill-switch drill operations;
- unchanged player-facing judgement; and
- GF-003 disabled.

SGF Engine V1 does not require canonical puzzle identity. Until V1.1 is
implemented, every event must honestly retain:

```text
canonical_puzzle_id = null
invalid_identity = true
gf003_related = false
```

No V1 rollout gate may infer identity from legacy `question_id`,
`record_index`, route, mode, category, filename, SGF path, ordering, or a
content fingerprint.

## V1.1 deferred scope

SGF Engine V1.1 — Immutable Puzzle Identity Foundation separately owns:

- `source_record_uuid`;
- writer locking and generation compare-and-swap;
- the lifecycle ledger;
- frozen genesis bootstrap;
- historical identity policy; and
- Shadow UUID propagation.

No V1 change may implement, restore, package, migrate, backfill, or partially
simulate that deferred work. PR #157 identity code remains reverted by PR
#158 and is not a V1 rollout prerequisite.

## V2 boundary

V2 remains blocked on its own readiness requirements, including the later
Identity work and the unresolved leaf-semantics decision. A successful V1
Shadow rollout, drill, or observation window does not satisfy either gate and
does not authorize authoritative judging.
