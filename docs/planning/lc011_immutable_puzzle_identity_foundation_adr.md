# ADR — Immutable Puzzle Identity Foundation V1.1

Status: **DESIGN — OWNER RATIFICATION REQUIRED.** No backfill, no corpus / SGF /
DB / schema / `app.py` change. Supersedes the preliminary LC010 "Model B on the
live source path" reading.

Branch base: `13d6515f6421fb131924e9d9f7fd3717a2e3faa0` (LC010 head — candidate
lineage, not master-merged).
Canonical master at task time: `c2a1dab3125cdef0cff381815d3d995bdd340538`.
Genesis snapshot: `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`
(42,804 records).

Artifacts:
- `docs/planning/lc011_identity_registry_contract.json` — machine-readable contract; sha256 `61c2f13afb7dbd6d04c2f2b21021acb16292abb1ad6a35762529ade740ed231e`
- `docs/planning/lc011_owner_identity_decision_packet.md` — the 8 decisions to ratify
- `tools/lc011_identity_registry_prototype.py` — PROTOTYPE_ONLY executable contract sketch
- `tests/test_lc011_identity_registry_contract.py` — 43 tests

---

## 1. Decision (locked, pending owner ratification)

**Canonical identity = `source_record_uuid`, held in a persistent identity
registry, bootstrapped once from a frozen genesis snapshot (LC010 Model D).**

| lock | value |
|---|---|
| `LIVE_SOURCE_PATH_IS_CANONICAL_IDENTITY` | **NO** |
| `SOURCE_PATH_ROLE` | **GENESIS_SEED_AND_RESOLVER_ALIAS_ONLY** |
| `POST_GENESIS_UUID_RECOMPUTATION` | **FORBIDDEN** |
| `CONTENT_HASH_AS_IDENTITY` | **FORBIDDEN** (resolver evidence only) |
| `LEGACY_ID_UNIQUE_AUTHORITY` | **NO** (11 collision groups; compatibility alias only) |
| `RECORD_INDEX_IDENTITY_AUTHORITY` | **NO** (already shifted +201 in a past re-ingestion) |
| genesis mint (historical external SGF) | **UUIDv5**(namespace, genesis key) |
| new-record mint (admin-authored / source-less) | **UUIDv4**, persisted once |
| request-time UUID generation | **impossible by construction** |

**Why the live source path is not identity** (LC10-A evidence): the historical
builder `build_questions.py` "refreshes `content` and `source` from the SGF
tree" on every rebuild and preserves `id`, not `source`; `record_index` has
already moved; `sgf_engine_reentry_audit_v1.md` §6 and
`sgf_engine_v1_scope_freeze_20260718.md` both forbid identity from an SGF path.
The path is a perfect **genesis seed** (unique on the frozen snapshot) and a
useful **resolver alias** — nothing more.

## 2. Namespace  (`OWNER_NAMESPACE_RATIFICATION_REQUIRED = YES`)

`PROPOSED_CANONICAL_NAMESPACE_UUID = c70b30f4-b745-5585-b5c3-64021901ad76`

- **Generated** deterministically as
  `uuid5(uuid.NAMESPACE_URL, "godokoro:immutable-puzzle-identity:source-record-namespace:scheme-v1")`
  — reconstructible from this contract alone. **The seed deliberately does NOT embed the ADR document version** (LC11-E) — `scheme-v1` is the identity-generation scheme version; an ADR text revision never changes the namespace. `assert_namespace()` mechanically rejects any other value at every mint.
- **Documented** here and in the contract JSON.
- **Frozen**: once ratified, this UUID is a checked-in constant. It is never
  edited.
- **Protected from accidental replacement**: the backfill and the authoring
  flow read the constant from the ratified contract; a mismatch between a
  record's stored `namespace_uuid` and the constant is a drift error → STOP.
- **Versioned, not rotated**: a future *incompatible* identity-generation
  scheme uses a **new namespace** derived from a `.../v2` URL string, and new
  records mint under it while existing `source_record_uuid`s are untouched
  (the registry maps both). Namespace change is **never** ordinary versioning —
  a canonicalisation tweak or a new field bumps `canon-source-vN` /
  `genesis-key-vN`, not the namespace.
- The LC010 prototype namespace `892f7446-c0ca-5320-806f-798d5acc3c27` is
  explicitly **NOT** promoted; the contract records it only so it can never be
  silently reused.
