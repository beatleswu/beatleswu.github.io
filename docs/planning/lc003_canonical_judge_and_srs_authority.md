# LC003 — Canonical Judge + /api/srs/review Server-Authority Closure

BASE_SHA (branch base): c2a1dab3125cdef0cff381815d3d995bdd340538
LC002 evidence commit: f8842e0525317729abd0f1cb1415a78479e35176
Branch: claude/lc003-canonical-judge-srs-authority

## What LC003 delivers

1. `canonical_learning_judge.py` — one server-authoritative judgement contract.
2. `/api/srs/review` wiring so that when the client supplies an `attempt`
   block, the canonical judge owns the grade; the client's `grade` /
   `correct` fields are ignored for correctness. Ambiguous / unverifiable /
   malformed inputs fail closed (the review is not recorded and no client
   value is consulted).
3. LC002 judge-divergence regression harness carried forward unchanged.

Out of scope (explicitly not touched): source_record_uuid migration/backfill,
SM-2 redesign, rating/difficulty, question capacity, AI explanation, RPG
combat rewiring, schema/migrations, Dockerfile, deploy, production.

## Recon (source-verified at branch base)

| Field | Value |
|---|---|
| PRIMARY_SRS_REVIEW_ENDPOINT | `POST /api/srs/review` |
| PRIMARY_SRS_REVIEW_HANDLER | `app.srs_review` (app.py:13950) -> `ReviewService.review` -> `_srs_review_operation` (app.py:14000, the single durable writer) |
| CURRENT_CLIENT_GRADE_INPUT | `data.get('grade')`, validated to `{0,3,5}` inside `_srs_review_operation` (app.py:14047) |
| CURRENT_CLIENT_CORRECTNESS_INPUT | none on this route today; the client sends only `grade` (LC001). A `correct` boolean is accepted-and-ignored on other routes. |
| MAP_BATTLE_JUDGE | `map_battle_runtime.judge_map_battle_answer_v1` (unchanged) |
| RATING_JUDGE | `app._rt_server_verify` / `_rt_replay` / `_rt_parse_answer_tree` (unchanged) |
| SGF_ENGINE_PRIMITIVES | `sgf_engine.parser.sgf_parser.parse_sgf`, `sgf_engine.core.matcher.match_move` (via `find_child_by_move`), `sgf_engine.core.autoreply.get_auto_reply`, `sgf_engine.core.coord_utils.opponent_of` |
| ACCEPTED_MOVE_SOURCE | `question['accepted_moves']` / `accepted_answers` (content authority); read via `app._question_accepted_moves` |
| TRANSFORM_SOURCE | `map_battle_runtime._transform_index` / `_transform_point` / `_transform_sgf` — the one implementation LC002 proved correct for the tree/display/accepted relationship |
| PLAYER_COLOR_SOURCE | client `attempt.player_color`, enforced structurally against the authored tree (a move of the wrong colour matches no child) |
| QUESTION_IDENTITY_INPUT_CURRENT | legacy integer `question_id` -> `_load_questions()` `id` lookup |
| SOURCE_RECORD_UUID_RUNTIME_AVAILABLE | NO — zero occurrences of `source_record_uuid` in any runtime `.py` file |

## Canonical judge contract

`canonical_learning_judge.judge_answer(question_content, attempt, accepted_moves)` -> `JudgeResult(status, reason_code, judge_version, transform_index, matched_path, player_color)`.

`JudgeStatus`: CORRECT | INCORRECT | CONTINUE | AMBIGUOUS | UNVERIFIABLE | MALFORMED.
AMBIGUOUS / UNVERIFIABLE / MALFORMED are never collapsed into INCORRECT — they are `is_fail_closed` and carry their own `reason_code`.

### Locked semantics (LC003 task sections 2 / 8 / 9 / 14)

| Concern | LC003 behaviour |
|---|---|
| LEAF_SEMANTICS | **FAIL_CLOSED_UNTIL_EXPLICIT_VERDICT**. A childless node is UNVERIFIABLE (`leaf_without_explicit_verdict`) unless it carries an explicit marker: a non-failure `RE[...]` game-result, a `TE` (tesuji) property, or a success token in the node comment (`正解` / `correct` / …). An explicit failure token yields INCORRECT. The old map_battle "any childless node == CORRECT" behaviour is deliberately not preserved. Corpus implication: most current bare answer-tree leaves resolve to UNVERIFIABLE — making them judgeable is a content/review task, not this one. |
| AMBIGUOUS_AUTOREPLY | **FAIL_CLOSED_NO_BLIND_CHILD0**. If the post-player node does not have exactly one child that is a single opponent move, return AMBIGUOUS. Never `children[0]`, never guess, never advance. |
| Player colour | Enforced. `find_child` matches on `(colour, coord)`. A correct coordinate played as the wrong colour -> INCORRECT `off_answer_tree`. |
| Transforms | All 8 pass. The authored tree (`_transform_sgf`), the client's display-space move, and any accepted alternative (`_transform_point`) are compared in the same display space. One transform helper reused (`map_battle_runtime`), no new copy. |
| Accepted alternatives | Server/content authority only. Single-move alternatives from the SERVER-supplied set are honoured (`accepted_authoritative_alternative`). The `attempt` payload has no channel to declare one; forbidden fields (`grade`, `correct`, `result`, `verdict`, …) are rejected. |
| Parse failure | MALFORMED (strict parse) or UNVERIFIABLE (transform failure / empty content / no moves / unsupported transform). **Never** a client fallback. |
| KataGo additive accept | OFF. `judge_answer` has no `katago_best_move` parameter; the rating-test additive behaviour is characterized in LC002 and deliberately not carried in. |
| `sgf_engine.apply_move` | Not used (LC002 defects: missing overrides file, unreachable `result` metadata, Postgres-bound OFF_TREE logger). LC003 wraps the safe primitives in a new orchestration layer. |

