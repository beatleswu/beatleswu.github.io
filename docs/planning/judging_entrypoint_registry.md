# Judging Entrypoint Registry

Status: Repository-only closure inventory

Audited repository: `D:\go-website-sgf-v1-closure-20260717`

Audited branch: `codex/sgf-v1-closure-20260717`

Audited HEAD: `551e5650f3486e1d544cb99bd1be17c55e9879d3`

Runtime impact: None

Player-facing judging changed: No

## Scope and Decision Rule

This registry enumerates player answer submission, Legacy SGF judgement, replay,
candidate and fallback, admin validation, and scheduler or precompute surfaces
found by repository-only inspection. It does not infer production identity or
production traffic from branch names, source presence, or local tooling.

The conservative Shadow eligibility rule is:

1. An entrypoint must represent a live player judgement, not display,
   explanation, administration, validation, scheduling, or aggregate reporting.
2. The server-side observation point must have stable question identity, the
   actual player move sequence, player color, and the complete transform context.
3. Missing diagnostic context must not be synthesized merely to increase
   coverage, and Shadow must not change Legacy judgement or side-effect order.

Under that rule, only the three routes already wired to the shared adapter are
`ALREADY_COVERED`. No newly enumerated route is `ELIGIBLE` in this audit.

## Traffic Evidence Qualification

The Task Book supplies the Phase 23 status for the three known routes:
`rating_test` has organic evidence, while `daily_challenge` and
`friend_challenge` have smoke-only evidence. The referenced artifact
`docs/testing/phase23_analysis_20260717.md` is absent at the audited HEAD, so
those three statuses are recorded as owner-supplied Phase 23 statuses, not as
repository-verified report contents. All other traffic values are conservative
repository-only classifications; unknown traffic is not reported as zero.

## Registry

