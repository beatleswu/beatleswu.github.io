SGF_ENGINE_REENTRY_AUDIT_001: READY_FOR_OWNER_REVIEW

# SGF Engine Re-entry Audit v1

Document: `SGF-ENGINE-REENTRY-AUDIT-001`
Scope: current-state recovery, wrong-answer audit architecture, and human repair workflow
Owner: GO / Codex SGF Engine workstream
Audit date: 2026-08-09 (Asia/Taipei)
Status: read-only audit complete; implementation of the next Sprint is not started

## 1. Executive Summary

The current repository contains a real, provenance-recorded `sgf_engine` vendor, but it is not yet the single live judging implementation for every product answer route.

The evidence-backed current split is:

- `sgf_engine.parser` and `sgf_engine.core` are the operational engine used by Shadow observation and by offline tests/tools.
- Rating Test has a server-side authoritative verifier in `app.py` (`_rt_server_verify` -> `_rt_parse_answer_tree` -> `_rt_replay`). It replays the application’s own adapter, then checks the persistent `accepted_moves` field, then a single precomputed `katago_best_move` tolerance.
- `sgf_engine.engine.apply_move` is not imported by the current application rating-test route and is not the common authority for daily challenge, friend challenge, or SRS. Daily and friend challenge currently persist a client-supplied boolean; SRS persists a client-supplied grade. Therefore there is no defensible claim that one SGF Engine judge currently governs all routes.
- Shadow is explicitly observation-only, fail-closed, and must not become a fallback. It uses `sgf_engine` parser/core with no override input and emits `user_facing_judgement_changed=false`.
- The clean `origin/master` snapshot does not contain `questions.json`, `.sgf` fixtures, historical SGF tests, or an active `puzzle_variation_overrides.json`. The canonical dirty worktree has a user-owned `questions.json`, but it was only read for inventory and was not copied or changed.
- The user-owned corpus snapshot contains 42,804 records, 42,793 distinct legacy IDs, 11 duplicate-ID groups, 404 duplicate-content groups, 163 strict parser failures, 2,425 SGFs with multiple root answer branches, and 60 parseable SGFs with no answer child. It contains 19,502 `katago_best_move` values and zero `accepted_moves` values in the inspected snapshot.
- Historical GF-003 evidence is a disabled candidate-only workflow: canonical `B[sf]` / Black T14, candidate `B[sd]` / Black T16, override disabled, automatic application false. No GF-003 runtime activation is present or authorized.
- A wrong-answer detector is feasible as an offline, read-only, evidence-producing tool. It is not safe to make it authoritative until identity, leaf semantics, multiple-response semantics, data provenance, and route integration are owner-resolved.
- The existing Admin review queue is sufficient for intake, context, read-only board preview, decision logging, and staleness metadata. It is not a safe SGF editor. Human repair should produce a review packet and a governed repair proposal; it must never directly mutate SGF bytes from the Admin page.

The immediate conclusion is `READY_FOR_OWNER_REVIEW`, not “ready to merge, deploy, or change judging.”

## 2. Current Judging Architecture

### 2.1 Authority map

| Surface | Current implementation | Authority status | Evidence |
|---|---|---|---|
| SGF parse/tree model | `sgf_engine.parser.sgf_parser`, `core.tree`, `core.matcher`, `core.autoreply` | Engine implementation used by Shadow/offline code | `sgf_engine/parser/sgf_parser.py:95`, `sgf_engine/core/*.py` |
| SGF orchestration | `sgf_engine.engine.apply_move` | Present as a reusable engine API; not the common live route authority | `sgf_engine/engine/engine.py:45`; no current `app.py` import of `apply_move` |
| Rating Test | `app._rt_server_verify` | Current server authority for Rating Test | `app.py:20821`, `app.py:21686` |
| Daily Challenge | `data.get('correct')` is persisted | Client-supplied result; not SGF-authoritative | `app.py:12053-12059` |
| Friend Challenge | `data.get('correct')` is persisted | Client-supplied result; not SGF-authoritative | `app.py:15493-15500` |
| SRS review | Client `grade` drives `_srs_review_operation` | Spaced-repetition operation, not an SGF judge | `app.py:10367`, `app.py:10378` |
| Shadow | `shadow_judging.observe_*` | Observation-only; never changes player result | `shadow_judging.py:404`, `shadow_judging.py:478`, `shadow_judging.py:611` |

