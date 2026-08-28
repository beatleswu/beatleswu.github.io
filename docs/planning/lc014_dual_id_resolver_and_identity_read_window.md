# LC014 — Dual-ID Resolver & Identity Read Window

Status: **read-only resolver + read-window contract delivered. No runtime
call-site wiring. No genesis bootstrap. Legacy integer `question_id` unchanged.**

Mode: IMPLEMENT / TEST / COMMIT / PUSH. `REAL_GENESIS_BOOTSTRAP = NOT RUN`,
`UUID_BACKFILL = NO`, `question_id` **not** removed, frozen corpus / SGF /
LC012-R2 artifacts untouched, no production migration, no `add_question()`
implementation, no manual-marker semantics.

Base: `19d797970` (LC013-R1). `origin/master` (fresh-fetch) =
`6829c4c528adf4800326e90534585a32e390ebec` — the Learning Core lineage stays
diverged from RPG master; LC014 does not merge / rebase / PR.

---

## 1. What LC014 adds

| file | role |
|---|---|
| `puzzle_identity_read_window.py` | **new** — `DualIdReadWindow`, `IdentityResolution`, `ResolutionStatus`. The read-only lens between legacy `question_id` and `source_record_uuid`. |
| `puzzle_identity_store.py` | additive read helpers: `resolve(alias_context=None)` (any-context), `resolve_batch()`, `aliases_of_kind()`, `has_identity_tables()`, `count_identities()`, `genesis_bootstrap_applied()`; `AmbiguousAliasError.candidates`. No write path changed. |
| `tests/test_lc014_dual_id_resolver.py` | **new** — 14 SQLite tests + 1 real-PostgreSQL parity test. |

Nothing else changes. `review_log`, SRS, admin, Learning Core and Adventure code
are **not touched** — the target callers get an API to adopt in LC015+, not an
edit now (before genesis the registry is empty, so a wired read path would just
return `MISSING` everywhere).

## 2. Resolution outcomes (`ResolutionStatus`)

| status | when | `source_record_uuid` | caller must |
|---|---|---|---|
| `EXACT` | exactly one *current* alias binding, identity `ACTIVE` | the uuid | use the uuid; may bind new data (`.attachable`) |
| `RETIRED` | exactly one current binding, identity `RETIRED` | the uuid | use the uuid for **reads** of historical rows; **not** `.attachable` |
| `AMBIGUOUS` | ≥2 distinct current identities for the alias value | `None` | **fail closed** — treat as unresolved, never pick one |
| `MISSING` | no current binding | `None` | explicit unresolved — keep using the legacy `question_id` |
| `UNAVAILABLE` | the identity tables are absent on this connection | `None` | explicit unresolved — keep using the legacy `question_id` |

`IdentityResolution` is a frozen dataclass. Helpers: `.resolved`
(`EXACT`/`RETIRED` with a uuid), `.attachable` (`EXACT` only), `.unresolved`
(`AMBIGUOUS`/`MISSING`/`UNAVAILABLE`), `.uuid_or_legacy(question_id)` → the
dual-ID join key.

**Exact / high-confidence only.** A binding counts only if it is the single
`is_current=1` alias row for the value. `HIGH_CONFIDENCE` / `RECORDED` confidence
alias rows resolve the same way *only while they are the sole current binding* —
there is no fuzzy or scored match, and no automatic merge.

## 3. Resolvers

- `resolve_legacy_question_id(question_id)` — `LEGACY_QUESTION_ID`,
  **context-agnostic**: a legacy id that is a current binding in more than one
  alias context (e.g. `genesis-v1` *and* `post-genesis`) pointing at different
  identities fails closed as `AMBIGUOUS`. Integer and string ids are equivalent.
- `resolve_current_source_path(path)` — `CURRENT_SOURCE_PATH`. After a
  rename/move the old path returns `MISSING` (superseded) and the new path
  returns `EXACT`; the legacy id is unaffected.
- `resolve_canonical_source(key)` — `CANONICAL_SOURCE_KEY` (the `canon-source-v1`
  key minted at genesis).
- `resolve_historical_source_path(path)` — `HISTORICAL_SOURCE_PATH` (the
  pre-reorg path recorded for the 918 renamed genesis rows).
- `resolve_many_legacy_question_ids(ids)` → `{str(id): IdentityResolution}` — one
  `IN (…)` query (chunked at 400), each value classified independently; an
  ambiguous value is its own fail-closed row, it never aborts the batch. For
  SRS / `review_log` aggregate reads (`GROUP BY question_id`,
  `question_id IN (…)`).

## 4. Reverse lookup (admin / audit)

- `legacy_question_ids_for(source_record_uuid)` → the identity's current
  `LEGACY_QUESTION_ID` alias values.
