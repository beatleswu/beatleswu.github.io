# LC010 — `source_record_uuid` Identity Foundation & Backfill Feasibility

Branch base: `b3fd5e12f8789c82d1a74494904d550269f70c1d` (LC008 head)
Canonical master at task time: `c2a1dab3125cdef0cff381815d3d995bdd340538`
Mode: **READ / ANALYZE / PROTOTYPE / TEST ONLY.** No corpus mutation. No UUID
backfill. No request-time generation. No LC009-semantics change. No DB/schema.

Artifacts:
- `tools/lc010_source_identity_prototype.py` — PROTOTYPE_ONLY read-only analyzer + hypothetical-UUID generator
- `docs/planning/lc010_source_identity_feasibility_manifest.json` — deterministic feasibility manifest (summary + 404-group audit + 13-record audit + bounded sample); sha256 `abd2a300699fce185244d4d1e57641385766807a7cc8bdde5897f6a2d7211186`
- `tests/test_lc010_source_identity_prototype.py` — 22 tests

## 0. Executive summary

Two things are true and must not be conflated:

1. **A one-time GENESIS assignment of `source_record_uuid` is mechanically
   feasible for 100 % of the 42,804 records of this frozen snapshot.** Every
   record carries a unique, well-formed `source` SGF path; on the *frozen*
   snapshot `source`, `record_index`, and `(record_index, legacy_question_id)`
   are all unique and immutable. The prototype assigns 42,804 distinct
   hypothetical UUIDv5s with **0 collisions**, separating all 404 exact-content
   duplicate groups and all 13 legacy-`id` collision records, deterministically.

2. **No field in the live corpus survives re-ingestion**, so a *pure
   deterministic function of a live field* is NOT a safe identity. LC10-A
   evidence: the historical builder `build_questions.py` "refreshes `content`
   and `source` from the SGF tree" on every rebuild and preserves `id`, not
   `source`; `record_index` has already shifted **+201** between two real
   corpus revisions with identical content; `id` collides (11 groups) and is
   reuse-eligible; `app.py add_question()` writes `source=''`; two current
   authoritative docs (`sgf_engine_reentry_audit_v1.md` §6,
   `sgf_engine_v1_scope_freeze_20260718.md`) explicitly forbid identity from
   "SGF path" / "filename".

**Recommended model: D — a persistent identity registry, bootstrapped from a
FROZEN GENESIS snapshot.** The genesis UUID for each record is minted once,
offline, as `UUIDv5(owner-namespace, genesis_sha256 + ":" +
"sgf-source-file:v1:" + canonical(source))` — reconstructible from the frozen
snapshot alone — and written to an insert-only registry that thereafter is the
sole identity authority. A resolver + lineage ledger carry identity across
future re-ingestions (match on content + `source` + legacy id; mint only for
genuinely new records; record split / merge / rename). The pure Model B
(deterministic on the *live* `source`) is rejected because `source` is a
regenerated projection.

`BACKFILL_FEASIBILITY = PARTIAL`:
- **feasible now:** the genesis assignment for all 42,804 frozen-snapshot
  records (prototype-proven, deterministic, collision-free, dup/legacy
  separable);
- **still blocked:** the owner A/B identity decision is unmade
  (`canonical_identity_owner_decision_20260717.md` = `OWNER_DECISION_REQUIRED`);
  no owner-ratified namespace + canonicalisation ADR; the registry + resolver +
  lineage ledger do not exist; the external `SGF題庫` tree has no immutable
  versioning; `add_question()` must be changed to stop writing `source=''`.

None of the blockers is a *data* problem in this snapshot — they are the
governance + build work the reverted PR #157 / the V1.1 "Immutable Puzzle
Identity Foundation" scope already anticipated.

## 1. Q1 — what is a real source record? (`SOURCE_ARCHITECTURE_TRACED = YES`)

Every one of the 42,804 records maps 1:1 to **one source SGF file**, recorded
verbatim in `record["source"]` as a collection-relative path:

```
<top-level collection>\[<chapter folder>\ …]\<n>.sgf
```

Evidence (all from the byte-verified snapshot + tracked repo):