### 2.2 Rating Test root, deeper, multiple, and override behavior

The current Rating Test adapter does the following:

1. Transforms the SGF and player coordinates by the session transform.
2. Accepts a one-move `accepted_moves` entry if present.
3. Parses the answer tree. A direct sequence becomes one root child; parenthesized alternatives become multiple root children (`app.py:20730-20772`).
4. Replays each submitted player move against the current children. After a player move, it follows `cur['children'][0]` as the opponent reply (`app.py:20774-20792`).
5. If the player submitted one move and the tree did not accept it, it checks one precomputed `katago_best_move` (`app.py:20821-20850`).
6. The route ignores the client’s `correct` field for the Rating Test verdict and uses `bool(server_correct)` (`app.py:21686-21715`).

This means:

- Multiple root answer branches are supported by the Rating Test adapter.
- A deeper A -> opponent X -> player C and B -> opponent Y -> player D shape is supported when each player branch has one authored opponent reply.
- Multiple opponent replies are not explored by the Rating Test adapter; the first child wins.
- `sgf_engine.autoreply.get_auto_reply` has a stricter and different contract: it returns no auto-reply when there are multiple children. The standalone engine and the current application adapter therefore disagree on ambiguous opponent branches.
- The reusable `sgf_engine.engine.apply_move` supports direct branch, governed equivalent, off-tree, sole auto-reply, and result handling, but its override path is not the current Rating Test route.
- `matcher.match_move` gives a direct SGF branch precedence over an equivalent override. This is a useful invariant for a future common judge.

### 2.3 Shadow contract

V1 is an observation layer, not a second judge:

- Schema is `shadow-v4` (`shadow_judging.py:26`).
- Supported entry points are Rating Test, daily challenge, and friend challenge (`shadow_judging.py:29-33`).
- Shadow imports parser/core modules and calls `matcher.match_move(..., None)`; it does not load an active override (`shadow_judging.py:404-475`).
- It uses explicit result metadata, sole opponent auto-reply, and leaf semantics, then classifies disagreement/candidate evidence.
- The event records `canonical_puzzle_id`, `invalid_identity`, `gf003_related`, parser status, candidate fields, and `user_facing_judgement_changed=false` (`shadow_judging.py:478-617`).
- Configuration is fail-closed. JSONL storage is bounded, rotating, lock-protected, and dashboard reads are budgeted.

## 3. Historical SGF Engine Roadmap

The historical roadmap is coherent as a governance sequence even though not all artifacts are in current `origin/master`:

1. Isolate a parser/tree/matcher engine and vendor it from the SGF Engine development line.
2. Add parser diagnostics and offline inventory without turning inventory into a production judge.
3. Define override identity and runtime boundaries; keep candidate and active states separate.
4. Build Shadow observation with bounded event storage and dashboard/kill-switch controls.
5. Defer immutable canonical identity until the owner chooses a stable alias key.
6. Build Admin review intake and human decisions before any SGF repair editor.
7. Treat SGF edits as a separate governed repair batch with dry-run, byte diff, tree-preservation tests, review, merge, build, deploy, and production verification gates.

Historical evidence:

- `60e9f4f09` (`docs/planning/masterplans/sgf_engine_master_plan.md`) separates parser, inventory, quality issue review, override identity/runtime, owner review, and operational metrics. It explicitly rejects treating “owner review required” as an accepted fix and rejects automatic override activation.
- `4979fb297` (`docs/planning/ADMIN_REVIEW_QUEUE_PLAN.md`) defines Phase 1 as report intake, queue, read-only preview, and decision logging; Phase 2 as limited alternative-branch repair proposals; and Phase 3 as a separate ADR for free SGF-tree editing.
- `9c4b4197f` (`docs/planning/specs/sgf_override_workflow_spec.md`) records candidate-versus-active separation, owner approval, test coverage, rollback, and no activation in a documentation-only batch.
- The historical source line is `origin/testing-baseline-test-isolation`; the current vendor records source commit `d729645c0ae267be6d89a5b49c007bc64284bbcc`.

