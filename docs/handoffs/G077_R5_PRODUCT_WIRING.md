# G077 Lane C / R5 Product wiring — HOLD

2026-10-23. Sole writer scope: `D:\go-odyssey-g076-r4-grimoire-worker-20261023`.
Verified entry HEAD: `3c27bc6fad2998b722c38247dfdc8c1db9b3c0c0`.
Branch: `g076-r4-grimoire-worker-20261023` (not renamed).

**Independent Grimoire flag wiring: IMPLEMENTED, Flask/PG validation BLOCKED.
Official corpus/UUID importer, real entitlements and lesson policy: NOT VERIFIED.
Official Product readiness: HOLD. LOCAL_COMMIT=NOT_CREATED.**

## Official source discovery

- `app.py`: `DATA_FILE = os.environ.get('QUESTIONS_JSON_PATH', 'questions.json')`.
  Its general loader may repair decoding and mutate the cached records through
  encounter classification. That cache is unsuitable as canonical raw SHA proof.
- `grimoire_api.py` previously hardcoded `questions.json`; it now uses the same
  environment path. The new strict classifier rejects missing/invalid bytes,
  duplicate keys/IDs, invalid IDs and unknown/ambiguous membership. Classification
  supplies no entitlement or source UUID.
- There is **no root questions.json in this worktree**. Tracked JSON files under
  `tests/fixtures/` are fixtures and were NOT used as official provider data.
  No configured mounted Product corpus, its SHA or actual lesson folder values
  were verified. No other worktree's corpus was substituted.
- The official schema in `app.py` has `zones(id,folder_path,min_level)` and
  `grimoires(id,zone_id,folder_path,discipline,node_count,unlock_level,difficulty)`.
  These are DB catalog paths, not proof that those directories or their imported
  records exist here. No Product DB query was made to obtain their values.
- Question consumption uses numeric `id`, `grimoire_id`, `content` (SGF),
  `enabled`, `grimoire_difficulty`, discipline/stage and access metadata.
  `source` is a path/string; it is not a canonical UUID. The step authority rejects
  unsupported answer policies and alternate accepted-move/KataGo answer overlays.
- `identity_read_adapter.py` explicitly permits bootstrap-cold legacy integer
  fallback. This is not the independent canonical import receipt needed by
  `CanonicalCorpus`. No UUID was generated from an integer, hash or fixture.
- Existing entitlement helpers use user plan/premium expiry and question free
  policy; the Practice helper additionally consumes session admin state. They
  do not establish reviewed Grimoire ownership, active-account and lesson policy
  on this native PG transaction. They were not silently treated as sufficient.

## Installed behavior

`app.py` calls `install_product_grimoire` immediately after the existing
`install_othermode_guard`, before subsequent request hooks. Installation performs
no database connection, DDL, source import, membership grant or flag change.

| Grimoire flag | Global privacy | New player / admission | Legacy behavior |
|---|---|---|---|
| OFF | OFF | 503 | existing behavior preserved |
| OFF | ON | 503 | existing global guard still applies |
| ON | OFF | authenticated page; admission requires providers | independent containment applies |
| ON | ON | same Product boundary | both existing and independent guards apply |

Only `ProductGrimoire` overrides the PG gate prerequisite. The underlying
`PgGrimoireSteps` default continues requiring both flags, preserving the prior
prototype contract. No global environment flag is overwritten or temporarily
toggled. Server-owned board projection, canonical SGF judge, ownership, nonce,
proof, entitlements and PG commit boundary remain mandatory.

The existing real links to `/?grimoire=...` and `/index.html?grimoire=...` redirect
to `/grimoire/player` while ON. OFF returns the previous player. The new player
uses the existing actual HTML/WGo/JS and Product admission/steps endpoints.
The server chooses the lesson; the old query value does NOT become a client
choice of question, scope, entitlement or next round.

`GET /api/g076/grimoire/product/manifest` requires the flag and authenticated
session. It names actual player/admission/steps URLs, independent gate behavior,
configured-provider status, exact aggregate endpoints contained and explicit
`corpus_verified=false`, `entitlements_verified=false`, `product_readiness=HOLD`.
Configuration presence is not an acceptance receipt. No raw corpus, UUID proof,
signing key, answer tree or grade is included.

## Bypass containment and availability effect

ON denies old Grimoire daily/contaminated/answer routes and endpoint aliases.
Common SRS review/practice admission classify the trusted raw question; legacy
practice-answer/nonmap practice transport verify the signed uid-owned token
before classification. Unknown/missing corpus, forged/unknown token or unknown
qid fails closed. Browser mode, qid beside a token, grade and correct cannot
exempt a Grimoire question. Known non-Grimoire Practice retains its handler.
Direct `/api/question/<qid>` and endpoint aliases deny Grimoire/unknown questions
before legacy solution-bearing handlers, even when global privacy is OFF.

Aggregate transports cannot safely infer membership from a browser qid. ON
therefore contains training daily, mistakes, daily today/submit/history list/detail,
Friend Challenge detail/answer, rating start/resume/answer, Map v1
attempt/resume/state/nonce/answer, Map v2 start/step, the daily-step blueprint,
and nonmap flow=daily. Endpoint identities protect aliases; explicit Map rules
also protect the canonical transport paths. This intentionally reduces their
availability while ON; it does not certify playable cross-mode support. OFF
does not install a replacement policy for those routes. Responses while ON
are private/no-store. Do not remove these blocks merely to restore availability.

This is bounded Product wiring, not a whole-site security admission, exhaustive
route audit, internal-writer exclusivity proof or authorization to enable any
flag in an existing environment. Old sessions/previously downloaded answers
cannot be recalled by this change.

