# G077 Lane A / B1 Product settlement — HOLD

2026-10-23. Outcome: **NOT COMPLETED / NOT PLAYABLE / semantic parity NOT PROVEN**.
Native acceptance: **BLOCKED_ENVIRONMENT / NOT_EXECUTED**.

## Authority and source binding

- Sole worker in this session; no subagents or other writers launched.
- Work confined to `D:\go-odyssey-g076-p0b-gates-20261023`.
- Verified initial HEAD: `8a5101fae1ac685ce2c05b76fa330155b9631052`.
- Verified initial tree: `2d83ade29e07a99d42d3eed37c410c9f127049c8`.
- Existing branch: `g076-p0b-gates-20261023`; initial tracked/untracked status clean.
- No Product edits or B1 implementation branch created. This delivery is an
  uncommitted audit and proposed migration. No assertion of a system-wide writer
  lease is inferred from clean Git status.
- No push, merge, Oracle deployment, production connection, DDL/data mutation,
  signing infrastructure, scheduler, or credential changes performed.
- Proposed whitelist: this document, `G077_B1_SOURCE_RECEIPT.json` in this
  directory, and `migrations/g077_mistakes_flow_PROPOSED.sql` only.
- Commit gate remains closed: requested native greens do not exist.

## Blocking findings at the pinned HEAD

| ID | Finding and exact source | Required closure |
| --- | --- | --- |
| B1-01 | `app.py:33525` registers the Mistakes blueprint without services. `g076_mistakes_product.py` checks six callable ports; enabled-without-provider returns 503. | Implement and register genuine transaction/question/identity/context/admit/settle ports only after parity and native acceptance. Retain current HOLD meanwhile. |
| B1-02 | `_srs_review_operation` starts at `app.py:17326`, owns `get_db()` and commits at lines 18171, 18316, 18366 and 18447. Later errors roll back only the later segment. | Extract shared connection-borrowing persistence without commits, rollback, close, second connections or optional failure swallowing. An outer transaction must own review, rewards, cursor and receipt together. Simply suppressing `commit()` in a proxy would conceal changed failure semantics. |
| B1-03 | The internal path loads `_map_battle_progression_submission` and requires settled battle evidence (`app.py:17674` onward); noncombat/combat tails branch at 18200 onward. | Separate server judgement trust from battle provenance. Do not synthesize a battle submission or invoke `internal=True` for Mistakes. Preserve existing Map Battle behavior in shared extraction. |
| B1-04 | Public review authority is scheduling-only. `_persist_practice_review` (`app.py:17117`) deliberately does not grant progression. The existing isolated B1 fixture sets `ProgressCreditPolicy.NEVER` and returns XP 0. | Neither path demonstrates requested Mistakes XP/coins parity. A new writer must use canonical formulas and sticky credits, with explicit domain policy, rather than copying a zero-XP fixture. |
| B1-05 | Existing nonmap SQL only admits practice/daily. The prior Mistakes SQL comments describe a needed flow constraint change but do not apply it. | Review the new explicit proposed SQL and test it in disposable PostgreSQL. No SQL was applied in this attempt. |
| B1-06 | Commands execute as `beatles\codexsandboxoffline`; `Get-Command python.exe,python3.exe,py.exe` found no executable in the current PATH. Available connected tools provide no beatles native terminal execution port. | Execute and record tests as the real beatles Windows user with its actual Python executable. Sandbox, synthetic identity or a historical receipt cannot satisfy this requirement. No native execution or elevation was attempted. |

Line references refer to the unchanged pinned source; see SHA256 receipt for bytes.

## Canonical behavior that must survive extraction

**Scheduling and lifetime credit.** `srs_scheduling_core.py` already accepts the
caller's connection and owns SM-2 and `srs_cards`. Reuse it unchanged.
`should_grant_review_progress` permits only the first passing answer per
user/question; sticky `progress_credited` survives later failures and upserts
use `GREATEST`. FIRST_PASS_ONLY is used by the battle internal path; public and
Practice use NEVER. SRS advancement is a separate choice: ordinary public
reviews use CORRECT_ONLY_WHEN_DUE, while the existing internal path uses ALWAYS.
A trusted Mistakes implementation must make both choices explicitly and test
future/due/overdue cards; trust alone is not a policy selection.

