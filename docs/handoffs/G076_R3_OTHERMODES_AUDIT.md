# G076-R3 other-mode authority audit and bounded containment

Date: 2026-10-23. Worker: isolated Codex, branch `g076-r3-othermodes-codex`.
Authority/base: `0b358cc7e5987ffc335dd1b7088b4299b1585518` in
`D:\go-odyssey-g076-r3-othermodes-codex-20261023` only.
Base tree: `6b093d71848005d03c94fbbbc85d0dd4a4400f99`.

Status: LOCAL_CONTAINMENT_IMPLEMENTED; APPLICATION_INTEGRATION_PENDING;
ROLLOUT_HOLD. No runnable private Grimoire or Friend Challenge is claimed.
The new module is deliberately not imported by app.py in this worker.
No production, Oracle, deployment, push, PR, merge, secret or player access.

## Actual findings at the base

Source locators below are function names plus base line numbers. These refer
to code read during this run, not production observations.

| Flow | Existing authority and remaining attack surface | Reveal boundary |
| --- | --- | --- |
| Lord/Boss | `POST /api/adventure/boss/start`, `adventure_boss_start` (app.py:14206), selects admitted questions and resumes signed exam state. `POST /api/srs/review` -> `_validate_adventure_boss_review_context` (16759) validates signed attempt, expiry, membership and next unsettled question; `_srs_review_operation` invokes `judge_lord_trial_answer` (17442), builds/persists a server envelope and derives `lord_trial_submission_id(attempt_id,qid)`. `POST /api/adventure/boss/finish` (14568) consumes persisted evidence, not client correct/total. This is already judged. Pre-submit full SGF from `/api/question/<int:qid>` with privacy OFF still gives an entitled user the answer. | `/api/question` checks premium/free rights but full SGF under OFF is not conditional on submission. ON projects board only and clears comment/accepted/KataGo fields; no attempt-bound full solution reveal endpoint was found in this path. Existing verdict/count responses are safe evidence, not permission to fetch future solution branches. |
| Guild mission | `_guild_quest_answer_eligibility` (18826) resolves catalog membership, premium catalog and accepted quest for the authenticated owner. `guild_answer` selects the real server judge (17519); `guild_quest:v1:` is reserved server evidence. Bare grade/source label grants no leaderboard correctness. The existing `grade` used for SRS scheduling is distinct from the envelope's authoritative grade; do not silently replace the scheduling contract. No issued step nonce/cursor exists for this Guild answer transport; client submission identities are not a new owned step protocol. | Same full-question leakage with OFF; ON board view has no post-submit reveal capability. `guild_progress` is committed progress projection, not a solution grant. |
| Guild mission rewards | `_stage_completion_state` (18923) defines completion as presence in `srs_cards`, not correct answers. `/api/rewards/sync` (19069) uses that practiced set and the existing idempotent claim writer. Thus a caller can satisfy practiced semantics through public scheduling; this must not be described as proof of correct solutions or silently changed into a new reward policy. | Owner policy required if mission rewards are intended to require correctness. No replacement Coin/XP writer introduced here. |
| Rating Trial | `rt_start` (32685), `rt_resume` (32771), `rt_answer` (32824). `_rt_server_verify` (31949) replays moves through `judge_map_battle_answer_v1`, including server-derived geometric transform. Answer locks the session row, checks owner (or anonymous sid capability), current qid and token, then rotates token/advances round. Client correct is shadow telemetry, not rating authority. Full SGF/accepted moves from `_strip_question` (32268) under OFF allow answer harvesting despite trusted grading. ON strips these but browser `loadTestQuestion` (rating_test.html:1609) still parses an answer tree; no private step UI is complete. | Answer response gives this verdict/rating and next stripped question, not a full submitted solution grant. Resume returns committed results and current question. Repeated sid creation / requested init_elo policy are separate abuse questions, not proven grade forgery. No changes to rating or SP claim writers. |
| Grimoire / contaminated training | `grimoire_api.api_training_daily` (`GET /api/grimoire/training/daily`, 454) returns full content from recommendation/cache; `api_training_contaminated` (`GET /api/training/contaminated`, 677) returns full content for owned contaminated rows. `api_training_answer` (`POST /api/training/answer`, 515) directly converts client `correct` with bool(), loads any known qid, updates node mastery/history, grimoire progress and daily cache, then commits. No issued-attempt membership/nonce, trusted judge or idempotency boundary. Repeated forged correct increases attempt_count; a truthy string is also accepted. This is a real correctness bypass. | The existing `_g076_grimoire_exposure` after_request hook only masks two GET envelopes under ON. It does not authorize the answer, create entitlement or make the old tree-driven UI runnable. The raw route does not establish premium rights or daily-issued membership before accepting answers. No authorized post-submit full solution reveal exists here. |
| Mistake review | `get_mistakes` (`GET /api/mistakes`, 20197) checks user ownership and premium/free content; ON projects board only. `mistakes.html` submits grade via `/api/srs/review` (1322). `resolve_public_srs_review_authority` permits scheduling only; `_srs_review_operation` uses `ProgressCreditPolicy.NEVER` on public requests. Do not report grade=5 alone as newly proven XP/battle authority. Browser increments its local correct_after optimistically; it is not server proof. `/api/mistakes/remove` is explicit owned deletion, not a correct-answer grant. | OFF full SGF is visible before an answer. ON has no mistake-specific owned private step/reveal protocol; older Daily history also stays projected, because past date is not submission evidence. |
| Friend Challenge | `friend_challenge_answer` (`POST /api/challenges/friend/<int:cid>/answer`, 24646) checks participant, active challenge, qid membership and pre-existing answer, but stores client correct directly. Completion calls `_award_challenge_reward` (24525), deriving XP/results from those forged booleans. Shadow observation after commit is not an enforced judge. Duplicate SELECT alone is not proof of concurrent reward safety; database concurrency qualification was not executed. | `friend_challenge_detail` returns IDs/counts rather than SGF; fetching the generic question still reveals solutions with OFF. No owned server-judged reveal grant. |
| Premium weekly / other legacy review | `premium_weekly_training` (29024) checks premium, set owner and published report; returns item metadata/IDs. Question loading still uses the generic question endpoint. Public grade does not complete premium items: that mutation is internal-only (17894 onward). Standard review, old SRS due, recommendation and training surfaces are not transformed into owned private modes by this module. | Catalog/entitlement is not post-submit reveal permission. Complete site-wide static/raw dataset and alternate content endpoint inventory remains coordinator work. This audit does not certify absence of all leaks. |