| observation | value |
|---|---|
| records with a non-empty `source` | 42,804 / 42,804 |
| distinct `source` values | **42,804 / 42,804 — unique per record, 0 collisions** |
| `source` values ending `.sgf` | 42,804 / 42,804 |
| path separator | back-slash in all 42,804; **0** forward-slash; 0 leading/trailing whitespace; 0 change under Unicode NFC |
| distinct top-level collections | 55 (each equals a `map_name` / `map_id`; `map_name` is a substring of `source` in 42,804 / 42,804) |
| path depth (folder segments) | 1→10,723 · 2→23,145 · 3→1,522 · 4→7,341 · 5→73 |
| `.sgf` files tracked in this repo | **0** — the SGF corpus is an external curated workbook tree, ingested into `questions.json` |

So the *source entity* is a file in an external SGF workbook collection. The
`source` field is the ingestion's faithful record of which file each canonical
question came from. It is the natural source-native key (Model C ≡ the path).

Prior identity work: `docs/planning/canonical_identity_owner_decision_20260717.md`
left the alias-key choice `OWNER_DECISION_REQUIRED` between a globally-unique
permanent `question_id` (A) and the historical composite
`(record_index, legacy_question_id)` (B). LC008 then superseded both by locking
`source_record_uuid` as the canonical identity. LC010 evaluates whether that is
buildable — and it is, from `source`. (LC10-A lineage findings appended in §12.)

## 2. Q2 — which source attributes are actually stable?

| candidate field | present | distinct | classification | note |
|---|---:|---:|---|---|
| `source` (SGF path) | 42,804 | **42,804** | **CONDITIONALLY_STABLE** | unique + well-formed *in this snapshot*, and the best genesis anchor; but a **regenerated projection** — `build_questions.py` "refreshes `content` and `source` from the SGF tree" every rebuild and preserves `id`, not `source` (LC10-A); `add_question()` writes `source=''` |
| `id` (legacy) | 42,804 | 42,793 | **UNSTABLE** | 11 collision groups (22 rec); sparse 7,955–74,792 with 24,045 gaps; allocated `max+1`, deletable/reusable |
| `record_index` | (positional only) | 42,804 | **UNSTABLE / DERIVED** | array position; **demonstrably already shifted +201** between two real corpus revisions with identical content (LC10-A, `sgf_answer_current_canonical_contract_v2`); forbidden in identity by rule |
| `map_id` / `topic` | 42,804 | 55 | CONDITIONALLY_STABLE | collection identity; derivable from `source` top-level |
| `grimoire_id` | 42,688 | 214 | CONDITIONALLY_STABLE | 116 missing; curatorial grouping, not per-record |
| `sort_order` | 42,804 | 1,024 | UNSTABLE | in-chapter ordinal; `(map_id, sort_order)` has 20,312 records in collisions |
| `display_name` | 42,804 | 2,966 | UNSTABLE | per-file label (often the leaf number); `(map_id, display_name)` collides 35,824 |
| `katago_full_report` / `_applied_at` | 18,763 | 2 | DERIVED | KataGo run artefacts, not identity |
| `answer_source` | 18,770 | 5 | DERIVED | answer-authority provenance, not identity |
| `manual_restore_note` | 7,560 | 3 | DERIVED | restore-batch breadcrumb |
| import batch / source hash / mapping table / source-native numeric key | — | — | **MISSING** | none present in the snapshot (LC10-A) |
| SGF node/path identity | n/a | n/a | AMBIGUOUS | 404 groups are byte-identical SGF → cannot identify a record |

**`source` is the only field that is unique across all 42,804 records**, and
the best *genesis* anchor, but it is not immutable identity (it is regenerated
by the builder). `id` collides; `record_index` has already moved. No
import-batch id, source file hash, or SGF→record mapping manifest exists.

## 3. Q3 — identity survival across re-ingestion

Anchored on a **frozen genesis snapshot** with a persistent registry (the
recommended Model D). A "genesis key" = `canonical(source)` on the frozen
snapshot; the registry, not any live field, is authority after bootstrap.

| scenario | Same UUID? | mechanism |
|---|---|---|
| **A. Corpus reorder** | **YES** | genesis key never uses `record_index`; registry lookup by content + `source` |
| **B. Rebuild from the same SGF tree** | **YES *if* the SGF tree layout is pinned** | genesis key re-derives; else the resolver re-matches new records to genesis UUIDs by `(content_sha256, source, legacy_id)` and only mints for genuinely new files. `build_questions.py` regenerates `source`, so a bare deterministic re-derive is **not** safe on its own — the resolver + registry are required |
| **C. Metadata enrichment** | **YES** | genesis key ignores every metadata field; registry unaffected |
| **D. SGF content correction** (same source file) | **YES** | still the same source entity; resolver matches on `source` + prior `content_sha256` lineage; verdict may change, identity does not |
| **E. Source file rename** | **YES via registry** | resolver cannot re-derive; a lineage-ledger `rename(old_key → uuid)` row preserves it |
| **F. Folder move** | **YES via registry** | same as rename |

