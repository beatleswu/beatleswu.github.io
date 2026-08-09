# SGF-ANSWER-REPAIR-BATCH-001 — Phase 1B End-to-End Verdict Safety

Status: READY_FOR_OWNER_SAFE_BATCH_REVIEW

The native-only dry run was accepted as PASS_WITH_BLOCKER. This continuation checks the final effective first-move verdict across current player-facing paths. It is read-only and is not GO_APPLY.

## Snapshot identity

- Proposal snapshot timestamp: 2026-08-09T11:20:32.116Z
- Proposal snapshot SHA-256: `5897644200246f5bdecf7c291054f3db982a78ba402956ba563bea804d400b2c`
- Reviewed questions SHA-256: `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`
- Current target evidence SHA-256: `64e40182906485e740354f45bb767c97777ec4ca6d321551a1f79cd0d1256778`
- Current Production questions SHA-256: `4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`
- Current Production question count: 41591
- Repair plan SHA-256: `81e8b958193a34271fa29e3478f92c0237601bf6482b76922af38c2ecf8ac5d6`
- Safe first batch SHA-256: `388bba6fb0a2c8c9f7c087f1516816b34262b3c98c43737bb9ac85a55037c696`

## End-to-end classification

| Classification | Groups |
| --- | ---: |
| `FULLY_APPLYABLE_END_TO_END` | 54 |
| `NATIVE_REPAIR_VALID_BUT_FALLBACK_CONFLICT` | 3 |
| `MANUAL_RECONSTRUCTION_REQUIRED` | 1 |
| `STALE_OR_CONFLICTED` | 2 |
| `UNRESOLVED_SOURCE` | 47 |
| `NO_OP` | 0 |

Required invariant: `OWNER_DESIRED_VERDICT == SIMULATED_FINAL_EFFECTIVE_PLAYER_VERDICT`. Native SGF success alone no longer qualifies a group for the safe batch.

### Duplicate safety

- `DUPLICATE_GROUPS=6`
- `MULTI_RECORD_REPAIR_GROUPS=6`
- `DUPLICATE_FANOUT_RECORDS=11`
- `DUPLICATE_GROUP_CONFLICTS=0`

## Validation

| Check | Result |
| --- | --- |
| SGF parse before/after | PASS |
| Native judging | PASS |
| Position/root/surviving variations | PASS |
| Multi-answer validation | PASS |
| Final effective judging simulation | PASS |

## Actual current verdict architecture

- Main practice injects `accepted_moves` into the native SGF client tree. `/api/srs/review` records the resulting grade; it does not re-judge the move.
- Daily Challenge judges in the client against the native SGF tree; the submit route trusts client `correct`.
- Friend Challenge uses the main client verdict; the answer route trusts client `correct`.
- Map Battle V1 checks server-side `accepted_moves`, then the native SGF tree; it does not use `katago_best_move`.
- Rating Test uses `_rt_server_verify`: accepted moves, native legacy replay, then stored `katago_best_move`. Current `_build_rt_pool` omits accepted moves from pool records, so the effective current pool path is native legacy replay then stored fallback.
- Shadow/candidate judging is observational and does not alter final verdicts.

### Historical fallback traces

#### Question 15436

- `FALLBACK_SOURCE_FIELD=katago_best_move`
- `FALLBACK_STORAGE_LOCATION=per-question /app/data/questions.json katago_best_move field; copied into the in-memory Rating Test pool. The optional rating_verified_questions.json override file is absent from the canonical tree and is not copied by the Dockerfile`
- `VERIFIED_OVERRIDE_EVIDENCE=CANONICAL_FILE_ABSENT_AND_NOT_PACKAGED`
- `FALLBACK_PROVENANCE=historical Owner-side offline KataGo preprocessing before upload; no Production KataGo execution is involved`
- `FALLBACK_ACCEPTANCE_CONDITION=Rating Test only: exactly one submitted move equals the session-transformed stored fallback after accepted/native legacy replay has not returned true`
- `FINAL_VERDICT_PATH=` main practice: accepted_moves injected into native SGF client tree → daily challenge: native SGF client tree; server trusts client correct → friend challenge: main client verdict; server trusts client correct → Map Battle V1: server accepted_moves then native SGF tree → Rating Test: pool accepted_moves check (currently empty because pool projection omits it), native legacy SGF replay, stored katago_best_move fallback
- Current native: A2, B1
- Owner desired: B1
- Stored fallback: Q4
- Simulated final effective verdict: B1, Q4
- Classification: `NATIVE_REPAIR_VALID_BUT_FALLBACK_CONFLICT`

