# LC004 — Primary SRS Attempt Transport + Legacy Authority Cutover

Branch: claude/lc004-srs-attempt-transport-cutover (base d0cb7b7c5, LC003 HEAD)
Parent LC003 pushed to origin/claude/lc003-canonical-judge-srs-authority.

## Goal

Wire the real frontend to send factual attempt data so the LC003 canonical
judge is the sole grade basis on the primary learning flow, and remove the
client self-reported grade as correctness authority — **subject to** a
read-only corpus terminal-verdict coverage check.

## 1. Client caller recon (LC4-A)

`POST /api/srs/review` has **3** distinct browser call paths across 2 pages, funnelled through 1 shared transport:

| # | Caller | Class | Body today | Grade source | Sends moves/colour/transform? |
|---|---|---|---|---|---|
| 1 | `index.html:9385` `submitSRS()` -> `SRS.review()` -> `ReviewTransport.legacyReview()` | ACTIVE_PRIMARY | 8 keys (question_id, grade, unit_name, unit_done, response_ms, source_context, training_set_id, is_scaffolding) | literal `3` (client SGF leaf-walk in `onBoardClick`) or `0` (Boss wrong) | NO |
| 2 | `index.html:11616` `ReviewTransport.review(observerCommand)` | ACTIVE_SECONDARY | same 8 keys, `grade:0` | literal `0` on first wrong move | NO |
| 3 | `mistakes.html:1308` raw `fetch('/api/srs/review')` | ACTIVE_SECONDARY / near-LEGACY | 2 keys (question_id, grade) | literal `3` (client leaf-walk) | NO |

- `SRS_REVIEW_CLIENT_CALLERS` = 3
- `PRIMARY_FRONTEND_CALLER` = `index.html` `submitSRS` -> `SRS.review` -> `ReviewTransport.legacyReview` -> POST
- `CURRENT_REQUEST_BODY` (primary) = `{question_id, grade, unit_name, unit_done, response_ms, source_context, training_set_id, is_scaffolding}`; `submission_id` supported by the transport, never sent by any browser caller
- `CURRENT_GRADE_SOURCE` = pure client-side walk of the parsed SGF answer tree in `onBoardClick` (`index.html:11588-11658`); literal `3` at a leaf, `0` on a miss. No server judging.
- `CURRENT_QUESTION_ID_SOURCE` = `currentQ.id` / `currentMistake.question_id`
- `CURRENT_MOVE_SOURCE` = none for normal practice (only `_mapBattleV1Moves`, and that mode reroutes to `/api/adventure/map-battles/v1/answers`)
- `CURRENT_TRANSFORM_SOURCE` = none; `_cropInfo` (`_ox`/`_oy`) is a crop/pan offset, not a rotation. So attempt facts carry `transform: "identity"` and canonical-space moves.
- `CURRENT_PLAYER_COLOR_SOURCE` = global `playerColor` = `(currentProblem.pl) || currentQ.player_color || 'B'` — already server-derived
- Post-response: index.html re-derives its own advance/counter UI from the **client** `grade` var (`if(grade===0){resetProblem()}else{nextQuestion()}`, `if(grade>=3)_todayCorrect++`). A full cutover requires the frontend to read the server verdict from the response instead — part of the blocked follow-on.
- Non-browser callers: tests only. No other services.

## 2. Attempt transport contract

`js/game/review_transport.js` — `buildRequest` now forwards a **sanitized** `attempt` object; `legacyReview` threads `metadata.attempt` through.

`ATTEMPT_PAYLOAD_CONTRACT` = `{ moves: [{x,y}...], player_color: "B"|"W", transform: "identity"|"tN", board_size: int }` — **facts only**. `sanitizeAttempt`:
- drops the entire attempt if any of `grade / correct / is_correct / result / verdict / judge_result / accepted / server_correct` is present (`CLIENT_ATTEMPT_FACTS_ONLY`)
- drops it if `moves` is not an array
- keeps only the 4 fact keys; prunes everything else

`CLIENT_ATTEMPT_FACTS_ONLY = PASS` (node contract runner `tests/e2e/run_lc004_attempt_transport_contract.mjs`, 20 checks).

## 3. Frontend attempt population (gated OFF)

`index.html` + `mistakes.html`: `onBoardClick` records the factual player move (canonical coords, already un-transformed by `_ox`/`_oy`) into `_lc004Attempt`. `_lc004AttemptFacts()` builds the facts object **only when `window.__LC004_ATTEMPT_TRANSPORT` is truthy** (default undefined). It is spread into the review body via `_currentReviewMetadata()` (index) / the `submitSRS` fetch body (mistakes). Default: the legacy body is byte-identical to today.

Why gated: the corpus audit (below) blocks safe enforcement. The transport is wired, tested end-to-end, and a single flag flip away from active once the corpus carries terminal verdicts.

