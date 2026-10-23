# G076 R3 Practice product integration

Worker: `D:\go-odyssey-g076-r3-codex-security-20261023`.
Branch: `g076-r3b-codex-security`.
Base: `b5f4fed440aca85c451a9ccc22c8ef816b9cce74`.

This replaces the earlier **Practice integration HOLD** with a gated product
implementation for the supported ordinary Practice SGF subset. It does not
qualify all R3 modes, the canonical corpus, a release image, or production.

## Product behavior

`app.py` registers `g076_practice_product.install` and serves the existing
nonmap browser client. Activation requires all three server environment flags:

- `G076_ANSWER_PRIVACY_ENFORCED`
- `G076_NONMAP_STEPS_ENABLED`
- `G076_PRACTICE_STEPS_ENABLED`

All default OFF. The capability read cannot issue attempts or answers.
Ordinary `index.html` calls this capability, obtains the existing signed
Practice attempt, opens private steps, and uses its real `onBoardClick`, WGo
renderer and QuestionLoader. An unavailable capability, partial activation,
unsupported question, missing schema or authority error stops the flow without
local grading. No other mode is admitted by the product step resolver. Only
the explicitly selected complete Practice activation rejects the old whole
answer route with `practice_steps_required`; the OFF behavior remains available.

Open returns initial board SGF and committed past moves only. A successful
player prefix returns at most its current opponent reply. The browser never
receives future player choices. A lost response freezes the exact request;
another coordinate cannot replace it. Reload gets the same server attempt,
prefix and terminal receipt. Generation/identity guards suppress stale UI work.
Reset, answer reveal and hints cannot bypass private steps. While loading or
held, the old visible board cannot accept a locally graded click.

There is one attempt per authenticated user/question/server calendar date.
Repeated token issuance cannot reset a wrong terminal or create parallel probes;
the following server day permits another legitimate SRS practice. Tokens from
previous dates, independent legacy tokens and other players are rejected.
Content or puzzle-identity changes within a slot require reconciliation. The
existing 24-hour signed-token expiry remains enforced. There is no public
restart/reset endpoint. This is a bounded anti-probing policy, not unlimited
same-day replay practice.

## One durable transaction

The original Practice persistence block is extracted into
`app.py::_persist_practice_review`. Both transports use this one writer through
the `review_service.PracticeReviewService` borrowed-connection port. It retains
`practice_answer_authority`, original nonce submission identity, canonical
payload hash, identity attachment, quota helpers, rating snapshots, trusted
source marker and `srs_scheduling_core.apply_srs_scheduling`.

Entitlements use the existing `_premium_live_from_fields` policy on the borrowed
connection, including the original signed admin override. No cached browser
plan grants entitlement. Every step/replay checks live account existence,
question enablement, identity, revision and paid/free rights. Terminal
settlement does not open another connection, commit or dispatch external effects.

The step receipt, terminal state, review_log and SRS card commit together before
the HTTP result. SQLite uses `BEGIN IMMEDIATE`; PostgreSQL locks the step session
row. Duplicate requests replay the committed receipt; conflicting coordinates
cannot reschedule. Settlement exceptions roll back review_log, SRS and step
state. A prior legacy settlement under the same event identity explicitly
HOLDs for reconciliation instead of scheduling again.

Practice's existing progression-credit policy is `NEVER`: **XP awarded is 0**,
with no battle/reward writer. The UI shows server correct/wrong marks, the SRS
interval, XP +0 and DB-derived daily counts/accuracy (including lost-response
recovery). Its combat panel is hidden for private Practice. The existing
`/api/curriculum/summary` reads the SRS card and counts the question as practiced;
Practice does not manufacture a defeated Boss or first-clear reward.

## Schema and supported content

`migrations/g076_practice_steps_v1.py::upgrade` is additive and requires the
separate exact migration gate `G076_PRACTICE_STEPS_MIGRATION_APPROVED=1` supplied
by its caller. It creates the two step ledger tables plus daily bounded Practice
attempts. It never reads a default DSN or commits. Application import/startup
and HTTP routes never apply DDL. Reapplication fails rather than silently
accepting a partial/incompatible schema. An already installed proposed ledger
needs an operator-owned schema reconciliation before this migration.

