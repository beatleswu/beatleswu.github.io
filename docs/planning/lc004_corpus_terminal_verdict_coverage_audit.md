# LC004 — Corpus Terminal-Verdict Coverage Audit (read-only)

Branch base: d0cb7b7c5522dd6bd1f0f7282fd115460bd9f603 (LC003 HEAD)
Purpose: measure whether the current corpus carries enough explicit
authoritative terminal evidence for the LC003 canonical judge to serve the
primary learning flow after the /api/srs/review cutover.

## SNAPSHOT vs LIVE (read first)

`questions.json` does **not exist** in this worktree (`ls -la questions.json` -> not found). LC004 must not fetch or query Production. Every figure below is a **SNAPSHOT-DERIVED ESTIMATE** compiled read-only from committed repo audits — it is **not** a live measurement.

| Snapshot | Identity | Records |
|---|---|---|
| User-owned local `questions.json` | SHA-256 `88da3e43…f654ff`, 75,675,637 bytes, last write 2026-07-22 12:56:54 UTC | 42,804 |
| Production runtime corpus | provenance check 2026-08-09T10:16Z | 41,591 |

Structural/marker inventory was computed on the 42,804-record snapshot (`docs/planning/sgf_engine_reentry_audit_v1.md` §7, `docs/planning/sgf_answer_suspect_detector_v1.md` §4/§5/§10). Production is ~2.8% smaller; percentages hold, absolute counts scale down.

## How the LC003 judge decides a terminal (recap)

A leaf is `CORRECT` only if `_explicit_terminal_is_correct` honours a marker **on the reached leaf node**:
- a non-failure `RE[...]` result **on that move node** (parser sets `metadata["game_result"]` only for an `RE` on the node itself; a standard game-info `RE[...]` at the SGF root is folded into the root container, which always has children, so it is **never consulted**), or
- a `TE` (tesuji) property on the leaf, or
- a success token in the leaf's `C[...]` comment (`正解 / 正確 / 成功 / correct / success / ✓ / ✔`).

An explicit failure token yields `INCORRECT`. Otherwise a bare childless leaf yields `UNVERIFIABLE` (`leaf_without_explicit_verdict`). Multi opponent-reply -> `AMBIGUOUS`. Strict parse failure -> `MALFORMED`. These semantics are owner-locked (`FAIL_CLOSED_UNTIL_EXPLICIT_VERDICT`, `FAIL_CLOSED_NO_BLIND_CHILD0`) and LC004 does not weaken them.

## Snapshot evidence (source-cited)

`RA` = `docs/planning/sgf_engine_reentry_audit_v1.md`; `SD` = `docs/planning/sgf_answer_suspect_detector_v1.md`.

| Metric | Count | Source |
|---|---:|---|
| Total records | 42,804 | RA §7.1; SD §2 |
| Strict `parse_sgf` success | 42,641 | RA §7.3 |
| Strict parse `ValueError` failures | 163 | RA §7.3; SD §4 |
| Parseable, zero answer-tree children (empty) | 60 | RA §7.3; SD §4 |
| Exactly one root child | 40,156 | RA §7.3 |
| More than one root child | 2,425 | RA §7.3 (distribution L215-227) |
| Multiple **native** root answers (move-only, dedup) | 1,535 | SD §4 |
| Ambiguous opponent-reply structure | 489 | SD §4 |
| Records with `RE`/`GB`/`GW`/`BM`/`TE`/`DO`/`N` metadata **anywhere in tree** | 1,470 | RA §7.3 L211 |
| Records "containing parser comments" | 41 | RA §7.3 L210 |
| `accepted_moves` present | **0** | RA §7.2 |
| `katago_best_move` present (judge ignores it) | 19,502 | RA §7.2 |
| Duplicate legacy-id groups | 11 | RA §7.2 |
| SGF side-to-move: Black / White / Unknown | 39,575 / 3,017 / 212 | SD §10 |

Key qualifier: the 1,470 metadata figure unions 7 properties (5 of which the judge ignores: `GB`,`GW`,`BM`,`DO`,`N`) and counts a property *anywhere in the tree*, not on a reachable terminal. `RE` is conventionally a game-info **root** property -> not consulted. So the judge-honoured subset (an `RE` or `TE` on a reachable **leaf**, or a success comment on a leaf) is materially smaller than 1,470.

## Required results (SNAPSHOT-DERIVED ESTIMATES — not live)

