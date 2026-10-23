# G076 R4 isolated Grimoire worker — bounded candidate, mode HOLD

日期：2026-10-23。NON-PRODUCTION isolated development only.

## Source and writer receipt

- Working directory: `D:\go-odyssey-g076-r4-grimoire-worker-20261023`
- Branch: `g076-r4-grimoire-worker-20261023`
- Verified BEFORE edits: `git rev-parse HEAD` = `f414db82b5c1aa45f8b7086c1defb1bfe0f307eb`.
- Initial `git status --short`: empty. No shared source was edited.
- Newly authored files only: `g076_grimoire_adapter.py`, `tests/test_g076_grimoire_adapter.py`, this handoff.
- Commit status: **NOT_COMMITTED / BLOCKED_ENVIRONMENT**. The explicit three-file `git add -- ...` failed: `fatal: Unable to create 'D:/go-website/.git/worktrees/go-odyssey-g076-r4-grimoire-worker-20261023/index.lock': Permission denied`. That administrative index is outside this session's writable root, and approval policy is never. No bypass or commit was attempted after staging failed; all three files remain untracked.
- After-work HEAD: `f414db82b5c1aa45f8b7086c1defb1bfe0f307eb` (unchanged). Tracked-source `git diff --exit-code`: exit 0. The requested green-code commit remains for MASTER/an environment with legitimate Git administrative write access.

## Findings and source diff

Read legacy `grimoire_api.py` answer/daily/contaminated handlers and purity calculation, `g076_othermode_authority.py`, `g076_nonmap_steps.py`, `g076_server_step_authority.py`, question privacy projection, canonical answer/judge helpers, DB wrapper, and applicable existing SQLite/authority/containment tests.

Legacy POST `/api/training/answer` accepts browser `correct` and updates node mastery, catalog purity/rank/counters and daily completed IDs. Legacy GET daily/contaminated exposes full SGF. Existing privacy guard returns 409 before these handlers; that guard is containment, not playable Grimoire authority. Existing historical unsafe default-OFF behavior is preserved. No claim that it is fixed site-wide.

The additive source diff is one standalone module, one new test file, and this artifact. The module adds:

- A SQLite-only transactional service. Each operation owns a fresh connection, `BEGIN IMMEDIATE`, COMMIT before returning, rollback on errors and close. No DB URL, schema installation, network calls or application registration.
- Server-only issuance with opaque random attempt token, authenticated owner binding, immutable canonical-question/identity/board/policy binding, expiration and stable server admission scope. Reissuing that scope resumes the same attempt and cannot reset a failed answer. Scope is never accepted by HTTP.
- Mandatory read-only question, canonical identity and rights providers. Rights must return exactly `True`, and all providers run again for resume/submission/replay. The transport accepts only the signed Flask session user ID, never a body owner, entitlement or premium claim.
- A board-only preview via the existing projection, server-derived size/side, canonical step validation and judge, server history, HMAC step nonce, strict sequence, replay comparison, terminal lockout and canonical full-answer cross-check. Continuation discloses only the committed step and forced reply. Full solution SGF is never returned, including after settlement.
- A mandatory same-connection settlement callback and an exact receipt allowlist. Mastery, terminal attempt state and replay event commit atomically. The supplied `settle_node_only` uses the unchanged legacy `calc_node_purity`, five booleans, attempt count, last-correct preservation and contamination rule. It refuses catalog and current-date cache settlement rather than partially updating them.
- An additive Flask blueprint factory for isolated tests/integration: POST `/api/g076/grimoire/steps`; strict body fields, same-origin checks, bounded body and private/no-store responses. It has no login/token issuance route and is not registered anywhere in the product.

`ISOLATED_SCHEMA` is fixture DDL for dedicated attempts/events, not a migration. Tests explicitly create disposable SQLite mastery/cache tables. No XP, SRS, review-log, catalog rank or reward adapter was invented.

## Bounded test receipts

Run from the named worktree with local Python, without importing `app.py` or connecting to Oracle:

1. `python -m pytest -q tests/test_g076_grimoire_adapter.py`
   - Exit 1; **61 passed, 1 failed**, 13.13s.
   - Failure: unsafe settlement receipt correctly produced `unsafe_settlement_receipt`; test incorrectly expected the generic backend error. Corrected the assertion, preserving strict rejection/rollback. This receipt is historical FAIL, not relabeled PASS.