## Implemented guard

`g076_othermode_authority.install_othermode_guard(app)` installs an app-level
before_request hook. Under the existing `privacy_enforced(os.environ)` gate it
returns HTTP 409 `othermode_authority_unavailable`, `retryable:false`,
`Cache-Control:no-store` for:

- Grimoire daily, contaminated and answer routes, including Blueprint endpoint aliases.
- Friend Challenge answer rule, including aliases retaining the original endpoint.

It denies before reading JSON, loading questions or touching database/reward
writers. It accepts no client grade, original identifier, owner, entitlement,
nonce, source label, query, header or claimed post-submit reveal exemption.
HEAD/OPTIONS for matched routes are contained too; 404/405 remain normal.
No attempts or schemas are fabricated. No SRS/XP/mastery/reward writer is
duplicated, and no original identity is generated or rebound.

OFF/default/unknown gate values preserve current behaviour. No extra rollout
flag can override privacy ON. Lord/Guild/Rating and the Practice/Daily worker
endpoints are outside this guard's scope. This is a complete denial boundary
for the enumerated unsafe entry points, not an implementation of those modes.
All legacy vulnerabilities remain reachable with the existing gate OFF.

An honest adapter needs changes to owned files: server-issued owner-bound
attempt/cursor, canonical UUID plus SGF content/revision binding, expiry,
entitlement on open/step/reveal/retry, row serialization and durable replay
events; terminal judgement and the existing mode writer must share the same
transaction. Grimoire currently commits independently, and Friend Challenge
owns separate reward writes. A callback that simply invokes these HTTP routes
would keep client correctness, non-atomic commits or duplicate side effects.
This worker therefore ships the permitted fail-closed guard instead.

## Exact coordinator patch instructions (not applied)