- The owner may instead ratify an opaque random UUIDv4 as the namespace — the
  registry contract does not depend on how it was generated, only that it is
  frozen and owner-ratified.

## 3. Canonicalisation ADR  (`canon-source-v1`)

Applied to `record["source"]` to produce the genesis seed / resolver alias key.
**Not** identity by itself.

| rule | value | rationale |
|---|---|---|
| `UNICODE_NORMALIZATION` | **NFC** (never NFKC) | NFKC merges meaningful fullwidth chars (`｜`, `０-９`, `．`) that are part of distinct collection names |
| `PATH_SEPARATOR` | every `\` → `/` | one canonical separator |
| `LEADING_SEPARATOR` | stripped | |
| `TRAILING_SEPARATOR` | stripped | |
| `DUPLICATE_SEPARATOR` | `/{2,}` → `/` | |
| `WHITESPACE` | whole-string leading/trailing stripped; **internal preserved verbatim** | folder names like `10.布 局` contain real spaces |
| `CASE_POLICY` | **PRESERVE** (never casefold) | source FS case-sensitivity is unproven; casefold could merge two genuinely distinct files. (0 casefold-collisions in this corpus, but the rule must not depend on that.) |
| `FILE_EXTENSION_POLICY` | path **must** end `.sgf` (lower, exact); kept verbatim; `.SGF` → **fail closed**. The check is a **literal suffix test — never `splitext` / last-dot**; 327 folder segments contain `.` (`3.死 活`, `Vol. 2`) and are preserved (LC11-A). | the identity layer does not silently normalise a bad extension |
| `RELATIVE_ROOT_POLICY` | collection-relative; the `SGF題庫` tree root is **not** in the key (pinned separately by the source-tree manifest, §12) | |
| `COLLECTION_NAME_POLICY` | first path segment; preserved verbatim under the global rules | it is data, not identity structure |
| reject → `SOURCE_NOT_RECOVERABLE` (fail closed) | any C0/C1 control, BOM, **zero-width / bidi-control / NBSP / ideographic-space / word-joiner / line-or-para separator** (LC11-E), U+001F; any empty / `.` / `..` segment; any segment ending in space or dot; non-`.sgf` | ambiguous — the **curator** fixes the source tree, not the identity layer |

Over the frozen snapshot: all 42,804 `source` values canonicalise to **42,804
distinct keys**, **0** fail-closed (contract + LC10-E). This is a property of
*this* snapshot; a dirtier future corpus fail-closes correctly.

## 4. Genesis key contract  (`genesis-key-v1`) — **Option C: no snapshot SHA in the name**

```
name = "gk1" ⟨U+001F⟩ "sgf-source-file" ⟨U+001F⟩ "v1" ⟨U+001F⟩ <canonical_source>
source_record_uuid(genesis) = uuidv5(PROPOSED_CANONICAL_NAMESPACE_UUID, name)   # name UTF-8 encoded
```

- `U+001F` (Unit Separator) is the field delimiter; it is a control char, so
  the canonicaliser **rejects** any source containing it → the join is
  unambiguous and a maliciously-named SGF file cannot forge another record's
  key (a real canonical source can never contain `U+001F`, and never begins
  `gk1⟨US⟩…` — `gk1` would be a folder segment and the `US` bytes are rejected).
- **`GENESIS_KEY_SPEC_VERSION = genesis-key-v1`.**
- The genesis snapshot SHA is **NOT** in the name. It is immutable **registry
  provenance** (`genesis_snapshot_sha256`, plus a stable owner-assigned
  `corpus_id`) and a hard **`GENESIS_BOOTSTRAP_ONCE_ONLY`** gate (§13).

### Why NOT the snapshot SHA in the name (§10 analysis — revised after LC11-A)

| option | identical frozen rebuild | later corpus version, same file | rename / tree correction | **operator re-runs the mint on a refreshed `questions.json`** |
|---|---|---|---|---|
| **A** — ns + canonical_source only, **no gate** | same UUID | **same UUID silently** — a different corpus's file merges onto the genesis identity | new UUID unless registry | **silently mints a NEW disjoint identity set — undetected** |
| **B** — ns + **snapshot SHA** + canonical_source | same UUID (re-derive) | bare re-derive differs → resolver | resolver + ledger | **silently reassigns ALL 42,804 identities to a disjoint set** — the SHA changed, so the mint "succeeds"; `source` is a regenerated projection so there is no in-file anchor to catch the drift (LC11-A) |
| **C** — ns + canonical_source, **+ `corpus_id` / snapshot-SHA registry provenance + `GENESIS_BOOTSTRAP_ONCE_ONLY`** (**recommended**) | same UUID (re-derive, audit only) | bare re-derive is identical, but a second bootstrap is **REFUSED** by the gate → the new corpus goes through the resolver + `MANUAL_IDENTITY_RECONCILIATION` | resolver + ledger | **REFUSED** — the gate sees a genesis bootstrap already ran and stops; drift is an error, not a silent event |

**Recommendation: Option C.** Option B makes "mint exactly once, ever"
load-bearing for correctness with nothing enforcing it — the single most
dangerous property, because the one thing that goes wrong (an operator points
the bootstrap at a rebuilt corpus) is exactly the thing B fails to catch.
Option C keeps the name a pure function of the canonical source (benign
rebuilds reproducible, re-imports idempotent) and turns "the mint was re-run"
from *silent total identity reassignment* into a **refused operation**, via:
`GENESIS_INPUT_EXACT_MATCH` (the input must be this exact snapshot) **and**
`GENESIS_BOOTSTRAP_ONCE_ONLY` (the registry records that the one bootstrap
happened; a second one for a different `(corpus_id, snapshot_sha)` raises).
Post-genesis nobody re-derives (§6).

## 5. Persistent registry contract

Logical record; `field → authority class`:

| field | class | meaning |
|---|---|---|
| `source_record_uuid` | **AUTHORITY** | the identity |
| `identity_status` | **AUTHORITY** | ACTIVE / RETIRED / AMBIGUOUS / NEEDS_REVIEW / SOURCE_MISSING (§9) |
| `mint_method` | **AUTHORITY** | GENESIS_UUIDV5 / NEW_RECORD_UUIDV4 |
| `namespace_uuid`, `genesis_snapshot_sha256`, `genesis_key_spec_version`, `canonicalisation_rules_version`, `genesis_source_raw`, `genesis_content_sha256`, `minted_batch_id`, `minted_at`, `minted_by`, `lineage_parent_uuids`, `superseded_by_uuid`, `retired_reason` | **AUDIT** | provenance / history; never consulted for a runtime decision |
| `genesis_source_canonical`, `legacy_question_id`, `current_source_alias`, `historical_source_aliases` | **ALIAS** | resolver inputs; NOT identity, NOT unique (`legacy_question_id` collides) |
| `source_collection` | **DERIVED** | first segment of the current alias |
| `created_identity_kind` | **DERIVED** | HISTORICAL_EXTERNAL_SGF / NEW_NATIVE |
| `review_note` | **OPTIONAL** | |

`REGISTRY_AUTHORITY`: after genesis, `source_record_uuid` is **never recomputed
from any mutable field**. A source change flows: *resolver → lineage event →
the same persisted UUID where it is the same source entity*.
`LEGACY_ID_UNIQUE_CONSTRAINT = NO` (it would reject 11 valid corpus groups).

## 6. Resolver contract (fail closed)

Deterministic priority ladder (full form in the contract JSON). Result classes:
`EXACT`, `HIGH_CONFIDENCE_UNIQUE`, `AMBIGUOUS`, `MISSING`, `COLLISION`.
**Only `EXACT` and `HIGH_CONFIDENCE_UNIQUE` auto-preserve an identity.**

1. incoming `canonical_source` == a record's current or historical alias
   (exactly 1 ACTIVE):
   - content matches (or not supplied) → **EXACT**
   - content changed **and** a `CONTENT_CORRECTION` event exists → **HIGH_CONFIDENCE_UNIQUE**
   - content changed, no event → **AMBIGUOUS** (correction vs replacement — human)
   - >1 ACTIVE claim the alias → **COLLISION** (integrity error — human)
2. `genesis_source_canonical` **and** `genesis_content_sha256` both match
   (retired records included → restore) → **EXACT**
3. `content_sha256` matches exactly 1 ACTIVE, no path relationship →
   **HIGH_CONFIDENCE_UNIQUE**; matches >1 (the 404 duplicate groups) →
   **AMBIGUOUS** (`CONTENT_HASH_AS_IDENTITY = FORBIDDEN`)
4. `legacy_question_id` maps to exactly 1 ACTIVE → **HIGH_CONFIDENCE_UNIQUE**;
   maps to >1 (the 11 collision groups) → **AMBIGUOUS**
5. nothing matches → **MISSING** (mint a new identity — correct for a genuinely
   new file)

`AMBIGUOUS` / `COLLISION` → route to `MANUAL_IDENTITY_RECONCILIATION`;
never auto-assign. Content hash is only ever corroborating evidence.

## 7. Lineage ledger (append-only)

Event types: `SOURCE_RENAME`, `SOURCE_MOVE`, `SOURCE_COLLECTION_RENAME`,
`SOURCE_CASE_ONLY_RENAME`, `CANONICALISATION_RULE_CHANGE`, `CONTENT_CORRECTION`,
`METADATA_CORRECTION`, `DELETE`, `RESTORE`, `SOURCE_SPLIT`, `SOURCE_MERGE`,
`SOURCE_REPLACED`, `MANUAL_IDENTITY_RECONCILIATION`.

Each event: `sequence` (monotonic per registry — ordering, not wall-clock),
`event_type`, `source_record_uuid` (subject) or `parent_uuids` / `child_uuids`
(split / merge), `old_provenance` / `new_provenance`
(`{canonical_source?, content_sha256?}`), `reason`, `evidence`
(`{resolver_class, corroborating_fields}`), `authority`
(`RESOLVER_AUTO` | `OWNER_REVIEW` | `ADMIN`), optional caller-supplied
`occurred_at`.

## 8. Source-mutation semantics

| event | Same UUID? | how |
|---|---|---|
| rename only / folder move | **YES** | registry updates the alias, old → `historical_source_aliases`; UUID **never recomputed** from the new path |
| collection rename | **YES** | one `SOURCE_COLLECTION_RENAME` rewrites every affected record's alias; UUIDs unchanged |
| case-only rename | **YES** | case is preserved in the alias; UUID unchanged |
| canonicalisation rule change (`canon-source-v2`) | **YES** | a `CANONICALISATION_RULE_CHANGE` event; genesis UUIDs are **never re-minted**; the registry maps the old canonical key → the existing UUID |
| content correction, same source entity | **YES** | `CONTENT_CORRECTION` event, `OWNER_REVIEW` authority; resolver rank 1.1 |
| **different puzzle at the same filename** | **NO** | `SOURCE_REPLACED` event; the old identity is RETIRED or moved to its new alias; the new file → `MISSING` → new mint. Without an explicit event the resolver returns **AMBIGUOUS** (fail closed) — a human classifies it |
| split (one source record → several) | **NO** | parent → RETIRED (`reason SPLIT`); each child gets a fresh identity; `child.lineage_parent_uuids = [parent]`; parent kept for audit |
| merge (several → one) | **NO** | one survivor kept ACTIVE; the others RETIRED with `superseded_by_uuid = survivor`; all histories preserved |
| delete → restore | **only** on `EXACT` / `HIGH_CONFIDENCE_UNIQUE` | `DELETE` → RETIRED; `RESTORE` reactivates the **same** UUID only if the resolver is strong; weak evidence → new mint; **no request-time fresh UUID** just because a file vanished |
| reimport of the identical frozen corpus | **YES** | genesis key = f(canonical_source) re-derives (Option C); the once-only gate then refuses a second write |
| reimport under a new snapshot sha | **YES for the same entity** | bare re-derive differs → resolver matches on alias / genesis source+content; a genuinely new file → `MISSING` → new mint |

## 9. Identity lifecycle & runtime contract

States: `ACTIVE` (the **only** state runtime may consume as canonical
identity), `RETIRED`, `AMBIGUOUS`, `NEEDS_REVIEW`, `SOURCE_MISSING`.

Runtime **consumes** `source_record_uuid` from the canonical persisted
read-model, `identity_status == ACTIVE` only. Runtime **must not**: recompute
identity, inspect a filesystem path to mint identity, generate a request-time
UUID, or fall back to `content_sha256` as identity. **Migration fallback**: if
`source_record_uuid` is absent, runtime uses `legacy_question_id` as a
**labelled non-canonical** compatibility key and emits
`canonical_identity_missing = true` (mirrors the LC003/LC004
`canonical_puzzle_id = null` / `invalid_identity = true` pattern). It never
mints or guesses.

### Dual-ID migration window

| aspect | rule |
|---|---|
| write authority | the offline genesis backfill + the future authoring flow are the **only** writers of `source_record_uuid`; nothing at request time |
| read authority | the canonical read-model; `source_record_uuid` preferred, `legacy_question_id` a labelled alias |
| API serialization | emit both `source_record_uuid` (or null) and `question_id`; `question_id` is non-unique |
| logging | `source_record_uuid` where present, else `legacy_question_id` + `canonical_identity_missing=true` |
| admin tools | key edits by `source_record_uuid` where present; the 11 legacy-collision groups are editable **only** via `source_record_uuid` or the `(record_index, legacy_question_id)` audit locator |
| test fixtures | may carry a clearly-fake `PROTOTYPE_ONLY` `source_record_uuid` or none |

## 10. New admin-created / source-less records

`app.py add_question()` writes `source = ''` (0 such records exist today, so
none were added since the last rebuild). Policy:

`NEW_RECORD_IDENTITY_POLICY = REGISTRY_MINTED_PERSISTED_UUIDV4`. At
authoritative creation of a hand-authored canonical question, the authoring
flow mints **one random UUIDv4**, writes it to the registry
(`mint_method = NEW_RECORD_UUIDV4`, `created_identity_kind = NEW_NATIVE`,
`genesis_* = null`) and persists it on the record. Never recomputed, never
request-time regenerated. Rejected alternative:
`UUIDv5(author + counter + content_sha256)` — none of those is a stable
*source entity* (author can be wrong, the counter is an allocation-order =
`record_index` analog, content can change).

**Hybrid architecture accepted** (§22): historical external-SGF records use
UUIDv5 genesis; new native records use UUIDv4. Both obey one registry
contract — mint once, persist, never recompute, resolver + lineage carry
forward. Risks / rules (LC11-A):
- a v5/v4 cross-collision is **impossible** (RFC 4122 version nibble differs);
  within-v4 collision is ~2⁻¹²² (negligible);
- a consumer branching on `uuid.version` is **forbidden** by the runtime
  contract (§9): the UUID is an opaque identifier;
- a v4 is **not recomputable** (it exists only in the registry), so the
  registry + lineage **must** be append-only *and replicated* storage — it is
  the single point of truth for every NEW_NATIVE identity;
- **`v4 → v5 "upgrade" is FORBIDDEN**: if a NEW_NATIVE record later acquires a
  real `source`, the path becomes a `current_source_alias` — it never triggers
  a re-mint. The v4 is permanent.

