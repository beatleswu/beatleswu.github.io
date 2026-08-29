# SGF_SOURCE_TREE_GENESIS_MANIFEST — contract

Status: **SPEC ONLY.** The manifest itself is **NOT produced** by LC012 — no
authoritative SGF source tree for the `88da3e43…` frozen snapshot was located
(see `lc012_sgf_source_tree_genesis_freeze_report.md`). This document is the
drop-in contract: when the owner supplies an authoritative tree, running
`tools/lc012_sgf_source_tree_freeze.py --tree-root <tree>` produces a manifest
that must satisfy every clause here.

It binds the LC011 identity foundation (`lc011_immutable_puzzle_identity_foundation_adr.md`,
contract sha `61c2f13afb7dbd6d04c2f2b21021acb16292abb1ad6a35762529ade740ed231e`).

---

## 1. Purpose

Pin the external SGF題庫 tree that produced the frozen corpus so a future
genesis backfill is (a) reproducible and (b) drift-detectable. It is the
missing `sgf_tree_manifest_sha256` in the LC011 `GENESIS_BOOTSTRAP_ONCE_ONLY`
gate.

## 2. Header (required)

| field | value / rule |
|---|---|
| `manifest_version` | `sgf-source-tree-genesis-manifest-v1` |
| `canonicalisation_rules_version` | `canon-source-v1` (exact) |
| `genesis_key_spec_version` | `genesis-key-v1` (exact) |
| `namespace_uuid` | `c70b30f4-b745-5585-b5c3-64021901ad76` (exact — `assert_namespace()`-enforced) |
| `corpus_id` | `godokoro-canonical` |
| `snapshot_sha256` | `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` (the corpus this tree is frozen against) |
| `corpus_record_count` | `42804` |
| `source_tree_root_descriptor` | a **descriptor**, not a machine path — e.g. `"SGF題庫 @ <owner-assigned tree revision id>"`. **No absolute path, no credentials, no secret, no protected-file info.** |
| `file_count` | the count of `.sgf` files in the tree; **must == 42804** for a full genesis (else `COUNT_MISMATCH`, fail closed) |
| `tree_manifest_sha256` | §5 |
| `generated_at` | ISO-8601 string supplied by the caller (never fabricated by the tool) |
| `generator_version` | `lc012-sgf-source-tree-freeze-v1` |

## 3. Per-file entry (required)

For every `.sgf` file in the authoritative tree:

| field | authority | rule |
|---|---|---|
| `raw_relative_path` | AUDIT | the tree-root-relative path, verbatim (original separators) |
| `canonical_relative_path` | ALIAS | `canon-source-v1` of `raw_relative_path`; if canonicalisation fails → the file is `SOURCE_NOT_RECOVERABLE` and the manifest is **rejected** (fail closed — the curator fixes the tree) |
| `content_sha256` | AUDIT / evidence | `sha256` of the raw SGF file bytes |
| `collection` | DERIVED | first segment of `canonical_relative_path` |
| `byte_size` | AUDIT (optional) | raw byte length |

**Never stored:** `mtime`, `inode`, absolute path, machine name, credentials,
secret paths, tokens, private keys, or any protected-file information.
Unstable filesystem metadata is **not** identity authority.

## 4. Uniqueness (fail closed)

`CANONICAL_PATH_COLLISIONS = 0` — if two physical files canonicalise to the
same `canonical_relative_path`, **STOP**. Do **not** invent a suffix or
auto-rename. `canon-source-v1` preserves case and normalises only `\`→`/`,
outer whitespace, and `//`, so a collision means a genuine tree defect.

## 5. Deterministic tree-manifest hash

1. take every entry's `canonical_relative_path\t<byte_size>\t<content_sha256>`
2. **sort** those lines lexicographically by the full line (filesystem
   enumeration order MUST NOT affect the result)
3. join with `\n`, UTF-8 encode
4. `tree_manifest_sha256 = sha256(that body)`

