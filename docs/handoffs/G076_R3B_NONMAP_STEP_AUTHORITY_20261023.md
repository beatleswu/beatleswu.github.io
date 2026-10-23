# G076 R3-B follow-up: independent Practice/Daily step bridge

Worker `g076-r3b-codex-security`, base `a91627a37f7b2d94aec08313a7d49cbf2c3226c4`.
All work is in `D:\go-odyssey-g076-r3-codex-security-20261023`.

**DELIVERED: independent authority layer, HTTP adapter, client, negative tests.**
**PRODUCT INTEGRATION / ENFORCEMENT: HOLD. No entire non-Map Battle mode is
claimed migrated in the application.** No app registration, index wiring,
packaging change, schema application, push, merge, deploy, or production write.
The initial untracked task documents are preserved and excluded from commits.

## Implemented boundary

`g076_nonmap_steps.py` uses the existing Practice and Daily signed attempts,
the existing G076 step kernel, and the existing mode's canonical final judge.
It accepts one coordinate and an owner/flow/step-bound nonce. History comes
only from the transactional ledger. It returns a board-only SGF on open,
committed past moves on resume, and at most the current opponent reply.
It never returns future player coordinates, accepted alternatives, comments,
the solution tree, or the canonical server answer payload.

Practice uses the original `practice-v1:<nonce>` submission identity. Daily
uses one cursor per user/date, shared across newly issued /today tokens; a
wrong terminal cannot be reset by refreshing. Reissued Daily tokens with a
changed question/revision cannot open a second cursor for that date. Practice
retains the legacy policy that a newly issued nonce represents a new play.
This is not a prohibition on learning solutions through repeated plays.

Every request, including committed retries, resolves identity/revision and
rechecks the mandatory mode-specific entitlement callback. Practice rejects
opaque editorial revisions that cannot bind content; Daily checks its signed
content hash. Session bindings also pin content bytes and policy. Unsupported
flows, transforms, accepted-move alternatives, KataGo hints, malformed previews,
ambiguous opponent choice, unsupported policies and ambiguous legacy terminals
fail closed. This bounded implementation is not an all-corpus Go rules audit.

Terminal judgment must agree with the existing full-answer judge. Only then
does the required settlement callback run on the caller's connection. Callback
writes, frozen step history, terminal result and retry receipt must commit in
one transaction before HTTP returns. Missing adapter/schema is unavailable,
not a legacy fallback. Concurrent identical requests replay one committed
event; different moves with the same cursor conflict. Raw bearer step nonces
and original attempt tokens are not persisted in event responses.

The callback response has an explicit allowlist for the submission identity,
SRS schedule and XP amount; it cannot attach solution data. The adapter may
not commit, open another database connection, or perform external effects.
SQLite requires `BEGIN IMMEDIATE`; PostgreSQL uses row locking through the
repository qmark adapter. PostgreSQL execution is **NOT_EXECUTED** here; the
SQL file is **PROPOSED**, never auto-applied by runtime code.

The unregistered Blueprint requires both `G076_ANSWER_PRIVACY_ENFORCED` and
`G076_NONMAP_STEPS_ENABLED`, defaults OFF, uses Flask session ownership,
rejects cross-site Origin/Fetch-Site requests, bounds input size, rejects extra
authority fields, and returns `private, no-store`. Integrators must retain the
application's existing authentication/account/CSRF policies at registration.
No environment setting was changed.

The independent browser client accepts only `practice` or `daily`, waits for
server verdicts, freezes an uncertain request for exact retry, and recovers
committed state on refresh. Failed open clears the previous identity; no
fallback to local tree judging or client grade is provided. The client is not
served or loaded by the product yet.

## Existing paths and remaining integration work

