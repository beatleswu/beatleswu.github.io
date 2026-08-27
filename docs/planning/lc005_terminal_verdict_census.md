# LC005 — Terminal-Verdict Corpus Remediation Census + Dry-Run

Branch base: b77d1707379c128fab70a01fa11a70250e9f59d4 (LC004 HEAD)
Type: content-contract remediation PLANNING. **No corpus mutation. No markers applied. LC004 not enabled. Leaf semantics not weakened.**

Artifacts:
- `tools/lc005_terminal_verdict_census.py` — deterministic read-only classifier + CLI
- `tests/test_lc005_terminal_verdict_census.py` — classifier + judge-regression tests
- `docs/planning/lc005_terminal_verdict_repair_manifest.json` — dry-run manifest (schema + rule + representative samples; **no live corpus present** — see §2)

## 1. Corpus authority

| Field | Value | Source |
|---|---|---|
| CANONICAL_CORPUS_SOURCE | `canonical/current/questions.json` (runtime `/app/data/questions.json`), repo `beatleswu/beatleswu.github.io` | `docs/planning/sgf_answer_current_canonical_contract_v2/source-provenance.json`, `current-baseline-receipt.json` |
| SOURCE_SCOPE | **SNAPSHOT** — an immutable, byte-verified read-only snapshot; the live corpus file is **absent from this worktree** (`ls questions.json` → not found). Production must not be queried. | LC004 / LC4-B; `source-provenance.json` `source_status: IMMUTABLE_SNAPSHOT_BYTE_VERIFIED` |
| CORPUS_VERSION | `890f9b1d9f6eb3a4e38e5b74a9062f1d66d59a07:88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` (`source_commit_or_snapshot_id`) | `source-provenance.json` |
| CORPUS_HASH | `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` (size 75,675,637 bytes) | `source-provenance.json`, `repair-batch-manifest.json` |
| CORPUS_RECORD_COUNT | **42,804** (snapshot) / 41,591 (Production provenance check 2026-08-09) | `source-provenance.json` `source_record_count`; `sgf_answer_repair_batch_001_dry_run.md` |

No committed per-record structural index exists. All population figures below are **SNAPSHOT-DERIVED ESTIMATES** from committed audits (`sgf_engine_reentry_audit_v1.md` §7, `sgf_answer_suspect_detector_v1.md` §4/§10), refined against the LC003 judge's exact terminal semantics. They are not a live measurement.

## 2. Why this is a dry-run schema, not a full 42k census

`questions.json` is not in the worktree and LC005 must not fetch or query Production. The deliverable is therefore:
1. a **deterministic classifier** (`classify_record`) that places any record in exactly one of the 9 classes and computes the dry-run marker action;
2. a **mechanically-testable SAFE_AUTO rule** (§5) proven by `tests/test_lc005_terminal_verdict_census.py` on synthetic records covering every class;
3. a **manifest** carrying the classifier output over a representative sample set + the rule spec + the exact command to produce the full manifest once a snapshot is supplied.

`python -m tools.lc005_terminal_verdict_census --snapshot <questions.json> --snapshot-sha256 88da3e43… --out-manifest <path>` produces the full 42,804-row census in one deterministic pass.

## 3. Existing terminal-marker conventions (SNAPSHOT-DERIVED)

The LC003 judge honours a terminal `CORRECT` only from a marker **on the reachable terminal node**: a non-failure `RE[...]` result on the node, a `TE` property on the node, or a success token (`正解 / 正確 / 成功 / correct / success / ✓ / ✔`) in the node's `C[...]` comment. An explicit failure token → `INCORRECT`.