## Trusted provider composition; no fake default

`grimoire_api.configure_official_grimoire(app, *, expected_sha256, canonical,
entitlements, lesson, connect, schema, secret)` is an explicit trusted WSGI
composition seam. Call before the first request. No HTTP route or environment
module-name loader can inject a provider. Default installation has no service:
admission returns 503, containment remains installed, the page can show its
unavailable state. This is an executable fail-closed installation, not a claim
that the missing importer has been supplied.

Required inputs from the future reviewed composition:

1. Exact official raw corpus path via QUESTIONS_JSON_PATH and independently
   approved SHA256. Strict CanonicalCorpus validates the full bytes and record
   shape. OfficialCorpus rechecks current file SHA before lookup, so file
   replacement invalidates the frozen service until explicitly rebuilt.
2. `canonical(conn,qid)` reads/locks a trusted independently imported receipt:
   nonzero `source_record_uuid`, exact `corpus_sha256`, canonical
   `question_sha256` (existing sorted compact UTF-8 JSON algorithm) and
   `catalog_revision`. The PG service checks the actual catalog revision and
   qid/grimoire membership. No candidate receipt table was invented or installed.
3. `entitlements(conn,uid,question)` returns exactly True only for reviewed
   account, content and membership rights, rechecked on admission/resume/step/
   replay. Do not use an unconditional True, browser claim or nested DB helper.
4. `lesson(conn,uid)` returns `Lesson(question_id, stable_scope, title)` from the
   real server policy. Existing admission uses selection and issue transactions
   separately; issue rechecks proof/rights/catalog. Atomic scheduler reservation
   across these two transactions is NOT claimed.
5. `connect` returns a fresh idle native psycopg2 connection to the explicit
   reviewed schema; secret is server bytes >=32. Providers use the supplied
   transaction, never commit/open connections or perform external effects.

No approved implementation of items 2–4 was discovered/bound. No Product schema
was created. A full official catalog reconciliation, rights policy review and
real installed-app run are still required. Do not pass the disposable test
providers to this composition seam.

Dockerfile now explicitly copies the four Grimoire Python runtime modules,
actual player HTML and JS. This prevents the new unconditional app import from
being absent from the declared image context. No Docker build was run.
`G077_R5_PRODUCT_WIRING_MANIFEST.json` records exact working-file hashes, base
HEAD and the distinction between runtime closure and unverified Product data;
it is not a release provenance, built-image or deployment manifest.

## New validation and blockers

- Installed system Python312 was explicitly attempted and execution was denied
  (`ResourceUnavailable`, access denied). No permission bypass was attempted.
- Installed bundled Python 3.12.14 executes. Six changed/new Python files parse
  with `ast.parse`: PASS. This is syntax evidence only.
- Exact bundled invocation `-B -m pytest -q -p no:cacheprovider
  tests/test_g077_grimoire_product_wiring.py` failed before collection with
  `No module named pytest`. Flask/psycopg2 dependencies are also unavailable in
  that runtime. A bounded pip target attempt with retries=0/timeout=5 failed
  `No matching distribution found for pytest`; no dependency set was installed.
- `node --test tests/e2e/g076_grimoire_product_client_unit.mjs`: **5 PASS** in
  this turn. Existing JS was unchanged; this is JS unit evidence with explicit
  doubles, not Chrome/Flask/PG or official provider proof.
- `git diff --check`: PASS at the source verification boundary.
- `docker inspect g076-r5-isolated-pg-20261023 --format '{{json .Config.Labels}}'`
  was denied access to Docker config/engine pipe. Exact container labels could
  NOT be confirmed. No PG connection, schema, table or other Docker operation
  followed. Native PG tests: **NOT_EXECUTED**.
- New tests in `test_g077_grimoire_product_wiring.py` cover the independent flag,
  unavailable providers, accurate HOLD manifest, aggregate aliases, OFF legacy,
  old navigation, direct question reads, daily relabel and packaging declaration.
  They are authored, NOT passed Python evidence.
- New `test_g077_grimoire_product_pg_live.py` refuses fixture setup until the
  externally reviewed full nonempty label object is supplied as
  `G077_DISPOSABLE_PG_EXPECTED_LABELS` and matches inspect of ONLY the authorized
  container. It also checks exact name, image, running state, tmpfs data and
  127.0.0.1:55476 mapping before asking for the inherited disposable schema
  fixture. It tests global-OFF native commit/retry, same-transaction providers,
  rights/proof revocation and real INSERT/COMMIT failure rollback with retry.
  Labels have not been guessed or populated from a blocked inspect.
- Chrome → actual Product Flask/PG: **NOT_EXECUTED**, dependent on the blocked
  native fixture/Python environment. Existing contract-stub Chrome and isolated
  prototype pages were not presented as official player evidence.

The user's prior 200 Python PASS + 2532 subtests, real Chrome 12 PASS and native
PG16/Flask results remain **historical SHA-bound reused evidence only**. Earlier
handoffs contain other historical totals; this work does not reconcile, rewrite,
rerun or promote any of them into new Product proof. Existing untracked PG
credentials, G076 receipts and artifacts were not modified or included in a
commit. Only the container/database/port metadata was read from the credentials
file as metadata; DSN/credentials were not printed or used for a connection.

## Integration disposition

No local commit: the requested green Python/native PG condition is unmet.
HEAD remains the exact base above. No push, merge, Oracle operation, Product DB
write, migration, flag enablement, container creation/removal or deployment.
G MASTER remains the sole later merge integrator. Independent mode flag wiring
and official corpus/entitlements verification must retain separate acceptance
decisions. Build/image validation, full route/mode review, real Chrome against
the installed Product app and Owner acceptance remain outstanding.
