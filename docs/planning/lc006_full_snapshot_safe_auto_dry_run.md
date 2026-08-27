# LC006 — Full-Snapshot SAFE_AUTO Terminal-Verdict Dry-Run

Branch base: `c48251d5e8c8332c250b0438e5376b851052d1c2` (stated PARENT_HEAD; LC005 line)
Type: **exact measurement + dry-run**. No corpus mutation. No markers applied. No
Production query. Leaf semantics unchanged. LC005 SAFE_AUTO rule unchanged.

This replaces every **SNAPSHOT-DERIVED ESTIMATE** band in
[`lc005_terminal_verdict_census.md`](lc005_terminal_verdict_census.md) with an
**exact count** obtained by running the unmodified LC005 classifier over the full
byte-verified canonical snapshot.

Artifacts:
- `tools/lc006_full_snapshot_safe_auto_dry_run.py` — hash-gate + full-snapshot driver + judge before/after simulation
- `tests/test_lc006_full_snapshot_safe_auto_dry_run.py` — hash-gate, judge-simulation, reclassification, manifest-shape tests (synthetic data; the 42k run is not reproducible in-tree because the snapshot is untracked)
- `docs/planning/lc006_full_snapshot_safe_auto_manifest.json` — the SAFE_AUTO manifest (see §4) + full exact census metadata

## 1. Snapshot identity — hash-verified