## 11. External SGF tree freeze  (`EXTERNAL_SGF_TREE_FREEZE_REQUIRED = YES`)

Minimum prerequisite artifact **`SGF_SOURCE_TREE_GENESIS_MANIFEST`**:
- per file: `relative_path` (raw, pre-canonicalisation), `content_sha256`
  (SGF bytes on disk), `collection` (first segment);
- tree-level: `file_count` (must == 42,804), `tree_manifest_sha256` (sha256 of
  the canonically-sorted manifest body).

Checked into the repo as a path+hash list (a few MB) or a hashed/compressed
form. The raw SGF corpus is **not** copied into the repo unless separately
authorized. **LC011 cannot build this** — the SGF tree is external and not
present; producing it is a gated prerequisite step.

## 12. Frozen genesis manifest

Deterministic binding of the 42,804 records to source provenance, produced once
against the frozen snapshot. Per record: `record_index` (**AUDIT ONLY** — not
identity), `legacy_question_id` (ALIAS), `raw_source` (AUDIT),
`canonical_source` (ALIAS), `content_sha256` (evidence),
`proposed_source_record_uuid` (the genesis mint). Header: `snapshot_sha256`,
`record_count = 42804`, `genesis_key_spec_version`, `namespace_uuid`,
`canonicalisation_rules_version`. The contract JSON carries the header + a
bounded sample + collision/fail-closed counts; the full 42,804-row form is
reproducible from the prototype and is not committed.