- `current_source_path_for(source_record_uuid)` → the single current source path,
  or `None`.

## 5. Dual-ID window

`LEGACY_ID_REMOVED = NO`, `DUAL_ID_WINDOW = YES`.

- `dual_id_key(question_id)` → `("uuid", <uuid>)` once the identity resolves
  **`EXACT`**, otherwise `("legacy", str(question_id))`. This is the join /
  comparison key callers use during the migration: rows may be keyed by either
  form, and a retired or unresolved identity keeps the legacy key (you never
  write new data against a `("legacy", …)` key's would-be uuid).
- `bootstrap_state()` → `{tables_present, genesis_applied, identity_count, hot}`.
  `hot` is `True` only when the genesis bootstrap receipt is `APPLIED` **and**
  identities exist. **Callers check `hot` before routing any read through the
  window**; until then they use the legacy integer `question_id` exactly as
  today. LC014 ships with `hot = False` in every real environment (genesis not
  run).

## 6. NO SILENT FALLBACK

`不得在 resolver 找不到 identity 時偷偷創造 identity。`

- `puzzle_identity_read_window.py` imports **only** `PuzzleIdentityStore`,
  `AmbiguousAliasError`, `PuzzleIdentityError` — it has no reference to
  `create_historical_genesis_identity`, `create_native_identity`,
  `mint_genesis_uuid`, `GenesisBootstrap`, or any `INSERT` / `UPDATE`. A test
  parses the module AST and asserts this.
- Every non-resolving path returns a typed `MISSING` / `UNAVAILABLE` /
  `AMBIGUOUS` result. A test issues thousands of resolve calls against a seeded
  DB and asserts the registry / alias / lineage row counts are byte-for-byte
  unchanged.
- Unsupported alias kinds or malformed input → `MISSING` with a `detail`
  string, never an exception into the caller, never a fabricated identity.

## 7. Per-caller integration guidance (for LC015+, not wired here)

| caller | today | with the window (after `bootstrap_state().hot`) |
|---|---|---|
| `review_log` aggregates (`GROUP BY question_id`, `DISTINCT question_id`, `question_id IN (…)`) | integer `question_id` | `resolve_many_legacy_question_ids(ids)`; keep `MISSING`/`AMBIGUOUS` rows on the legacy key; group by `dual_id_key` |
| SRS (`srs_cards WHERE user_id=? AND question_id=?`) | `(user_id, question_id)` | resolve `question_id` once per card read; `EXACT` → also accept a `source_record_uuid` column when it exists; `RETIRED` cards still load; never create a card for an unresolved id |
| admin lookup | question id / path search | `resolve_legacy_question_id` / `resolve_current_source_path` + `legacy_question_ids_for` for the reverse view; surface `AMBIGUOUS` candidates to the operator, do not auto-pick |
| Learning Core identity reads | legacy id on the attempt/judge path | resolve for display / analytics binding only; the judge remains keyed by the SGF the client sends |
| Adventure identity consumers | zone/question legacy id | resolve for cross-referencing progress to the permanent id; `MISSING` ⇒ leave progress on the legacy id |

In all cases: `EXACT` → use the uuid; `RETIRED` → use the uuid for historical
reads only; `AMBIGUOUS` / `MISSING` / `UNAVAILABLE` → keep the legacy integer
`question_id`, do not block, do not fabricate.

## 8. Real PostgreSQL parity

`tests/test_lc014_dual_id_resolver.py::test_pg_parity_resolver_semantics` runs
`upgrade()` + genesis/native/retire seeding + the full resolver surface
(`EXACT` / `RETIRED` / `MISSING`, single + batch, cross-context `AMBIGUOUS`,
`bootstrap_state`) on a disposable `postgres:16.14-alpine` container — same
semantics as SQLite. Docker-absent → skip.

## 9. What LC014 does NOT do

- No real 42,804 genesis bootstrap; no UUID backfill; no
  `IDENTITY_REGISTRY_PRODUCTION_POPULATION`.
- No `question_id` removal; no schema change beyond LC013-R1; no production
  migration.
- No `app.py` / `add_question()` / SRS / `review_log` / Adventure / Learning-UI
  code change — the callers adopt the window in a later task.
- No manual-marker semantics; no resolver-side identity creation of any kind.
- No merge / rebase / PR onto RPG master.

## 10. Result

`READY_FOR_LC015 = YES` — the dual-ID read window exists, is exact/high-confidence
only, fails closed on ambiguity, returns explicit unresolved results, never
fabricates an identity, and is proven on SQLite and real PostgreSQL. LC015 can
wire the target callers (behind `bootstrap_state().hot`) and, separately, the
owner-gated genesis bootstrap can populate the registry.