| Mode | Existing answering path | Remaining work / status |
| --- | --- | --- |
| Ordinary Practice | `index.html` `_incident002ServerPracticeFlow`, `_practiceAnswerMoves`, `submitSRS`; `review_transport.js` calls `/api/srs/practice/attempt` and `/answer`. Existing authority verifies signature, owner, canonical UUID/revision and server SGF grade; final route writes review and canonical SRS. | **HOLD**: extract transaction-safe settlement from `srs_practice_answer`, preserving identity, quota, rating snapshots, trusted source marker and payload hash. Reconcile existing review rows using the original nonce before touching SRS. Wire board rendering, captures, retries, generation cancellation and SRS receipt into the independent client. Practice currently grants SRS evidence, **no Practice XP/battle rewards**; this work does not invent a new reward policy. |
| Daily Challenge | Standalone `daily_challenge.html` loads `/today`, follows `currentNode.children`, accumulates `submittedMoves`, then calls `/submit`. `daily_challenge_authority.py` judges moves, ignoring client `correct` for reward authority. `dc_submit` uses D5B replay and unique `(user_id,challenge_date)`, then XP/badges/appearance. | **HOLD**: extract same-connection D5B reservation/unique daily settlement/XP/badges/appearance adapter; reconcile any prior legacy settlement. Wire the page to step replies and receipt rather than tree traversal. Preserve history, give-up and post-submit UX without exposing reusable answers. Daily currently has XP, not a battle HP/reward transaction or Practice SRS grant. |
| Lord/Boss | `index.html` accumulates `_lordTrialAnswerMoves`; `/api/srs/review` requires the active session exam/attempt/question/window; `lord_trial_answer_service.py` reconstructs judge context and server verdict. | **HOLD**, unsupported by the new adapter. Needs a Lord-owned cursor tied to the ordered exam and existing verdict/reward writer. A public mode label must not select eligibility. |
| Guild | `_guildQuestAnswerMoves` and `_buildGuildQuestReviewMetadata` feed `/api/srs/review`. `guild_quest_answer_service.py` judges moves; accepted quest/catalog eligibility and reserved server envelope govern trusted leaderboard credit. | **HOLD**, unsupported by the new adapter. Preserve practiced-quest semantics separately from judged leaderboard evidence and existing reward ownership. |
| Rating Trial | `rating_test.html` follows the local tree; `/api/rating_test/start`, `/answer`, `/resume/<sid>` serialize questions via `_strip_question`; `_rt_server_verify` judges the submitted sequence. | **HOLD**, unsupported. Needs transform-aware session cursor, token/owner admission before judging, ordered progression/retry recovery, and a cross-mode solution disclosure policy. |

Calling an existing Flask settlement route from the new callback is unsafe:
these routes own their own connections/commits. It would create independent
transactions, potential locking and partial completion. The fixture does not
do this and no production adapter is claimed. The callback contract is useful
integration code, not evidence that those integrations have happened.

## Bypasses and residual cheat surface

- Global privacy remains OFF by default. Existing `/api/question/<id>` without
  `view=board`, `/api/mistakes`, Daily today/history, Rating serialization and
  the existing Grimoire/training surfaces retain their known legacy exposure
  when OFF. Asking only the new layer for a private board does not close them.
- Original `/api/srs/practice/answer` and `/api/daily-challenge/submit` do not
  consult the new step ledger. Players can submit full move sequences through
  those endpoints, including sequences learned from other routes or old
  caches. They still run their existing server judges; this is **not** a claim
  that forged client `correct` can grant Daily XP. An unreconciled bridge
  adapter plus a legacy Practice submission could schedule twice; activation
  is blocked until both writers share the original event identity/digest.
- `/api/srs/review` still accepts a public self-reported grade for scheduling.
  Its code explicitly denies ordinary public correctness/progression authority.
  This remains a way to manipulate scheduling, not established battle/XP
  authority. Changing a browser mode/source label does not create a Lord exam,
  Guild accepted-quest eligibility, or a reserved server verdict envelope.
- Rating `rt_answer` still emits `best_move = pool_q['katago_best_move']` after
  settling that trial question, even with the projection flag ON. A settled
  question may be reused elsewhere, and the authenticated/anonymous trial
  access policy is distinct from Daily/Practice settlement. This is an exact
  source-observed cross-mode reuse gap; exploitability for a chosen qid was
  **NOT_EXECUTED**. Do not treat per-question settlement as bank-wide secrecy.