## 13. Backfill algorithm design (NOT executed)

1. **Input + once-only validation** — `sha256(questions.json) ==
   GENESIS_SNAPSHOT_SHA256` exactly; `record_count == 42804`; the live SGF tree
   reproduces `SGF_SOURCE_TREE_GENESIS_MANIFEST` exactly
   (`GENESIS_INPUT_EXACT_MATCH`); **and the registry holds no prior genesis
   bootstrap** (`GENESIS_BOOTSTRAP_ONCE_ONLY` — a second run for a different
   `(corpus_id, snapshot_sha)` is refused). Any mismatch → **STOP, mint nothing**.
2. **Manifest build** — canonicalise every `source`; fail closed on any
   `SOURCE_NOT_RECOVERABLE`; mint the genesis UUID for each; assert 42,804
   distinct UUIDs (collision detection) → abort on any collision.
3. **Existing-UUID detection** — for each record consult the registry via the
   resolver; `EXACT` match to the proposed UUID → skip (idempotent); a
   *different* existing UUID → **STOP (drift), human**.
4. **Dry-run** — emit the full plan (`N` to mint / `0` to change / `M` already
   present) with per-record before/after; **no writes**.
5. **Apply** — OWNER-GATED, separate step (not LC011): insert-only into the
   registry; write `source_record_uuid` into a **new** canonical read-model
   (**not** `questions.json` — that stays the frozen genesis input); append a
   `GENESIS` lineage marker per record.