In app.py, immediately following the existing `app = Flask(__name__)` at base
line 575, before any request hook or application serving, apply:

```diff
 app = Flask(__name__)
+from g076_othermode_authority import install_othermode_guard
+install_othermode_guard(app)
```

This is a startup registration only. Do not change environment defaults or
enable `G076_ANSWER_PRIVACY_ENFORCED`. Installation rejects preceding app
before_request hooks; repeated installation is idempotent. Existing
after_request projection does not modify the 409 errors. If coordinator has
added earlier writers/hooks, move registration to app construction; do not
silence this ordering error. Confirm deployment packaging includes the module
through the coordinator-owned packaging process; no manifest was edited here.

After registration, exercise actual full app login and Blueprint routing with
synthetic users, confirm no denied writer executes, and present the 409 state
in the coordinator-owned UI. Do not fall back to client correct, unjudged SRS,
raw SGF or a different endpoint when denied. Before any rollout, privately
migrate Lord/Guild/Rating/mistake browser answer-tree consumers as well; their
unchanged routes are not protected by this bounded guard. Full solution reveal
must stay denied until a durable terminal event for the authenticated owner,
exact original identity/revision and current entitlement is checked; never
trust a query flag, client grade, historical date or mere premium membership.

## Validation receipts

All databases here are process-local SQLite `:memory:`. AST-extracted legacy
function bodies run in Flask test_client with isolated dependencies; app.py is
never imported, so bootstrap, secrets and persistent player files are avoided.
Scope stubs prove guard non-interference only, not other workers' integration.

Initial isolated run: 23 passed in 16.65s. Added real Guild eligibility and
Rating judge proofs plus explicit gate-value cases. The first expanded run
was 93 passed / 3 failed in 27.04s: one owned fixture used unapproved
`C[correct]`, corrected to `answer_policy=g065-explicit-v1` and terminal
`C[G065:CORRECT]`; its rejection is now explicitly asserted. Two failures
remain in untouched `tests/test_p0_guild_quest_server_evidence.py`:

- `test_correct_guild_answer_is_judged_pass_by_the_server`
- `test_a_verdict_requires_server_resolved_guild_eligibility`

Both fail before the expected assertion: `sgf_answer_authority.terminal_verdict`
rejects legacy `C[correct]` as `legacy_ambiguous_requires_owner_review`, wrapped
as Guild `judge_unavailable`. Those fixtures/tests and authority modules were
not edited. These failures are retained, not upgraded to PASS.

Final scoped command:

```text
python -m pytest tests/test_g076_othermode_authority.py tests/test_g076_answer_privacy_contract.py tests/test_guild_answer_player_to_move_p0.py -q -p no:cacheprovider
77 passed in 28.91s
```

The new file contributes 29 cases; this final command excludes the historical
Guild evidence suite whose two failures are recorded above. The expanded
failing command was the same list plus
`tests/test_p0_guild_quest_server_evidence.py`. This is not a claim that all
repository tests pass. `git diff --exit-code <base> --` over protected app/UI,
Grimoire/Guild/Lord/SGF authority modules and the historical failing test
returned zero; no tracked base files changed. `git diff --check` passed.

Stable new-file SHA-256 receipts (before commit; docs excluded from its own hash):

```text
g076_othermode_authority.py
CC151CB03AA0C43E30D07EAC33B2C4ED6492F36A36761476D1BE5C066C50D9C2
tests/test_g076_othermode_authority.py
747F73703F83988ABC16527CB79B9AF4432E00658699BE51295A11D99FAAAD90
```

Only this module, its test file and this handoff are staged for the local
commit. The pre-existing untracked `G076_CODEX_OTHERMODES_TASK.md` is excluded.
No generated artifacts, prompts or overlapping files are committed. Coverage
includes forged booleans/grades/original IDs, repeated submissions, no owner or
premium/admin bypass, no content on claimed reveals, exact/alias routes,
HTTP methods, default OFF, registration ordering, real Guild catalog/owner
eligibility and real Lord/Guild answer-field rejection / Rating judgement.

NOT_EXECUTED: full app runtime, PostgreSQL concurrency, browser UAT, production
or real-player validation. NOT_CLAIMED: rollout readiness, global privacy
closure, security admission or runnable private other modes.
