# LC012 — SGF Source-Tree Genesis Freeze & Manifest Closure

Status: **STOP_AND_REPORT — `SOURCE_TREE_AUTHORITY_UNRESOLVED`.**
Mode: READ / ANALYZE / MANIFEST / TEST ONLY. No corpus / SGF / schema /
`app.py` / LC009 change. `SGF_SOURCE_FILES_MUTATED = 0`.

Branch base: `2406e0bd6118b3495b3aa1f57a22f7db43eb9f21` (LC011 head — candidate
lineage, not master-merged).
`origin/master` (fresh-fetch, report only): `047e036177a5abf2d4b8dd15b7787b274bc41945`.
Frozen corpus: `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`
(42,804 records) — hash-verified.

Artifacts:
- this report
- `docs/planning/lc012_sgf_source_tree_genesis_manifest_contract.md` — the drop-in manifest spec (for when an authoritative tree is supplied)
- `tools/lc012_sgf_source_tree_freeze.py` — READ-ONLY tool (tree inventory + deterministic tree-manifest hash + corpus↔tree join + drift gate + corpus-side proposed-UUID evidence + once-only gate)
- `docs/planning/lc012_sgf_source_tree_freeze_report.json` — machine-readable run (sha256 `70ce35f08446fcf109d5883b74c6d6062f5a557fc2656583b1cc01768ac48f0c`)
- `tests/test_lc012_sgf_source_tree_genesis_freeze.py`

---

## 0. Executive summary

