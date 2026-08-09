# SGF-ANSWER-REMOTE-OWNER-REVIEW-001

Status: `READY_FOR_OWNER_REMOTE_DEPLOY_DECISION`

This Sprint audits and narrowly hardens the merged SGF Answer Review Queue for
remote Owner use. It does not deploy, contact Production, create a new login
system, or mutate canonical puzzle data.

## Phase A closure

- PR #298 Owner desktop visual review: `PASS`
- Accepted source HEAD: `a016f3f51d723b22890313d4b1a3420a5ea8044c`
- Merge commit: `4e92155e0684c7b91ee079655de0d3763cd8c65b`
- Merge method: repository-standard merge commit
- Pre-merge regression: 61 Review Queue tests and 50 build/packaging tests passed
- Production contact and deployment: none

## Architecture decision

`REMOTE_ARCHITECTURE = EXISTING_ADMIN_AUTH_PLUS_NARROW_REVIEW_CSRF`

The merged queue already uses the normal Flask application and its existing
`admin_required` decorator. The page, JavaScript, bootstrap API, save API, undo
API, and progress API all require the ordinary signed account session and the
session's Admin flag. No remote QA account, universal password, username-only
trust, tunnel, VPN, or second authentication system is needed.

The merged state model is already server-side and account-scoped. Review state,
progress, idempotency records, repair proposals, and audit history are keyed by
Owner account and detector snapshot. Browser storage remains retry support only.

### Why a narrow code change is required

The application has credentialed CORS enabled globally. Although the existing
session cookie is HttpOnly, SameSite=Lax, and Secure when `SITE_URL` is HTTPS,
the merged Review Queue write APIs did not carry a dedicated anti-CSRF token.
Remote administrative writes therefore need a narrow defense-in-depth change.

This Sprint adds only:

- a cryptographically random, session-bound Review Queue CSRF token;
- strict same-origin rejection for Review Queue bootstrap and write APIs;
- the token header on save, undo, progress, and offline-retry transmissions;
- integration and deployment-preflight tests for the remote security boundary.

It does not change review scoring, ordering, content grouping, board UX, repair
proposal semantics, canonical SGF data, accepted moves, or player verdicts.

## Remote access matrix

| Actor/request | Expected result |
| --- | --- |
| Anonymous page/API | Redirect to login / HTTP 401 |
| Authenticated non-Admin | Redirect to home / HTTP 403 |
| Authenticated Admin | Page and bootstrap allowed |
| Admin write without same-session CSRF | HTTP 403 |
| Cross-origin bootstrap or write | HTTP 403 |
| Local QA bootstrap in normal app | HTTP 404 |

The deployment URL is:

`https://godokoro.com/admin/sgf-answer-review`

The public nginx configuration redirects HTTP to HTTPS, serves TLS 1.2/1.3,
and emits HSTS. Production compose defaults `SITE_URL` to
`https://godokoro.com`, causing Flask's session cookie to carry Secure,
HttpOnly, and SameSite=Lax attributes.

## Local QA bootstrap boundary

`/__local_qa__/owner-login` is registered only by
`tools/run_sgf_answer_review_queue_qa.py`. The normal application route map does
not contain it. The harness binds explicitly to `127.0.0.1`, and the Dockerfile
does not copy the harness or the whole tools directory into the runtime image.
It is therefore impossible to reach through a normal deployed application
image.

## Persistence and schema preflight

The Review Queue uses four additive PostgreSQL tables:

- `sgf_answer_review_states`
- `sgf_answer_review_progress`
- `sgf_answer_review_mutations`
- `sgf_answer_review_audit`

`app.py` calls `ensure_review_queue_tables()` during application startup. The
statements use `CREATE TABLE/INDEX IF NOT EXISTS`, a PostgreSQL advisory
transaction lock, foreign keys to `users(id)`, and no canonical question table.
No separate migration command is required.

An authorized first deployment will nevertheless perform an additive Production
schema mutation when the new app starts. The deployment authorization must
explicitly cover creation of these staging-only tables. Rolling back to the
previous application image is compatible: the old app ignores the additive
tables, which can remain dormant for audit/history preservation.

## Packaging and service worker

The application image explicitly includes the Review Queue Python, HTML,
JavaScript, and reviewed 500-record source. The localhost QA harness is absent.
The Review Queue API path is network-only under `sw.js`; no review API response
or account state is stored in Cache Storage. The HTML is network-first. The
Review Queue JavaScript is supplied by the new application image and will be
fetched on its first Production request because this route has not previously
been deployed.

This requires an application-image release, not a static-only release, because
the route, CSRF enforcement, and additive persistence tables are server-side.

## Deployment and rollback preflight

No deployment command was executed in this Sprint. After a separate
`GO_DEPLOY` authorization, use only the canonical `scripts/release/*` flow:

1. build and package an exact image from the final merged Phase B SHA;
2. verify image revision, build inputs, and Review Queue runtime files;
3. run the canonical Production preflight;
4. confirm PostgreSQL health and authorization for additive table creation;
5. deploy the exact artifact and verify anonymous/non-Admin/Admin access;
6. verify iPad save followed by desktop resume on the same Owner account;
7. rollback to the captured prior image if health, auth, persistence, or public
   gameplay checks fail.

The real-iPad gate remains pending because Production deployment is not
authorized. Automated Safari-like viewport QA cannot replace that final Owner
test.

## Local validation evidence

Automated regression results on the Phase B worktree:

- remote security, queue, frontend, and packaging: `35 passed`
- detector, judging registry, and SGF vendor provenance: `37 passed`
- canonical build inputs and remote deployment contracts: `57 passed`
- Python compilation, JavaScript syntax, and Git whitespace checks: pass

Browser QA used the disposable localhost harness and the merged 500-record
review source. It verified a normal Admin session bootstrap, a CSRF-protected
save, a board-intersection repair tap producing a staged `K10` proposal, and
immediate state visibility in a second browser tab using the same account.
Browser console diagnostics were empty.

| Safari-like viewport | Board | Horizontal overflow | Minimum visible button | Result |
| --- | ---: | --- | ---: | --- |
| 768x1024 portrait | 573x573 | no | 48px | pass |
| 820x1180 portrait | 697x697 | no | 48px | pass |
| 1024x768 landscape | 406x406 | no | 48px | pass |
| 1180x820 landscape | 458x458 | no | 48px | pass |

In every viewport the board ended above the sticky navigation, primary actions
remained available, repair taps remained reliable, and technical details stayed
collapsed. This is responsive-browser evidence only, not the still-pending
real remote iPad acceptance gate.

## Safety assertions

```text
EXISTING_PRODUCTION_AUTH_REUSED=YES
NEW_AUTH_SYSTEM_CREATED=NO
LOCAL_QA_BOOTSTRAP_REMOTE_EXPOSURE=NO
DETECTOR_RANKING_CHANGED=NO
CANONICAL_SGF_MUTATED=NO
QUESTIONS_JSON_MUTATED=NO
ACCEPTED_MOVES_MUTATED=NO
PLAYER_VERDICT_MUTATED=NO
KATAGO_RUN=NONE
IDENTITY_IMPLEMENTED=NO
RANK_CALIBRATION_FIX=DEFERRED
E10_CINEMATIC_TOUCHED=NO
CANONICAL_REPAIR_BATCH_STARTED=NO
PRODUCTION_CONTACT=NONE
PRODUCTION_MUTATION=NONE
DEPLOY=NO
```