| Field | Estimate | Basis |
|---|---:|---|
| RE_SUCCESS_COUNT (records with a non-failure `RE`, anywhere in tree) | ≈ 1,300–1,450 of the 1,470 "RE/GB/GW/BM/TE/DO/N metadata" records | `sgf_engine_reentry_audit_v1.md` §7.3 L211 (1,470 union of 7 props). Judge-honoured only when the `RE` sits on the **terminal move node**; the SGF-standard game-info-root `RE[...]` is folded into the parser's root container (never a leaf) and is **not** read — LC4-B verified this. |
| — of which on the reachable terminal (judge-honoured today) | ≈ 300–800 (point ≈ 450) | subset; most `RE` is at the game-info root |
| — of which at the game-info root only (mis-located) | ≈ 500–1,000 | the SAFE_AUTO population (§5) |
| TE_SUCCESS_COUNT | small (tens–low hundreds) | `TE` is inside the 1,470 union; rarely used in PDF-converted tsumego |
| COMMENT_SUCCESS_COUNT (success token in a terminal `C[...]`) | ≤ 41 | `sgf_engine_reentry_audit_v1.md` §7.3 L210 ("records containing parser comments": 41); this is the ceiling for any comment-based marker |
| EXPLICIT_FAILURE_COUNT (authored failure annotation) | small; subset of the above | failure-`RE` or failure comment tokens |

Convention verdict: **MIXED**. The corpus mixes (a) SGF-standard game-info-root `RE` (dominant, but not judge-honoured), (b) a small set of terminal-node `RE`/`TE` (judge-honoured), and (c) a very small set of `C[正解]`-style comments. There is **no single authored convention** for "this terminal is the solution", and — critically — no documented corpus-generation convention that the bare answer-tree terminal alone denotes success (the PDF→SGF→KataGo pipeline in `sgf_engine_reentry_audit_v1.md` §9.1 produced answer *lines*, not success *annotations*).

`OWNER_MARKER_DECISION_REQUIRED = YES` — see §11.

## 4. Classification schema (9 classes; exactly one per record)

Precedence order in `classify_record`: MALFORMED_SOURCE → EMPTY_OR_UNANSWERABLE → COLOR_AUTHORITY_INCOMPLETE → AMBIGUOUS_AUTOREPLY → ALREADY_EXPLICIT → (bare terminal) → DUPLICATE_IDENTITY_BLOCKED → SAFE_AUTO_CANDIDATE → MANUAL_SEMANTIC_REVIEW → OTHER_BLOCKED.

| Class | Meaning | SNAPSHOT-DERIVED estimate (of 42,804) |
|---|---|---:|
| ALREADY_EXPLICIT | judge returns a definite verdict at the terminal today (honoured success marker, honoured failure marker, or server `accepted_moves`). `accepted_moves` present in snapshot: **0**. | ≈ 450 (band 150–800) — all via terminal `RE`/`TE`/comment |
| SAFE_AUTO_CANDIDATE | bare terminal(s) + an existing non-failure game-info-root `RE[...]` + deterministic line + colour-resolvable + unique id + no conflicting marker (§5) | ≈ 500–1,000 (point ≈ 800) |
| MANUAL_SEMANTIC_REVIEW | bare terminal(s), no existing success annotation anywhere; a human must decide | ≈ 40,000–40,800 (the bulk) |
| AMBIGUOUS_AUTOREPLY | a reachable line has a non-unique opponent reply → judge returns AMBIGUOUS | ≈ 489 (band 450–550) |
| MALFORMED_SOURCE | strict parse raises | **163** (exact per snapshot) |
| EMPTY_OR_UNANSWERABLE | parses but no reachable player-move terminal | ≈ 60–61 |
| DUPLICATE_IDENTITY_BLOCKED | legacy id shared by >1 record → auto-repair unsafe until `source_record_uuid` | ≈ 22 (11 groups) |
| COLOR_AUTHORITY_INCOMPLETE | no `PL` and no first-move colour signal on a root child | ≈ 212 |
| OTHER_BLOCKED | residual (should be 0) | 0 |

CLASSIFICATION_TOTAL == INPUT_RECORD_TOTAL by construction (`run_census` asserts `classification_accounting_pass`); tested in `TestClassificationAccounting`.