| Field | Value |
|---|---|
| SNAPSHOT_BASENAME | `questions.json` (untracked; main-checkout root; **absent from this worktree's git tree**) |
| EXPECTED_SNAPSHOT_SHA256 | `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` |
| MEASURED_SNAPSHOT_SHA256 | `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` |
| SNAPSHOT_HASH_MATCH | **YES** (exact) |
| SNAPSHOT_SIZE_BYTES | 75,675,637 |
| CORPUS_RECORD_COUNT | **42,804** (JSON list; matches provenance `source_record_count`) |

The driver refuses to run against any file that does not hash-match
(`SNAPSHOT_HASH_MISMATCH → SystemExit`, no substitution). Verified by
`tests/test_lc006_full_snapshot_safe_auto_dry_run.py::TestSnapshotHashGate`.

## 2. Exact census — all 9 classes (of 42,804)

| Class | LC005 estimate | **LC006 exact** | Subtags (exact) |
|---|---:|---:|---|
| ALREADY_EXPLICIT | ≈ 450 (150–800) | **1** | TERMINAL_SUCCESS_MARKER 1 — **substring false-positive, see §5** |
| SAFE_AUTO_CANDIDATE | ≈ 800 (500–1,000) | **0** | — |
| MANUAL_SEMANTIC_REVIEW | ≈ 40,000–40,800 | **41,830** | 1,066 of these carry a `C[...]` comment a reviewer can read |
| AMBIGUOUS_AUTOREPLY | ≈ 489 (450–550) | **731** | TRUE_AMBIGUOUS_REPLY 703 / OTHER_BRANCHING_SHAPE 28 |
| MALFORMED_SOURCE | 163 (exact) | **163** | MALFORMED_SGF 158 / TRUNCATED_SGF 3 / OTHER_PARSE_FAILURE 2 |
| EMPTY_OR_UNANSWERABLE | ≈ 60–61 | **66** | EMPTY_TREE 60 / MISSING_ANSWER_TREE 6 |
| DUPLICATE_IDENTITY_BLOCKED | ≈ 212 | **13** | (11 duplicate-legacy-id groups, 22 records: 13 bare-terminal → blocked here, 6 → AMBIGUOUS, 3 → MALFORMED) |
| COLOR_AUTHORITY_INCOMPLETE | ≈ 212 (shared band) | **0** | see §6 |
| OTHER_BLOCKED | 0 | **0** | — |
| **CLASSIFICATION_TOTAL** | | **42,804** | **CLASSIFICATION_ACCOUNTING_PASS = YES** (1 + 0 + 41,830 + 731 + 163 + 66 + 13 + 0 + 0) |

MALFORMED_SOURCE (163) and EMPTY_TREE (60) match `sgf_engine_reentry_audit_v1.md`
§7.3 exactly — same strict parser, independent confirmation the run is sound.

## 3. Why the estimates were optimistic — the corpus has ~no terminal markers

LC005's `RE`/`TE`/comment estimates were derived from
`sgf_engine_reentry_audit_v1.md` §7.3's "1,470 records with
`RE∪GB∪GW∪BM∪TE∪DO∪N` metadata anywhere". Direct measurement of the snapshot:

| Probe | Exact result |
|---|---:|
| records with `RE[` substring anywhere in `content` | **9** |
| — of those, `RE` value after strict parse | **all `RE[]` — empty**; `root.metadata["game_result"] == ""` for every one; 0 on any move node |
| records with a non-empty game-info-root `RE[...]` (the SAFE_AUTO input) | **0** |
| records with `TE[` substring | **0** |
| records with `TE` on a reachable terminal | **0** |

The 1,470 union is overwhelmingly `GB`/`GW`/`BM`/`N` (none of which the judge
reads). The nine `RE[]` records are Lizzie-exported game-info headers with an
empty result field. **There is no `RE` value anywhere in the corpus to
propagate**, so the LC005 SAFE_AUTO rule (ROOT_RE_PROPAGATION) — preserved here
byte-for-byte — matches **zero** records. This is not a classifier defect; it is
the corpus's actual state.

## 4. SAFE_AUTO manifest + dry-run judge validation

`SAFE_AUTO_EXACT_COUNT = 0`. The manifest
(`docs/planning/lc006_full_snapshot_safe_auto_manifest.json`,
sha256 `9044d26b85358a5a03c47a615dcf82ec04af3e48179081320c1a2a1679b4a56c`)
carries `"safe_auto_candidates": []` plus the full exact census metadata.

`SAFE_AUTO_PROJECTED_JUDGE_PASS_RATE = 100%` is **vacuous (0 / 0)** on the real
corpus. The before/after judge-simulation mechanism it certifies is, however,
implemented and proven on synthetic candidates:

| Check (synthetic) | Result |
|---|---|
| genuine ROOT_RE_PROPAGATION candidate → `judge_answer` BEFORE | **UNVERIFIABLE** (`leaf_without_explicit_verdict`) |
| same, AFTER `RE[<root value>]` copied onto the reached bare terminal | **CORRECT** (`explicit_terminal_verdict`) |
| candidate LC005 flags SAFE_AUTO but the stricter judge sim cannot confirm | **reclassified → MANUAL_SEMANTIC_REVIEW** (`safe_auto_reclassified_manual` counter) |

So had any real candidate existed, each would have been independently re-judged
and any that did not go UNVERIFIABLE → CORRECT would have been dropped to MANUAL,
guaranteeing the 100% by construction rather than by assertion.

Per-row manifest schema (unused this run, one row per candidate):
`snapshot_sha256, record_index, legacy_question_id, source_record_uuid,
content_sha256, root_RE, player_colour, terminal_locators, proposed_action
{action, marker_property=RE, marker_value, targets, after_content_sha256},
reason_code, confidence, judge_before=UNVERIFIABLE, judge_after_projected=CORRECT,
applied=false`.

## 5. The single ALREADY_EXPLICIT record is a substring false-positive

`record_index 17147`, `legacy_question_id 8023`. The classifier honoured it via a
`_SUCCESS_COMMENT_TOKENS` match (`正解`) on a reachable terminal comment. On
inspection the record has two root variations:

- `(;W[ob]N[正解] …)` — labelled "correct solution", line ends at a **bare**
  terminal `B[ra]` (no marker).
- `(;W[ob]N[参考] …)` — labelled "参考" ("reference / for comparison"), line ends
  at `B[qb]` with `C[黑地虽然和正解一样，但白增加4目。]` ("Black's territory is the
  same as *the correct solution*, but White gains 4 points").

The honoured token `正解` sits in a comment on the **reference** variation whose
own text says that line is *worse* than the solution. The judge's substring
comment matcher (`tok in comment`) cannot tell "正解" used as a success label from
"正解" used as a noun inside an explanatory sentence.

Consequences:
- **CURRENT_EXPLICIT_VERDICT_COVERAGE (mechanical) = 1 / 42,575 = 0.002349 %**
- **VERIFIED_TRUE_EXPLICIT_VERDICT_COVERAGE = 0 / 42,575 = 0.000 %**

LC006 reports the mechanical figure (it is the exact classifier output the spec
asked for) and flags the correction. **Fixing the matcher changes judge
semantics** — anchoring `_SUCCESS_COMMENT_TOKENS`, honouring `N[正解]` on a node
as a marker, or excluding comments that also reference 正解 as a noun — and is an
**owner semantics decision**, out of scope for this measurement task
(`OWNER_MARKER_DECISION_REQUIRED = YES`).

## 6. COLOR_AUTHORITY_INCOMPLETE = 0 is correct for this corpus

`_server_expected_player_color` returns `None` only when the SGF has neither a
root `PL[...]` nor any first-move colour. Every such record in the snapshot has
**no root children at all** (empty / setup-only tree) and is therefore already
classified `EMPTY_OR_UNANSWERABLE` at an earlier precedence step. Zero records
reach the colour-authority check unresolved. The `suspect_detector` §10 "≈ 212
unknown side-to-move" figure resolves, under judge-consistent classification, to
163 parse failures + ~49 empty/answerless trees — all counted elsewhere.

## 7. Coverage projections (exact)

| Metric | Value |
|---|---|
| TERMINAL_ANSWER_RECORDS (42,804 − 163 MALFORMED − 66 EMPTY) | 42,575 |
| CURRENT_EXPLICIT_VERDICT_COVERAGE (mechanical) | 1 / 42,575 = **0.002349 %** |
| CURRENT_EXPLICIT_VERDICT_COVERAGE (verified, §5) | 0 / 42,575 = **0.000 %** |
| SAFE_AUTO_EXACT_COUNT | **0** |
| PROJECTED_AFTER_SAFE_AUTO | (1 + 0) / 42,575 = **0.002349 %** (no change) |
| MANUAL_REVIEW_REMAINING | **41,830** |
| SOURCE_LEVEL_BLOCKED_REMAINING (AMBIGUOUS 731 + MALFORMED 163 + EMPTY 66 + DUP 13 + COLOR 0 + OTHER 0) | **973** |
| best-case coverage if the entire MANUAL population is adjudicated | (42,575 − 973) / 42,575 = **97.714 %** |

## 8. What this means for the Learning Core

The automated remediation lever LC005 sized at ~800 records is **empty**. Every
one of the 41,830 MANUAL records needs a human (or an owner-approved
policy) to decide what "solved" means for that answer tree — the corpus was
generated as answer *lines*, not annotated verdicts, and it carries no usable
`RE`/`TE`/comment success markers. The FAIL_CLOSED_UNTIL_EXPLICIT_VERDICT judge
(LC003) therefore returns `UNVERIFIABLE` for ~98 % of the corpus on the primary
attempt path today, and **no mechanical step in scope moves that number**. The
next decision is an owner marker-policy decision, not another classifier pass.

LC006 does **not** choose that policy.
