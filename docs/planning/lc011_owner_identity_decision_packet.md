# Owner Identity Decision Packet — Immutable Puzzle Identity Foundation V1.1

Ratify all 8 before any `source_record_uuid` backfill begins
(`OWNER_IDENTITY_FOUNDATION_APPROVAL_REQUIRED = YES`). Nothing in LC010/LC011
has mutated the corpus, the registry, a schema, or `app.py`. Companion:
`lc011_immutable_puzzle_identity_foundation_adr.md`,
`lc011_identity_registry_contract.json` (sha256
`61c2f13afb7dbd6d04c2f2b21021acb16292abb1ad6a35762529ade740ed231e`).

---

## DECISION 1 — Canonical identity authority

**Recommended:** a **persistent `source_record_uuid` identity registry**
(LC010 Model D). The registry, not any live field, is the sole authority after
genesis.

- **Alternatives:** (a) `legacy question_id` as sole key — **rejected**: 11
  collision groups (22 records), sparse, `max+1`-allocated and reusable.
  (b) `(record_index, legacy_question_id)` composite (the reverted PR #157 /
  ADR-021) — **rejected**: `record_index` has already shifted +201 in a real
  re-ingestion. (c) a deterministic function of the live `source` path —
  **rejected**: `build_questions.py` regenerates `source` every rebuild.
- **Trade-offs:** a registry is state to build, back up and operate; but it is
  the only construct that survives rename / move / rebuild / re-ingestion.
- **Migration consequence:** a new insert-only `identity_registry` +
  append-only `identity_lineage` store; a dual-ID window (ADR §9).
- **Evidence:** LC008 (content ≠ identity), LC010 (`source` is the only unique
  field but a regenerated projection), LC10-A (no reproducible ingestion, no
  mapping manifest, `record_index` drift), `sgf_engine_v1_scope_freeze_20260718.md`
  already scopes exactly this as "V1.1 Immutable Puzzle Identity Foundation".

## DECISION 2 — Genesis mint method + genesis key (Option C)

**Recommended:** **UUIDv5** for the 42,804 historical external-SGF records,
name = `"gk1"⟨US⟩"sgf-source-file"⟨US⟩"v1"⟨US⟩canonical_source` — **no snapshot
SHA in the name (Option C)**. The snapshot SHA + a stable `corpus_id` are
immutable registry provenance and a hard **`GENESIS_BOOTSTRAP_ONCE_ONLY`**
gate. A persisted **UUIDv4** minted once for admin-authored / source-less
records (hybrid — Decision 7).

- **Alternatives:** (a) **snapshot SHA in the name (Option B)** — **rejected
  (LC11-A)**: it makes "mint exactly once, ever" load-bearing with nothing
  enforcing it; an operator re-running the bootstrap on a refreshed
  `questions.json` would *silently* reassign all 42,804 identities to a
  disjoint set, and `source` (a regenerated projection) gives no in-file
  anchor to detect the drift. Acceptable only with an equally hard once-only
  machine guard — in which case the SHA in the name is redundant.
  (b) random UUIDv4 for *all* 42,804, table-only — **rejected**: an
  un-reconstructible table = a single point of total identity loss.
  (c) UUIDv7 — **rejected**: its timestamp encodes *mint time* (ingestion-run
  metadata), differs on every run, adds nothing.
- **Trade-offs:** Option C means the bare genesis re-derive is *not*
  snapshot-scoped, so the once-only gate + `GENESIS_INPUT_EXACT_MATCH` must
  carry the "one corpus only" guarantee (they do). Two UUID versions in one
  registry — mitigated by treating the UUID as opaque (ADR §9).
- **Migration consequence:** the genesis backfill is a single deterministic
  offline pass, refused if it has ever run.
- **Evidence:** LC010 + LC10-E (42,804 distinct, 0 collisions, independently
  reproduced); LC11 dry-run over the real snapshot — 42,804 to mint, 0
  conflicts, `BACKFILL_IDEMPOTENCY_DESIGN = PASS`, once-only gate verified;
  LC11-A snapshot-in-name analysis.

## DECISION 3 — Canonicalisation rules (`canon-source-v1`)