Records may additionally carry non-reclassifying `blockers` (e.g. an ALREADY_EXPLICIT record that is also in a duplicate-id group → `blockers: ["duplicate_legacy_id"]`) so no information is lost.

## 5. SAFE_AUTO_CANDIDATE rule (mechanically testable)

`SAFE_AUTO_RULE` = **ROOT_RE_PROPAGATION**. A record is SAFE_AUTO_CANDIDATE iff ALL of:
1. strict-parses; non-empty; has ≥1 reachable player-move terminal;
2. every reachable line is **deterministic** — no ambiguous opponent reply (else AMBIGUOUS_AUTOREPLY);
3. the expected player colour is server-resolvable (root `PL` or first authored move);
4. its legacy id is unique (not in a duplicate-id group);
5. NO reachable terminal already carries a judge-honoured marker AND no authored failure annotation appears anywhere;
6. it carries an **existing** explicit non-failure success annotation elsewhere in the same record — specifically a game-info-root `RE[...]` whose value contains no failure token.

This is **not** "bare leaf == safe" — condition 6 requires a pre-existing authored `RE` success result; a bare terminal with no `RE` → MANUAL_SEMANTIC_REVIEW (tested: `test_bare_leaf_alone_is_never_safe_auto`). The evidence is "explicit success semantics elsewhere in the same source record" (an allowed basis per the task) — the annotation exists, it is merely mis-located for the parser/judge.

`SAFE_AUTO_RULE_TESTABLE = YES` — `tools/lc005_terminal_verdict_census.classify_record` + `tests/test_lc005_terminal_verdict_census.py` (`TestSafeAutoRuleIsConservative`, 5 cases).

### Proposed marker action (NOT applied)

`PROPOSED_MARKER_TYPE = RE` (propagated). `PROPOSED_MARKER_VALUE` = the record's **own** root `RE[<value>]`, verbatim — no value is invented. Action: copy `RE[<value>]` onto every reachable bare terminal move node. Dry-run only; `applied: false` on every manifest entry (tested: `test_proposed_action_is_dry_run_only`).

Judge effect, proven: `(;GM[1]SZ[19]RE[B+];B[pd])` → UNVERIFIABLE today; `(;GM[1]SZ[19]RE[B+];B[pd]RE[B+])` (after propagation) → CORRECT (`test_safe_auto_projected_judge_result_after_marker`).

## 6. Ambiguous auto-reply sub-split (AMBIGUOUS_AUTOREPLY ≈ 489)

Owner lock preserved: `AMBIGUOUS_AUTOREPLY_SEMANTICS = FAIL_CLOSED_NO_BLIND_CHILD0`. `children[0]` is never selected.

| Sub-tag | Meaning | Estimate |
|---|---|---:|
| TRUE_AMBIGUOUS_REPLY | a post-player node has >1 opponent-coloured child | ≈ 489 (`sgf_answer_suspect_detector_v1.md` §4 "ambiguous opponent-reply structure") |
| MULTI_ROOT_BUT_RESOLVABLE | >1 root child, but each root branch is its own deterministic line — the judge walks the matched branch, so these are **not** AMBIGUOUS | ≈ 1,935–2,336 (of the 2,425 multi-root records; the judge handles them like any single-root record per LC4-B samples S6/S7) |
| OTHER_BRANCHING_SHAPE | sole "reply" is a same-colour move / a move-less child; duplicate-coordinate root branches | ≈ 1,286 duplicate-coordinate root branches (`SD` §4) + a small same-colour-reply set |

The classifier reports these sub-tags; only TRUE_AMBIGUOUS_REPLY and OTHER_BRANCHING_SHAPE land in AMBIGUOUS_AUTOREPLY. Remediation for a TRUE_AMBIGUOUS_REPLY record requires the reply to be disambiguated in source **and** a terminal marker added — it is never auto-repaired.