Only A and C are safe from the deterministic key alone. B and D need the
**resolver**; E and F need the **lineage ledger**. This is why the model must
be registry-anchored, not a pure function of the live `source`.

## 4. Source-tree reproducibility — the blocking evidence gap (LC10-A)

The SGF source files are **not in this repo** and the ingestion is not
reproducible from tracked code:

- The historical builder is `build_questions.py` — **not in this repo**;
  described in `sgf_answer_repair_batch_001_phase2c_canonical_corpus_provenance.md`
  as a local file whose behaviour is: input root = sibling `SGF題庫` tree,
  **"`content` and `source` are refreshed from the SGF tree"** every run,
  **"existing IDs and non-source fields are preserved where possible"** — so a
  rebuild preserves `id`, *not* `source`.
- `SGF題庫` has "only timestamped backup siblings," **no manifest pinning
  paths**, no version control.
- `sgf_engine_reentry_audit_v1.md` §6 (current): `source` path =
  "Human-readable path, **not immutable identity**"; `record_index` =
  "Reordering/re-ingestion can change it"; `IDENTITY_DECISION = DEFERRED`.
- `sgf_engine_v1_scope_freeze_20260718.md` (current): "No V1 rollout gate may
  infer identity from … **filename, SGF path**, ordering, or a content
  fingerprint."
- Direct proof of past re-ingestion: `record_index` shifted **+201** for
  records with identical content hash between the historical and current
  corpus (`sgf_answer_current_canonical_contract_v2/*.json`; e.g. legacy id
  7956: index 16931 → 17132).
- `app.py add_question()` (`:13258`) sets `'source': ''` for every
  admin-created record — a permanent hole in any `source`-derived scheme
  (0 such records exist now, so none were added since the last rebuild).

The "pre-KataGo backup" restore (`manual_restore_note`, 7,560 records) changed
`content` / recorded answer only — **no evidence it touched `source`**.

Conclusion: `source` is faithful *within one ingestion era* but is a
regenerated projection of an unpinned external tree. It is a valid **genesis**
anchor; it is not a re-ingestion-stable identity by itself.

## 5. Identity model comparison

| | **A — random UUIDv4, persisted once** | **B — deterministic UUIDv5 on the *live* `source`** | **C — native source ID → mapping** | **D — persistent registry, frozen-genesis bootstrap** |
|---|---|---|---|---|
| identity authority | the persisted table | the live `source` field | the source-native id | **the registry** |
| genesis assignment feasible now | yes (mint 42,804 v4) | yes (v5 of `source`) | n/a — no native id exists | yes (v5 of frozen `canonical(source)`) |
| survives reorder (A) / metadata edit (C) | yes | yes | — | yes |
| survives rebuild (B) — `build_questions.py` regenerates `source` | table restored → yes | **NO** — key changes when `source` regenerates | — | yes, via resolver match on `(content, source, legacy_id)` |
| survives SGF correction (D) | yes | yes (same path) | — | yes |
| survives rename (E) / move (F) | table row keeps it | **NO** | — | yes, via lineage ledger |
| reconstructible without persisted state | no | yes (but see rebuild) | — | genesis layer yes; ongoing identity no |
| `add_question()` `source=''` hole | n/a (mint anyway) | **breaks** | breaks | resolver mints a fresh uuid |
| collision properties | 122-bit random | name-based; 0 in this snapshot | 0 | enforced unique |
| loss / recovery risk | **high** (lose table = lose identity) | low *if* `source` were immutable — it is not | — | medium (registry is backed up, additive, rollback-survivable) |
| already scoped by the org | reverted PR #157 minted v4 per record | — | — | **`sgf_engine_v1_scope_freeze_20260718.md` V1.1 "Immutable Puzzle Identity Foundation"** (registry + writer lock + CAS + lifecycle ledger + frozen genesis bootstrap) |