6. **Idempotent rerun** — same frozen input → step 3 finds all present →
   0 mint, 0 change. (`BACKFILL_IDEMPOTENCY_DESIGN = PASS` — prototype dry-run
   verified over the full snapshot.)
7. **Rollback / recovery** — the registry is additive / insert-only; rollback =
   drop the read-model overlay; rows from a failed run are identifiable by
   `minted_batch_id` and are **tombstoned** (never hard-deleted) by an
   owner-gated recovery step.

`GENESIS_INPUT_EXACT_MATCH = YES` is a hard gate: any snapshot / manifest drift
→ STOP; identities are never minted against a different corpus.

## 14. Owner gate & boundaries

`OWNER_IDENTITY_FOUNDATION_APPROVAL_REQUIRED = YES` — no mint begins until the
owner ratifies: the identity model, the namespace, the canonicalisation ADR,
the genesis key spec, the registry contract, the new-record policy, and the
SGF source-tree freeze artifact (the 8 decisions in
`lc011_owner_identity_decision_packet.md`).

`APP_PY_CHANGED = NO`. `ADD_QUESTION_PATCH_REQUIRED = YES` — future behaviour
(not a patch here): `add_question()` must either set a real `source` for an
imported SGF or, for a hand-authored question, call the authoring flow that
mints a persisted `NEW_RECORD_UUIDV4` and never leave identity to a later
guess. The current RPG `app.py` writer path belongs to B051; this ADR only
records the required future behaviour.