2. `python -m pytest -q tests/test_g076_grimoire_adapter.py tests/test_g076_othermode_authority.py tests/test_g076_server_step_authority.py`
   - Exit 0; **106 passed**, 23.16s (**62 new**, 44 existing).
   - New tests cover linear multi-step play/resume, wrong terminal lockout, exact replay, forbidden authority claims, authentication/owner, rights/identity/revision/content/expiry rechecks even for replay, default OFF without opening DB, malformed/ambiguous/unsupported trees, explicit success/failure branches, alternative-policy HOLD, invalid coordinates, nonce/cursor/scope separation, concurrent retries and conflicting moves, missing schema/dependency, legacy history/purity/timestamp/contamination, final judge disagreement, cross-origin/body limit and precise partial-settlement HOLD.
   - Real file-backed SQLite failure injection: exception after mastery write; unsafe receipt after mastery write; event INSERT abort after mastery/state update; deferred foreign-key failure at actual COMMIT. Each rolls back and permits the identical request to recover once. Four concurrent terminal retries yield one fresh settlement and three replay responses.
3. `git diff --check` before staging: exit 0, but does not include untracked files. After staging was denied, `git diff --no-index --check -- NUL <file>` was run separately on all three new files: exit 1 for each because each differs from the empty file, with no whitespace-error diagnostics. Staged verification and commit are NOT_EXECUTED due to the administrative index restriction above.

Authored source SHA-256 receipts after the green test run (documentation-only updates followed):

| File | SHA-256 |
| --- | --- |
| `g076_grimoire_adapter.py` | `525BC17D56DF98789C029EFCD429C92D8EF7DA24AA83B400B9D38450B53415CD` |
| `tests/test_g076_grimoire_adapter.py` | `5A1560BF9490AEBAD09B64903E9226EE4D16DE53DBD0F718BD6FCF5B580ABF33` |

## Precise integration HOLDs and safety limits

1. **Catalog settlement HOLD:** real questions with `grimoire_id` require MASTER's same-transaction catalog membership/node denominator, aggregate purity, one-rank-per-answer behavior, counters and timestamp adapter. The node-only helper raises `catalog_grimoire_settlement_hold` before writing mastery. It must not be used to claim catalog mode playable.
2. **Daily cache HOLD:** current-date cache presence raises `daily_cache_settlement_hold` before mastery writes. MASTER must integrate the legacy completed-ID update atomically. This worker does not implement or repeat the separate Daily challenge work.
3. **Admission policy HOLD:** MASTER must define the stable server scope and when a genuinely new mastery attempt may be admitted for recommendation/contaminated retries. A *different* server scope is a different attempt; exactly-once here applies within one admitted attempt, not one reward per question forever. Browser-driven scope minting would invalidate that guarantee. No issuance route is provided.
4. **Runtime providers/authentication HOLD:** MASTER must implement canonical identity, current account/entitlement/catalog membership and server-selected question providers, connect to the application's authentication/CSRF policy, register additive routes and build the player client. Providers must use the transaction connection and never commit. Session validity and rights are integrator responsibilities; tests use synthetic identities/rights and signed local sessions.
5. **PostgreSQL HOLD / NOT_EXECUTED:** this candidate explicitly rejects non-raw-SQLite connections. PG row locking, qmark wrapper, schema and cross-attempt catalog serialization require a separately reviewed integrator adapter and real disposable PG receipts. No PG parity claim.
6. **Legacy exposure HOLD:** shared guard, daily/contaminated GETs, legacy POST, application/client/build configuration remain unchanged. Enabling this isolated candidate cannot bypass the existing 409 guard or make old GETs safe. MASTER must integrate preview/admission without weakening containment. Both candidate and privacy flags default OFF; only local injected test dictionaries enable them.
7. Settlement callbacks are trusted integration code: the service cannot undo an external network side effect or an independently committed connection. They must use the supplied connection, perform no external I/O and never commit. The supplied bounded helper follows that contract. Issuance/step rows contain bearer tokens and must be treated as private; they are not telemetry.
8. Unsupported transforms/alternatives/ambiguous opponent branches are not guessed. No content corpus, legacy formula, historical report, other worktree, deployment or real account was changed. No reward eligibility or full security admission was inferred from static/SQLite results.

**MODE_READY=NO; INTEGRATION=HOLD; PRODUCTION_MUTATION=NO; ORACLE_CALLS=NONE; PG/IPAD/CI/BUILD/DEPLOY=NOT_EXECUTED.** No push, PR, merge, migration, feature-flag switch, new Owner Gate or real-user action.