**Recommendation: D — persistent identity registry, bootstrapped from a frozen
genesis snapshot; genesis UUID minted deterministically as UUIDv5 of the
frozen `canonical(source)` (reconstructible), with a resolver + lineage ledger
for all subsequent re-ingestions.**

- **B alone is rejected** — its key (the live `source`) is regenerated on every
  rebuild and is explicitly disallowed as identity by current org docs.
- **A alone is rejected** — an un-reconstructible table as the sole authority
  is a single point of total identity loss.
- **C does not exist** — there is no source-native id; the path is the closest
  thing and it is not immutable.
- **D uses the good parts of B** (deterministic, reconstructible genesis keys)
  **and A** (a persisted authority) while adding the resolver + ledger that the
  re-ingestion evidence (§4) proves are mandatory.

## 6. UUID technology review

| version | mechanism | fit for source identity |
|---|---|---|
| **UUIDv4** | 122 random bits | Model A only. Not reconstructible; identity lives entirely in a table. |
| **UUIDv5** | SHA-1 of `namespace + name` | **Recommended for the genesis layer.** Deterministic, reconstructible, namespaced, ordering-independent — "same frozen `source` → same genesis id". (v3/MD5 is the weaker-hash equivalent — prefer v5.) Post-genesis, the *registry* is authority; new records may get v5 (if a stable key exists) or v4 (if not). |
| **UUIDv7** | 48-bit Unix-ms timestamp + random | **Rejected.** Chronological ordering encodes *when the UUID was minted* — ingestion-run metadata, not source identity; would differ on every backfill run. "Newer" is not a reason. |

`RECOMMENDED_UUID_VERSION = UUIDv5` (genesis mint).

## 7. Required invariants

| | invariant | status under the recommended Model D |
|---|---|---|
| I1 | uniqueness (`UUID_COLLISION_COUNT = 0`) | **PASS** — 42,804 distinct frozen `canonical(source)` keys → 42,804 distinct UUIDs, 0 collisions (prototype + LC10-E) |
| I2 | stability on unchanged sources / re-ingestion | **NOT MET BY A LIVE-FIELD KEY; MET ONLY BY THE REGISTRY.** `build_questions.py` regenerates `source`; `record_index` already shifted +201. A frozen-genesis key is stable *for the frozen snapshot*; ongoing stability requires the registry + resolver, which do not exist. **This is the primary blocker.** |
| I3 | ordering independence | **PASS** — genesis key = `source` path only; `record_index` never used |
| I4 | request independence | **PASS** — offline genesis mint + offline resolver; never at request time (`add_question()` must be changed to not write `source=''`, but it never mints identity) |
| I5 | exact-content duplicates separable | **PASS** — all 404 groups' members get distinct UUIDs (every member's frozen `source` differs) |
| I6 | non-identity metadata edit stability | **PASS** — genesis key + registry ignore every metadata / provenance / answer field |
| I7 | legacy `id` is not authority | **PASS** — UUID derives from `source` / the registry, not `id`; the 13 `id`-collision records get 13 distinct UUIDs |
| I8 | fail closed | **PASS** — missing / ambiguous / non-`.sgf` `source` → no UUID assigned; `add_question()` `source=''` records → resolver mints fresh, never guesses |

## 8. Namespace governance (required if UUIDv5)

The prototype uses a **placeholder** namespace
`uuid5(NAMESPACE_DNS, "source-record.canonical.godokoro.com")` =
`892f7446-c0ca-5320-806f-798d5acc3c27` — clearly marked `PROTOTYPE_ONLY`. A real backfill
needs the owner to ratify:

| governance point | proposed rule |
|---|---|
| namespace ownership | a single constant UUID, owned by the Learning Core identity ADR, checked into the repo |
| namespace immutability | never changed; a new scheme = a new `KEY_SCHEME` prefix, not a new namespace |
| key scheme / versioning | `"sgf-source-file:v1:"` prefix on the name; bump to `v2:` only on a deliberate, documented key-shape change |
| path separator | normalise `\` → `/` (one canonical form) |
| case | **preserve** — a CJK workbook filesystem is not proven case-insensitive; lowering risks manufacturing collisions on rebuild (0 casefold-collisions today, but the rule must not depend on that) |
| Unicode | NFC (corpus is already 100 % NFC) |
| whitespace | strip leading/trailing on the whole string; **preserve internal** (folder names like `10.布 局` contain real spaces) |
| repeated separators | collapse `//` → `/` |
| extension | keep `.sgf` verbatim |