**Recommended:** NFC; `\`→`/`; strip leading/trailing separators + whole-string
whitespace; collapse `//`; **preserve case**; require and keep `.sgf`;
collection-relative; **fail closed** on control chars / BOM / U+001F / empty /
`.` / `..` / space-or-dot-terminated segments / non-`.sgf` (ADR §3 table).

- **Alternatives:** (a) casefold the path — **rejected**: source FS
  case-sensitivity unproven; casefold could merge distinct files. (b) NFKC —
  **rejected**: merges meaningful fullwidth chars in collection names
  (`｜`, fullwidth digits). (c) silently normalise a bad extension / a
  trailing-dot segment — **rejected**: the curator fixes the source tree, not
  the identity layer.
- **Trade-offs:** a stricter rule fails closed on a handful of hypothetical
  future paths (0 in this corpus) — deliberate: fail-closed beats a silent
  identity merge.
- **Migration consequence:** a future rule tweak bumps `canon-source-v2` and is
  applied via a `CANONICALISATION_RULE_CHANGE` lineage event; **genesis UUIDs
  are never re-minted**.
- **Evidence:** over the frozen snapshot all 42,804 canonicalise to 42,804
  distinct keys with 0 fail-closed (contract JSON + LC10-E; LC11-A stress
  appended in the ADR).

## DECISION 4 — Immutable namespace UUID

**Recommended:** **`c70b30f4-b745-5585-b5c3-64021901ad76`** =
`uuid5(NAMESPACE_URL, "godokoro:immutable-puzzle-identity:source-record-namespace:scheme-v1")`
— reconstructible from this contract, frozen as a checked-in constant, and `assert_namespace()`-enforced at every mint. The seed carries `scheme-v1` (the identity scheme version), **not** the ADR document version, so an ADR revision never re-keys identities (LC11-E).
`OWNER_RATIFICATION_REQUIRED = YES`.

- **Alternatives:** (a) an opaque random UUIDv4 namespace — acceptable; the
  contract does not depend on how it was made, only that it is frozen. (b) reuse
  the LC010 prototype namespace `892f7446-…` — **rejected**: it was explicitly
  PROTOTYPE_ONLY.
- **Trade-offs:** a URL-derived namespace is self-documenting but reveals the
  scheme; a random one is opaque but must be stored carefully.
- **Migration consequence:** a future *incompatible* scheme uses a **new**
  `.../v2` namespace; existing UUIDs are untouched; namespace change is
  **never** ordinary versioning.
- **Evidence:** ADR §2; LC11-A verifies the value is reconstructible and that
  the v1/v2 strings cannot collide.

## DECISION 5 — Post-genesis alias / resolver authority

**Recommended:** the resolver ladder in the contract; **only `EXACT` and
`HIGH_CONFIDENCE_UNIQUE` auto-preserve** an identity; `AMBIGUOUS` / `COLLISION`
→ `MANUAL_IDENTITY_RECONCILIATION`; `content_sha256` is corroborating evidence
only (`CONTENT_HASH_AS_IDENTITY = FORBIDDEN`).

- **Alternatives:** (a) let content-hash equality auto-assign — **rejected**:
  the 404 duplicate groups (940 records) would collapse. (b) let a
  legacy-id match auto-assign — **rejected**: the 11 collision groups.
- **Trade-offs:** a strict resolver sends more re-ingested records to human
  review after a messy rebuild; deliberate.
- **Migration consequence:** a re-ingestion workflow needs a
  `MANUAL_IDENTITY_RECONCILIATION` queue.
- **Evidence:** ADR §6; LC08 (404 groups), LC10 (11 legacy groups); LC11-E
  attempts to make the resolver auto-preserve a wrong identity (appended).

## DECISION 6 — Rename / move semantics

**Recommended:** a renamed / moved / recollected source file keeps the **same
`source_record_uuid`**, updated **only** through a registry lineage event; the
UUID is **never** recomputed from the new path. A *different puzzle placed at
the same filename* is a `SOURCE_REPLACED` event → the old identity is
retired/moved, the new file gets a new identity; without an explicit event the
resolver returns `AMBIGUOUS` (fail closed).