### /api/srs/review authority adapter

`resolve_srs_review_authority(data, load_questions, accepted_moves_reader)` -> `AuthorityResolution`:

- **No `attempt` block** -> `server_authoritative=False`, `grade = data['grade']` unchanged, `grade_basis = CLIENT_SELF_REPORT_NO_SERVER_JUDGE`. The legacy client is preserved; its grade is a scheduling self-report, explicitly labelled non-authoritative, and cannot reach any authoritative-handoff consumer.
- **`attempt` block present** -> the canonical judge is authoritative:
  - CORRECT -> `grade 3`, basis `SERVER_JUDGE_CORRECT`
  - INCORRECT -> `grade 0`, basis `SERVER_JUDGE_INCORRECT`
  - CONTINUE -> `grade 0`, basis `SERVER_JUDGE_CONTINUE_NOT_A_PASS` (retained, not collapsed to "incorrect")
  - AMBIGUOUS / UNVERIFIABLE -> HTTP 422, review not recorded
  - MALFORMED -> HTTP 400, review not recorded
  - forbidden `attempt` field -> HTTP 400
  - ambiguous legacy question id (>1 corpus record for that `id`) -> HTTP 409 `ambiguous_question_identity`
  - unknown question -> HTTP 422

SERVER_GRADE_MAPPING = `CORRECT -> 3`, `INCORRECT -> 0`, `CONTINUE -> 0`. This matches the LC003 task's explicit compatibility guidance for the public route (`incorrect -> 0`, `correct -> 3`); the internal Map Battle handoff keeps its own `correct -> 5` mapping and is untouched.

### Identity limitation (recorded, not fixed)

`RUNTIME_SOURCE_RECORD_UUID_AVAILABLE = NO`. The judge resolves the legacy integer `question_id` via `_load_questions()`. `IDENTITY_FALLBACK_USED = YES` on the attempt path. A legacy id that maps to more than one corpus record fails closed (`AMBIGUOUS_LEGACY_ID_FAIL_CLOSED = YES`). No request-time UUID is generated (`REQUEST_TIME_UUID_CREATED = NO`).

## app.py change scope

Two hunks, one writer:
1. import line after `from review_service import ...`: `from canonical_learning_judge import resolve_srs_review_authority`.
2. `srs_review()` route body (app.py ~13961-13985): call `resolve_srs_review_authority`; return `fail_closed_body` / status directly when fail-closed; otherwise build `ReviewCommand` with `grade = authority.grade if authority.server_authoritative else data.get('grade')`. One argument changed: `grade=data.get('grade')` -> `grade=review_grade`.

`_srs_review_operation` (the durable writer) is byte-unchanged. It still owns SM-2, the anti-farm gate, D5B idempotency, and every `srs_cards` / `review_log` write. The route still does not call it directly (ReviewService does, exactly once) — the `test_e10_backend_review_service_v1a2` route-scan contract still holds.

## LC002 evidence preservation

`tests/test_lc002_judge_divergence.py` + `tests/fixtures/lc002_judge_fixtures.py` are carried forward unchanged and pass. The 14/17 old-judge divergences (map_battle vs rating vs sgf_engine primitives) are intact because LC003 modified none of those judges — it added a new one. `LC002_DIVERGENCE_FIXTURES_RECHECKED = YES`; no previously demonstrated divergence disappeared.

The canonical judge resolves several of those divergences *in its own path* (all fail-closed where LC003 requires it):
- player colour: canonical judge enforces it (map_battle did, rating/sgf-primitives did not).
- blind `children[0]`: canonical judge returns AMBIGUOUS (rating blindly advanced).
- lenient parse: canonical judge is strict -> MALFORMED (rating's hand parser accepted truncated SGF).
- accepted-move transform space: canonical judge compares in display space for all 8 transforms (rating mishandled 1,2,3,4,5,7).
- leaf: canonical judge is UNVERIFIABLE without an explicit marker (map_battle and rating accepted any leaf).

## Known pre-existing failures (not LC003)

Verified by reverting app.py to pristine master and re-running:
1. `tests/test_e10_backend_review_service_v1a2.py::test_update_monster_and_quests_body_only_adds_retaliation_mitigation` — E023 source-freeze drift between current master's `_update_monster_and_quests` and the frozen git baseline ref. Not in LC003 change scope.
2. `tests/test_map_battle_legacy_adapter.py::test_postgres_concurrent_map_battle_progression_is_exactly_once` — `psycopg2.OperationalError`; needs a disposable PostgreSQL not present in this environment.
3. `tests/test_map_battle_runtime.py::test_submission_lifecycle_postgres_validation_rollback_retry_and_nonce_race` — same PostgreSQL environment gap.

TASK_INTRODUCED_FAILURES = 0.

## Follow-on (not LC003)

- Frontend: have `index.html` / `mistakes.html` submit the `attempt` block so the legacy no-attempt self-report path can be retired.
- Persist `grade_basis` on `review_log` (needs a column -> schema change).
- Give the corpus explicit terminal markers (or run the LC001 suspect detector) so bare answer-tree leaves stop resolving to UNVERIFIABLE.
- Decide whether the internal Map Battle judge and the rating-test judge converge onto `canonical_learning_judge` (broad RPG/judge cutover — a later integration task).