## 4. V1 Status

### Implemented or evidenced

- Vendored SGF parser/core/engine/override/inventory tree exists on current `origin/master`.
- `sgf_engine/VENDORED_FROM.txt` records the source repository, source branch, full source commit, normalized comparison method, 18 matched implementation files, and the no-direct-edit rule.
- `sgf_engine/PROVENANCE_VERIFICATION.md` records resolved line-ending-only mismatch, 16 shared semantically identical files, and historical 109/109 engine-test results across source, Graph A, and Production trees.
- Shadow-v4 event envelope, candidate classes, identity fail-closed behavior, bounded JSONL storage, rotation/retention/locking, dashboard budgets, and kill-switch scripts/runbook exist.
- GF-003 remains disabled in current docs and inventory contracts.

### Not complete or not proven in this audit

- The owner-gated Production kill-switch drill remains `PENDING OWNER-GATED DRILL`; no Production contact was made.
- Current `origin/master` has no tracked `tests/sgf_engine` or gold SGF fixtures. Those were inspected only from historical Git objects/source refs.
- No current canonical identity alias table/ledger/resolver or durable UUID propagation was found.
- No active override JSON configuration was found in the clean worktree.
- No evidence establishes `sgf_engine.engine.apply_move` as the live authority for all answer routes.
- No current full-corpus answer-verdict audit was run with KataGo or any runtime engine. The only corpus work in this task was read-only parser/inventory computation.

## 5. Restore Gap Status

| Restore area | Current status | Gap |
|---|---|---|
| Engine source | RESTORED/VENDORED | Current vendor is provenance-recorded from `d729645c0...` |
| Parser and tree preservation | OPERATIONAL for Shadow/offline | Current app Rating Test uses a separate adapter; semantics are not unified |
| Historical engine test corpus | HISTORICAL ONLY | Tests/fixtures exist on historical source refs, not current `origin/master` |
| Live authoritative integration | NOT RESTORED | `app.py` does not route all judging through `sgf_engine.engine.apply_move` |
| Override configuration | DISABLED/ABSENT | Scaffold exists, but active data file is absent and no runtime activation is evidenced |
| Identity | BLOCKED ON OWNER DECISION | No durable UUID/alias ledger; duplicate legacy IDs exist in the user-owned snapshot |
| Corpus source in clean branch | ABSENT | `questions.json` is external/untracked runtime data, not in clean `origin/master` |
| Production drill | PENDING OWNER-GATED DRILL | No drill or production verification is authorized by this audit |

The practical recovery conclusion is “source and observation foundation recovered; unified judging and identity recovery not complete.”

## 6. V1.1 Identity Status

The owner decision document is still `OWNER_DECISION_REQUIRED` (`docs/planning/canonical_identity_owner_decision_20260717.md:1-11`). The conflict is between:

- Decision A: globally unique, permanently non-reusable numeric `question_id` as the alias key, with duplicate remediation and allocator/tombstone governance.
- Decision B: `(record_index, legacy_question_id)` as the alias key, with an immutable ingestion record identifier that survives reordering/re-ingestion.

Identity matrix:

| Identity candidate | Found now | Safe as canonical identity? | Finding |
|---|---:|---:|---|
| `canonical_puzzle_id` UUIDv4 | Event field only | No | Shadow validates UUID input but no resolver/ledger supplies it |
| `source_record_uuid` | No | No | Deferred V1.1 contract |
| `legacy_question_id` | Yes | No | 11 duplicate groups in the inspected snapshot |
| `record_index` | Used by review helpers | No | Reordering/re-ingestion can change it |
| `source` path | Yes | No | Human-readable path, not immutable identity |
| SGF content hash | Computable | No by itself | Duplicate content can represent multiple records; hash cannot prove ownership |
| `(record_index, legacy_question_id, content_sha256, snapshot_sha256)` | Auditable composite | Temporary audit locator only | Useful for a bounded packet, not a replacement for owner-approved identity |