- Old browser/in-page/service-worker caches and previously downloaded SGFs
  cannot be revoked here. Teacher/admin review remains unchanged. Board labels,
  titles and free text are not certified answer-free editorial content.
- Attempts still expire under the existing authorities. The bridge rechecks
  expiry/rights/revision even for a stored terminal; post-expiry receipt recovery
  is not implemented. Daily's original D5B replay policy differs and must be
  preserved in its production adapter.
- No prevention of multiple accounts, repeated Practice attempts, offline
  solving, or learning from a legitimate prior settlement is claimed. No
  all-route/static-host/cache deployment admission was performed.

## Isolated validation and evidence

Tests use synthetic users, SGFs, identities and signing keys; they never import
`app.py` startup or connect to its configured databases/services. The fixture
uses the **real** Practice/Daily signature validators, step kernel, final judges
and canonical `apply_srs_scheduling` for Practice. Its receipt and Daily XP
tables/writer are **synthetic providers**, not `dc_submit`, production review
logging, battle settlement, badge/appearance or leaderboard proof.

Real localhost HTTP tests exercise signed Flask session cookies and the actual
new Blueprint on an ephemeral loopback port. Real headless Chrome loads the
new script, executes both flows, loses a terminal response after commit,
blocks a different move, retries, refreshes and checks settlement receipts.
The browser harness reports **PASS 20**. External hostname resolution is
disabled for this browser invocation; no remote/site test was requested.
Node syntax-compiles all classic inline scripts from `index.html`,
`daily_challenge.html`, `rating_test.html`, plus the new client (9 scripts).
This is not full product browser play, WGo rendering or iPad/Safari evidence.

Negative tests cover wrong-answer freezing, Daily token reissue, stale revision,
rights revocation including retries, cross-user/flow/attempt nonces, malformed
coordinates, forged grade/history, missing schema/adapter, unavailable policy,
ambiguous SGF, canonical judge disagreement, unsafe callback output and a failure
after settlement writes. Failures roll back SRS/XP/receipt/step changes together.
Concurrent identical and different-move submissions exercise SQLite locking.

An initial 50-test authority run passed. The first combined HTTP/browser run
had **52 PASS / 2 FAIL**: the harness incorrectly searched an opaque HMAC for
the substring `cc`, and assumed more than 10 scripts rather than the actual 9.
Both assertions were corrected; the next real HTTP/browser run passed 4/4.
The following combined regression passed **253 tests** before the final
Practice submission-identity adjustment and competing-answer test. Final
validation is recorded in the worker's final handoff/receipt, rather than
relabeling these earlier attempts as the final run.

**Final run: 256 passed in 30.96s**, with no skips, including the actual
Chrome harness and loopback HTTP. The new focused suite accounts for 71 tests;
the selected existing suites account for 185. `git diff --check` and the
standalone client `node --check` also passed. Final JUnit, rendered browser
DOM and source hashes are in `artifacts/g076-nonmap/`; earlier failed browser
DOM and the 253-test intermediate receipt are explicitly historical files.

Reproduce with local Python 3.12, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and
`PYTHONDONTWRITEBYTECODE=1`:

```powershell
python -m pytest tests/test_g076_nonmap_steps.py tests/test_g076_nonmap_live_http.py tests/test_g076_r3b_exposure.py tests/test_g076_answer_privacy_contract.py tests/test_g076_server_step_authority.py tests/test_g076_step_http_isolated.py tests/test_g076_step_ledger_sqlite.py tests/test_g076_step_concurrency.py tests/test_incident_002_practice_answer_authority.py -q -p no:cacheprovider --basetemp=artifacts/g076-nonmap-verified-tmp --junitxml=artifacts/g076-nonmap-verified.xml
```

The local sandbox initially denied launching the installed Python executable;
the approved local-test escalation succeeded. No automatic approval rejection
occurred. Git/source receipts bind the final source and untouched product files;
the exact local commit is reported after validation. No packaging edits.