#### Question 15388

- `FALLBACK_SOURCE_FIELD=katago_best_move`
- `FALLBACK_STORAGE_LOCATION=per-question /app/data/questions.json katago_best_move field; copied into the in-memory Rating Test pool. The optional rating_verified_questions.json override file is absent from the canonical tree and is not copied by the Dockerfile`
- `VERIFIED_OVERRIDE_EVIDENCE=CANONICAL_FILE_ABSENT_AND_NOT_PACKAGED`
- `FALLBACK_PROVENANCE=historical Owner-side offline KataGo preprocessing before upload; no Production KataGo execution is involved`
- `FALLBACK_ACCEPTANCE_CONDITION=Rating Test only: exactly one submitted move equals the session-transformed stored fallback after accepted/native legacy replay has not returned true`
- `FINAL_VERDICT_PATH=` main practice: accepted_moves injected into native SGF client tree → daily challenge: native SGF client tree; server trusts client correct → friend challenge: main client verdict; server trusts client correct → Map Battle V1: server accepted_moves then native SGF tree → Rating Test: pool accepted_moves check (currently empty because pool projection omits it), native legacy SGF replay, stored katago_best_move fallback
- Current native: D2, B2
- Owner desired: B2
- Stored fallback: Q4
- Simulated final effective verdict: B2, Q4
- Classification: `NATIVE_REPAIR_VALID_BUT_FALLBACK_CONFLICT`

#### Question 65095

- `FALLBACK_SOURCE_FIELD=katago_best_move`
- `FALLBACK_STORAGE_LOCATION=per-question /app/data/questions.json katago_best_move field; copied into the in-memory Rating Test pool. The optional rating_verified_questions.json override file is absent from the canonical tree and is not copied by the Dockerfile`
- `VERIFIED_OVERRIDE_EVIDENCE=CANONICAL_FILE_ABSENT_AND_NOT_PACKAGED`
- `FALLBACK_PROVENANCE=historical Owner-side offline KataGo preprocessing before upload; no Production KataGo execution is involved`
- `FALLBACK_ACCEPTANCE_CONDITION=Rating Test only: exactly one submitted move equals the session-transformed stored fallback after accepted/native legacy replay has not returned true`
- `FINAL_VERDICT_PATH=` main practice: accepted_moves injected into native SGF client tree → daily challenge: native SGF client tree; server trusts client correct → friend challenge: main client verdict; server trusts client correct → Map Battle V1: server accepted_moves then native SGF tree → Rating Test: pool accepted_moves check (currently empty because pool projection omits it), native legacy SGF replay, stored katago_best_move fallback
- Current native: R18, S18, Q19
- Owner desired: R18
- Stored fallback: D17
- Simulated final effective verdict: D17, R18
- Classification: `NATIVE_REPAIR_VALID_BUT_FALLBACK_CONFLICT`

## Question 15436 mandatory proof

- Current native: A2, B1
- Owner desired: B1
- Stored fallback: Q4
- `B1=ACCEPT`
- `A2=REJECT`
- `Q4=ACCEPT`
- `QUESTION_15436_FINAL_EFFECTIVE_VERDICT_SAFE=NO`
- Classification: `NATIVE_REPAIR_VALID_BUT_FALLBACK_CONFLICT`

The native rewrite removes A2 and preserves B1, but Q4 remains accepted by Rating Test fallback. Question 15436 is excluded from the safe first batch.

## Safe first batch

- `SAFE_BATCH_GROUPS=54`
- `SAFE_BATCH_RECORDS=65`
- `SAFE_BATCH_FILES=65`
- `SAFE_BATCH_SHA256=388bba6fb0a2c8c9f7c087f1516816b34262b3c98c43737bb9ac85a55037c696`
- Filter: `FULLY_APPLYABLE_END_TO_END` only.
- Every safe record contains current effective, Owner desired, and simulated final verdict evidence with `MATCH=YES`.

## Unresolved source breakdown

### Reasons

| Reason | Groups |
| --- | ---: |
| `QUESTION_ID_NOT_IN_CURRENT_CORPUS` | 47 |
| `REVIEW_SNAPSHOT_FROM_OLDER_CORPUS` | 47 |

### Dispositions

| Disposition | Groups |
| --- | ---: |
| `RE_REVIEW_REQUIRED` | 47 |