- **Alternatives:** recompute the UUID from the new path — **rejected**: it
  forks one entity's history.
- **Trade-offs:** rename/move must go through a curator tool that writes the
  lineage event; a bare filesystem rename with no event leaves the resolver at
  `AMBIGUOUS` until reconciled — acceptable and safe.
- **Migration consequence:** curator tooling gains "record a rename/move".
- **Evidence:** ADR §8; LC11 tests `test_rename_keeps_same_uuid_and_never_recomputes`,
  `test_folder_move_same_uuid`.

## DECISION 7 — New admin-created / source-less record mint

**Recommended:** `NEW_RECORD_IDENTITY_POLICY = REGISTRY_MINTED_PERSISTED_UUIDV4`
— at authoritative creation, mint one random UUIDv4, persist it on the record
and in the registry (`created_identity_kind = NEW_NATIVE`), never recompute,
never regenerate at request time.

- **Alternatives:** (a) `UUIDv5(author + counter + content_sha256)` —
  **rejected**: none is a stable source entity. (b) leave `source_record_uuid`
  null and rely on `legacy question_id` — **rejected**: it collides and reuses.
- **Trade-offs:** two mint mechanisms (hybrid, ADR §10) — accepted; both obey
  one registry contract.
- **Migration consequence:** `add_question()` (future — B051, not this task)
  must call the authoring-mint flow instead of writing `source = ''`
  (`ADD_QUESTION_PATCH_REQUIRED = YES`).
- **Evidence:** LC10-A (`add_question()` writes `source=''`, `max+1` id alloc);
  LC11 tests `test_source_less_record_gets_persisted_uuidv4_once`,
  `test_new_native_rejects_non_v4`.

## DECISION 8 — Split / merge identity semantics

**Recommended:** **Split** — the parent UUID is RETIRED (`reason SPLIT`), each
child gets a **new** identity, `child.lineage_parent_uuids = [parent]`, the
parent is kept for audit. **Merge** — one survivor stays ACTIVE, the others are
RETIRED with `superseded_by_uuid = survivor`, all histories preserved. Neither
is ever done silently; both are `OWNER_REVIEW` lineage events.

- **Alternatives:** (a) split → both children keep the parent UUID —
  **rejected**: two entities cannot share one identity. (b) merge → mint a
  fresh UUID for the merged record — **rejected**: discards both audit trails.
- **Trade-offs:** downstream consumers holding a retired UUID must follow
  `superseded_by_uuid` / `child_uuids`; the registry exposes both.
- **Migration consequence:** the reconciliation tool gains "split" and "merge".
- **Evidence:** ADR §8; LC11 tests `test_split_retires_parent_and_children_get_new_ids`,
  `test_merge_keeps_one_survivor`.

---

## Ratification checklist

| # | decision | owner ratifies |
|---|---|---|
| 1 | persistent `source_record_uuid` registry is the identity authority | ☐ |
| 2 | genesis = UUIDv5, name = canonical_source only (Option C, no snapshot SHA) + `GENESIS_BOOTSTRAP_ONCE_ONLY`; new native = persisted UUIDv4 | ☐ |
| 3 | canonicalisation rules `canon-source-v1` (incl. preserve-case, NFC, fail-closed set) | ☐ |
| 4 | namespace UUID `c70b30f4-b745-5585-b5c3-64021901ad76` (or an owner-chosen frozen UUID); `assert_namespace()`-enforced | ☐ |
| 5 | resolver ladder; only EXACT / HIGH_CONFIDENCE_UNIQUE auto-preserve; content hash ≠ identity | ☐ |
| 6 | rename / move → same UUID via lineage event only; replacement → new identity | ☐ |
| 7 | source-less new records → registry-minted persisted UUIDv4; `add_question()` future patch | ☐ |
| 8 | split → new child identities + retired parent; merge → survivor + `superseded_by_uuid` | ☐ |
| + | authorise producing `SGF_SOURCE_TREE_GENESIS_MANIFEST` (external tree freeze) | ☐ |
| + | authorise the offline genesis backfill (separate, owner-gated, after 1–8) | ☐ |