**XP and progression.** `app.py:1216` calculates
`round((XP_BY_DIFF.get(diff,10) + first_bonus + correction_bonus) * combo_mult)`
as an integer. Existing constants are first bonus 5 and correction bonus 15;
combo thresholds are 30→3.0, 10→2.0 and 3→1.5. The equipment combo effect doubles
only the earned multiplier bonus. `app.py:17979` onward gates awards on newly
granted lifetime credit, then applies equipment, pet and potion factors in
order with integer truncation at the existing stages. Preserve pet growth,
rank/LV progress, max HP, badge and appearance effects and wrong-answer shield
consumption. `is_new` uses prior SRS row existence, not lack of lifetime credit.
An existing uncredited card can earn first lifetime credit without the
first-answer bonus. Copying only `calc_xp_gain` is insufficient parity.

**Correction.** `app.py:18121` onward increments wrong_count on trusted failure;
trusted success increments an existing mistake's `correct_after` and
last_correct_at even when lifetime progress was previously credited.
`user_stats.mistake_corrected` increases only on newly granted lifetime credit.
These distinct counters must remain distinct. Receipt replay must change neither.

**Coins and ledgers.** `user_stats.coins` is the balance and `currency_log` is the
ledger (`app.py:5633`, `_grant_coins` at 25898). Ordinary cap is 500/day. Existing
daily quest completion grants 15 coins and all-complete grants 50 through
`_update_daily_quests` (`app.py:9299` onward), alongside quest XP and pet food.
There is no justified flat per-correct-Mistakes coin amount in the inspected
core XP block. Do not invent one or include battle kill/drop rewards by accident.
`coin_reward_authority.grant_coins_in_transaction` supplies locking and caller
transaction ownership, but its ACT-C scope is not automatic proof that switching
all legacy review grants preserves ledger reasons, exclusions and cap semantics.
Review/quest integration and concurrent cap enforcement remain unimplemented.

**Quota and entitlement.** FREE_DAILY_LIMIT is 20 plus authoritative extra
capacity. `_lock_user_for_daily_quota` (`app.py:7743`) locks the user row; the
snapshot also counts battle settlements awaiting review projection, preventing
cross-mode overspend. The current public operation checks duplicate identity
before quota, and checks Premium outside its main write connection. A Mistakes
transaction must read current plan/expiry and question eligibility in its own
connection, reuse entitlement evaluation (including lifetime/null expiry and
malformed-expiry rejection), lock before quota admission, and count its inserted
review once. Cached session Premium is insufficient. Preserve existing exception
rules in existing callers without importing Boss exceptions into Mistakes.

**Review identity and receipt.** Reuse
`question_idempotency.insert_review_log_with_identity` and existing
`uq_review_log_user_submission_id` migration; equal identity/different payload
is conflict. Do not mint a new reward table merely to bypass review identity.
`g076_nonmap_steps.submit_step` already passes the connection to settlement,
uses server grade 5/0, stable `g076-nm:<session id>`, and inserts response_json in
the same transaction as the terminal cursor update. Its receipt allowlist only
permits submission_id/xp_awarded/srs. If coin projection is added, define a narrow
safe response contract and preserve durable exact replay without exposing SGF.
Any settlement failure must roll back review, SRS, counters, XP, coin ledger,
quest/pet effects and terminal event together; no early commit is acceptable.

**Rights, revision and accounts.** Current Mistakes adapter rechecks owned
mistake_log membership plus admission on every request and binds its persisted
attempt to rights hash and content hash. The practice resolver also checks signed
user identity, canonical UUID and revision. PostgreSQL nonmap sessions are locked
FOR UPDATE. These are inspected mechanisms, not new test results. Product
providers and race tests must prove entitlement changes, mistake removal,
revision/UUID changes and cross-account denial, including replay. Preserve the
current rights-first replay behavior unless explicitly redesigned; a revoked
account must not obtain answer content from an old settled token.