| Field | Value | Band / basis |
|---|---:|---|
| CORPUS_RECORDS_TOTAL | 42,804 (snapshot) / 41,591 (Production) | exact per snapshot |
| TERMINAL_ANSWER_RECORDS | ≈ 42,580 | 42,540–42,620 (42,641 parsed − ~61 empty/no-answer) |
| EXPLICIT_SUCCESS_VERDICT_RECORDS | ≈ 450 | 150–800; hard ceiling 1,511 (1,470 ∪ 41) |
| BARE_LEAF_ONLY_RECORDS | ≈ 42,050 | 41,300–42,430 (~98.7% of terminal-answer records) |
| MALFORMED_RECORDS | 163 | exact per snapshot |
| AMBIGUOUS_TERMINAL_RECORDS | 489 | 450–550 (multi opponent-reply only; multi-root alone does NOT trigger) |
| EXPLICIT_VERDICT_COVERAGE_PERCENT | ≈ 1.1% | 0.35%–3.5% |

## Sample-through-the-judge (read-only; `judge_answer` invoked directly)

| # | Shape | Result |
|---|---|---|
| bare single-root leaf | `(;SZ[19];B[pd])` play pd | UNVERIFIABLE `leaf_without_explicit_verdict` |
| leaf `RE[B+]` | `(;SZ[19];B[pd]RE[B+])` play pd | CORRECT `explicit_terminal_verdict` |
| leaf `C[正解]` | `(;SZ[19];B[pd]C[正解])` play pd | CORRECT |
| **root-level** `RE[B+]`, bare leaf | `(;SZ[19]RE[B+];B[pd])` play pd | **UNVERIFIABLE** (root RE not consulted) |
| multi-root, both bare | `(;SZ[19](;B[pd])(;B[dp]))` play pd | UNVERIFIABLE (walks matched branch; multi-root != ambiguous) |
| multi-root, both leaves `RE` | play pd | CORRECT |
| multi opponent-reply | `(;SZ[19];B[pd](;W[dd];B[qf]RE[B+])(;W[dp];B[cf]RE[B+]))` play pd,qf | AMBIGUOUS `ambiguous_autoreply` |
| truncated | `(;SZ[19];B[pd];W[dd]` | MALFORMED `strict_parse_failed` |
| deep line unique reply, bare terminal | `(;SZ[19];B[pd];W[dd];B[qf])` play pd,qf | UNVERIFIABLE `leaf_without_explicit_verdict` |
| deep line unique reply, `RE` terminal | play pd,qf | CORRECT |
| player stops one move short | play pd only | CONTINUE `valid_partial_sequence` |
| off-tree wrong move | play qq | INCORRECT `off_answer_tree` |
| right coord, wrong colour (no PL) | W plays pd | INCORRECT `player_color_contradicts_server` (LC004) |
| bare-leaf answer + server `accepted_moves=[dd]` | B plays dd | CORRECT `accepted_authoritative_alternative` |

The shapes the snapshot is dominated by — bare single-root leaves, bare deep lines, bare multi-root, and standard root-level `RE` — all resolve `UNVERIFIABLE`.

## Verdict

**Is explicit-verdict coverage sufficient for normal primary-flow operation? NO.**

A typical learner answering a typical question reaches a bare answer-tree leaf and receives `UNVERIFIABLE`. Under the LC004 `fail_closed` cutover path that is HTTP 422 with no review recorded — a correct answer yields no SRS progress. Coverage is ~1% (ceiling 3.5%); the fail-closed rate for well-formed genuine attempts would be ~97–99%.

```
CUTOVER_STATUS = BLOCKED_TERMINAL_VERDICT_COVERAGE
```

`SRS_REVIEW_NO_ATTEMPT_POLICY` must remain `legacy`. The LC004 cutover mechanism (frontend attempt transport + server `fail_closed` policy + server-authored player colour) is built and tested but its enforcement is gated OFF.

## Remediation population (later content/SGF task — out of LC004 scope)

**BARE_LEAF_ONLY_RECORDS ≈ 42,050** (band 41,300–42,430; ~40,850 pro-rated to Production). Each needs an explicit judge-honoured terminal marker authored onto the reachable terminal node(s) of its answer line: a non-failure `RE[...]` on the terminal move node, a `TE[]` on it, or a success-token `C[...]` comment on the terminal leaf.

Sub-populations needing distinct handling:
- 163 MALFORMED — source re-supply / SGF repair, not marker injection.
- ~61 empty / no-answer trees — unanswerable content gaps.
- 489 ambiguous opponent-reply — the reply must be disambiguated **and** a terminal marker added.
- 1,286 duplicate-coordinate root branches + 1,535–2,425 multi-root — each surviving branch needs its own terminal marker.
- 11 duplicate-legacy-id groups — fail closed (409) at runtime until `source_record_uuid` lands.
- 212 records with no SGF colour signal — LC004 falls back to the client-stated colour for those (documented limitation; server-authored colour applies only when the SGF supplies `PL` or a first move).

This aligns with the existing `SGF-ANSWER-REVIEW-QUEUE-001` recommendation and the LC001 suspect-detector plan.
