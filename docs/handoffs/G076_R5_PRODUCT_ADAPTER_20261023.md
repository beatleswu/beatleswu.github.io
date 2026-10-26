# G076 R5 Product Grimoire adapter continuation — HOLD

2026-10-23, writer worktree `D:\go-odyssey-g076-r4-grimoire-worker-20261023`.
Base HEAD `0b72d442e6edc14ef63da1c72d7e78631085fdcf`;
parent `b664ff53a201ae7afb6e6f5900d51434b7b4c17a`.

**Product completion: HOLD. Local commit: NOT_CREATED (new Python/integration
tests are not green). Registration, importer, real membership binding and
official navigation remain G MASTER work. No deployment authorization implied.**

## Actual player discovery

There IS an existing Grimoire player integration: `index.html` reads the
`grimoire` query parameter, requests `/api/questions?grimoire_id=...`, filters
the returned questions and calls `loadQuestion`. Its selection consults
`/api/srs/all`; the common review writer is `/api/srs/review`. This is the
legacy shared player, not a PG Grimoire step consumer. The old Grimoire daily,
contaminated and answer routes remain in `grimoire_api.py`; the existing
global othermode guard contains those routes with 409 when privacy is ON.
That containment is not playable Grimoire Product completion.

The new `grimoire_player.html` is a Product-shaped candidate for
`/grimoire/player`, with its own JS consumer. It is **not registered or linked
by the official application**. Neither the prior isolated prototype nor this
new unregistered page is evidence of complete official wiring.

## New allowed-writer files

- `g076_grimoire_product.py`: explicit installer and `ProductGrimoire`, a
  `PgGrimoireSteps` subclass. No app import, DDL, connection at import,
  default corpus, synthetic Product catalog or permissive rights fallback.
- `CanonicalCorpus`: verifies SHA256 of exact supplied source bytes, rejects
  duplicate keys/IDs, indexes detached copies. The trusted canonical receipt
  must independently bind corpus SHA, canonical question SHA, nonzero UUID and
  catalog revision. Each issue/resume/step/replay obtains proof and entitlement
  inside the inherited native PG transaction. Catalog revision is checked
  against PG by the existing service. Missing proof/catalog membership fails
  closed. No canonical record is created or assigned here.
- `Lesson(question_id, scope, title)` is the proposed minimal training
  projection. The provider chooses it from authenticated uid on the PG
  connection. POST admission accepts exactly `{}`; the browser cannot select
  qid, user, scope, next round or a flag. Admission returns title and a real
  service token. Reissuance uses the existing stable scope/attempt semantics.
  Policy selection and `issue` are separate transactions; issue rechecks rights,
  source and catalog. No claim that scheduler selection is atomic with issue.
- HTML/JS: responsive Chinese page, real WGo SGF parser and game, setup stones,
  side to move, board size, labels, captures and committed event replay. No
  solution/answer tree is sent. Controls show errors, retry the identical pending
  nonce/move after uncertain delivery, reconnect and resume from server history,
  display terminal receipt, and prevent clicks during uncertainty/after terminal.
  Tokens are held only in memory, not local/session storage or URL.

## Gate and bypass containment

The server environment `G076_GRIMOIRE_STEPS_ENABLED` controls this seam.
Requests cannot enable it. The inherited PG service additionally requires
`G076_ANSWER_PRIVACY_ENFORCED` and fails closed if that prerequisite is OFF.
The Grimoire containment guard itself does **not** depend on the global privacy
gate: with the Grimoire gate ON, the three legacy Grimoire routes and endpoint
aliases are denied before their handlers. With Grimoire OFF, this new guard
returns None and preserves previous legacy behavior, including any existing
global guard. New candidate endpoints return 503 while OFF.

The same guard recognizes Grimoire qids in `/api/srs/review` and
`/api/srs/practice/attempt` (including endpoint aliases). It also verifies the
server-signed, uid-owned practice token before classifying preexisting tokens at
`/api/srs/practice/answer` and shared nonmap practice steps. A browser-supplied
qid, grade, correct, mode label or claimed entitlement cannot exempt a Grimoire
question. Missing/unknown corpus qids and invalid tokens fail closed. Known
non-Grimoire practice retains its original handler.

The shared daily branch remains owned by its existing resolver. Relabelling a
practice token as daily must be rejected there by its separate signed-token
authority. This continuation does not certify daily/Map/Friend Challenge or
the whole mode matrix, nor the internal common review operation. G MASTER must
audit all server-issued cross-mode admissions and internal writers before
claiming exclusivity across the entire Product. B1/B2 were not edited.

Installer refuses to run behind an existing writer hook. It accepts only the
known existing `g076_othermode_authority` hook ahead of itself, and must run
before any blueprint writer hook. POST endpoints require same-origin JSON
with `X-Grimoire-Request: 1`, reject cross-site/foreign Origin, bound body size,
use Flask session uid and return private no-store responses. Error bodies do
not expose provider exceptions. HTTPS/cookie/proxy policy remains official app
configuration, not a browser identity substitute.

## G MASTER registration proposal — not applied

Exact insertion anchor in existing `app.py`: immediately after
`install_othermode_guard(app)` at the application construction boundary, before
other request hooks. G MASTER must supply a real provider factory; none exists
in this writer's allowed files. This is a review proposal, **not an executable
patch with pretend production bindings**:

```diff
 install_othermode_guard(app)
+# G MASTER-owned factory required; no synthetic/default provider allowed.
+from g076_grimoire_product import install_product_grimoire
+from g076_grimoire_product_bindings import build_product_grimoire_service
+install_product_grimoire(app, build_product_grimoire_service())
```