The manifest contains a machine-readable mapping for every unresolved group. All 47 reviewed IDs are absent from the exact current-corpus target inventory; the older review snapshot is retained as evidence and no mapping is guessed.

## Five stale/conflict groups

### Question / review group 74535

- `OWNER_REVIEWED_CURRENT_STATE=` {"native_answers": [], "reviewed_content_sha256": "50f407823cebaa6f2469db01a19e2b6da35f5df20abf015af945804339509e0c", "side_to_move": "UNKNOWN"}
- `CURRENT_CANONICAL_STATE=` [{"accepted_moves": [], "content_sha256": "50f407823cebaa6f2469db01a19e2b6da35f5df20abf015af945804339509e0c", "legacy_question_id": 74535, "native_answers": [], "side_to_move": "UNKNOWN", "source_path": "12龍之谷守衛 ｜ Go - Dragon Guard\\手筋題\\871.sgf", "stored_precomputed_fallback": "Q16"}]
- `OWNER_DESIRED_STATE=` ["D19"]
- `CONFLICT_REASON=` SOURCE_PATH_CHANGED
- `RECOMMENDED_DISPOSITION=RE_REVIEW_REQUIRED`

### Question / review group 35389

- `OWNER_REVIEWED_CURRENT_STATE=` {"native_answers": [], "reviewed_content_sha256": "c7ca364f97095c29d2d1cb9a90a898e2b20cc5cb51cb90fc13d3797f2ff1d0c0", "side_to_move": "UNKNOWN"}
- `CURRENT_CANONICAL_STATE=` [{"accepted_moves": [], "content_sha256": "c7ca364f97095c29d2d1cb9a90a898e2b20cc5cb51cb90fc13d3797f2ff1d0c0", "legacy_question_id": 35389, "native_answers": [], "side_to_move": "UNKNOWN", "source_path": "6哥布林巡邏隊 ｜ Go - Goblin Patrol\\死活題\\454.sgf", "stored_precomputed_fallback": "R16"}]
- `OWNER_DESIRED_STATE=` "MANUAL_RECONSTRUCTION_OWNER_DECISION_REQUIRED"
- `CONFLICT_REASON=` SOURCE_PATH_CHANGED
- `RECOMMENDED_DISPOSITION=RE_REVIEW_REQUIRED`

### Question / review group 15436

- `OWNER_REVIEWED_CURRENT_STATE=` {"native_answers": ["A2", "B1"], "reviewed_content_sha256": "bc664d0d262df5cb92a078ff67618fe699ad29415c57a04ba6e2d67c2e8c735c", "side_to_move": "W"}
- `CURRENT_CANONICAL_STATE=` [{"accepted_moves": [], "content_sha256": "bc664d0d262df5cb92a078ff67618fe699ad29415c57a04ba6e2d67c2e8c735c", "legacy_question_id": 15436, "native_answers": ["A2", "B1"], "side_to_move": "W", "source_path": "幻影刺客的暗器 ｜ Go - Phantom Kunai\\17.sgf", "stored_precomputed_fallback": "Q4"}]
- `OWNER_DESIRED_STATE=` ["B1"]
- `CONFLICT_REASON=` UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET
- `RECOMMENDED_DISPOSITION=OWNER_FALLBACK_DECISION_REQUIRED_THEN_RE_REVIEW`

### Question / review group 15388

- `OWNER_REVIEWED_CURRENT_STATE=` {"native_answers": ["B2", "D2"], "reviewed_content_sha256": "ccca265260eae2da61d1b4d72c90de992a8e428bafd36351c1a698eda6f34b90", "side_to_move": "W"}
- `CURRENT_CANONICAL_STATE=` [{"accepted_moves": [], "content_sha256": "ccca265260eae2da61d1b4d72c90de992a8e428bafd36351c1a698eda6f34b90", "legacy_question_id": 15388, "native_answers": ["B2", "D2"], "side_to_move": "W", "source_path": "幻影刺客的暗器 ｜ Go - Phantom Kunai\\126.sgf", "stored_precomputed_fallback": "Q4"}]
- `OWNER_DESIRED_STATE=` ["B2"]
- `CONFLICT_REASON=` UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET
- `RECOMMENDED_DISPOSITION=OWNER_FALLBACK_DECISION_REQUIRED_THEN_RE_REVIEW`

### Question / review group 65095