Until the owner chooses A or B, all Shadow identity joins must remain fail-closed: `canonical_puzzle_id=null`, `invalid_identity=true`, `gf003_related=false`. No coordinate, filename, SGF path, route, ordering, or content fingerprint may infer GF-003 identity.

## 7. Dataset Inventory

### 7.1 Snapshot and scope

The inspected runtime snapshot was the user-owned, untracked canonical file:

`D:\go-website\questions.json`

Snapshot facts:

- SHA-256: `88DA3E43B41F46380A2C0534FA2FC892B69EB99DF4055DD635333B7153F654FF`
- Size: 75,675,637 bytes
- Last-write timestamp observed: 2026-07-22 12:56:54 UTC
- Records: 42,804
- Every record has a non-empty `content` field in the inspected snapshot; therefore “records without an SGF field” is 0.
- Clean `origin/master` contains no tracked `questions.json`, `.sgf` corpus, or equivalent runtime corpus path.

### 7.2 Record and content integrity counts

| Metric | Count |
|---|---:|
| Records | 42,804 |
| Distinct legacy IDs | 42,793 |
| Duplicate legacy-ID groups | 11 |
| Extra records in duplicate-ID groups | 11 |
| Distinct SGF content hashes | 42,268 |
| Duplicate content groups | 404 |
| Extra records in duplicate-content groups | 536 |
| `katago_best_move` present | 19,502 |
| `accepted_moves` present | 0 |
| `solution_state` present | 0 |
| explicit objective/goal/problem/answer-type fields present | 0 |

The first 36 common record keys are metadata/catalog fields (`id`, topic/level/display fields, content/source, discipline/rank/stage, tags, map/monster fields, and `grimoire_id`). The snapshot does not carry an explicit authoring/generation/provenance field for its SGF answer tree or `katago_best_move`.

### 7.3 Strict parser inventory

Read-only parsing with current `sgf_engine.parser.parse_sgf` produced:

- strict parse success: 42,641
- strict `ValueError` failures: 163
- parseable records with zero answer-tree children: 60
- conservative unusable-answer-tree count: 223 (`163 + 60`)
- records with exactly one root child: 40,156
- records with more than one root child: 2,425
- parsed nodes: 221,611
- average parsed nodes per successful record: 5.197
- maximum parsed depth: 273
- records containing parser comments: 41
- records with answer metadata (`RE`, `GB`, `GW`, `BM`, `TE`, `DO`, or `N`): 1,470

Root-child distribution among successful parses:

```text
0: 60
1: 40156
2: 1765
3: 319
4: 244
5: 57
6: 22
7: 4
8: 11
16: 2
24: 1
```

The 163 failures were parser-structural failures such as invalid property identifiers at recorded offsets. This is a detector input and review queue signal; it is not permission to rewrite malformed SGF.

## 8. Answer Provenance Findings

### Confirmed

- `content` and `source` exist on all 42,804 snapshot records.
- `katago_best_move` exists on 19,502 records; the record also often has `score_gap` and related pool metadata in application code.
- `accepted_moves` is absent in this snapshot, so there is no persisted alternative-answer evidence to explain accepted non-tree moves.
- `sgf_engine/PROVENANCE_VERIFICATION.md` describes vendor-source provenance for the engine code, not provenance for individual question answers.

### Historical offline-run evidence

The dirty canonical snapshot contains:

- `D:\go-website\katago_answer_report_all_20260529_120156.log` (5,834,244 bytes), whose header says a 42,804-question run, `visits=300`, `local=True`, `write=False`, and records `SGF=...`, `KataGo=...`, gap, and visits for each item.
- Zero-byte sibling `katago_answer_report_all_20260529_120117.log`.
- Backup names such as `questions.json.bak_before_katago_auto_20260529_2208`, `questions.json.bak_before_katago_full_...`, `questions.json.bak_before_sgf_done_sync_...`, and `questions.json.bak_before_review_import_...`.
- `katago_explain.py`, which explicitly distinguishes stored SGF/correct moves from KataGo reference moves and says KataGo’s best move is not automatically the stored problem answer.