Required factory inputs, all mandatory:

1. `connect`: NEW idle native psycopg2 connection per transaction to the reviewed
   Product schema; `schema`: explicit reviewed identifier; signing `secret` from
   server configuration (at least 32 bytes); `environ=os.environ`.
2. `corpus=CanonicalCorpus(source_bytes, expected_sha256, canonical_provider)`:
   exact official **complete** question corpus and externally approved source
   SHA, not a browser upload or test rows. Canonical provider reads/locks the
   canonical UUID and import receipt on the supplied connection. Receipt fields
   are `source_record_uuid`, `corpus_sha256`, `question_sha256`,
   `catalog_revision`. `question_sha256` uses `question_sha` (UTF-8, sorted keys,
   compact JSON, ensure_ascii=False); corpus SHA hashes original file bytes.
   The authoritative importer must reconcile all catalog members, node counts,
   UUID lineage and source revisions before admitting a lesson. This module
   neither imports tables nor fabricates missing canonical provenance.
3. `entitlements(conn, uid, question)`: verifies real user membership, active
   account and exact question/catalog ownership; returns exactly True only when
   admitted, and rechecks on every issue/resume/step/replay. Read/lock canonical
   rights on THIS connection; no nested connection, commits or external effects.
4. `lesson(conn, uid)`: real server daily/lesson selection and stable scope,
   including expiry/new-round policy. No local fixture list, arbitrary reset or
   client-supplied scope. It returns a `Lesson`; the service independently
   validates its question through provenance and admission.
5. Separately reviewed schema/import process and all cooperating writers using
   inherited PG locks. Do not run test DDL in Product. Existing PG proposal is
   historical input, not migration approval. No XP/SRS/new reward writer added.

Then G MASTER can add official gated navigation to `/grimoire/player`, retain
OFF legacy navigation, and serve the existing `/wgo/<path:filename>` assets
(already present in app.py). Do not replace the existing othermode guard with
an exemption allowing old answer handlers. No edit to app.py/index.html is made
by this continuation.

## New validation and precise non-claims

- **5 PASS**, Node built-in unit tests against actual Product JS with explicit
  DOM/WGo/HTTP doubles: server selection, nonce-preserving response-loss retry,
  terminal reload lock, revoked-rights reconnect lock/recovery, no speculative
  move on network error. Command:
  `node --test tests/e2e/g076_grimoire_product_client_unit.mjs`.
  Receipt: `G076_R5_PRODUCT_CLIENT_UNIT_20261023.log`. These are unit tests,
  not real browser, real rights, Flask or PG evidence.
- Python AST and JS syntax checks: PASS. `git diff --check`: PASS.
- New real-Flask tests in `tests/test_g076_grimoire_product.py`: **NOT_EXECUTED**.
  New Flask+native PG adapter tests in
  `tests/test_g076_grimoire_product_pg_live.py`: **NOT_EXECUTED**. The latter
  reuses only the existing isolated fixture safety contract and creates its own
  unique test schema when explicitly run; it does not start a PG container or
  rerun prior completed tests. No schema was created in this continuation.
- System Python312 execution/read of dependencies was denied. Bundled Python
  runs but lacks Flask/pytest/psycopg2. Existing D: venv paths contained namespace
  remnants, not runnable modules. Attempted pip target installation failed
  network access with WinError 10013; no packages installed. Exact final new
  pytest invocation failed before collection: `No module named pytest`.
  Receipt: `G076_R5_PRODUCT_PYTEST_BLOCKED_20261023.log`.
- New actual-HTML/JS Chrome/WGo contract HTTP test:
  `node tests/e2e/g076_grimoire_product_client.mjs`: **BLOCKED/0 checks**, CDP
  `Page.enable` timeout. It deliberately uses a contract HTTP stub, not PG.
  New receipt: `artifacts/g076-r5-product-adapter-1792750485762/result.json`.
  Earlier attempt `1792750445168` was interrupted when CDP stalled before timeout
  handling was added; it has no PASS receipt. Both are kept distinct from the
  prior PG/Chrome artifacts. Profiles are disposable test profiles, not release
  assets. No screenshot/visual QA or real WGo behavior PASS is claimed.

The prior 106 PASS, 136 PASS/2532 subtests, native PG 7 PASS, combined 143
PASS/2532 subtests, and real PG/Chrome 14 PASS are **historical SHA-bound reused
evidence only**. None was rerun, overwritten, or promoted to new Product proof.
The three previously untracked `artifacts/g076-r5-pg-chrome/` files were present
at entry; they were left untouched and must not be swept into a new commit.
At the final status check an untracked `.g076-r5-disposable-pg.json` also
appeared, absent from initial status. This writer did not create it or read
its credentials. Treat it as external/concurrent state; do not commit it or
infer new fixture authority from its presence.

## Acceptance and local commit disposition

HOLD remains until new Flask and native-PG tests execute green, actual Product
canonical importer/entitlements/lesson bindings exist and are reviewed, official
registration/navigation is integrated by G MASTER, actual new page passes real
Chrome+PG and visual QA, and bypass/flag matrix is independently verified.
Native iPad/Safari, packaging/ARM64/release and Owner acceptance remain separate.

**LOCAL_COMMIT=NOT_CREATED**: user authorized an exact local commit only if
green; this candidate is not green. Base HEAD remains unchanged. Do not mark
R5 COMPLETE, ready, merged, deployed or accepted. No push, merge, Oracle,
Production DDL, player/question modification or official app registration was
performed. Forbidden tracked files and B1/B2 remain unchanged.