- `OWNER_REVIEWED_CURRENT_STATE=` {"native_answers": ["Q19", "R18", "S18"], "reviewed_content_sha256": "5cf86117daf0d1b60eec84e57f0a14dc639e46c3329910223e497190361aaea2", "side_to_move": "W"}
- `CURRENT_CANONICAL_STATE=` [{"accepted_moves": [], "content_sha256": "5cf86117daf0d1b60eec84e57f0a14dc639e46c3329910223e497190361aaea2", "legacy_question_id": 65095, "native_answers": ["Q19", "R18", "S18"], "side_to_move": "W", "source_path": "遠古大師殘卷 ｜ Go - Ancient Master Scrolls\\死之部71題\\5.sgf", "stored_precomputed_fallback": "D17"}]
- `OWNER_DESIRED_STATE=` ["R18"]
- `CONFLICT_REASON=` UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET
- `RECOMMENDED_DISPOSITION=OWNER_FALLBACK_DECISION_REQUIRED_THEN_RE_REVIEW`

## Manual reconstruction preview

### Question 65170

- Current source: `遠古大師殘卷 ｜ Go - Ancient Master Scrolls\活之部103題\13.sgf`
- Current content SHA-256: `ca4995fb8504bde2aca3b121d28261a4d55ecd74b248c60e63fdc0da4441de96`
- Board/setup: 19x19; {'black': 7, 'white': 4, 'empty': 0}
- Side to move: `W`
- Current native answer(s): none
- Historical fallback evidence: `D16`
- Owner-reviewed intended answer: NOT_SPECIFIED_RECONSTRUCTION_REQUIRED
- Automatic reconstruction unsafe: OWNER_FLAGGED_SOURCE_POSITION_INCLUDES_ANSWER, NO_OWNER_APPROVED_CORRECTED_INITIAL_POSITION, NO_OWNER_APPROVED_NATIVE_ANSWER_SEQUENCE
- Likely options: REMOVE_THE_ALREADY_PLAYED_ANSWER_FROM_SETUP_AND_AUTHOR_A_NATIVE_TREE, CORRECT_SIDE_TO_MOVE_AND_AUTHOR_A_NATIVE_TREE, RECOVER_THE_PRE_CONVERSION_SOURCE_POSITION
- Exact Owner decision required: Approve the corrected initial stones, side to move, and complete native answer variation; the D16 fallback is evidence only.

## Fallback remediation boundary

- Recommended: `A_PER_RECORD_FALLBACK_REMOVAL_ONLY_AFTER_EXPLICIT_OWNER_DECISION`
- Option A: NARROWEST; existing planner can clear the exact per-record field only when a reviewed REJECT_HISTORICAL_PRECOMPUTED_FALLBACK proposal matches current evidence
- Option B: NOT_IMPLEMENTED; would require governed per-record metadata and precedence semantics
- Option C: `NOT_AUTHORIZED_AND_NOT_PROPOSED`
- Global impact audit: `NOT_RUN_BECAUSE_NO_GLOBAL_PRECEDENCE_CHANGE_IS_PROPOSED`. No global precedence change is proposed, so corpus-wide changed-verdict counts were not inferred from the bounded 71-record target snapshot.

## Reproduction

```powershell
python tools\sgf_answer_repair_batch.py --proposal-snapshot docs\planning\sgf_answer_repair_batch_001_proposal_snapshot.json --reviewed-questions D:\go-website\questions.json --current-targets D:\go-website-sgf-answer-repair-batch-001-artifacts\current_canonical_targets.json --manifest docs\planning\sgf_answer_repair_batch_001_manifest.json --safe-batch docs\planning\sgf_answer_repair_batch_001_safe_batch.json --report docs\planning\sgf_answer_repair_batch_001_dry_run.md --simulation-dir D:\go-website-sgf-answer-repair-batch-001-artifacts\isolated-repairs-phase1b
```

Run the command twice against the same immutable inputs and require byte-identical manifests, reports, safe-batch artifacts, ordering, and hashes.

## Safety assertions

    GLOBAL_JUDGING_CHANGE_IMPLEMENTED=NO
    CANONICAL_SGF_MUTATED=NO
    QUESTIONS_JSON_MUTATED=NO
    ACCEPTED_MOVES_MUTATED=NO
    PRODUCTION_DB_MUTATED=NO
    PLAYER_VERDICT_MUTATED=NO
    KATAGO_RUN=NONE
    IDENTITY_IMPLEMENTED=NO
    MERGE=NO
    DEPLOY=NO