**Privacy and OFF.** Original GET `/api/mistakes` (`app.py:20244`) selects this
account's mistakes; entitlement locks content. Global privacy OR nonlegacy
Mistakes mode projects unlocked SGF through `_g076_exposure_content`.
Both flags OFF preserve legacy shape/content. Global ON must retain projection
even while Product capability is HOLD. No app.py, HTML, JS or privacy change was
made, and no fresh OFF/global-ON PASS is claimed.

## Migration proposal, not applied

`migrations/g077_mistakes_flow_PROPOSED.sql` explicitly replaces the expected
PostgreSQL flow CHECK in a transaction after locking the table. It depends on
the two existing nonmap/Mistakes proposals; it intentionally fails on unexpected
constraint names. It is not a full production rollout or a new reward schema.
The existing review identity migration and all Product reward tables remain
separate prerequisites. Rehearse upgrade, mixed practice/daily/mistakes rows,
constraint rejection, rollback and receipt preservation in a disposable database.
No existing PostgreSQL, local player database or production schema was opened.

## Acceptance still required — all NOT_EXECUTED in this attempt

Use an actual beatles terminal, record `whoami`, absolute Python executable and
version, branch/HEAD/tree, source hashes, exact argv, exit code, JUnit and log.
Existing disposable SQLite fixtures and a fresh disposable PostgreSQL instance
must be isolated from configured Product DB credentials. Do not run
`tests/e2e/run_g076_isolated_postgres.py` unchanged: it hardcodes a different
worktree and output directory. No infrastructure bypass or scheduled native
process was created in this sandbox.

1. Implemented Product provider, not injected zero-XP settlement: correct,
   incorrect, future/due/overdue SRS, new/uncredited/credited lifetime states;
   reference comparisons for formulas, rounding, counters and every reward effect.
2. Successful terminal correction, durable receipt and lost-response replay;
   conflicting move/hash and concurrent same-event requests; one review, one
   lifetime credit, one reward ledger effect. Include another next-day attempt.
3. Inject failures after review insert, SRS, correction, XP, coin/quest/pet writes,
   cursor and event insert, and outer commit. Compare every affected table;
   retries after rollback must perform one whole settlement.
4. Free, Premium, expired, lifetime and malformed expiry; revoked membership,
   changed rights/revision/UUID/content, missing/disabled/ambiguous question;
   cross-account and grade/reward spoofing; no answer exposure on rejection.
5. Quota 19/20/extra-capacity and 499/500 coin boundaries; concurrent Mistakes
   versus public/Practice/battle events. Verify actual coin grants and ledger
   reasons, not only nominal reward projection.
6. Original GET `/api/mistakes` OFF/legacy and global privacy ON; original page
   start/continue/correct/wrong/reload/retry with the real registered provider.
7. Disposable PostgreSQL migration and locking tests, then integrated base suites.

Candidate bounded base command (not run; not evidence of native execution):

```powershell
python -B -m pytest -q -p no:cacheprovider tests/test_g076_mistakes_product_readiness.py tests/test_g076_mistakes_steps_isolated.py tests/test_g076_nonmap_steps.py tests/test_g076_othermode_authority.py tests/test_g076_r3b_exposure.py tests/test_g076_answer_privacy_contract.py tests/test_g076_p0b_gate_matrix_contract.py tests/test_g076_daily_p0a.py tests/test_g076_practice_product.py --junitxml=docs/handoffs/G077_B1_NATIVE_BASE.xml
```

This existing suite is only base regression coverage; it cannot certify a new
Product writer. The new parity/fault/concurrency tests above are not implemented.
No Python tests, browser tests, SQL execution or product acceptance were performed.
Historical PASS counts in earlier G076 handoffs are reused history only and have
not been promoted to fresh PASS here. Source inspection and document whitespace
checks are the only verification in this delivery. B1 remains HOLD pending both
the actual single-connection extraction and real beatles acceptance.
