SGF_ANSWER_SUSPECT_DETECTOR_001: READY_FOR_OWNER_VALIDATION

# SGF Answer Suspect Detector v1

## 1. Outcome and Decision Boundary

This Sprint implements a deterministic, explainable, read-only detector that ranks puzzle records for Owner inspection. It does not decide that an answer is wrong.

```text
DETECTOR_OUTPUT = OWNER_REVIEW_RECOMMENDED
DETECTOR_OUTPUT_DOES_NOT_MEAN = WRONG_ANSWER_CONFIRMED
CANONICAL_IDENTITY = DEFERRED
AUDIT_IDENTITY = AUDIT_LOCATOR_ONLY
```

The full local corpus snapshot was analyzed twice. Both runs produced byte-identical evidence artifacts and identical ordering. A practical 500-record validation pack is ready for Owner precision review before any repair or repair UI is considered.

## 2. Git and Snapshot Boundary

```text
BASE_REF = origin/master
BASE_SHA = 204e4b95fa0c27be9b40020324652a02043a75a7
BRANCH = codex/sgf-answer-suspect-detector-001
WORKTREE = D:\go-website-sgf-answer-suspect-detector-001
REGISTERED_WORKTREES_AT_START = 351
NEW_WORKTREE_STATUS_AT_START = CLEAN
IMPLEMENTATION_COMMIT = recorded after the implementation content commit
```

The clean Git base does not contain `questions.json`. The detector was given the explicit user-owned local snapshot previously identified by the re-entry audit:

```text
SNAPSHOT_PATH = D:\go-website\questions.json
SNAPSHOT_BYTES = 75675637
SNAPSHOT_SHA256 = 88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff
QUESTION_COUNT = 42804
```

The source hash was verified before and after both full runs. The snapshot was not copied into Git, rewritten, normalized, or otherwise changed. Every emitted record carries a locator made from snapshot SHA-256, record index, legacy question ID, and content SHA-256. This locator is strictly `AUDIT_LOCATOR_ONLY`, not canonical identity.

## 3. Implementation

The detector is implemented in `tools/sgf_answer_suspect_detector.py`. It accepts explicit source and output paths, enforces bounded JSON input, rejects source/output path collision, hashes the source again after generation, and emits only summary metrics and the selected validation set. It does not emit full SGF bytes.

Reproduction command:

```powershell
python tools/sgf_answer_suspect_detector.py `
  --questions "D:\go-website\questions.json" `
  --output-dir "D:\go-website-sgf-answer-suspect-detector-001-artifacts\release-a" `
  --top-limit 500