These are historical local artifacts, not a reproducible provenance chain. The log establishes a read-only comparison batch existed, but it does not bind each current `katago_best_move` byte to a specific engine version/configuration/input hash/author decision, nor does it prove that the current `questions.json` was produced by that run. No runtime engine was started in this audit.

### Provenance conclusion

The current data should be classified as:

- SGF answer tree: `SOURCE_PRESENT_BUT_AUTHORING_PROVENANCE_UNRESOLVED`
- `katago_best_move`: `PRECOMPUTED_CANDIDATE_OR_TOLERANCE_DATA; LINEAGE_UNRESOLVED`
- accepted alternative: `NO_PERSISTED_EVIDENCE_IN_SNAPSHOT`
- owner truth: `NOT_PRESENT_AS_A_DURABLE_FIELD`

Therefore KataGo output may be an audit candidate or explanatory reference, but cannot be promoted to authoritative answer provenance by this task.

## 9. Historical Offline Generation Findings

The repository history and dirty snapshot show an offline-analysis workflow, not a fully reproducible answer-generation pipeline:

- The current tracked source has `katago_explain.py` and application explanation/runtime integration, but no tracked `precompute.py`, deterministic corpus-generation manifest, engine binary checksum, or current answer-generation command under `origin/master`.
- The historical log is a comparison report with statuses such as `OK`, `ACCEPTABLE`, `CONFLICT`, and `NEEDS_REVIEW`; it compares SGF first moves with one KataGo recommendation and reports visits/gap.
- The log header says `write=False`, which is evidence against that particular invocation directly writing the corpus. It does not explain how the 19,502 persisted `katago_best_move` fields entered the current snapshot.
- The current application’s Rating Test verifier uses `katago_best_move` as a one-move tolerance after SGF replay. That makes it a live input to Rating Test authority even though its lineage is not currently modeled.
- `katago_explain.py` contains a safer conceptual boundary: a stored SGF answer is authoritative when available; KataGo is a reference move otherwise. The current Rating Test fallback should be treated as a known governance risk until a separate owner-approved decision removes or constrains it.

No KataGo mass run, engine start, answer regeneration, or corpus write was performed.

## 10. Multiple Solution Findings

### SGF tree support

The parser preserves variations recursively (`sgf_engine/parser/sgf_parser.py:129-164`), and the current snapshot has 2,425 records with multiple root children. Synthetic read-only fixtures confirmed:

- root alternatives A and B both parse as independent branches;
- `sgf_engine.engine.apply_move` can traverse either root branch with a unique opponent auto-reply;
- current `_rt_replay` can accept both root alternatives and a deeper one-reply-per-branch continuation;
- current `_rt_replay` does not explore a second opponent child;
- standalone `sgf_engine.autoreply` deliberately returns no reply when opponent children are ambiguous.

### Current multiple-solution layers

1. Authored SGF branch: strongest available answer evidence.
2. `accepted_moves`: a persistent first-move alternative layer, currently empty in the snapshot.
3. Override equivalent move: governed scaffold, currently disabled/absent in the clean worktree.
4. `katago_best_move`: one precomputed tolerance/reference move, not a complete multiple-solution model.

These layers are not currently represented as one normalized answer contract. A future detector must report them separately and never silently merge them.

## 11. GF-003 Findings

Historical gold-fixture evidence from `origin/testing-baseline-test-isolation` records:

- SGF fixture: `(;CA[UTF-8]FF[4]AB[pg][qc][pf][qg][rc][rg]AW[qd][pc][qe][od][qf][pb]PL[B]SZ[19] GM[1]GN[2-87 黑先] ;B[sf])`
- canonical answer: `B[sf]` / Black T14
- candidate answer: `B[sd]` / Black T16
- candidate is not a root child and is `OFF_TREE` without an override
- status: `CANDIDATE_REQUIRES_OVERRIDE`
- runtime status: disabled
- `apply_automatically=false`
- test-only mapping exists in historical fixture validation; runtime activation does not
- current docs require identity-only GF-003 classification and forbid inferring it from coordinates, filenames, KataGo, or `accepted_moves`