## 7. Malformed / empty sub-split

| Sub-tag | Estimate | Remediation |
|---|---:|---|
| MALFORMED_SGF (invalid property identifier at a recorded offset) | bulk of the 163 | source re-supply or a reviewed SGF structural edit |
| TRUNCATED_SGF (unbalanced parens / unterminated value / incomplete escape) | subset of 163 | source re-supply |
| INVALID_COORDINATE (invalid move coord under strict parse) | subset of 163 | reviewed SGF edit |
| OTHER_PARSE_FAILURE | residual of 163 | manual inspection |
| EMPTY_TREE (root has no children) | ≈ 60 | classify as unanswerable / content gap — never marked |
| MISSING_ANSWER_TREE (children exist but no reachable move terminal) | ≈ 1 (`SD` §4 "61 no valid root answer" = 60 empty + 1 non-move root) | content gap |

**None of these receive an automatic success marker.** Total ≈ 163 + 61 = 224 records needing source-level work.

## 8. Identity

Owner lock: `CANONICAL_FUTURE_IDENTITY = source_record_uuid`. LC005 does **not** implement UUID migration/backfill and generates **no** request-time UUID (`REQUEST_TIME_UUID_CREATED = NO`; the classifier passes `source_record_uuid` straight through as `null`).

| Field | Value |
|---|---:|
| DUPLICATE_LEGACY_ID_GROUPS | 11 (`sgf_engine_reentry_audit_v1.md` §7.2; `canonical_learning_judge.py` comment) |
| DUPLICATE_RECORD_COUNT | ≈ 22 (11 groups, 11 "extra" records — `RA` §7.2 L184-186) |
| AUTO_REPAIR_BLOCKED_BY_IDENTITY | every bare-terminal record whose legacy id is in a duplicate group → DUPLICATE_IDENTITY_BLOCKED. A marker cannot be safely auto-injected without knowing which of the shared-id records it targets. |

The prior repair-batch (`sgf_answer_repair_batch_001_dry_run.md`) handled 6 duplicate groups / 11 fan-out records with per-record `selected_record_index` disambiguation and 0 conflicts — the same discipline applies here once markers are proposed.

## 9. Colour authority

For records lacking `PL` and any first-move colour signal, no colour is invented.

| Field | Value | Basis |
|---|---:|---|
| SERVER_COLOR_RESOLVABLE | ≈ 42,592 (Black 39,575 + White 3,017) | `sgf_answer_suspect_detector_v1.md` §10 |
| COLOR_SILENT | ≈ 212 | `SD` §10 "Unknown" side-to-move |
| COLOR_REPAIR_REQUIRED | ≈ 212 → COLOR_AUTHORITY_INCOMPLETE; each needs an authored `PL[...]` (or a colour-bearing first move) added in source before any terminal-marker repair |

## 10. Dry-run repair manifest

`MANIFEST_PATH = docs/planning/lc005_terminal_verdict_repair_manifest.json`. Each entry: `locator` (`AUDIT_LOCATOR_ONLY`: snapshot_sha256 + record_index + legacy_question_id + content_sha256 + source_path — never legacy integer id alone), `legacy_question_id`, `record_index`, `source_record_uuid` (`null`), `content_sha256`, `classification`, `subtag`, `current_terminal_semantics`, `proposed_marker_action` (`applied: false`), `evidence_basis`, `confidence_class`, `manual_review_required`, `blockers`, `reason_code`.

Because the live corpus is absent, the committed manifest carries `corpus_status: LIVE_CORPUS_ABSENT_FROM_WORKTREE__SCHEMA_RULE_AND_SAMPLES_ONLY` and the classifier's output over a **representative sample set** (24 records spanning all 9 classes), plus the SAFE_AUTO rule spec and the one-line command to produce the full 42,804-row manifest from a snapshot.

## 11. Owner marker decision