This prevents platform drift (`Book\A\001.sgf` vs `Book/A/001.sgf` vs
`book/a/001.sgf` — the first two converge, the third stays distinct by design).

## 9. Full 42,804-record feasibility census

| class | count |
|---|---:|
| `IDENTITY_PROVABLE` | **42,804** |
| `IDENTITY_PROVABLE_WITH_REGISTRY` | 0 |
| `IDENTITY_AMBIGUOUS` | 0 |
| `IDENTITY_MISSING_SOURCE_PROVENANCE` | 0 |
| `IDENTITY_COLLISION` | 0 |
| `SOURCE_NOT_RECOVERABLE` | 0 |
| **`IDENTITY_CENSUS_TOTAL`** | **42,804** (accounting PASS) |

Every record canonicalises to a unique `.sgf` key and receives one distinct
hypothetical UUIDv5. `IDENTITY_PROVABLE` here means *"a deterministic UUID is
unambiguously assignable from current provenance"* — it does **not** claim the
identity is immune to a future un-registered rename/move (that is what §3 E/F +
the registry address).

## 10. 404 exact-content duplicate-group identity audit (identity lens only)

| result | groups | records |
|---|---:|---:|
| `DUPLICATE_GROUPS_IDENTITY_PROVABLE` (all members → distinct UUIDs) | **404** | 940 |
| `DUPLICATE_GROUPS_PARTIAL` | 0 | 0 |
| `DUPLICATE_GROUPS_UNRESOLVED` | 0 | 0 |

Byte-identical SGF content, but every member has a distinct `source` path
(388/404 within one collection, 11/404 across collections), so the proposed
architecture separates every member. **This does not authorise review
fanout** — LC008's `SAFE_REVIEW_FANOUT = 0` stands; provable identity is a
*precondition* for a future fanout task, not a fanout result. LC010 implements
no fanout.

## 11. 13 `DUPLICATE_IDENTITY_BLOCKED` (legacy-`id` collision) identity audit

`LEGACY_COLLISION_RECORDS = 13` — indexes `16715, 16716, 16751, 16786, 16787,
17094, 32194, 33715, 41082, 41155, 41283, 41321, 41467`.
`LEGACY_COLLISION_RECORDS_SEPARABLE = 13 / 13`.
All 13 have distinct `source` SGF paths (e.g. `id 40511` = both
`…\2.行 棋\7.綜合測驗\2.sgf` and `…\7.实力测试\第2回\7.sgf`), so the source-derived
UUID gives each a distinct identity. Root cause of the *legacy* block —
`id` reuse — is bypassed entirely (I7). Not mutated.

## 12. Source-mutation semantics decision table

"Same UUID?" = under the recommended **Model D** (frozen-genesis mint +
registry + resolver + lineage ledger).

| source event | Same UUID? | Reason (evidence-based) |
|---|---|---|
| corpus reorder | **YES** | genesis key excludes `record_index`; registry lookup unaffected (§3A, I3) |
| metadata-only edit | **YES** | genesis key + registry ignore all metadata fields (§3C, I6) |
| typo correction in description | **YES** | `comment` / `display_name` not in the key |
| recorded-answer correction (`katago_best_move` etc.) | **YES** | answer-authority fields not in the key; identity ≠ answer |
| SGF answer-tree correction | **YES** | same source file → same entity; verdict may change, identity does not (§3D) |
| source filename rename | **YES via lineage ledger** | the resolver cannot re-derive; a `rename(old_key → uuid)` ledger row preserves it (§3E). Without the ledger: NO |
| folder move | **YES via lineage ledger** | same as rename (§3F) |
| exact file duplication (new file, same bytes) | **NO** | a new `source` path = a new source entity = a new UUID — this is *why* the 404 groups stay separable (I5) |
| source record split (one file → two) | **NO** | two new paths → two new UUIDs; ledger records `parent_uuid` |
| source record merge (two files → one) | **NO** | one surviving path → one UUID; ledger records the merged `parent_uuid`s |
| deleted then restored (same path) | **YES** | same frozen canonical key → same genesis UUID; registry row still present |
| reimport from the same canonical source | **YES *if* the `SGF題庫` layout is pinned; otherwise via the resolver** | `build_questions.py` regenerates `source`, so a bare re-derive is unsafe — the resolver re-matches new records to genesis UUIDs by `(content_sha256, source, legacy_id)` and mints only for genuinely new files (§3B, §4) |