| entrypoint ID | route or function | file and symbol | legacy judge used | question identity form | player move input availability | player color availability | transform availability | side effects | shadow eligibility | exclusion reason | traffic evidence | evidence source | notes / risks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| JEP-001 | `POST /api/rating_test/answer` / `rt_answer` | `app.py:20814-20890` `rt_answer`; `app.py:19949-19978` `_rt_server_verify`; `shadow_judging.py:466-484` `observe_rating_test` | Server-side `_rt_server_verify` replays the transformed answer tree and checks accepted-move or KataGo fallback branches | Legacy question ID plus rating session ID and per-question token | Yes; request `moves` is required and passed to the adapter | Not an explicit request field; derivable from the transformed SGF context supplied to the existing adapter | Yes; dihedral transform `0..7` from `_rt_transform_idx` is available and passed | Rating-session answer/index/score updates, mistake handling, rating/progress response, and related player progression | `ALREADY_COVERED` | Not applicable; the shared adapter is already invoked after the Legacy verdict and failures are caught | `ORGANIC_OBSERVED` | `phase23 report` | Current hook is `observe_rating_test` to the shared adapter. Phase 23 status is owner-supplied; its artifact is absent at audited HEAD. Risk: `_rt_server_verify` compares stored accepted-move coordinates without applying the session transform, while the frontend payload and KataGo fallback are transformed; this can surface a Legacy candidate mismatch but must not be repaired in this work item. |
| JEP-002 | `POST /api/daily-challenge/submit` / `dc_submit` | `app.py` `dc_submit`; `daily_challenge.html` `onBoardClick`; `shadow_judging.py` `observe_answer_route` | Client-side Legacy SGF tree walk produces the submitted `correct` boolean; the server preserves that result | Daily challenge state resolves the Legacy question ID for the authenticated user and date | The route accepts `moves` only when a caller supplies a list; the audited browser caller submits only the Legacy outcome. V4 emits explicit `missing canonical moves` and never synthesizes them | No player-color field reaches the server route | No live board transform reaches the route; the adapter records the identity/default transform | Daily completion, reward, XP/progress, badge and appearance state, followed by the original response | `ALREADY_COVERED` | Not applicable; this is an existing guarded shared-adapter hook, not evidence that the current caller supplies complete diagnostic input | `SMOKE_ONLY` | `phase23 report` | Current hook is `observe_answer_route` after commit and receives read-only accepted-move candidates. Phase 23 status is owner-supplied; its artifact is absent at audited HEAD. Candidate classification remains unavailable when actual moves or color are absent. |
| JEP-003 | `POST /api/challenges/friend/<int:cid>/answer` / `friend_challenge_answer` | `app.py` `friend_challenge_answer`; `index.html` `_submitChallengeAnswer`; `shadow_judging.py` `observe_answer_route` | Client-side Legacy SGF tree walk supplies `correct`; the server validates challenge membership and preserves that result | Challenge ID, authenticated user ID, and submitted Legacy question ID | The route accepts `moves` only when a caller supplies a list; the audited browser caller submits question ID and Legacy outcome. V4 emits explicit `missing canonical moves` and never synthesizes them | No player-color field reaches the server route | No complete live board transform reaches the route; the adapter records the identity/default transform | Challenge-answer persistence, challenge/progress and reward effects, then the original response | `ALREADY_COVERED` | Not applicable; this is an existing guarded shared-adapter hook | `SMOKE_ONLY` | `phase23 report` | Current hook is `observe_answer_route` after commit and receives read-only accepted-move candidates. Phase 23 status is owner-supplied; its artifact is absent at audited HEAD. Any later SRS-family observation must avoid emitting a duplicate event for this same answer. |
| JEP-004 | `POST /api/srs/review` / `srs_review` | `app.py:9637-10002` `srs_review`; `index.html:9105-9182` `onBoardClick`; `index.html:7667-7678` `submitSRS`; `mistakes.html:1164-1200` `onBoardClick`; `mistakes.html:1295-1322` `submitSRS` | Client-side Legacy SGF tree walk is reduced to submitted SRS grade `0`, `3`, or `5`; the server applies SRS policy but does not replay the move | Authenticated user plus Legacy question ID; caller metadata can distinguish only some modes | No actual move sequence in the server request; the browser has board state but does not submit it | No player-color field in the server request | No complete board transform context in the server request; crop or display state at the caller is insufficient | SRS scheduling, review log, stats, mistake state, XP/progress, badges, monster/quest/grimoire effects, and response data | `EXCLUDED` | The server observation point lacks the actual player move sequence, player color, and complete transform context. Task Book rules prohibit force-connecting incomplete inputs | `UNKNOWN_NOT_MEASURED` | `repository-only inference` | This is a high-value multi-mode sink for practice, daily training, Adventure, Boss, premium weekly, guild quest, and mistakes. It may be reassessed only after those callers pass read-only actual moves, player color, full transform, and a mode discriminator without changing Legacy judgement, persistence order, rewards, SRS, or progress. Friend Challenge also requires deduplication. |
| JEP-005 | `POST /api/training/answer` / `api_training_answer` | `grimoire_api.py:455-605` `api_training_answer`; blueprint registration at `app.py:31` and `app.py:66` | Client-supplied `correct` boolean; the server validates identifiers and updates Grimoire state but does not replay an SGF answer | Authenticated user plus `questionId`; no in-repository caller was found to establish stronger identity context | No actual move sequence; request contains `questionId`, `correct`, and `timeSec` | No player-color field | No transform context | Node mastery, Grimoire purity, daily cache and related progression persistence | `EXCLUDED` | The registered server route lacks actual moves, player color, complete transform context, and a confirmed in-repository caller. Connecting it would violate the complete-input rule | `UNKNOWN_NOT_MEASURED` | `repository-only inference` | Reassess only if a live caller is confirmed and passes stable identity plus read-only actual moves, player color, and full transform context. The existing Legacy boolean and side-effect order must remain authoritative and unchanged. |
| JEP-006 | `POST /api/adventure/boss/finish` / `adventure_boss_finish` | `app.py:8678-8729` `adventure_boss_finish`; caller at `index.html:13146` | Client-submitted aggregate `correct` and `total` values drive the Legacy pass/stars calculation | Authenticated user and Boss/adventure aggregate; no per-question identity | No per-question moves; aggregate counts only | No | No | Boss completion, stars, cooldown and Adventure progression | `EXCLUDED` | Aggregate completion is not a per-question player judgement and lacks question identity, moves, color, and transform | `UNKNOWN_NOT_MEASURED` | `repository-only inference` | Per-question Boss answers flow through the SRS-family UI and remain covered by JEP-004's exclusion. Changing the client-trusted aggregate contract is outside this audit. |
| JEP-007 | `POST /api/question/alternative-report` / `question_alternative_report` | `app.py:14094-14127` `question_alternative_report`; callers at `index.html:9354` and `mistakes.html:1707` | No verdict; this records a player's suspected alternative answer after the Legacy path | Authenticated user plus Legacy question ID | At most the single reported coordinate; no complete answer sequence | No player-color context | No complete transform context tied to the report | Creates or updates an alternative-answer report for later review | `EXCLUDED` | Reporting a suspected candidate is governance input, not authoritative or Shadow player judgement, and the diagnostic context is incomplete | `UNKNOWN_NOT_MEASURED` | `repository-only inference` | This is a candidate-source signal only. It must not promote a move into the candidate set or change the Legacy result automatically. |
| JEP-008 | `POST /api/admin/question-alternative-reports/<int:report_id>/resolve` / `admin_question_alternative_report_resolve` | `app.py:14226-14272` `admin_question_alternative_report_resolve`; `app.py:4191-4219` `_append_question_accepted_move` | Human admin decision: accept, dismiss, or disable; no live player judge | Alternative-report ID resolving to a Legacy question ID | A stored reported coordinate may be present, but no live player sequence | No live player-color context | No verified live-answer transform context | Report resolution/audit and possible mutation of accepted moves or question state | `EXCLUDED` | Admin governance and corpus mutation are not player judgement and cannot be used as a live Shadow entrypoint | `NOT_APPLICABLE` | `repository-only inference` | Accepted moves are a Legacy candidate source. Coordinate-space and cache invalidation behavior are risks to monitor separately; this registry does not modify them. |
| JEP-009 | `POST /api/admin/review-queue/import` / `admin_review_queue_import` | `app.py:13642-13724` `admin_review_queue_import`; strict parser call at `app.py:13687` | Strict SGF corpus validation with `parse_sgf(..., strict=True)`; no player verdict | Admin review-queue item and Legacy question identity | No live player move | No | Not applicable to a live answer | Review-queue import, audit and corpus-management persistence | `EXCLUDED` | Administrative corpus validation is not a player judgement surface | `NOT_APPLICABLE` | `repository-only inference` | Parser acceptance here must not be counted as player traffic or Shadow agreement. No corpus payload was inspected for this audit. |
| JEP-010 | `_build_rt_pool` / `_ensure_rt_pool` | `app.py:19980-20117` `_build_rt_pool`, `_ensure_rt_pool`; answer-tree parser `_rt_parse_answer_tree` | Rating-pool eligibility validation parses answer trees before questions enter the in-process pool | Legacy question ID inside the rating pool | No player move | No | No per-session transform at pool-build time; transform is selected later | Builds or refreshes the in-process rating question pool and readiness/TTL state | `EXCLUDED` | Validator/precompute work has no player answer or verdict and is not a live judgement entrypoint | `NOT_APPLICABLE` | `repository-only inference` | This is an upstream pool-quality control, not traffic. Failures can affect availability but must not emit player Shadow events. |
| JEP-011 | `POST /api/explain` / `ai_explain` | `app.py:7159-7258` `ai_explain`; candidate collection at `app.py:7206-7227` | No correctness verdict; explanation logic consumes the prior result and candidate sources such as accepted moves or KataGo data | Legacy question ID plus explanation request context | A prior or selected move may be available, but not a guaranteed complete answer sequence | No complete player-color context | No complete live-answer transform contract | Explanation response, cache or KataGo-related lookup/generation | `EXCLUDED` | Explanation is downstream of Legacy judgement and lacks the complete inputs required for Shadow comparison | `UNKNOWN_NOT_MEASURED` | `repository-only inference` | Accepted moves and KataGo best moves are candidate sources, not automatic correctness authority. Explanation output must not be reinterpreted as a judge verdict. |
| JEP-012 | `POST /api/katago-move` / `katago_move` | `app.py:7114-7152` `katago_move`; caller at `mistakes.html:1048` | No verdict; performs a cached post-error opponent-reply lookup | Legacy question ID and prior-move lookup context | At most one prior move; no complete player sequence | No complete player-color context | No complete live-answer transform contract | Read-only cached response lookup and API response | `EXCLUDED` | A post-error reply helper is neither a player judgement nor complete diagnostic input | `UNKNOWN_NOT_MEASURED` | `repository-only inference` | KataGo-derived replies and best moves are fallback/candidate evidence only. No referenced precompute script is present as a tracked live judgement entrypoint. |
| JEP-013 | Admin SGF preview functions | `manage.html:3193-3480` `parseSGF`, `openPreview`, `closePreview`; `admin.html:2051-2113` `parseAltAnswerBoard`, `renderAltAnswerBoard` | UI parser and renderer only; no persisted Legacy verdict | Admin-selected question or report identity | Preview/candidate coordinates may be displayed; no live player answer sequence | No live player-color context | Display-only board state, not a server judgement transform contract | Ephemeral admin UI rendering only | `EXCLUDED` | Admin preview is visual inspection, not player judgement, and has no eligible server observation point | `NOT_APPLICABLE` | `repository-only inference` | Preview parsing must not be treated as runtime corpus validation or traffic evidence. |
| JEP-014 | Player answer replay / `showAnswer` | `index.html:9194-9205` `showAnswer`; `mistakes.html:1395-1412` `showAnswer` | No new verdict; displays the answer path after an outcome is already known | Current client question identity | Answer-tree moves may be rendered, but they are not a new submitted player sequence | Rendering may derive colors locally; no new server context | Current display board only; no new server transform context | Ephemeral UI replay/display | `EXCLUDED` | Post-outcome display is not a judgement entrypoint and must not emit a second event | `NOT_APPLICABLE` | `repository-only inference` | The corresponding live answer remains governed by its submission route; game-record replay outside puzzle flows is likewise not applicable. |
| JEP-015 | `_start_premium_weekly_scheduler` / `_start_community_leaderboard_weekly_scheduler` | `app.py:21382-21415`; startup calls at `app.py:21420-21421`; scheduler setup support in `scheduler.py:13-20` | No SGF or player judge | No puzzle-question identity | No | No | No | Starts periodic premium report and community leaderboard/reward work | `EXCLUDED` | Scheduling and reward/report jobs are operational background work, not player judgement or SGF precompute | `NOT_APPLICABLE` | `repository-only inference` | Repository search found no scheduler that consumes a live puzzle answer. Background rewards must remain separate from judging instrumentation. |
| JEP-016 | `_question_accepts_move` | `app.py:4188-4189` `_question_accepts_move`; accepted-move accessor `_question_accepted_moves` | Coordinate-membership helper over configured accepted moves; no call sites were found | In-memory question object, optionally carrying a Legacy ID | One `x,y` candidate argument, not a player answer sequence | No | No transform parameter | None | `EXCLUDED` | Dead, uncalled helper code is not an entrypoint; it also lacks player color and transform context | `NOT_APPLICABLE` | `repository-only inference` | Keep distinct from active accepted-move consumers. Its presence does not establish runtime coverage or traffic. |

## Totals

- Total entry points: 16
- `ALREADY_COVERED`: 3
- `ELIGIBLE`: 0
- Newly hooked: 0
- `EXCLUDED`: 13
- Player-facing judging changed: No

## Re-evaluation Gate for Incomplete Player Routes

JEP-004 (`/api/srs/review`) and JEP-005 (`/api/training/answer`) may move from
`EXCLUDED` to a fresh eligibility review only when their server observation
points receive all of the following as read-only diagnostic context:

- stable question identity and an explicit mode/entrypoint discriminator;
- the actual player move sequence, not a result-derived synthetic path;
- player color;
- the complete transform needed to map displayed coordinates to canonical
  coordinates; and
- enough answer identity to prevent duplicate observations across overlapping
  routes such as Friend Challenge and SRS.

Any future hook must still execute after Legacy judgement, catch every Shadow
failure, return the unchanged Legacy response, and preserve persistence,
rewards, SRS, progress, and other side-effect ordering.

## Protected-Data Boundary

This registry was produced without reading protected question corpus payloads,
SGF bytes, databases, SQLite files, environment files, secrets, or production
systems. Repository source symbols and documentation were the only evidence
used for the newly enumerated rows.