The current clean branch has the override schema/loader/runtime scaffold but no `puzzle_variation_overrides.json` and no active payload. `GF-003_OVERRIDE_ENABLED = NO` is therefore both the current evidence and the required audit assertion.

The dirty corpus contains 33 records whose source basename is `431.sgf`; no record with legacy ID `431` was found. This is precisely why basename or numeric-ID inference is unsafe and why those records are not treated as GF-003.

## 12. Wrong-Answer Detection Feasibility

### Feasibility result

`FEASIBLE_AS_READ_ONLY_AUDIT_TOOL; NOT_READY_AS_AUTHORITATIVE_JUDGE`

The minimum deterministic detector can be built from the current parser/core without KataGo:

| Input condition | Detector result | Human action |
|---|---|---|
| strict parse failure | `PARSE_FAILURE` | inspect source; do not auto-repair |
| valid tree, no answer child | `EMPTY_ANSWER_TREE` | classify as unanswerable/source gap |
| submitted move matches authored child | `BRANCH_MATCH` | usually no issue; inspect continuation semantics |
| unique authored opponent reply followed by valid continuation | `SEQUENCE_MATCH` | usually no issue |
| multiple opponent replies | `AMBIGUOUS_AUTOREPLY` | manual review; no first-child assumption |
| submitted move maps through active governed equivalent | `EQUIVALENT_MATCH` | require identity and owner-approved override evidence |
| submitted move is not authored/equivalent | `OFF_TREE` | candidate wrong answer or candidate alternative; queue for review |
| leaf/result says success | `ACCEPT` | record exact evidence path |
| leaf/result says fail | `REJECT` | record exact evidence path |

### Required guardrails

- Use a bounded input snapshot and include snapshot SHA-256, record index, legacy ID, content SHA-256, parser version, and detector version in output.
- Do not mutate `questions.json`, SGF bytes, DB rows, or player verdicts.
- Do not use KataGo to fill a missing tree or convert `OFF_TREE` into correct.
- Do not infer canonical identity from ID, index, path, coordinate, or filename.
- Treat multiple opponent branches and unresolved leaf semantics as `MANUAL_REVIEW_REQUIRED`, not as a first-child acceptance.
- Keep `accepted_moves`, active override equivalents, and KataGo candidates as distinct evidence classes.
- Run historical fixtures for direct branch, equivalent, direct-over-equivalent precedence, off-tree, pass, explicit result, multiple reply children, root alternatives, deep continuations, and GF-003 disabled behavior.

The primary unresolved semantic is leaf policy: the current app accepts any branch that reaches a leaf, while the historical engine’s auto-reply helper refuses ambiguous replies. V2 remains blocked on a separately documented leaf-semantics decision.

## 13. Existing Admin/Review Infrastructure

### Existing capability

The current application has:

- `question_alternative_reports` table and list/context/resolve API (`app.py:3488-3506`, `app.py:15005-15114`);
- `corpus_review_queue` table with source type, source reference, record index, legacy ID, source path, content hash, questions snapshot commit, reason, status, resolution action, admin note, and reviewer fields (`app.py:3537-3564`);
- review queue list/context/resolve/import endpoints (`app.py:14403-14601`);
- Admin review queue section with explicit Phase 1 text: no direct `questions.json` or formal corpus mutation, and SGF/answer repairs require a separate repair batch (`admin.html:648-655`);
- read-only board preview for queue/report context (`admin.html:1500-1540`, `admin.html:1817-1950`);
- historical import safety rule: revalidate current corpus state before importing old audit candidates, rather than blindly trusting stale reports (`docs/planning/ADMIN_REVIEW_QUEUE_PLAN.md` at historical commit `4979fb297`).

### Current limitations

- The Admin board preview renders initial `AB`/`AW` stones, not a full interactive answer-variation tree.
- Queue resolution records a human decision but does not generate a byte-level SGF repair patch.
- Existing alternative-report `accept` can append an accepted first move through `_append_question_accepted_move` and `_save_questions`; this is a narrow persistent data path, not a general SGF tree editor and not evidence that the move is correct without owner review.
- Review queue staleness metadata is useful but cannot replace an immutable canonical identity ledger.
- The queue is an intake and decision system, not a judging authority.