## 13. Backfill feasibility

`BACKFILL_FEASIBILITY = PARTIAL`.

- **Feasible now (the genesis layer):** minting one `source_record_uuid` per
  record of *this frozen snapshot* is unambiguous for **all 42,804** records
  (census §9), collision-free (I1), order-independent (I3), request-independent
  (I4), duplicate/legacy separable (I5, I7), metadata-stable (I6),
  fail-closed (I8). Prototype-proven and independently verified (LC10-E).
- **Still blocked (everything that makes it a lasting identity):**
  1. `BACKFILL_BLOCKER_OWNER_DECISION` — the canonical alias-key decision is
     still open (`canonical_identity_owner_decision_20260717.md` =
     `OWNER_DECISION_REQUIRED`; the reverted PR #157 used
     `(record_index, legacy_question_id)`).
  2. `BACKFILL_BLOCKER_NAMESPACE` — no owner-ratified namespace + canonicalisation
     ADR (§8); the prototype namespace is a placeholder.
  3. `BACKFILL_BLOCKER_REGISTRY` — Model D's registry + resolver + lineage
     ledger (the V1.1 "Immutable Puzzle Identity Foundation" scope) do not
     exist; without them, identity does not survive re-ingestion (I2).
  4. `BACKFILL_BLOCKER_SOURCE_TREE` — the external `SGF題庫` tree is not under
     version control and `build_questions.py` regenerates `source` each
     rebuild (§4); re-ingestion stability is unproven.
  5. `BACKFILL_BLOCKER_ADD_QUESTION` — `app.py add_question()` writes
     `source=''`; the route must set a real `source` (or the resolver must
     handle empty `source`) before it is used for new records.
- None of blockers 1–5 is a *data* problem **in this snapshot**. They are the
  governance decision + the identity-foundation build the org has already
  scoped for V1.1.

`LC010 does NOT require BACKFILL_FEASIBILITY = READY to PASS.` A rigorous
PARTIAL — genesis assignable now, durable identity gated on the V1.1 build — is
the honest conclusion.

## 14. Prototype

`tools/lc010_source_identity_prototype.py` — `PROTOTYPE_ONLY`, `NOT_CANONICAL`,
non-mutating. Computes hypothetical UUIDs in memory / manifest only; never
writes a UUID to the corpus, an SGF, a DB, a runtime record, or Production.
Deterministic (manifest sha stable on rerun). 22 tests in
`tests/test_lc010_source_identity_prototype.py` cover canonicalisation
(separator / whitespace / case / NFC), UUIDv5 determinism + version,
same-source→same-id, different-source→different-id, reorder-invariance,
duplicate-SGF-still-separable, legacy-`id`-collision-still-separable,
missing→fail-closed, non-`.sgf`→not-recoverable, byte-identical-source→collision,
and the full-snapshot census / 404-audit / 13-audit / determinism.

## 15. Prior identity lineage (LC10-A evidence)

| artifact | reachability | conclusion |
|---|---|---|
| `ADR-021-canonical-puzzle-identity.md` @ `4839a065` | ~12 side branches only — **not master, not LC010** | alias key = `(record_index, legacy_question_id)` → one ingestion-minted **UUIDv4** per record; content hash / SGF content / legacy id alone explicitly **not** canonical id |
| `docs/architecture/ADR-021…md` + `puzzle_identity.py` + `migrations/puzzle_identity_alias_v1.py` + `tools/puzzle_identity_backfill.py` | added on master by **PR #157** (`d507df960`, 2026-07-17) → **fully reverted same day by PR #158** (`94e75a5c7`); revert is in LC010 ancestry | working impl: `record_index` = zero-based JSON position, `legacy_question_id` = `id`, "No SGF/content field is read", insert-missing-only into a SQLite `puzzle_identity_alias` table; resolver fail-safe (0 rows→missing, ≥2→ambiguous, never first/last) |
| `canonical_identity_owner_decision_20260717.md` | **current on master + LC010** | **`OWNER_DECISION_REQUIRED`** — A (new globally-unique permanent numeric id) vs B (keep `(record_index, legacy_question_id)`, "owner must define how `record_index` survives re-ingestion"). **No decision recorded.** |
| `sgf_engine_reentry_audit_v1.md` §6 | current | `IDENTITY_DECISION = DEFERRED`; `source` path = "Human-readable path, **not immutable identity**"; interim `AUDIT_LOCATOR_ONLY` = `(snapshot_sha256, record_index, legacy_question_id, content_sha256)` — "must not be used to join long-term history across corpus revisions" |
| `sgf_engine_v1_scope_freeze_20260718.md` | current | V1 needs no identity; "no gate may infer identity from … filename, SGF path, ordering, or a content fingerprint"; **V1.1 "Immutable Puzzle Identity Foundation"** owns `source_record_uuid` + writer locking + compare-and-swap + lifecycle ledger + **frozen genesis bootstrap** + Shadow UUID propagation |
| ingestion script / SGF→record mapping manifest | — | **NONE in this repo.** Historical builder `build_questions.py` lives outside the repo; "`content` and `source` are refreshed from the SGF tree", "existing IDs … preserved" |
| per-record stable id beyond `id` / `source` | — | **NONE.** 0 records carry `uuid` / `source_record_uuid` / `record_index` / `canonical_puzzle_id` / any `*_number` |
| proof of past re-ingestion | `sgf_answer_current_canonical_contract_v2/*.json` | `record_index` shifted **+201** for records with identical content between historical and current corpus |