Before even the first reply, all reachable player branches are checked against
the shared step kernel. Ambiguous legacy annotations/variations, missing
explicit-policy terminal marks, duplicate player-coordinate branches, pass
moves, unsupported opponent choices, transformations, accepted alternatives,
KataGo answer hints and opaque unbound revisions fail closed. The final shared
Practice judge must agree with the terminal step verdict. No canonical corpus
bytes were edited. This is not a complete Go-legality or all-corpus qualification.

## Validation and limits

Final acceptance: **268 passed, 1 explicitly redundant browser parameter skipped**
in 60.98 seconds. Additional unchanged Map Battle browser/client regressions:
**13/13** and **7/7**. `git diff --check` and JavaScript syntax checks pass.
Source review covered registration/default gates, identity and entitlement
rechecks, one-connection transaction ownership, replay/conflict ordering,
UI loading/stale-generation guards and the absence of runtime DDL/reward writes.

The reproducible acceptance command is the seven pytest modules listed in
`artifacts/g076-practice/acceptance-04.xml`, using Python 3.12, `-B`, worker-local
`--basetemp`, and `G076_LOCAL_PG_TEST=1`. The final receipt is
`artifacts/g076-practice/final-evidence.json`; the precise tested source hashes,
counts, XML hash and Chrome checks are recorded there. Earlier attempts are
retained separately; they are not relabeled as the final pass.
The committed copy is `G076_R3_PRACTICE_TEST_RECEIPT_20261023.json` beside this report.

The tests import the actual Flask app (no AST replacement or application import
stubs), with synthetic sessions/corpus, freshly seeded isolated identity registry
and database providers. They exercise SQLite and actual PostgreSQL 16 in a
uniquely named disposable container bound to `127.0.0.1:55493`, with no host mounts
and no product DATABASE_URL. Coverage includes partial/reload/terminal/replay,
same/different-move races, quota rejection, rights/identity/revision/expiry,
deleted users, injected post-write rollback, single connection ownership,
same-day probe rejection, next-day practice and prior legacy settlement HOLD.

Chrome loads unmodified `index.html` and actual gameplay scripts, calls the real
`loadQuestion`, and clicks the actual canvas. It verifies opponent stones,
correct/wrong marks, displayed daily accuracy, interval, XP +0, school summary,
response-loss retry, reload and partial-gate HOLD. Unrelated account/onboarding
`window.onload` is suppressed, non-Practice ancillary reads are fixture responses,
and external origins are blocked. This is focused real Practice UI acceptance,
not sign-in/onboarding, real-player, Safari/iPad or release-image acceptance.
The redundant PostgreSQL browser parameter is explicitly skipped; PostgreSQL
product route/race/transaction tests actually execute.

Historical runs are retained: acceptance-01 had 260 passes/1 skip before later
hardening; acceptance-02 had 261 passes, one Chrome initialization failure
(`_currentUserId` temporal-dead-zone), and one skip. Its root cause was not
established. The diagnostic UI rerun and acceptance-03 (264 passes/1 skip) and
acceptance-04 all passed; final Chrome explicitly rejects uncaught page errors.
Those later passes do not erase the earlier startup failure or establish that
the full account/onboarding boot is free of intermittent faults.

## Remaining R3 blockers

1. Daily, Lord/Boss, Guild and Rating still need their own product cursor and
   settlement integrations. They are not activated by the Practice flag.
2. Global answer privacy cannot be declared complete: other modes and their
   legacy post-answer disclosures (including Rating best-move behavior), old
   browser caches and cross-mode replay need a combined admission audit. This
   patch cannot erase solutions previously delivered to a browser.
3. The legacy public self-reported review route remains scheduling-only under
   its existing policy; it is not Practice correctness or XP authority. Its
   independent scheduling signal has not been globally migrated or disabled.
4. Unsupported SGF/policy records remain explicit HOLDs until their authority
   and step policy are supplied. No corpus-wide playability claim is made.
5. The main coordinator owns packaging/Dockerfile/build-manifest and integration.
   This worker supplies source only. Production migration, enablement, full
   authenticated entry acceptance and global R3 acceptance remain separate work.
6. The retained earlier browser initialization failure needs diagnosis during
   full authenticated-entry acceptance; this worker has no proven root-cause fix.

No GitHub push/PR/merge, deployment, canonical corpus edit, primary-worktree
product edit or production-player DB write was performed.