## 4. Server authority (default unchanged)

`canonical_learning_judge.py`:

- **`SRS_REVIEW_NO_ATTEMPT_POLICY`** env, default `legacy`:
  - `legacy` (default): a no-attempt request passes the client's self-reported grade through, explicitly labelled `CLIENT_SELF_REPORT_NO_SERVER_JUDGE`, non-authoritative. **Exactly the LC003 behaviour.**
  - `fail_closed` (cutover): a no-attempt request gets HTTP **409** `srs_attempt_required` with `refresh_required: true`; **no review is recorded**; the client grade / `correct` boolean is never consulted.
- **Server-authored expected player colour** (`_server_expected_player_color`): derived from the question SGF root `PL[...]` else the first authored move's colour. The judge enforces this colour; a client-transported colour that contradicts it -> `INCORRECT / player_color_contradicts_server`. When the SGF supplies neither signal (212 snapshot records), the judge falls back to the client-stated colour (documented limitation).
- `EXPECTED_PLAYER_COLOR_SERVER_AUTHORED = YES` (except the ~0.5% SGF-silent records).

`app.py` is **not changed by LC004** — the LC003 route wiring (`resolve_srs_review_authority` + `authority.grade`) already carries both the attempt path and the fail-closed path.

Attempt-path behaviour is unchanged from LC003: CORRECT -> grade 3, INCORRECT/CONTINUE -> grade 0; AMBIGUOUS/UNVERIFIABLE -> 422; MALFORMED -> 400; ambiguous legacy id -> 409; all fail closed with no review recorded and no client value consulted.

## 5. Corpus terminal-verdict coverage audit -> CUTOVER BLOCKED

`questions.json` is absent from the worktree; live measurement is impossible and Production must not be queried. Snapshot-derived estimates (`docs/planning/lc004_corpus_terminal_verdict_coverage_audit.md`):

| Field | Estimate |
|---|---:|
| CORPUS_RECORDS_TOTAL | 42,804 snapshot / 41,591 Production |
| TERMINAL_ANSWER_RECORDS | ≈ 42,580 |
| EXPLICIT_SUCCESS_VERDICT_RECORDS | ≈ 450 (ceiling 1,511) |
| BARE_LEAF_ONLY_RECORDS | ≈ 42,050 (~98.7%) |
| MALFORMED_RECORDS | 163 |
| AMBIGUOUS_TERMINAL_RECORDS | 489 |
| EXPLICIT_VERDICT_COVERAGE_PERCENT | ≈ 1.1% (band 0.35–3.5%) |

```
CUTOVER_STATUS = BLOCKED_TERMINAL_VERDICT_COVERAGE
```

~97–99% of terminal-bearing records resolve `UNVERIFIABLE` under the locked leaf semantics. Enforcing the cutover now would fail-close nearly every genuine correct answer. Leaf semantics are **not** weakened to raise coverage (task section 7). Remediation population: ~42,050 bare-leaf records needing an explicit terminal marker — a later content/SGF-repair task.

## 6. Old / cached client safety

`OLD_CLIENT_NO_ATTEMPT_BEHAVIOR`:
- default (`legacy`): the legacy 2-8 key body is accepted; the client grade drives SM-2 scheduling only, labelled non-authoritative; it cannot reach the `EXTERNAL_AUTHORITATIVE_MAP_BATTLE` handoff (E023) and does not produce a server correctness claim.
- cutover (`fail_closed`): HTTP 409 `srs_attempt_required` + `refresh_required: true`; zero progress credit; no correctness claim.

Either way an old client **cannot** regain correctness authority by lacking the new payload. No client-version negotiation framework was introduced — one server env flag, consistent with the codebase's existing feature flags.

## 7. What LC004 did NOT touch

`sm2_update`, `should_grant_review_progress`, credited-review behaviour, KataGo additive accept (stays OFF; no `katago` param in `judge_answer`), AI explanation, capacity D-1/D-2/D-3, rating, RPG combat, schema, migrations, Dockerfile, deploy, production config, `source_record_uuid` ledger/backfill. No request-time UUID is generated.

## 8. Follow-on (blocked / later)

1. Content task: author explicit terminal markers onto ~42,050 bare-leaf records (or run the LC001 suspect detector to prioritise) -> unblocks `SRS_REVIEW_NO_ATTEMPT_POLICY=fail_closed` and live attempt population.
2. Frontend: read the server verdict from the review response and drive advance/counter UI from it (stop using the client `grade` var post-response); flip `window.__LC004_ATTEMPT_TRANSPORT` on.
3. `review_log.grade_basis` column to persist the basis (schema change — out of scope here).
4. `source_record_uuid` runtime identity (replaces the 409 fail-closed on the 11 duplicate-legacy-id groups).