LC012 was to produce the `SGF_SOURCE_TREE_GENESIS_MANIFEST` against the **actual
frozen external SGF source tree** for the 42,804-record snapshot. **That tree
could not be unambiguously identified on this machine** — a full `D:\` sweep
(1,061 top-level dirs, nine SGF-scale trees, independently reproduced by
LC12-E) finds no tree that is both 42,804-complete and byte-authoritative, and
not even the union of all nine reproduces the `content` of ≈ 5,150 records.
The canonical repo's own earlier provenance work already documents it as
unresolved. Per §9 / §14 / §17 / §39 this is a **STOP_AND_REPORT**, not
something to compensate for by loosening `canon-source-v1`, using a content
hash or legacy id as identity, inventing aliases, or skipping records.

The **corpus side** of the work — which needs only the frozen `questions.json`
— was completed and is clean: all 42,804 `source` values canonicalise to
42,804 distinct `canon-source-v1` keys with **0** fail-closed and **0**
canonical-path collisions; the ratified LC011 genesis UUIDv5 yields **42,804
distinct** proposed identities with **0 collisions**, cross-process
deterministic; the **404/404** content-duplicate groups and **13/13**
legacy-`id` collision records remain separable. This is **proposal / evidence
only** — no `source_record_uuid` was written anywhere, and **no genesis record
manifest was generated** (§21: only if all tree-reconciliation gates pass).

## 1. What "the authoritative SGF source tree" must be (§9)

The tree whose files, at the moment the `88da3e43…` snapshot was built, were
the input to `build_questions.py` — i.e. the tree that produced exactly those
42,804 records' `source` paths and (via the documented builder transform +
KataGo answer application) their `content`.

## 2. Candidate trees found on disk — and why none qualifies

A full `D:\` sweep (1,061 top-level dirs; LC12-E) enumerates every SGF-scale
tree on the machine. **None passes the LC012 manifest-contract gates**
(`file_count == 42,804`, `MATCHED == 42,804`, `MISSING == 0`,
`UNEXPLAINED_CONTENT_DRIFT == 0`, every path-hit byte-exact or FAIL CLOSED):

| candidate | `.sgf` files | join by exact relative path (of 42,804) | of the path-hits: `sha256(file) == sha256(record.content)` | best match under builder normalization | qualifies? |
|---|---:|---:|---:|---:|---|
| `D:\go-website_lb_rewards_pr1\SGF題庫` | 42,802 | **42,802** hit / 2 MISS | **0** | ~40,182 | **NO** — see §2.1 |
| `D:\go website\SGF題庫` (Production) | 41,591 | 33,925 hit / 8,879 MISS | 9 | ~33,893 | **NO** — later *pruned* Production state; count 41,591 ≠ 42,804 |
| `D:\desktop\go website\SGF題庫` | 51,080 | 27,922 hit / 14,882 MISS | 0 | ~24,445 | **NO** — different era; its own 51,080-record `questions.json` |
| `D:\desktop\SGF題庫` | 44,653 | ~500 hit | 0 | ~370 | **NO** — heavy naming drift |
| `D:\go website\SGF題庫_backup_before_katago_sync_20260530_001533` | 18,762 | 18,762 hit / 24,042 MISS | 0 | — | **NO** — partial pre-KataGo snapshot |
| `D:\go website\SGF題庫_backup_…_00{1858,1948}` | 470 / 470 | 470 hit each | 0 | — | **NO** — tiny partial backups |
| `D:\SGF題庫` | 16,676 | ~0 | 0 | 301 (norm-sha, any path) | **NO** — pre-curation upstream book library |
| `D:\圍棋` | 24,892 | ~0 | 0 | 301 (norm-sha, any path) | **NO** — upstream book library |
| `D:\go-website\SGF題庫` (inside the canonical repo, untracked) | 0 matching | ~0 | 0 | 0 | **NO** — empty for corpus paths |

Two facts kill tree authority across **every** candidate:

- **No candidate is byte-authoritative.** The single best byte-exact count on
  any tree is **9** (`sha256(file) == sha256(record.content)`), all in one
  sub-collection (`初階元素魔法導論 ｜ Go - Basic Element Magic\初级篇（中）`, and
  they cover the legacy-`id` collision values). `questions.json` `content` is a
  heavily transformed representation (builder refresh + KataGo answers + manual
  restores), and **there is no `build_questions.py` in the canonical repo** to
  certify a transform (§18) — so every non-exact path-hit is
  `UNEXPLAINED_CONTENT_DRIFT` by rule.
- **No count is 42,804.** The closest (`lb_rewards_pr1`, 42,802) is still 2
  short, with 2 records genuinely file-absent.

### 2.1 Closest candidate — `D:\go-website_lb_rewards_pr1\SGF題庫`

An **ungoverned local git worktree** (branch
`codex/community-lb-rewards-phase1-pr1-helper-tests`, HEAD `f26a5f716`), not in
the canonical repo. Its sibling `questions.json` has 42,804 records but sha
`6779258b95c9d1e203fe4428f93dddd0d0fccb68488c4b70a485b20fa1a7c432` — **a
different build**, not the frozen `88da3e43…`. Its `build_questions.py`
(13,739 B) differs from every other copy on the machine.

Against the **frozen** corpus:

| comparison | result |
|---|---|
| `source` set | identical (0 / 0 asymmetric) |
| legacy `id` (all 42,804) | identical |
| tree file present for `source` path | 42,802 / 42,804 (2 genuinely absent) |
| `sha256(file) == sha256(frozen content)` | **0** |
| frozen `content` vs file bytes, builder-normalized | 37,535 equal; best deterministic transform → 40,182 / 42,802; **residual ≈ 2,620** |
| sibling `questions.json` `content` vs frozen `content` | 40,164 byte-equal; **2,640 differ, none normalize-equal** — genuine SGF revisions (different move sequences / whole different problems) |

`tools/lc012_sgf_source_tree_freeze.py --tree-root D:\go-website_lb_rewards_pr1\SGF題庫`
→ `sgf_file_count` 42,802, `matched_to_source_tree` 42,802, `missing_source` 2,
`exact_raw_equivalent_count` 0, `unexplained_content_drift_count` 42,802,
`all_reconciliation_gates_pass` = **false** → `STOP_AND_REPORT: JOIN_OR_DRIFT_UNRECONCILED`.

It is a **lineage sibling ~94% coincident** with the genesis input, not the
genesis input. §9 forbids guessing a tree from naming / coincidence alone.

### 2.2 Correction to the earlier draft

The first draft reached the STOP after testing only `D:\go website\SGF題庫`
(Production) and four small / irrelevant trees, and framed the gap as "8,879
records structurally have no file / the whole first collection is absent". That
pattern is real **for the pruned Production tree** but is **not a property of
the search** — `lb_rewards_pr1` path-matches 42,802 / 42,804 with every
collection present. The STOP survives the correction (no tree is
byte-authoritative or 42,804-complete); the framing is now attributed to the
specific tree that exhibits it. This was a **report-narrative** fix — no
machinery changed.

## 3. The canonical repo already recorded this as unresolved

`docs/planning/sgf_answer_repair_batch_001_phase2c_canonical_corpus_provenance.md`:

- "files were found under `D:\go website`, but that directory is **not a Git**
  [repo]"
- `D:\go website\questions.json` — **41,591** records; the canonical snapshot —
  **42,804**
- "`D:\go website` tree were hashed; exact matches: **0**"
- `CURRENT_CORPUS_LOCAL_PATH = NOT_FOUND_EXACT`
- `Q7998_CANONICAL_SGF_SOURCE = UNRESOLVED` … (per-record SGF sources marked
  UNRESOLVED, only `LOCAL_SOURCE_HISTORY_CANDIDATE`s given)
- the historical `D:\go website\build_questions.py` is described as a **local,
  ungoverned** file — its "input root: sibling `SGF題庫`" — never promoted to
  canonical authority

`docs/planning/sgf_answer_current_canonical_contract_v2/source-provenance.json`
pins the corpus to `beatleswu/beatleswu.github.io :: canonical/current/questions.json`
and its sha — it carries **no SGF-tree reference, no tree manifest, no tree
checksum**.

`ACTUAL_SOURCE_TREE_TRACED = NO`.

## 4. Could the 42,804-snapshot tree be reconstructed? (§18)

**NO.** LC12-E tested reconstruction from the **union of all nine SGF trees on
`D:\`** (241,396 files):

- **paths:** the union covers every corpus `source` path — 42,804 / 42,804
  (`lb_rewards_pr1` supplies 42,802; the last 2 come from other trees).
- **bytes:** of those path-hits, `content` is byte-exact for **9** records and
  normalization-equal on the correct path for **37,650**. Ignoring paths
  entirely, a normalized content join reaches **39,141 / 42,804** —
  **3,660 distinct `content` values (≈ 5,150 records) exist as no file in any
  tree on the machine.**
- **builder:** three different untracked `build_questions.py` copies exist
  (345 / 315 lines / 13.7 KB), none tracked in the canonical repo, so no
  transform can be *certified* — every non-exact match is
  `UNEXPLAINED_CONTENT_DRIFT` by rule.
- **delta:** no `+1,213` (Production→snapshot) or `+2` (`lb_rewards_pr1`→snapshot)
  delta artifact exists in the canonical repo. Only **one** exact copy of the
  frozen corpus exists on disk — `D:\go-website\questions.json` itself. No SGF
  tree manifest / checksum / receipt binding any tree to the `88da3e43…`
  snapshot was found anywhere on `D:\` (241 `*manifest*` / `*checksum*` files
  scanned — all deploy / image / art / audio packs).

Reconstruction would mean *inventing* the `content` of thousands of records —
forbidden by §39.

## 5. Corpus-side result (completed — proposal / evidence only)

`tools/lc012_sgf_source_tree_freeze.py --snapshot <frozen questions.json>`
(no `--tree-root`) → `docs/planning/lc012_sgf_source_tree_freeze_report.json`:

| metric | value |
|---|---|
| `SNAPSHOT_HASH_MATCH` | YES |
| `CORPUS_RECORD_COUNT` | 42,804 |
| `NAMESPACE_UUID` | `c70b30f4-b745-5585-b5c3-64021901ad76` |
| `GENESIS_KEY_SPEC_VERSION` | `genesis-key-v1` |
| `CANONICALISATION_RULES_VERSION` | `canon-source-v1` |
| distinct canonical sources | **42,804** |
| `SOURCE_NOT_RECOVERABLE` | **0** |
| `CANONICAL_PATH_COLLISIONS` | **0** |
| `PROPOSED_UUID_COUNT` | **42,804** |
| `DISTINCT_UUID_COUNT` | **42,804** |
| `UUID_COLLISIONS` | **0** |
| `UUID_DETERMINISM_CROSS_PROCESS` | **PASS** — a fresh interpreter recomputes the identical set; `uuid_list_sha256 = cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2` |
| `DUPLICATE_CONTENT_GROUPS_SEPARABLE` | **404 / 404** |
| `LEGACY_COLLISION_RECORDS_SEPARABLE` | **13 / 13** |

This proves the ratified LC011 identity machinery is ready; it does **not**
close the genesis input, which is tree-bound.

## 6. Genesis bootstrap once-only gate (§27) — validated

`validate_once_only_gate()` requires an exact tuple of `corpus_id`,
`snapshot_sha256`, `record_count`, **`sgf_tree_manifest_sha256`**,
`namespace_uuid`, `genesis_key_spec_version`, `canonicalisation_rules_version`.
With no tree, `sgf_tree_manifest_sha256` is absent → `static_inputs_valid =
false` → `safe_to_bootstrap = false`. A prior bootstrap for a *different* tuple
→ `REFUSED`; an identical tuple → idempotent re-entry. `GENESIS_BOOTSTRAP_ONCE_ONLY_GATE_VALIDATED = YES`.

## 7. Drift fail-closed (§28) — A–J validated on fixtures

`tests/test_lc012_sgf_source_tree_genesis_freeze.py` builds temp SGF trees and
confirms each drift is refused / flagged: (A) SGF content changed →
`UNEXPLAINED_CONTENT_DRIFT`; (B) path renamed w/o lineage → `MISSING_SOURCE` +
an orphan tree file; (C) file missing → `MISSING_SOURCE`; (D) extra file →
`sgf_file_count` ≠ 42,804 gate fails; (E) snapshot hash mismatch → `run()`
`SystemExit`; (F) tree hash mismatch → once-only gate `prior_matches = false` →
REFUSED; (G) namespace mismatch → `assert_namespace` raises; (H) canon-rules
version mismatch → gate `static_inputs_valid = false`; (I) genesis-key version
mismatch → same; (J) canonical-path collision → `tree_inventory` reports it and
the reconciliation gate fails, no auto-rename. `GENESIS_DRIFT_FAIL_CLOSED = PASS`.

Case J is not hypothetical: LC12-E confirmed a canon-source-v1 collision is
**genuinely constructible** — NFC vs NFD of the same accented filename are two
distinct on-disk byte sequences that fold to one canonical key (also `\` vs
`/`). `tree_inventory` catches both files and fails the gate closed. **The
frozen corpus itself has 0 such collisions** (42,804 sources → 42,804 distinct
keys) — J is a latent tree-side risk the gate defends against, not an active
corpus defect.

## 8. Source-tree preservation evidence (§29)

Only `os.walk` + `open(…, "rb").read()` + `os.path.isfile/isdir/relpath` were
used against the candidate trees — zero writes, renames, or mtime-changing
operations. Read-only content-manifest sha256 (sorted `relpath\tsize\tsha256`):

| tree | files | pre-run sha | post-run sha |
|---|---:|---|---|
| `D:\go website\SGF題庫` | 41,591 | `ec8c83f16559653ec43d6789d59844b2006d669e964c0beb9753e13086977a17` | (re-checked identical) |
| `D:\SGF題庫` | 16,676 | `fed97c39fa747d3b1a45c470889b4d1c5bea0365abef47974ec6f2b95d2dd6b3` | (re-checked identical) |

`SOURCE_TREE_PRE_POST_CONTENT_HASH_EQUAL = YES` · `SGF_SOURCE_FILES_MUTATED = 0`.

## 9. What remains (to unblock a future LC012-B)

The owner must do **one** of:

1. **Locate the exact contemporaneous SGF tree** for the `88da3e43…` snapshot
   (a 42,804-file tree whose relative paths reproduce the corpus `source`
   values and whose bytes reproduce the corpus `content` under the recorded
   builder transform), place it under version control / immutable snapshotting,
   and re-run `tools/lc012_sgf_source_tree_freeze.py --tree-root <it>`.
2. **Re-scope genesis to Production** (41,591 records) with its verified SGF
   tree, and treat the +1,213 snapshot-only records as a separate identity
   sub-decision — an owner scope change, not something LC012 may assume.
3. **Ratify a `source`-string-only genesis basis** — i.e. accept the corpus
   `source` field (canonicalised) as the genesis seed *without* a tree hash
   binding, acknowledging that re-ingestion drift then has no external anchor.
   §9 forbids building the manifest this way *without* an explicit owner
   decision; the corpus-side evidence in §5 is exactly what that decision would
   rest on.

Until then: `source_record_uuid` genesis backfill stays blocked — as LC011
already specified (`OWNER_IDENTITY_FOUNDATION_APPROVAL` covered the identity
*architecture*; the genesis *input* — the SGF-tree freeze — is this task's gap).

## 10. Independent verification

`INDEPENDENT_VERIFICATION = PASS`. LC12-E (subagent, READ-ONLY; corpus hash
`88da3e43…` re-verified; no protected file read / hashed / moved / staged)
re-ran the corpus↔tree join from scratch, swept all of `D:\` for a qualifying
tree, tested a union reconstruction, re-verified the corpus-side machinery +
cross-process determinism, and exercised drift A–J against the real gate code.

### LC12-E findings

- **STOP conclusion — CONFIRMED.** `SOURCE_TREE_AUTHORITY_UNRESOLVED` is the
  right call. No single tree, and not the union of all nine SGF trees on `D:\`,
  is the authoritative genesis input; every candidate fails the
  manifest-contract gates (`all_reconciliation_gates_pass = false` — including
  via the Lead's own tool run against the closest tree).
- **Search-completeness correction (folded into §2 / §4).** LC12-E found three
  trees the first draft missed — `D:\go-website_lb_rewards_pr1\SGF題庫` (42,802
  files, 42,802 / 42,804 path hits, ~94%-coincident lineage sibling),
  `D:\desktop\SGF題庫` (44,653), `D:\desktop\go website\SGF題庫` (51,080, its own
  51,080-record `questions.json`). The "8,879 structural / first-collection-
  absent" framing was an artefact of testing only the pruned Production tree;
  §2.2 now attributes it correctly. **No architecture weakness** — the report
  narrative was corrected, the machinery was not.
- **Join reproduction — MATCH.** Every Production-tree metric reproduced exactly
  from scratch: 41,591 files, 33,925 hit / 8,879 miss, 9 byte-exact,
  128 / 42,268 content-sha overlap, first collection 0 hits. Backup `…001533`:
  18,762 hit, 0 exact.
- **Corpus-side machinery — ALL CONFIRMED.** 42,804 canonical sources / 0 path
  collisions / 0 `SOURCE_NOT_RECOVERABLE` / 42,804 distinct proposed UUIDs / 0
  collisions; 404 / 404 content-dup groups; 13 / 13 legacy-collision records
  (+ 11 id-collision groups, each 2 / 2). A second interpreter iterating a
  **shuffled** corpus recomputes the identical
  `uuid_list_sha256 = cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2`
  — byte-identical to pass 1 and to
  `lc012_sgf_source_tree_freeze_report.json`. **Cross-process determinism PASS.**
- **Drift A–J — 10 / 10 PASS** on independent temp fixtures against the real
  gate code (see §7 for the sharpened case-J finding).
- **Tree-manifest determinism — PASS.** A 27-file tree built in three scrambled
  orders yields one identical `tree_manifest_sha256`
  (`8ce8b7de7023a2d44a77c7b8f2f886bd9b4333acee4cab41ca2bfb77fd02c982`), matched
  by an independent re-implementation of the contract hash.

Deliverable: `scratchpad/lc12e_independent_verification.md` (+ 10 repro scripts
in `scratchpad/scripts/`).

## 11. Swarm

- LC12-A source-tree trace / provenance — Lead (§2, §3)
- LC12-B corpus-side canonical-source + proposed-UUID — Lead (§5)
- LC12-C tree-manifest + join + drift machinery + once-only gate — Lead (tool + tests)
- LC12-E independent adversarial verification — subagent (§10)