Excludes every generated / unstable field (`generated_at`, absolute paths,
mtime). `TREE_HASH_DETERMINISTIC = YES`; two independent generations MUST
produce `TREE_MANIFEST_SHA_MATCH = YES`.

## 6. Corpus ↔ tree join (fail closed)

Join every one of the 42,804 corpus records to the tree by
`canon-source-v1(record.source) == entry.canonical_relative_path`.

| gate | required |
|---|---|
| `MATCHED_TO_SOURCE_TREE` | 42,804 |
| `MISSING_SOURCE` | 0 |
| `AMBIGUOUS_SOURCE` | 0 |
| `CANONICAL_PATH_COLLISIONS` | 0 |
| `SOURCE_NOT_RECOVERABLE` | 0 |

`record_index` stays **AUDIT ONLY**; `legacy_question_id` stays **ALIAS ONLY** —
neither is a join key or an identity.

## 7. Content comparison (§18)

For each matched record classify `sha256(file bytes)` vs
`sha256(record.content)`:

| class | meaning |
|---|---|
| `EXACT_RAW_EQUIVALENT` | byte-identical |
| `EXPECTED_BUILDER_TRANSFORM` | differs, **but** the exact `build_questions.py` transform (parse → normalise → re-serialise, KataGo answer application, manual-restore) reproduces `record.content` from the file bytes — the transform + its version MUST be documented and re-runnable |
| `UNEXPLAINED_CONTENT_DRIFT` | differs and no certified transform explains it |
| `SOURCE_NOT_RECOVERABLE` | canonicalisation failed |

`UNEXPLAINED_CONTENT_DRIFT_COUNT = 0` is required for a full PASS. A non-zero
count → **STOP** (do not change SGFs, do not rewrite `questions.json`).

## 8. Proposed genesis record manifest (§21) — only after §4–§7 all pass

Header: `snapshot_sha256`, `record_count`, `genesis_key_spec_version`,
`namespace_uuid`, `canonicalisation_rules_version`, **`sgf_tree_manifest_sha256`**.
Per record: `record_index` (AUDIT), `legacy_question_id` (ALIAS), `raw_source`,
`canonical_source`, `content_sha256`, `proposed_source_record_uuid`
(= `uuidv5(namespace, "gk1"⟨U+001F⟩"sgf-source-file"⟨U+001F⟩"v1"⟨U+001F⟩canonical_source)`).

Requirements: `PROPOSED_UUID_COUNT = 42804`, `DISTINCT_UUID_COUNT = 42804`,
`UUID_COLLISIONS = 0`, `SOURCE_NOT_RECOVERABLE = 0`, cross-process
deterministic, `DUPLICATE_CONTENT_GROUPS_SEPARABLE = 404/404`,
`LEGACY_COLLISION_RECORDS_SEPARABLE = 13/13`.

**Proposal / evidence only** — never written into `questions.json`, any SGF, a
DB row, a runtime read model, or Production. `SOURCE_RECORD_UUID_BACKFILL = NO`.

## 9. `GENESIS_BOOTSTRAP_ONCE_ONLY` (§27)

A future genesis bootstrap requires an exact match on the tuple
{`corpus_id`, `snapshot_sha256`, `record_count`, `sgf_tree_manifest_sha256`,
`namespace_uuid`, `genesis_key_spec_version`, `canonicalisation_rules_version`}.
A second bootstrap against a **different** tuple fails closed unless an explicit
owner-approved identity-architecture migration says otherwise.

## 10. Large-artifact policy (§33)

A 42,804-row manifest is not committed verbatim. Commit: the deterministic
generator, the manifest `sha256`, `record_count`, representative samples
(first/last 25), the exact generated artifact path, and reproduction
instructions. `FULL_TREE_MANIFEST_COMMITTED = NO` / `FULL_GENESIS_MANIFEST_COMMITTED = NO`
(with the generator + sha as the committed proof). No Git LFS without separate
authorization.