```

Optional player evidence is accepted only as a PII-free aggregate JSON file bound to the exact snapshot and exact record locator. The loader rejects unknown fields so usernames, reporter IDs, notes, and raw rows cannot accidentally enter the pack. Supported aggregate fields are counts, reason-code counts, rejected move coordinates/counts, attempt/wrong totals, wrong rate, Shadow disagreement count, and explicitly calibration-dependent high-skill counts.

## 4. Structural Analysis

The detector reuses the strict `sgf_engine.parser.parse_sgf` parser. It validates setup coordinates, root answer coordinates, board bounds, pass/non-move roots, duplicate root coordinates, and ambiguous opponent reply structure.

Current snapshot results:

| Metric | Count |
|---|---:|
| Questions | 42,804 |
| Strict parse success | 42,641 |
| Strict parse failure | 163 |
| Zero valid root answer | 61 |
| Exactly one native root answer | 41,045 |
| Multiple native root answers | 1,535 |
| Empty solution tree | 60 |
| Duplicate same-coordinate root branch | 1,286 |
| Ambiguous opponent reply structure | 489 |
| Non-move root branch | 8 |
| Root pass with no point answer | 1 |

Native multiple root answers are counted but are not automatically suspicious. A duplicate same-coordinate branch or ambiguous opponent reply is reviewable structural evidence, but it is not treated as the same P0 integrity failure as parser failure or no valid answer.

## 5. Historical KataGo Data

Current master reconfirms the Rating Test path in `app.py`:

1. `_rt_server_verify` checks configured accepted moves;
2. replays the parsed SGF tree; and
3. after a failed one-move replay, accepts a transformed stored `katago_best_move` when it matches the submitted move (`app.py:20821-20847`).

Therefore:

```text
KATAGO_RUNTIME_IN_PRODUCTION = NO
PRECOMPUTED_KATAGO_DATA_AFFECTS_CURRENT_VERDICT = YES
KATAGO_RUN = NONE
```

Historical metadata inventory and detector results:

| Metric | Count |
|---|---:|
| Records with historical KataGo-related metadata | 19,503 |
| Records with a non-empty stored KataGo move | 19,502 |
| Valid stored KataGo coordinates | 19,502 |
| Precomputed move outside native root tree | 9,244 |
| Precomputed/native-tree disagreement with at least one native answer | 9,110 |
| Historical `NEEDS_REVIEW` status | 9,142 |
| Historical conflict evidence | 2,066 |
| Stored move with unresolved answer source | 733 |

These are review-priority signals. The detector neither runs KataGo nor changes/removes the current fallback.

## 6. Conservative Global-Tenuki Geometry

Geometry uses setup-stone concentration, bounding region, dominant connected cluster, quadrant concentration, an expanded active region, candidate distance, sparse unrelated quadrant, and continuation interaction. Distance alone never creates a suspect.

V1 thresholds:

| Rule | Threshold |
|---|---:|
| Minimum setup stones | 4 |
| Maximum local bounding width/height | 10 / 10 |
| Maximum local bounding area ratio | 0.30 |
| Minimum dominant cluster ratio | 0.80 |
| Maximum occupied quadrants for local position | 2 |
| Minimum dominant quadrant ratio | 0.70 |
| Expanded active-region margin | 3 intersections |
| Possible-tenuki minimum setup distance | 6 |
| High-confidence minimum setup distance | 8 |
| Continuation lookahead | 12 plies |

Broad positions are guarded when the bounding area reaches 0.45 of the board, either dimension reaches 0.75 of board size, or setup occupies at least three quadrants. A high-confidence geometry signal additionally requires a sparse unrelated quadrant, no continuation interaction with the active region, and historical/precomputed context. Results:

| Signal | Count |
|---|---:|
| `HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT` | 596 |
| `POSSIBLE_GLOBAL_TENUKI_SUSPECT` | 515 |

Unresolved false-positive classes remain explicitly visible: ko threats, ladders, outside liberties/support, long-range connection, escape routes, sente, intentional tenuki, whole-board tesuji, and non-tsumego positions. Only Owner board review can resolve them.

## 7. Player Reports, Attempts, Shadow, and Calibration

Repository infrastructure exists for:

- general `question_problem_reports` with reason/status and legacy question linkage;
- `question_alternative_reports` with reported rejected move coordinates and per-user/question/move uniqueness;
- confirmed general reports entering `corpus_review_queue` as `player_reported` with explicit duplicate-ID record selection;
- `review_log` and mistake/attempt aggregates; and
- Shadow candidate/disagreement event aggregation.

The safe local state contains no usable report rows: local `go_app.db` is empty and no local Shadow event file is present. The canonical application database is PostgreSQL and would require Production access, which is prohibited. No Production connection was attempted.

```text
PLAYER_SIGNAL_DATA = UNAVAILABLE_LOCAL
PLAYER_REPORT_COUNT = UNKNOWN
DISTINCT_REPORTER_COUNT = UNKNOWN
REJECTED_MOVE_CLUSTER = UNKNOWN
ABNORMAL_WRONG_RATE = UNKNOWN
SHADOW_DISAGREEMENT = UNKNOWN
```

The optional aggregate input contract keeps the architecture ready for these signals without fabricating counts. `CALIBRATION_DEPENDENT` evidence is recorded but never increases priority by itself. The existing `anchor_bank_unavailable` issue remains deferred and does not block this detector.

## 8. Priority Model and Reason Codes

Priority is tier-based, not a fake accuracy percentage:

- **P0 — structural integrity:** parser failure, empty/no valid answer, or invalid precomputed coordinate.
- **P1 — combined strong evidence:** at least two independent strong groups, such as global-tenuki geometry plus KataGo/tree disagreement, historical conflict plus disagreement, or reports plus repeated omitted alternative.
- **P2 — one strong signal:** KataGo/tree disagreement, historical review/conflict, high-confidence geometry, repeated rejected move, Shadow disagreement, or reviewable structural variation.
- **P3 — exploratory:** possible geometry, unresolved provenance, or calibration-dependent evidence alone.

Implemented stable reason codes:

```text
PARSER_FAILURE
EMPTY_SOLUTION_TREE
NO_VALID_ROOT_ANSWER
STRUCTURAL_SGF_ISSUE
DUPLICATE_ROOT_MOVE_BRANCH
NON_MOVE_ROOT_BRANCH
AMBIGUOUS_OPPONENT_REPLY
INVALID_PRECOMPUTED_MOVE
PRECOMPUTED_KATAGO_ONLY_FALLBACK
KATAGO_NATIVE_TREE_DISAGREEMENT
HISTORICAL_KATAGO_NEEDS_REVIEW
HISTORICAL_ANSWER_CONFLICT
HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT
POSSIBLE_GLOBAL_TENUKI_SUSPECT
PLAYER_REPORTED
REPEATED_REJECTED_MOVE
REPEATED_SAME_ALTERNATIVE
MULTIPLE_SOLUTION_REVIEW
ABNORMAL_WRONG_RATE
SHADOW_DISAGREEMENT
ANSWER_PROVENANCE_UNKNOWN
CALIBRATION_DEPENDENT
```

`WRONG_ANSWER_CONFIRMED` is intentionally absent.

## 9. Full-Corpus Suspect Distribution

| Priority | Count |
|---|---:|
| P0 | 224 |
| P1 | 1,599 |
| P2 | 10,891 |
| P3 | 371 |
| **Total suspects** | **13,085** |

Major reason counts:

| Reason | Count |
|---|---:|
| `PARSER_FAILURE` | 163 |
| `EMPTY_SOLUTION_TREE` | 60 |
| `NO_VALID_ROOT_ANSWER` | 61 |
| `STRUCTURAL_SGF_ISSUE` | 2,003 |
| `DUPLICATE_ROOT_MOVE_BRANCH` | 1,286 |
| `AMBIGUOUS_OPPONENT_REPLY` | 489 |
| `PRECOMPUTED_KATAGO_ONLY_FALLBACK` | 9,244 |
| `KATAGO_NATIVE_TREE_DISAGREEMENT` | 9,110 |
| `HISTORICAL_KATAGO_NEEDS_REVIEW` | 9,142 |
| `HISTORICAL_ANSWER_CONFLICT` | 2,066 |
| `HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT` | 596 |
| `POSSIBLE_GLOBAL_TENUKI_SUSPECT` | 515 |
| `ANSWER_PROVENANCE_UNKNOWN` | 733 |

Overlaps are recorded in `corpus_summary.json`; no count is interpreted as proof of a wrong answer.

## 10. Owner Validation Set and Viewer

A pure global prefix was dominated by structural records. The final deterministic selection preserves the highest 60% global rank prefix, then adds the highest not-yet-selected records required to represent P1/P2/P3, then fills remaining slots by global rank. Global detector rank remains present on every selected record.

Validation set distribution:

| Priority | Selected |
|---|---:|
| P0 | 224 |
| P1 | 176 |
| P2 | 75 |
| P3 | 25 |
| **Total** | **500** |

The static HTML viewer shows the initial board position, native root answer markers, stored precomputed marker, priority, reason codes, locator, concise spatial/player evidence, and collapsible detail metrics. It has filtering/search but no form, Save, Replace, Add Equivalent, DB, SGF, or verdict action.

Browser QA results:

```text
CARDS = 500
BOARD_CANVASES = 500
P2_FILTER_RESULT = 75
HIGH_CONFIDENCE_TENUKI_FILTER_RESULT = 178
FILTER_RESET_RESULT = 500
CONSOLE_ERRORS = 0
BUTTONS = 0
FORMS = 0
```

The annotation template is explicitly `NON_AUTHORITATIVE_OWNER_VALIDATION` and permits only: `confirmed_issue`, `valid_answer`, `possible_equivalent`, or `unclear`. Editing a copy never changes canonical data.

## 11. Determinism and Artifact Evidence

Two independent full runs (`release-a` and `release-b`) produced identical SHA-256 for every file:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `corpus_summary.json` | 6,125 | `d4b12ed39e5ea24703c195313655a760c81e0eb0f5965f1e062a80f7c020cbab` |
| `top_suspects.json` | 2,389,783 | `33c300a1e732740aebcce6cd7c2f60ce2c97fac5f5409ebd69f68c9c4a9540dc` |
| `owner_validation_pack.html` | 1,522,080 | `ed3308adb3450d8f5e9d50d64ce02588d5078adde9060dbb13a1f1f268fc1a0a` |
| `owner_review_annotations.template.json` | 195,656 | `aafeb1a9017cdf4ac9c62eb334ed7cc28e0a4cabe7a8c2292f333e823c517bd2` |
| `artifact_manifest.json` | 763 | `fe153be4caf6b8c7258c24f4c1b06e3d6c367345174ce8294552b7f8b0e74b74` |

Primary local evidence path:

```text
D:\go-website-sgf-answer-suspect-detector-001-artifacts\release-a
```

Generated evidence remains outside Git to avoid adding 4+ MiB of reproducible output to the Sprint PR. The PR carries the generator, tests, and this exact evidence ledger.

## 12. Tests

Focused tests cover:

1. local setup with an answer inside the active region;
2. local setup with an answer on the opposite side;
3. broadly distributed whole-board guard;
4. native multiple root answers not being suspicious by themselves;
5. duplicate same-coordinate root branches being reviewable but not P0;
6. empty/no solution branch;
7. parser failure with normalized, non-leaking evidence;
8. precomputed move outside the native tree;
9. combined signals ranking above isolated weak evidence;
10. explicit safe behavior when player data is absent;
11. calibration-dependent evidence remaining P3 by itself;
12. byte-identical repeated generation and unchanged source bytes;
13. snapshot-bound `AUDIT_LOCATOR_ONLY` identity; and
14. rejection of PII-shaped unsupported player-evidence fields; and
15. successful exact-locator linkage for safe aggregate player evidence.

Validation command and result:

```text
python -m pytest -q tests/test_sgf_answer_suspect_detector.py
16 passed
```

## 13. Existing Admin Reuse Boundary

The existing SGF board preview, alternative-report review surface, general problem-report queue, and Admin corpus Review Queue could support a later board-first workflow. This Sprint does not connect the detector to those mutation paths and does not implement repair UI.

## 14. Known Limitations and Recommendation

- Detector precision is unknown until the Owner labels the validation sample.
- Player-report, rejected-move, attempt-rate, and Shadow counts are unavailable without prohibited Production access; optional aggregate ingestion is implemented but unpopulated.
- Geometry cannot prove or disprove ko, ladder, outside support/liberties, sente, or whole-board dependencies.
- Historical KataGo metadata is evidence with incomplete lineage, not current solver output.
- Duplicate legacy IDs remain possible; `AUDIT_LOCATOR_ONLY` is snapshot-bound and not durable identity.
- Rank Calibration remains deferred; calibration-dependent evidence is non-primary.

Do not automatically recommend repair yet. First ask the Owner to review the 500-record pack and measure detector precision by category. If the high-priority sample is useful, a separately authorized Sprint may design a board-first Review Queue. If not, refine detector thresholds and ranking before any repair UI investment.

## 15. Required Assertions

```text
QUESTIONS_MUTATED = 0
SGF_BYTES_MUTATED = 0
QUESTIONS_JSON_MUTATED = 0
ACCEPTED_MOVES_MUTATED = 0
PLAYER_VERDICT_MUTATED = 0
DB_MUTATED = 0
PRODUCTION_CONTACT = NONE
KATAGO_RUN = NONE
IDENTITY_IMPLEMENTED = NO
GF003_OVERRIDE_ENABLED = NO
RANK_CALIBRATION_FIX = DEFERRED
REPAIR_UI_IMPLEMENTED = NO
E10_CINEMATIC_TOUCHED = NO
MERGE = NOT_AUTHORIZED
DEPLOY = NOT_AUTHORIZED
```

Workstream isolation:

```text
CODEX_WORKSTREAM = SGF_ENGINE_PUZZLE_ANSWER_QUALITY_ONLY
CLAUDE_WORKTREE_TOUCHED = NO
PR294_TOUCHED = NO
E10_CINEMATIC_RUNTIME_TOUCHED = NO
```
