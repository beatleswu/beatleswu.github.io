# LC012-R2 — P2 Genesis-Tree Pin, Freeze & Immutable Receipt

Status: **CLOSED — P2 genesis provenance freeze complete. Immutable genesis
receipt issued. `GENESIS_BOOTSTRAP` remains gated (no UUID written).**

Mode: READ / ANALYZE / HASH / MANIFEST / TEST / COMMIT / PUSH.
`C_GO_WEBSITE_MUTATED = NO` · `SOURCE_RECORD_UUID_BACKFILL = NO` ·
`IDENTITY_REGISTRY_POPULATION = NO` · `CORPUS_MUTATION = NO` ·
`SGF_MUTATION = NO` · `SCHEMA_CHANGED = NO` · `DEPLOY = NO`.

This report is **additive**. The original
[`lc012_sgf_source_tree_genesis_freeze_report.md`](lc012_sgf_source_tree_genesis_freeze_report.md)
(the `D:` STOP) and
[`lc012_r1_historical_c_drive_sgf_genesis_provenance_recovery.md`](lc012_r1_historical_c_drive_sgf_genesis_provenance_recovery.md)
(the `C:\go-website` forensic trace) remain valid historical evidence and are
**not** rewritten.

---

## 1. Owner ratification

The owner approved **`OWNER_GENESIS_TREE_PIN = P2`** and supplied the
authoritative pin:

| field | owner-ratified value |
|---|---|
| historical tree commit | `b162f9e72b93b73c08c1b044f365cb9287efae70` (`C:\go-website`, "新手村 16 章教學順序重排", 2026-06-11 00:23:33 +0800) |
| tree scope | `SGF題庫` |
| expected file count | `42804` |
| historical tree manifest sha256 | `12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53` |

All three reproduced exactly from a read-only `git archive` materialisation
(`tools/lc012_p2_genesis_freeze.py`): file count **42,804**, canonical-path
collisions **0**, `tree_manifest_sha256` **`12fcab4a…`** — byte-for-byte the
owner value. `HISTORICAL_TREE_COMMIT_EXACT = YES`, `TREE_MANIFEST_SHA256_EXACT = YES`.

## 2. Why P2 over P1

Both P1 (`de7cd979d8:SGF題庫`, 42,802 files) and P2 (`b162f9e72:SGF題庫`,
42,804 files) are Rank-B contemporaneous trees (LC012-R1 §9). P2 was chosen
because:

- **P2 has the exact file count (42,804)** matching the frozen record count; P1
  is 2 short and needs an explicit cross-commit graft of ids 31198 / 31200.
- **P2 is the exact `content` parent.** `b162f9e72`'s `questions.json`
  (blob `09ea97d28125`) has `content` **byte-identical to the frozen corpus for
  100 % of records** (42,793 / 42,793 distinct ids); 41,875 / 42,804 records
  match on every field. P1's stored corpus still diverges on 2,640 records.
- **The P1↔P2 delta is fully characterised** and small: 918 folder-renames from
  the 新手村 chapter-number reorg (§4), of which 916 pre-images are literally in
  `de7cd979d8`'s tree and 2 (the `征子 ｜ Ladder` pair) first appear in
  `b162f9e72`. Pinning P2 and shipping the 918-entry rename map captures the
  same provenance as P1 with none of P1's structural gaps.

The **918-entry `de7 → b162` rename map**
([`lc012_p2_historical_rename_map.json`](lc012_p2_historical_rename_map.json),
sha `473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d`) is the
bridge: every entry is `RENAME_OR_MOVE`, `identity_preserved = true`, matched on
`legacy_question_id` **and** byte-identical `content`. 0 collisions, 0
ambiguities, and the 918 post-images are an exact bijection with `b162f9e72`'s
918 tree paths that are not frozen `source` values.

## 3. Why P2 is stronger than Option 3 (source-string-only, no tree anchor)