## 14. Human Repair UX Recommendation

Use a three-stage repair workflow with explicit read-only and mutation gates.

### Stage A: evidence packet

Show, without editing:

- canonical identity state (`canonical_puzzle_id`, invalid/ambiguous reason, owner decision status);
- legacy ID, record index, source path, current corpus SHA, content SHA, and snapshot commit/hash;
- parser status and diagnostics;
- authored root branches and continuation tree, with the submitted move highlighted;
- detector classification: branch, unique sequence, ambiguous reply, off-tree, candidate-only, or parse failure;
- separate evidence cards for SGF, accepted alternative, override candidate, and KataGo reference;
- current production/runtime status only when supplied by a governed evidence artifact; never infer it from a branch name or local file.

### Stage B: human decision

Allowed decisions:

- `confirmed_needs_repair`
- `needs_source_material`
- `candidate_alternative_requires_owner_decision`
- `dismissed_false_positive`
- `wont_fix`

The Admin UI should not expose a “save SGF” action. A decision should create or update a review item and retain the exact evidence locator.

### Stage C: governed repair proposal

For a confirmed repair, generate a proposal packet, not an immediate write:

1. before content SHA and after content SHA;
2. byte-level diff and normalized tree diff;
3. affected record identity and staleness check;
4. answer-path preservation tests, including all existing variations;
5. explicit owner decision for alternative/override semantics;
6. a Codex implementation branch and Draft PR; and
7. separate owner-gated merge, exact artifact build, deployment, and production verification.

For a pure alternative move, prefer a narrowly scoped governed evidence/override path over rewriting the authored SGF. For a malformed or incomplete SGF, require source material or a separate SGF repair batch. Never let a user report or KataGo result directly activate an override.

## 15. Question 69816 Status

The inspected dirty runtime snapshot contains:

- record index: `40299`
- legacy ID: `69816`
- source: `陣線構築：見習防衛指南 ｜ Go - Line Construction Apprentice Guard\\（上）\\第04单元 对 杀\\01.数 气\\8.sgf`
- display name: `8`
- `katago_best_move`: `C10`
- `accepted_moves`: absent
- `solution_state`: absent

The clean tracked E10 contract says `69816` does not exist in the repository and must not be reused for E10 (`docs/planning/e10_final_screenplay_integration_contract_v1.md:258`). This is a data-snapshot/tracked-contract discrepancy, not permission to repair or reuse the record.

Disposition for this audit:

- do not edit or delete the record;
- do not assign it to E10, Claude, cinematic runtime, art, or audio;
- keep it in the Codex/SGF Engine audit scope as a provenance/identity case;
- queue it for human review only after an immutable identity decision and a read-only answer-tree packet exist;
- no player verdict, SGF byte, `questions.json` byte, or database mutation was performed.

## 16. Risk Register

| Risk | Severity | Current status | Containment |
|---|---|---|---|
| Multiple live judging authorities | Critical | Confirmed | Do not claim unified SGF Engine authority; keep Rating Test route facts separate |
| Daily/friend client-supplied verdicts | Critical | Confirmed | Separate future server-authoritative judging task; not changed here |
| KataGo fallback accepted as truth | High | Confirmed risk | Treat as candidate/reference; no new runs or activation |
| Duplicate legacy IDs | High | Confirmed: 11 groups | Owner must choose identity policy before alias/backfill |
| Record index drift | High | Confirmed risk | Include snapshot hash; never call index canonical |
| Unresolved SGF authoring provenance | High | Confirmed | Keep `SOURCE_PRESENT_BUT_AUTHORING_PROVENANCE_UNRESOLVED` |
| Ambiguous opponent reply | High | Confirmed by code/fixtures | Manual review; no implicit first-child acceptance in detector |
| Parse failures/empty trees | High | 223 conservative cases | Queue as source/parser evidence; no auto-edit |
| GF-003 false association | High | Guardrail required | Identity-only, disabled, no coordinate/path inference |
| Direct Admin SGF mutation | High | Existing narrow accepted-move path | Keep Phase 1 read-only; repair proposals only |
| Production provenance overclaim | Critical | Not evidenced in this audit | Require runtime/hash evidence and owner-gated release proof |
| Canonical dirty worktree contamination | High | Present | Preserve canonical; use isolated worktree and exact-file staging |