`SCHEMA_CHANGED = NO`, `MIGRATION_CHANGED = NO`. If the registry is later
persisted in a database, the migration requirements are produced as a separate
owner-gated task (insert-only `identity_registry` table keyed on
`source_record_uuid`; a separate append-only `identity_lineage` table; **no**
unique constraint on `legacy_question_id`).

`CORPUS_MUTATION = NO` · `SOURCE_RECORD_UUID_BACKFILL = NO` ·
`REQUEST_TIME_UUID_GENERATION = NO` · `LC009_SEMANTICS_CHANGED = NO` ·
`PRODUCTION_QUERY = NO` · `DEPLOY = NO` · `MASTER_MERGE = NO`.

## 15. Verification

- **Prototype + 35 tests** — deterministic frozen-genesis mint (42,804 / 42,804
  distinct, 0 collision on the real snapshot); reorder invariance; rename /
  move keep the UUID and never recompute; content-correction vs
  source-replacement; split / merge / delete / restore; resolver fail-closed on
  AMBIGUOUS / COLLISION; 404-duplicate + 13-legacy-collision separability;
  source-less new-record → persisted UUIDv4; no request-time identity API;
  idempotent non-mutating dry-run; drift gate fails closed.
- **LC11-A** (canonicalisation / resolver-collision / snapshot-in-name stress)
  and **LC11-E** (adversarial break attempt) — findings appended below.

### LC11-A findings (canonicalisation / resolver / snapshot-in-name stress) — folded in

- **Biggest risk (acted on): the snapshot-SHA-in-name (Option B) makes
  "mint once, ever" load-bearing with nothing enforcing it.** The ADR now uses
  **Option C** + `GENESIS_BOOTSTRAP_ONCE_ONLY` (§4, §13).
- **Character set:** 640 distinct code points across the 42,804 `source`
  values — ASCII alnum + space + `\` + `.` + `& ' ( ) -`, 566 CJK ideographs,
  `、` `—`, and 6 fullwidth-compat chars (`（ ） ， ６ ： ｜`, 91,279 occ).
  **Zero** control / C1 / BOM / zero-width / NBSP / ideographic-space / bidi /
  combining / surrogate / PUA. Already 100 % NFC. Zero trailing-dot/space
  segments, zero `.`/`..`, zero leading slash, zero `//` — the strip/collapse
  rules are currently no-ops. `.sgf` lowercase on 100 % of leaves.