`OWNER_MARKER_DECISION_REQUIRED = YES`. Multiple conventions are plausible for the ~40k MANUAL population (the SAFE_AUTO population has a defensible minimal choice — propagate the record's own `RE` — but the bulk does not):

| Option | Pro | Con |
|---|---|---|
| A. Terminal `RE[<result>]` | SGF-standard result property; already the judge's primary channel | needs an owner-decided value per record (`B+`/`W+`/…); many records have no authored result to copy |
| B. Terminal `TE[1]` (tesuji) | single fixed value; unambiguous "good move" | semantically "good move", not "problem solved"; rare in the corpus |
| C. Terminal `C[正解]` comment | matches the small existing tsumego-authoring convention | free-text; brittle; token set must be owner-fixed |
| D. A new dedicated property (e.g. `GX[SOLVED]`) | explicit, unambiguous, greppable | requires a judge change to honour it (out of LC005 scope; would reopen LC003) |

LC005 does **not** choose. For SAFE_AUTO_CANDIDATE it proposes only the minimal-assumption action (relocate the record's own existing `RE`). For MANUAL_SEMANTIC_REVIEW the marker convention is an explicit owner input to the follow-on content task.

## 12. Coverage projection

Denominator = TERMINAL_ANSWER_RECORDS ≈ 42,580 (42,804 − ~163 malformed − ~61 empty).

| Field | Value |
|---|---:|
| CURRENT_EXPLICIT_VERDICT_COVERAGE | ≈ 1.06% (≈ 450 / 42,580) |
| PROJECTED_AFTER_SAFE_AUTO | ≈ 2.9% (≈ (450 + 800) / 42,580); band 1.5–4% |
| PROJECTED_AFTER_MANUAL_REVIEW (best case: every MANUAL record confirmed a success and marked) | ≈ 97.8% ((42,580 − 489 ambiguous − 22 dup-id − 212 colour) / 42,580) |
| REMAINING_BLOCKED_RECORDS | ≈ 947 (489 ambiguous + 224 malformed/empty + 22 dup-id + 212 colour) — these need source-level remediation, not marker injection; not resolvable by the terminal-marker task alone |

Usable share of the active primary-learning corpus under LC003 fail-closed semantics: **~1% today → ~3% after SAFE_AUTO → up to ~98% only after a full manual-review pass of the ~40k MANUAL population**. 100% is not reachable while the ~947 blocked records exist. LC004 stays BLOCKED until at least the MANUAL pass reaches an owner-set coverage threshold.

## 13. Sample dry-run diffs (conceptual; no source writes)

### SAFE_AUTO_CANDIDATE (5)
| Before | After (proposed, not applied) |
|---|---|
| `(;GM[1]SZ[19]RE[B+];B[qq];W[pp];B[qp])` | `(;GM[1]SZ[19]RE[B+];B[qq];W[pp];B[qp]RE[B+])` |
| `(;GM[1]SZ[19]RE[B+];B[ee])` | `(;GM[1]SZ[19]RE[B+];B[ee]RE[B+])` |
| `(;GM[1]SZ[19]RE[W+];W[cp];B[eq];W[dq])` | `…;W[dq]RE[W+])` |
| `(;GM[1]SZ[19]RE[B+T];B[rb];W[ra];B[qa])` | `…;B[qa]RE[B+T])` |
| `(;GM[1]SZ[19]RE[Black];B[cd])` | `…;B[cd]RE[Black])` (value copied verbatim; not normalised) |

### MANUAL_SEMANTIC_REVIEW (5)
| Record | Why manual |
|---|---|
| `(;SZ[19];B[cc];W[dd];B[cd])` | bare deep line; no `RE` anywhere; a human must confirm `B[cd]` is the solve and choose a marker |
| `(;SZ[19];B[pd])` | bare single leaf; no annotation |
| `(;SZ[19];B[pd];W[dd];B[qf];W[nc];B[qi])` | bare 5-ply line; no annotation |
| `(;SZ[19]GB[1];B[pd])` | `GB` (good-for-black) is NOT judge-honoured; needs a proper terminal marker |
| `(;SZ[19];B[pd]N[Solution])` | `N` (node name) is NOT judge-honoured |

### AMBIGUOUS_AUTOREPLY (5)
| Record | Sub-tag |
|---|---|
| `(;SZ[19];B[sf](;W[se];B[re])(;W[rd];B[qc]))` | TRUE_AMBIGUOUS_REPLY — two W replies after `B[sf]` |
| `(;SZ[19];B[pd](;W[dd])(;W[dp]))` | TRUE_AMBIGUOUS_REPLY |
| `(;SZ[19];B[pd];B[qf]RE[B+])` | OTHER_BRANCHING_SHAPE — sole "reply" is same-colour |
| duplicate-coordinate root branch (`SD` §4: 1,286) | OTHER_BRANCHING_SHAPE |
| >2 opponent replies | TRUE_AMBIGUOUS_REPLY |
Remediation: disambiguate the reply in source, then treat as MANUAL. Never auto-marked.

### MALFORMED / EMPTY (5)
| Record | Class / sub-tag | Remediation |
|---|---|---|
| `(;SZ[19];B[dd]` | MALFORMED_SOURCE / TRUNCATED_SGF | source re-supply |
| `(;SZ[19];B[pd]4[bad])` | MALFORMED_SOURCE / MALFORMED_SGF | reviewed SGF edit |
| `not an sgf at all` | MALFORMED_SOURCE / OTHER_PARSE_FAILURE | source re-supply |
| `(;SZ[19]AB[dd][pd])` | EMPTY_OR_UNANSWERABLE / EMPTY_TREE | unanswerable — content gap, never marked |
| `(;SZ[19]AB[dd];W[])` | EMPTY_OR_UNANSWERABLE (pass-only) | content gap |

## 14. Judge regression (representative records through canonical_learning_judge)

| Check | Result | Test |
|---|---|---|
| ALREADY_EXPLICIT_REGRESSION | PASS — `RE[B+]` on terminal → CORRECT | `test_already_explicit_regression_pass` |
| SAFE_AUTO_PROJECTED_JUDGE_RESULT | PASS — bare → UNVERIFIABLE; after propagated `RE` → CORRECT | `test_safe_auto_projected_judge_result_after_marker` |
| AMBIGUOUS_REMAINS_FAIL_CLOSED | PASS — two opponent replies → AMBIGUOUS | `test_ambiguous_remains_fail_closed` |
| MALFORMED_REMAINS_FAIL_CLOSED | PASS — truncated SGF → MALFORMED | `test_malformed_remains_fail_closed` |
| BARE_UNREPAIRED_REMAINS_UNVERIFIABLE | PASS — bare leaf → UNVERIFIABLE | `test_bare_unrepaired_remains_unverifiable` |

The judge was **not** modified. LC005 changes no runtime code.

## 15. Follow-on (content task; not LC005)

1. Owner marker decision (§11) for the MANUAL population.
2. Run `tools/lc005_terminal_verdict_census.py` against the pinned snapshot to produce the full 42,804-row manifest.
3. SAFE_AUTO_CANDIDATE batch: propose the ~800 root-`RE` propagations, owner-review, apply through the governed content-release path (the same one the prior repair batch used), never a bulk file rewrite.
4. MANUAL_SEMANTIC_REVIEW: board-first review queue over the ~40k population, batched into governed content releases.
5. Source-level fixes for MALFORMED (163), EMPTY (61), COLOR_SILENT (212), duplicate-id (22), TRUE_AMBIGUOUS_REPLY (489).
6. Only when coverage clears an owner threshold: enable `SRS_REVIEW_NO_ATTEMPT_POLICY=fail_closed` and `window.__LC004_ATTEMPT_TRANSPORT` (LC004 cutover).