Option 3 (LC012 §9.3) would have ratified the corpus `source` strings as the
genesis seed **with no external tree hash** — meaning re-ingestion drift would
have had no anchor to detect against. P2 gives the identity foundation a real
external anchor:

- `historical_tree_manifest_sha256` (`12fcab4a…`) is now one of the immutable
  inputs of the `GENESIS_BOOTSTRAP_ONCE_ONLY` gate (§6). A future bootstrap that
  does not present the same tree hash **fails closed**.
- The 918-entry rename map is itself hash-locked into the gate, so the
  de7→b162 reconciliation cannot be silently altered.
- The genesis record manifest sha (`ee7b1bc4…`) is locked in too.

Option 3 remains the fallback **only** if the owner ever repudiates the C:
provenance; it is strictly weaker and is not used.

## 4. The 918 renames and why identity does not change

`b162f9e72` ("新手村 16 章教學順序重排") prefixed Starter-Village chapter folders
with teaching-order numbers:

```
不吃死棋 ｜ Don't Capture Dead Stones/…   ->   12不吃死棋 ｜ Don't Capture Dead Stones/…
征子 ｜ Ladder/56.sgf                     ->   07征子 ｜ Ladder/56.sgf
```

For every one of the 918: **same `legacy_question_id`, byte-identical
`content`**. `build_questions.py`@`de7cd979d8` keeps a record's `id` stable
across a path change (matched by `source`, else by `sha1(content)`), so the
reorg moved files, not identities.

Crucially, **the genesis `source_record_uuid` is minted from the frozen
corpus's `canonical_source`, not from the historical tree path.** The frozen
corpus recorded the *pre-reorg* paths for these 918, so their genesis UUIDs are
computed from the pre-reorg `canonical_source` and are unaffected by the reorg.
The rename map's role is purely to let the join resolve a frozen `source`
(`…/不吃死棋 ｜ …/1.sgf`) to the physical historical file
(`…/12不吃死棋 ｜ …/1.sgf`) as **provenance evidence** — `provenance_relation =
HISTORICAL_RENAME_MATCH`. It is never a UUID input.

`HISTORICAL_GIT_PATH_AS_DIRECT_UUID_AUTHORITY = NO`.

## 5. Why the provenance is Rank B, not Rank A

The receipt states this explicitly (`provenance_rank = "B"`,
`exact_build_binding = false`, `deterministic_byte_rebuild_from_one_tree =
false`, `frozen_artifact_reconciled_on_d_drive = true`):

- **The frozen `content` is not regenerable from any SGF tree.** Running the real
  `build_questions.py` (`read_sgf` = encoding-fallback decode + `.strip()`)
  against `de7cd979d8`'s tree reproduces the frozen `content` for only
  332 / 42,802 records — the `content` lineage is corpus-file → corpus-file, not
  tree → corpus at the snapshot point.
- **No single commit is 42,804-complete AND path-exact AND content-exact.** The
  frozen `source` layout = `de7cd979d8` paths + the 918 pre-reorg names + 2
  Ladder files; the frozen `content` = `b162f9e72`'s corpus. Those never
  coexisted in one commit — the frozen artifact was **assembled / reconciled on
  `D:`** (918 paths reverted to pre-reorg, ~929 minor field edits, 11
  duplicate-`id` groups, + `D:`-side KataGo enrichment growing it 73.7 → 75.7 MB).
- **No provenance receipt binds a C: commit to `88da3e43…`** — no build log,
  manifest, checksum, or commit message anywhere in `C:\go-website` references
  the frozen hash.

P2 is the strongest *available* pin: the origin repo, the exact content parent,
a path-authoritative sibling, the real builder, and a ~2-hour window — but it is
**contemporaneous provenance, not an exact deterministic build**. The receipt is
honest about this so no future step can quietly treat P2 as Rank A.

## 6. Why frozen `canonical_source` remains the UUID authority

Unchanged from LC011 / LC012:

- `source_record_uuid_proposed = uuidv5(namespace, "gk1" ⟨U+001F⟩
  "sgf-source-file" ⟨U+001F⟩ "v1" ⟨U+001F⟩ canonical_source)` where
  `canonical_source = canon-source-v1(frozen record.source)`.