## 17. Recommended Next Sprint

Exactly one next implementation Sprint is recommended; it is not started by this audit.

### `SGF-ENGINE-SPRINT-1: READ_ONLY_WRONG_ANSWER_AUDIT_AND_REPAIR_PACKET`

Prerequisite owner gates:

- choose identity Decision A or B;
- approve the detector’s leaf/multiple-response semantics;
- confirm the input snapshot and its SHA-256;
- keep GF-003 disabled and keep E10/Claude/PR294 outside the workstream.

Implementation scope:

1. Add a deterministic read-only corpus audit tool that accepts an explicit snapshot path, parser version, and output path; it must emit a summary plus per-record evidence packets without touching source corpus, SGF bytes, DB, or Production.
2. Reuse `sgf_engine.parser` and pure core functions; classify parse failure, empty tree, direct branch, unique continuation, ambiguous reply, off-tree, candidate-only, and explicit result.
3. Emit identity-safe locators containing snapshot SHA, record index, legacy ID, content SHA, source path, and detector version; do not invent UUIDs or aliases.
4. Add historical synthetic fixtures for root alternatives, deep alternatives, multiple opponent replies, pass nodes, explicit results, direct-over-equivalent precedence, and GF-003 disabled behavior.
5. Produce Admin-compatible read-only review packets and staleness checks; do not add SGF editing or automatic repair.
6. Document the first owner-review queue ordering, with Question 69816 as an identity/provenance case and GF-003 as a disabled candidate case, without changing either record.

Definition of done:

- exact clean worktree/base verified;
- no KataGo runtime or mass run;
- no `questions.json`/SGF/DB/Production mutation;
- deterministic tests pass on synthetic and historical fixtures;
- ambiguous semantics remain manual rather than silently accepted;
- one isolated branch, exact diff, owner-review Draft PR only;
- stop before merge, build, deploy, or production verification.

## Audit Assertions

```text
QUESTIONS_MUTATED = 0
SGF_BYTES_MUTATED = 0
QUESTIONS_JSON_MUTATED = 0
PLAYER_VERDICT_MUTATED = 0
DB_MUTATED = 0
PRODUCTION_CONTACT = NONE
KATAGO_RUNTIME_ADDED = NO
KATAGO_MASS_RUN = NONE
GF003_OVERRIDE_ENABLED = NO
CLAUDE_E10_WORK_TOUCHED = NO
MERGE = NOT_AUTHORIZED
DEPLOY = NOT_AUTHORIZED

CODEX_WORKSTREAM = SGF_ENGINE_ONLY
CLAUDE_WORKSTREAM_TOUCHED = NO
PR294_TOUCHED = NO
E10_CINEMATIC_RUNTIME_TOUCHED = NO
E10_ART_TOUCHED = NO
E10_AUDIO_TOUCHED = NO
```

## Git Handoff Metadata

```text
BASE_REF = origin/master
BASE_SHA = ca916729f8fcdfc648ede777187b9d8650e3d9c9
BRANCH = codex/sgf-engine-reentry-audit-001
WORKTREE = D:\go-website-sgf-engine-reentry-audit-001
AUDIT_HEAD_AT_START = ca916729f8fcdfc648ede777187b9d8650e3d9c9
COMMIT = TO_BE_RECORDED_IN_FINAL_HANDOFF
DRAFT_PR = NOT_OPEN_AT_REPORT_WRITING_CHECKPOINT
EXACT_DIFF = docs/planning/sgf_engine_reentry_audit_v1.md (new file only)
```

The isolated worktree also contained an untracked `secret_key.txt` sentinel. It was not read, hashed, moved, deleted, staged, or included in this exact diff.