- **327 folder segments contain `.`** (13,140 paths — chapter prefixes like
  `3.死 活`, `Vol. 2`). The `.sgf` rule is now an explicit **literal suffix
  test, never `splitext`** (§3).
- **Collision counts over the frozen corpus:** NFC = NFKC = casefold =
  NFKC+casefold = **0** — every policy is bijective today. Choice is
  future-proofing: keep **NFC** (NFKC would silently merge future `（）`/`()`,
  `６`/`6` variants); keep **preserve-case** (treat case variants as resolver
  aliases).
- **Resolver keys:** `(source, content_sha256)`, `(legacy_id, source)` and
  `(content_sha256, legacy_id)` are each **globally unique** (0 collisions).
  **No** record pair is identical on all non-`source` evidence. Weak spot: a
  rebuild that renames *and* content-corrects in one pass defeats both — the
  append-only `historical_source_aliases` + lineage ledger is the mitigation.
- **11 duplicate `legacy_question_id` values span 22 records** (all size-2);
  the LC008/LC010 census flags **13** of those 22 as `DUPLICATE_IDENTITY_BLOCKED`
  (the bare-terminal subset). All 22 are `source`-separable.
- **New-record key: UUIDv4 required** — `add_question()` sets no `created_at` /
  `created_by` / counter; `id = max+1` is unsafe (~24k gaps, 11 dup ids).

### LC11-E findings (adversarial break attempt) — folded in

**NO CORE BREAK.** No attack forged, collided, lost, or rebound a
`source_record_uuid`; `resolve()` never auto-preserved a wrong identity. All 7
attack areas held on the frozen corpus (genesis determinism/collision — 42,804
distinct v5, 0 collisions, byte-identical across two processes; canonicalisation
— all 42,804 clean, 0 fail-closed, NFC/NFKC/casefold all 0 collisions; resolver
— a 200-record realistic re-ingestion with renames + corrections + deletions +
new files produced 0 mis-resolves; hybrid v5/v4 — cross-collision impossible;
idempotency/drift — dry-run identical ×2, `GENESIS_BOOTSTRAP_ONCE_ONLY` refuses
a second bootstrap, a changed snapshot sha raises pre-mint).

**Six hardening gaps found and closed in this revision:**

1. **Namespace drift was promised in §2 but enforced nowhere.** Added
   `assert_namespace()` — called by `mint_genesis_uuid` and every genesis
   registration; any non-ratified namespace raises `NAMESPACE_DRIFT`. The seed
   string no longer embeds the ADR document version (`v1.1`) — it carries only
   the identity-scheme version (`scheme-v1`), so an ADR text edit can never
   re-key identities. (Namespace value changed to
   `c70b30f4-b745-5585-b5c3-64021901ad76`.)
2. **Non-C0/C1 invisibles** (zero-width, bidi controls, NBSP, ideographic
   space, word-joiner, line/para separators) were neither rejected nor
   stripped. Now **rejected** (`_INVISIBLE_CODEPOINTS`, fail closed) — a
   homograph cannot split one identity into two. ASCII-whitespace-only
   `.strip()`.
3. **`restore()` trusted a caller-supplied `resolver_class` string.** It now
   runs `resolve()` itself against real provenance and reactivates the UUID
   only when the resolver returns `EXACT` / `HIGH_CONFIDENCE_UNIQUE` **and**
   points at that exact UUID.
4. **`rename_or_move()` had no alias-uniqueness guard.** It now refuses to move
   onto a path already held by another ACTIVE record; a `check_integrity()`
   sweep is available.
5. **`split()` / `merge()` accepted unregistered children / non-ACTIVE
   subjects.** Both now assert registration and lifecycle state.
6. **`build_genesis_manifest()` never re-hashed its input.** It now requires a
   caller to pass the independently-verified snapshot sha (`run()` passes the
   sha it computed from the bytes) and refuses a mismatch.

Residual (acknowledged, not a defect): resolver rank 3.0 auto-preserves on a
unique *ACTIVE* content match even when a duplicate sibling is only RETIRED —
correct behaviour (RETIRED records are not competing claimants), documented in
the ladder.