- `namespace = c70b30f4-b745-5585-b5c3-64021901ad76` (owner-ratified,
  `assert_namespace`-enforced).
- The historical SGF tree is **provenance evidence**, not an identity seed.
  `CONTENT_HASH_AS_IDENTITY = NO`. `UUID_ALGORITHM_CHANGED = NO`.
  `POST_GENESIS_UUID_RECOMPUTATION = FORBIDDEN`.

The full 42,804 proposed-UUID set reproduces the LC012 proof exactly:
count 42,804, distinct 42,804, collisions 0,
`proposed_uuid_list_sha256 = cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2`
(byte-identical to LC012). The 404 content-duplicate groups (404/404) and 13
legacy-collision records (13/13) remain separable — no deduplication, no
content-based collapse.

## 7. The immutable genesis receipt

[`lc012_p2_genesis_receipt.json`](lc012_p2_genesis_receipt.json) — sha256
`834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c` — locks:

| field | value |
|---|---|
| `frozen_corpus_sha256` / `frozen_record_count` | `88da3e43…` / 42,804 |
| `identity_namespace` | `c70b30f4-b745-5585-b5c3-64021901ad76` |
| `canonicalization_version` / `genesis_key_version` | `canon-source-v1` / `genesis-key-v1` |
| `historical_tree_commit` / `_scope` / `_file_count` | `b162f9e72…` / `SGF題庫` / 42,804 |
| `historical_tree_manifest_sha256` | `12fcab4a…` (owner-ratified, exact) |
| `historical_rename_map_sha256` / `_count` | `473a80a3…` / 918 |
| `genesis_record_manifest_sha256` / `_row_count` | `ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828` / 42,804 |
| `proposed_uuid_list_sha256` | `cb47e9d6…` (== LC012) |
| `provenance_rank` / `exact_build_binding` | `B` / `false` |
| `genesis_bootstrap_once_only_gate.genesis_bootstrap_safe_to_run` | `true` **iff** every immutable input above matches |

The genesis record manifest is a deterministic **42,804-row** artifact
(`source_record_uuid_proposed`, `canonical_source`, `historical_source`,
`provenance_relation`, `legacy_question_id`, `record_index`,
`content_evidence_sha256`), sorted by `canonical_source`, sha256
`ee7b1bc4…`. It is ≈ 20 MB; per the LC012 §33 large-artifact policy it is
**not committed verbatim** — the committed
[`lc012_p2_genesis_record_manifest.json`](lc012_p2_genesis_record_manifest.json)
is the proof (header + full sha + row count + first/last 25 + exact regeneration
command). `FULL_GENESIS_MANIFEST_COMMITTED = NO`.

## 8. Once-only bootstrap gate

`validate_p2_once_only_gate()` requires all nine immutable inputs:
`frozen_corpus_sha256`, `record_count`, `namespace_uuid`,
`canonicalisation_rules_version`, `genesis_key_spec_version`,
`historical_tree_commit`, `historical_tree_manifest_sha256`,
`historical_rename_map_sha256`, `genesis_record_manifest_sha256`.
`genesis_bootstrap_safe_to_run` becomes `true` **only** when the static values
equal the frozen constants **and** the rename-map / manifest shas are internally
consistent **and** any prior bootstrap tuple matches exactly.
`GENESIS_BOOTSTRAP_ONCE_ONLY_GATE_VALIDATED = YES`.

## 9. Drift fail-closed (§19)

`tests/test_lc012_p2_genesis_receipt.py` exercises the real tool code:

| drift | outcome |
|---|---|
| frozen corpus hash mismatch | `run()` → `SystemExit` |
| record count mismatch | `run()` → `SystemExit` |
| historical tree commit / manifest mismatch (de7 tree in b162 slot) | `run()` → `SystemExit P2_TREE_FACTS_DO_NOT_REPRODUCE` |
| canonical-path collision (NFC vs NFD) | `tree_inventory` flags it → `run()` → `SystemExit` |
| namespace change | `assert_namespace` raises |
| canon-source / genesis-key version change | gate `static_inputs_valid = false` → not safe |
| rename-map mutation | gate `dynamic_inputs_consistent = false` → not safe |
| rename-map ambiguity (synthetic unmatched record) | `build_rename_map` `ambiguity_count ≥ 1`, record surfaced not dropped |
| genesis-record-manifest mutation | gate `dynamic_inputs_consistent = false` → not safe |
| proposed-UUID list hash mutation | `run()` → `SystemExit PROPOSED_UUID_LIST_SHA256_MISMATCH` |

`GENESIS_DRIFT_FAIL_CLOSED = PASS`.

## 10. Boundaries honoured

- **`C:\go-website`** — read-only `git archive` / `cat-file` / `ls-tree` / `show`
  only. HEAD (`415a321db…`), reflog `HEAD@{0}`, and `git status --porcelain`
  line count all byte-identical before and after. The `README-FROZEN.txt` deploy
  guard is respected (no deploy / docker / ssh / checkout / commit / push inside
  C:). `C_GO_WEBSITE_MUTATED = NO`.
- **Protected files** (`secret_key.txt`, `.env*`, `*.pem/*.key/*.p12/*.pfx`,
  credential / Production DB artifacts) — not read, hashed, copied, or staged.
- **No** `source_record_uuid` write, identity-registry population,
  identity-lineage population, `questions.json` mutation, SGF mutation, DB
  mutation, schema migration, Production query/mutation, or deployment.

## 11. What remains before LC013

1. Owner (or LC013) runs the **actual genesis bootstrap** — mint the 42,804
   `source_record_uuid` values into the persistent LC011 identity registry —
   an explicit, gated, offline write operation. The receipt's once-only tuple is
   the precondition; nothing in LC012/-R1/-R2 performs it.
2. The dual-ID migration window, resolver wiring, and `add_question()`
   `source=''` hole (LC011 decision packet) are the remaining LC011 items.
3. `_explicit_terminal_is_correct` marker policy for the 41,831 MANUAL records
   (`OWNER_MARKER_DECISION_REQUIRED`) is independent of identity and still open.

## 12. Final report