The recommended Model D is a direct fit for the V1.1 scope the org has already
defined; LC010 supplies the feasibility evidence that gates its owner decision.

## 16. What was proven / recommended / still blocked / next

- **WHAT_WAS_PROVEN:** the source architecture is one SGF file per record;
  `source` is the only field unique across all 42,804 records; a deterministic
  UUIDv5 on the canonicalised *frozen-snapshot* `source` assigns 42,804
  collision-free genesis identities, separates all 404 content-duplicate groups
  and all 13 legacy-`id` collisions, order-independent and metadata-independent,
  with no request-time generation. Independently reproduced (LC10-E). Also
  proven: `source` is a regenerated projection and `record_index` has already
  moved — so a pure live-field key is *not* a durable identity.
- **WHAT_IDENTITY_MODEL_IS_RECOMMENDED:** **Model D** — a persistent identity
  registry bootstrapped from a frozen genesis snapshot; genesis UUID =
  `UUIDv5(owner-namespace, genesis_sha256 + ":sgf-source-file:v1:" +
  canonical(source))`; a resolver (`content_sha256` + `source` + legacy id) and
  a lineage ledger (rename / move / split / merge) carry identity across
  re-ingestions. Registry is the sole post-genesis authority.
- **WHAT_IS_STILL_BLOCKED:** the owner alias-key decision
  (`OWNER_DECISION_REQUIRED`, unmade); an owner-ratified namespace +
  canonicalisation ADR (§8); the Model-D registry + resolver + lineage ledger
  (unbuilt — the V1.1 scope); immutable versioning for the external `SGF題庫`
  tree; and `app.py add_question()` writing `source=''`.
- **WHAT_NEXT_TASK_IS_JUSTIFIED:** an owner decision + design task that
  (a) selects the canonical alias key and supersedes ADR-021 explicitly,
  (b) ratifies the §8 namespace + canonicalisation rules as an ADR,
  (c) authorises building the V1.1 Model-D registry + resolver + lineage
  ledger against this frozen genesis snapshot, and (d) fixes `add_question()`.
  After that, an offline idempotent genesis backfill is mechanical. No corpus
  mutation before then.

## 17. Swarm

- **LC10-A** source architecture / ingestion lineage trace — subagent — **done** (§15)
- **LC10-B** stable-key candidate analysis — Lead (§2)
- **LC10-C** identity model prototype + determinism tests — Lead (§14)
- **LC10-D** 42,804 feasibility census — Lead (§9–§11)
- **LC10-E** independent verification from scratch — subagent — **PASS**: independently reproduced the 6-class census (42,804 IDENTITY_PROVABLE, sum checks), 42,804 distinct canonical keys → 42,804 distinct UUIDs (bijective, 0 collisions), 404/404 duplicate groups identity-provable, all 13 legacy-`id` collisions separable, deterministic across 3 runs, all 5 invariant spot-checks; independently confirmed `source` is the only unique pre-existing field. Caveat recorded: the 100% figure is a property of *this* snapshot + the prototype namespace; a dirtier future corpus fail-closes into `SOURCE_NOT_RECOVERABLE` / `IDENTITY_AMBIGUOUS`.