```
TASK                              = LC012_R2_P2_GENESIS_TREE_PIN_FREEZE_AND_IMMUTABLE_RECEIPT_001
OWNER_GENESIS_TREE_PIN            = P2

LC012_R1_LOCAL_HEAD              = 3720300acb403444f7ad7dcf72ce5360e07eab4b  (pushed this task — REMOTE_HEAD_EXACT now YES)
CURRENT_BRANCH                   = claude/lc012-sgf-source-tree-genesis-freeze
LOCAL_HEAD                       = <this commit>
TRACKING_HEAD                    = origin/claude/lc012-sgf-source-tree-genesis-freeze
REMOTE_HEAD                      = <this commit if push accepted, else 3720300ac>
REMOTE_HEAD_EXACT               = <YES if push accepted>

FROZEN_CORPUS_SHA256            = 88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff
FROZEN_RECORD_COUNT            = 42804

HISTORICAL_TREE_COMMIT          = b162f9e72b93b73c08c1b044f365cb9287efae70
HISTORICAL_TREE_SCOPE           = SGF題庫
SGF_TREE_FILE_COUNT             = 42804
TREE_MANIFEST_SHA256            = 12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53
TREE_MANIFEST_SHA256_EXACT      = YES

RENAME_MAP_ENTRY_COUNT          = 918
RENAME_MAP_SHA256               = 473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d
RENAME_MAP_COLLISIONS           = 0
RENAME_MAP_AMBIGUITIES          = 0

GENESIS_RECORDS_JOINED          = 42804
GENESIS_RECORDS_MISSING         = 0
GENESIS_RECORDS_AMBIGUOUS       = 0

DIRECT_PATH_MATCH_COUNT         = 41886
HISTORICAL_RENAME_MATCH_COUNT   = 918

PROPOSED_UUID_COUNT             = 42804
PROPOSED_UUID_DISTINCT          = 42804
UUID_COLLISIONS                 = 0
PROPOSED_UUID_LIST_SHA256       = cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2
PROPOSED_UUID_LIST_SHA256_EXACT = YES

DUPLICATE_CONTENT_GROUPS_SEPARABLE = 404/404
LEGACY_COLLISION_RECORDS_SEPARABLE = 13/13

PROVENANCE_RANK                 = B
EXACT_BUILD_BINDING             = NO

GENESIS_RECEIPT_PATH            = docs/planning/lc012_p2_genesis_receipt.json
GENESIS_RECEIPT_SHA256          = 834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c

GENESIS_RECORD_MANIFEST_PATH        = docs/planning/lc012_p2_genesis_record_manifest.json  (proof; full artifact regenerable, ~20 MB, FULL_GENESIS_MANIFEST_COMMITTED=NO)
GENESIS_RECORD_MANIFEST_SHA256      = ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828  (full 42,804-row artifact)

GENESIS_BOOTSTRAP_ONCE_ONLY_GATE_VALIDATED = YES
GENESIS_BOOTSTRAP_SAFE_TO_RUN              = true only when every immutable input matches (currently true against the frozen constants)

GENESIS_DRIFT_FAIL_CLOSED       = PASS

UUID_BACKFILL                   = NO
IDENTITY_REGISTRY_POPULATION    = NO
C_GO_WEBSITE_MUTATED           = NO
CORPUS_MUTATION                 = NO
SGF_MUTATION                    = NO
SCHEMA_CHANGED                  = NO
MIGRATION_CHANGED               = NO
PRODUCTION_QUERY                = NO
PRODUCTION_MUTATION             = NO
DEPLOY                          = NO

TESTS                           = tests/test_lc012_p2_genesis_receipt.py + regression LC008–012
TASK_INTRODUCED_FAILURES        = 0

WHAT_P2_PIN_PROVES              = The frozen 42,804-record corpus's genesis SGF tree is b162f9e72:SGF題庫 in C:\go-website — 42,804 files, tree_manifest 12fcab4a… (owner-ratified, reproduced), and the exact content parent of the frozen corpus (100% record content byte-match).
WHAT_THE_918_RENAME_MAP_PROVES = The only structural gap between the frozen source layout and the P2 tree is the 新手村 chapter-number folder reorg: 918 pure RENAME_OR_MOVE, identity preserved (same legacy id + byte-identical content), 0 collisions, 0 ambiguities, exact bijection with the P2 tree's 918 non-frozen paths.
WHY_UUID_IDENTITY_IS_STABLE    = source_record_uuid is uuidv5(fixed namespace, canon-source-v1(frozen record.source)) — computed from the frozen corpus, never from the historical tree path or content hash. The reorg renamed files, not identities; the proposed-UUID list sha (cb47e9d6…) is byte-identical to LC012.
WHAT_GENESIS_RECEIPT_LOCKS     = frozen corpus sha + count, namespace, canon-source & genesis-key versions, P2 tree commit + manifest sha + file count, 918 rename-map sha, 42,804 genesis-record-manifest sha, proposed-UUID list sha, provenance rank B / exact_build_binding NO — all as immutable inputs of a once-only bootstrap gate that fails closed on any drift.
WHAT_REMAINS_BEFORE_LC013      = the actual gated offline genesis bootstrap (mint the 42,804 UUIDs into the LC011 registry) — not performed here; plus the LC011 dual-ID window / resolver wiring / add_question source='' hole, and the independent MANUAL-record marker policy.

RESULT                         = P2_GENESIS_PROVENANCE_FREEZE_COMPLETE — IMMUTABLE_RECEIPT_ISSUED, BOOTSTRAP_GATED_NOT_RUN
READY_FOR_COORDINATOR_LC012_R2_REVIEW = YES
```
