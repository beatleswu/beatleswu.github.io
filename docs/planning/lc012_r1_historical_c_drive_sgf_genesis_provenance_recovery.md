# LC012-R1 — Historical `C:\go-website` SGF Genesis Provenance Recovery

Status: **HISTORICAL PROVENANCE SUBSTANTIALLY RECOVERED — genesis SGF tree traced
to a `C:\go-website` git commit boundary (Rank B). Owner tree-pin decision
required before an LC012 genesis freeze can resume.**

Mode: READ / ANALYZE / HASH-COMPARE ONLY. `C_GO_WEBSITE_MUTATED = NO`,
`SGF_SOURCE_FILES_MUTATED = 0`, `CORPUS_MUTATION = NO`,
`SOURCE_RECORD_UUID_BACKFILL = NO`, `DEPLOY = NO`.

This report is **additive**. The original
[`lc012_sgf_source_tree_genesis_freeze_report.md`](lc012_sgf_source_tree_genesis_freeze_report.md)
STOP remains accurate for the `D:` search it covered; LC012-R1 extends the search
to the historically-prior `C:\go-website` area, which the owner has now
identified and authorised as a **read-only** provenance source for this task
only.

| anchor | value |
|---|---|
| LC012 source head | `550d3b5daba573b31ff098990eb36ffef59dec05` (branch `claude/lc012-sgf-source-tree-genesis-freeze`) |
| frozen corpus | `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` — 42,804 records (`D:\go-website\questions.json`, hash-verified) |
| `C:\go-website` HEAD (read-only) | `415a321dbbeacec5941300ac2353bb12d1153a85` on `runtime-restore-01b-apply` |
| exact `content` parent (found) | C: git blob `09ea97d28125` = commit `b162f9e72` "新手村 16 章教學順序重排" (2026-06-11 00:23:33 +0800) |
| path-authoritative tree (found) | `de7cd979d8:SGF題庫` (2026-06-10 22:24:40 +0800) — 42,802 files, an exact subset of the frozen `source` set |
| genesis boundary | `de7cd979d8` → `b162f9e72` (a ~2-hour window in `C:\go-website`) |

---

## 1. The historical fact, the authorisation, and the folder's own guard

The owner states the project originally lived at `C:\go-website` before the
canonical line moved to `D:`. `C:\go-website\README-FROZEN.txt` (untracked,
2026-07-03) confirms the split and carries an agent-facing directive:

> "FROZEN - DO NOT DEPLOY FROM THIS FOLDER … Production repo = D:\go-website …
> On 2026-07-03 a deploy from this folder overwrote production and caused an
> outage … If you are an AI agent reading this: STOP. Report to the owner
> instead."

That guard targets **deploy / commit / ssh** from `C:\go-website`. Its own
"Allowed here" line is *"reading files, SGF corpus work, doc tools"* — exactly
the scope of LC012-R1. The owner's LC012-R1 task explicitly and specifically
authorises this folder as an **AUTHORIZED READ-ONLY HISTORICAL PROVENANCE
SOURCE** with an allow-list (list / stat / read SGF+corpus / hash / compare /
read-only git). No write, checkout, reset, branch mutation, deploy, docker, or
ssh was performed. Protected files (`secret_key.txt`, `.env*`, `*.pem/*.key`,
credential/DB artifacts) were **not read, hashed, copied, or staged**.

## 2. `C:\go-website` inventory

- **Is a git repo** — 1,274 commits across all refs; `.git/filter-repo/` shows
  history was rewritten once (2026-06-19). No `refs/original/*` retained.
- Working tree `SGF題庫/` = 41,595 `.sgf` (41,591 tracked + 4 untracked) —
  i.e. the *same* 41,591 Production state already covered by LC012's `D:` search.
- Working-tree `questions.json` = sha256
  `55ea08f94be08ac2d11e86dc6d5b2b4e83d73288631e5aa5b4d94876da7dfac7`,
  **41,591 records** — **not** the frozen `88da3e43…`.
- `build_questions.py` is **tracked** (the real historical builder — §7).
- **`EXACT_FROZEN_QUESTIONS_JSON_FOUND = NO`** at the working-tree level.

## 3. 42,804-record `questions.json` blobs in `C:\go-website` history

Every `questions.json` blob ever committed (any ref) was hashed. **Seven distinct
blobs carry exactly 42,804 records; none hashes to `88da3e43…`.**

| C: blob | bytes | records | sha256 | first seen |
|---|---:|---:|---|---|
| `019f93d0c351` | 74,687,285 | 42,804 | `3106a2bf…` | 2026-06-11 11:23 |
| `b0c658ca40b6` | 73,908,114 | 42,804 | `67badc8e…` | 2026-06-11 09:33 |
| `7f7aa64a7413` | 73,898,623 | 42,804 | `a7fcffb2…` | 2026-06-11 09:40 |
| `04c9ff0cde5e` | 73,881,077 | 42,804 | `a4119aca…` | 2026-06-11 09:30 |
| **`09ea97d28125`** | **73,726,903** | **42,804** | **`adf579e3…`** | **2026-06-11 00:23 (commit `b162f9e72`, +12 more)** |
| `cdf4601c18b6` | 66,030,612 | 42,804 | `70b95fdb…` | 2026-06-10 22:24 (commit `de7cd979d8`, +27 more) |
| *(one 66→74 MB intermediate rebuild chain, all 42,804)* | | | | 2026-06-10/11 |

The frozen corpus is **75,675,637 bytes** — larger than C's largest 42,804-record
blob. After 2026-06-11 12:55 the C: line drops to 42,779 → 42,768 → 41,615 →
41,591 by successive chapter removals. `FROZEN SHA IN C: HISTORY = NO`.

## 4. The exact `content` parent — C: blob `09ea97d28125` / commit `b162f9e72`

Comparing every C: 42,804-record blob to the frozen corpus **by legacy `id`**:

| C: blob | `source` overlap w/ frozen | `content` byte-equal (by id) | **full record identical** |
|---|---:|---:|---:|
| `09ea97d28125` (`b162f9e72`) | 41,886 / 42,804 | **42,793 / 42,793 (0 differ, 0 id-absent)** | **41,875 / 42,804** |
| `04c9ff0cde5e` | 35,769 | 42,792 (1 id-absent) | 35,758 |
| `cdf4601c18b6` (`de7cd979d8`) | **42,804 / 42,804** | 40,153 (2,640 differ) | 22,442 |

**The frozen corpus `content` field is byte-identical to `b162f9e72` for 100 % of
records** (42,793 / 42,793 distinct ids). 41,875 / 42,804 records match on *every*
field. The blob `09ea97d28125` is stable across **13 commits** —
`b162f9e72` (2026-06-11 00:23:33, "新手村 16 章教學順序重排") through
`451f87f097` (2026-06-11 08:33:14).

The frozen corpus is a **light `D:`-side derivative** of that 2026-06-11 state:
same `content`, ~918 `source` paths reverted to the pre-reorg layout (§6), ~929
records with minor field edits, 11 duplicate-`id` groups, plus the byte growth
(73.7 → 75.7 MB) consistent with `D:`-side KataGo enrichment.

## 5. The path-authoritative tree — `de7cd979d8:SGF題庫`

`git ls-tree` of `SGF題庫/` at the 2026-06-10/11 commits, canonicalised with
`canon-source-v1`, joined to the 42,804 frozen `source` keys (LC012's own
`tools/lc012_sgf_source_tree_freeze.py`, run against a read-only `git archive`
extraction):

| commit (all carry q.json blob `cdf4601c` unless noted) | `SGF題庫/*.sgf` | canon keys | matched / 42,804 | tree files **not** in frozen | frozen sources **not** in tree | collisions |
|---|---:|---:|---:|---:|---:|---:|
| `b4bd6506f` … `de7cd979d8` (2026-06-10 15:24 → 22:24) | 42,802 | 42,802 | **42,802** | **0** | **2** | 0 |
| `b162f9e72` … `451f87f097` (blob `09ea97d28125`) | 42,804 | 42,804 | 41,886 | 918 | 918 | 0 |
| `716846e2c` (2026-06-22) | 41,591 | 41,591 | 33,925 | — | 8,879 | 0 |

**`de7cd979d8:SGF題庫` is an exact subset of the frozen `source` set** — every one
of its 42,802 files is a frozen corpus record (`tree − frozen = 0`), 0
canonical-path collisions. `tree_manifest_sha256` (deterministic, LC012 contract
§5) = `d73c18ddcdb01c69b17bacdae40a636cc8bb87ef5ef97f018016973a6e54f247`.

`b162f9e72:SGF題庫` has the **exact count** (42,804) and 0 collisions but 918
paths differ from frozen (§6). `tree_manifest_sha256` =
`12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53`.

**No single commit in the window is simultaneously 42,804-complete *and*
path-exact against frozen.** The frozen `source` layout = `de7cd979d8` tree
(42,802) + 2 files (§6).

## 6. The "2 missing" and the "918 renamed" — the 新手村 chapter-number reorg

- **918 renamed:** `b162f9e72` ("16 章教學順序重排") prefixed 新手村 chapter
  folders with order numbers (`不吃死棋 …` → `03不吃死棋 …`, etc.). All **918 / 918**
  of the frozen `source` paths absent from `b162`'s tree have **byte-identical
  `content` elsewhere in `b162`'s own corpus** — pure folder-renames, no puzzle
  added or lost. The frozen corpus kept the **pre-reorg** folder names for these.
- **2 "missing"** (frozen ids 31198 / 31200): frozen `source`
  `…\征子 ｜ Ladder\56.sgf` / `58.sgf`; `b162f9e72` has the *same ids, same
  content length* at `…\07征子 ｜ Ladder\56.sgf` / `58.sgf`. A folder-number-prefix
  difference only — `canon-source-v1` (correctly) preserves the `07`, so they
  count as a join miss. They are **not** lost data.

So **every** frozen `source` path is accounted for at the `de7cd979d8` ↔
`b162f9e72` boundary; the only discrepancies are folder-name prefixes introduced
by the reorg and then partly reverted on `D:`.

## 7. The real historical builder — and why frozen `content` is not tree-derivable

`build_questions.py` (`de7cd979d8:build_questions.py`, 329 lines, tracked):

- `content` = `read_sgf(path)` = decode with the first working encoding of
  `utf-8, utf-8-sig, big5, gbk, latin-1`, then **`.strip()`**. No re-serialisation,
  no KataGo application in this builder.
- `source` = path relative to `SGF題庫/`.
- `id` = stable: matched by `source`, else by `sha1(content)` (folder-rename
  tolerant), else `max(id)+1`. Deleted SGFs drop their record.
- Sort: topic → level → `sort_order` → id.

Applying that exact transform to the `de7cd979d8` tree reproduces the frozen
`content` for **only 332 / 42,802** records — and reproduces `de7cd979d8`'s
*own* committed `content` for the same 332. **The `content` lineage is
corpus-file → corpus-file** (each `questions.json` carried forward, with SGF
edits landing in the tree but not re-flowed into `content` at every step), **not
tree → corpus at the snapshot point.** Frozen `content` therefore matches
another *`questions.json`* (`09ea97d28125`, exactly) but **cannot be regenerated
from any SGF tree**.

## 8. No provenance receipt

No commit message, tracked doc, build log, manifest, or checksum file anywhere in
`C:\go-website` (history or working tree) references `88da3e43…`, a "genesis"
build, or a frozen-snapshot hash. `git log --all --grep 88da3e43` → empty;
`grep -r 88da3e43` over tracked `*.md/*.txt/*.json/*.log` → empty.

## 9. Candidate ranking (§15)

| candidate | rank | why |
|---|---|---|
| `de7cd979d8:SGF題庫` (+ `b162f9e72` for ids 31198/31200) | **B — STRONGLY_PROVEN_CONTEMPORANEOUS** | exact subset of frozen `source` set (42,802, 0 extra, 0 collisions); the 2 residual paths resolve one commit later; origin repo; builder present; frozen `content` = the sibling `b162f9e72` corpus **exactly** |
| `b162f9e72:SGF題庫` | **B — STRONGLY_PROVEN_CONTEMPORANEOUS** | exact count 42,804, 0 collisions, **exact `content` parent**; 918 `source` paths need a documented de7→b162 rename map |
| C: 42,804-record blobs `019f93d0` / `b0c658ca` / `7f7aa64a` / `04c9ff0c` | C — LINEAGE_SIBLING | same 42,804-record lineage, 2026-06-11, but `source` overlap 35 k and full-record match ≤ 35,758 |
| `D:\go-website_lb_rewards_pr1\SGF題庫` (from LC012) | C — LINEAGE_SIBLING | 42,802 path hits, 0 byte-exact, different build (`6779258b…`) |
| `D:\go website\SGF題庫`, `D:\SGF題庫`, backups (from LC012) | D / E | later pruned Production / unrelated book libraries |

**No Rank A.** No tree deterministically produces the frozen corpus (no single
42,804-complete + path-exact + content-exact commit; frozen `content` not
tree-derivable; the frozen artifact was assembled on `D:`, and no receipt binds
a commit to `88da3e43…`).

## 10. Result

- **`C_HISTORICAL_SCOPE_SEARCHED = YES`.**
- **`ACTUAL_SOURCE_TREE_TRACED = YES`** — `SOURCE_TREE_FORM = HISTORICAL_GIT_TREE`,
  repo `C:\go-website`, boundary `de7cd979d8` → `b162f9e72`.
- **`EXACT_OR_AUTHORITATIVE_TREE_FOUND = PARTIAL`** — the authoritative **content
  parent** is exact (`09ea97d28125`); the authoritative **path tree** is
  `de7cd979d8:SGF題庫` at 42,802 / 42,804 (an exact subset).
- **`STRONG_PROVENANCE_BINDING_TO_88DA3E43 = YES`** (contemporaneous,
  multi-signal); **`EXACT_BUILD_BINDING = NO`**.
- This is **not** a clean §23 PASS (no single tree gives
  `MATCHED = 42,804 / MISSING = 0`) and **not** a §18 "not found" —
  it is a substantiated Rank-B trace.
- **`READY_FOR_LC012_GENESIS_FREEZE_RESUME = CONDITIONAL`** — one owner decision:

  - **P1 — pin `de7cd979d8:SGF題庫` + 2-file graft.** Take the 42,802-file tree
    and explicitly add ids 31198 / 31200 from
    `b162f9e72:SGF題庫/1圍棋新手村 ｜ Go - Starter Village/07征子 ｜ Ladder/{56,58}.sgf`,
    recorded as a documented graft. Yields 42,804 / 42,804 path coverage against
    the frozen `source` set.
  - **P2 — pin `b162f9e72:SGF題庫` + rename map.** Take the exact-count 42,804
    tree and ship the documented 918-entry de7→b162 新手村 folder-rename map so the
    frozen (pre-reorg) `source` paths resolve.

  Under **either**, the frozen `content` is **not** tree-derivable: it must be
  taken as the authoritative artifact (it equals `09ea97d28125` exactly), and the
  SGF-tree pin is for **path / identity genesis only**, with `build_questions.py`
  (`de7cd979d8` revision, captured) as the documented record transform.

A future `tools/lc012_sgf_source_tree_freeze.py` run would materialise the chosen
commit's `SGF題庫` deterministically via `git archive <commit> SGF題庫` into a
disposable evidence directory (as done here) — never a checkout into
`C:\go-website`.

## 11. Mutation boundary evidence

| control | before | after | verdict |
|---|---|---|---|
| `C:\go-website` HEAD | `415a321db…` | `415a321db…` | unchanged |
| `C:\go-website` reflog `HEAD@{0}` | `commit: fix(runtime): restore canonical production runtime` | same | unchanged |
| `C:\go-website` `git status --porcelain` line count | 34 (pre-existing untracked) | 34 | unchanged |
| operations used | `git log`, `git rev-list`, `git ls-tree`, `git cat-file`, `git archive`, `git show`, `git check-ignore` | — | all read-only |

`C_GO_WEBSITE_MUTATED = NO` · `SGF_SOURCE_FILES_MUTATED = 0` ·
`CORPUS_MUTATION = NO` · `QUESTION_RECORD_MUTATION = NO` ·
`SOURCE_RECORD_UUID_BACKFILL = NO` · `APP_PY_CHANGED = NO` ·
`SCHEMA_CHANGED = NO` · `MIGRATION_CHANGED = NO` · `PRODUCTION_QUERY = NO` ·
`PRODUCTION_MUTATION = NO` · `DEPLOY = NO`.

## 12. Evidence artifacts (not committed verbatim — large-artifact policy, LC012 §33)

Reproduce from `C:\go-website` (read-only):

```
git -C C:\go-website archive --format=tar de7cd979d8 "SGF題庫" | tar -x -C <tmp_de7>
git -C C:\go-website archive --format=tar b162f9e72 "SGF題庫" | tar -x -C <tmp_b162>
python tools/lc012_sgf_source_tree_freeze.py --snapshot D:\go-website\questions.json \
    --tree-root <tmp_de7>\SGF題庫  --out-report <report_de7>.json
```

| artifact | sha256 / value |
|---|---|
| frozen corpus | `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` / 42,804 |
| `de7cd979d8:SGF題庫` tree_manifest_sha256 (42,802 files) | `d73c18ddcdb01c69b17bacdae40a636cc8bb87ef5ef97f018016973a6e54f247` |
| `b162f9e72:SGF題庫` tree_manifest_sha256 (42,804 files) | `12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53` |
| C: blob `09ea97d28125` (content parent) | `adf579e308df97fa636d3f1cd2989c4607a45be4d4fd18a82c9a60070973d595` — 73,726,903 B, 42,804 rec |
| C: blob `cdf4601c18b6` (`de7cd979d8` corpus) | `70b95fdbf5c189e7222c652a505f976c9606e12cf208dc5a03338885ea35384f` — 66,030,612 B, 42,804 rec |
| `C:\go-website` HEAD (read-only) | `415a321dbbeacec5941300ac2353bb12d1153a85` |

Scratch scripts (read-only, disposable):
`scratchpad/lc12r1_blob_hunt.py`, `lc12r1_gittree_join.py`,
`lc12r1_content_lineage.py`, `lc12r1_blob_vs_frozen.py`, `lc12r1_window_scan.py`,
`lc12r1_ladder_and_renames.py`.

## 13. What remains

1. **Owner picks P1 or P2** (§10) — which commit's `SGF題庫` is the genesis tree
   pin, and (P1) the 2-file graft or (P2) the 918-entry rename map is recorded.
2. LC012-B then runs the freeze tool against that materialised tree, emits the
   `SGF_SOURCE_TREE_GENESIS_MANIFEST` per
   [`lc012_sgf_source_tree_genesis_manifest_contract.md`](lc012_sgf_source_tree_genesis_manifest_contract.md),
   and records `sgf_tree_manifest_sha256` into the LC011
   `GENESIS_BOOTSTRAP_ONCE_ONLY` tuple.
3. Frozen `content` is accepted as the authoritative artifact (it equals
   `09ea97d28125` exactly); `build_questions.py`@`de7cd979d8` is the documented
   record transform. No `content` is regenerated from SGF.
4. No `source_record_uuid` is minted or written — unchanged from LC011/LC012.

## 14. Final report (§24)

```
TASK                                  = LC012_R1_HISTORICAL_C_DRIVE_SGF_GENESIS_PROVENANCE_RECOVERY_001
LC012_SOURCE_HEAD                     = 550d3b5daba573b31ff098990eb36ffef59dec05
BRANCH                               = claude/lc012-sgf-source-tree-genesis-freeze
LOCAL_HEAD                           = 550d3b5daba573b31ff098990eb36ffef59dec05 (pre-commit of this report)
REMOTE_HEAD                          = 550d3b5daba573b31ff098990eb36ffef59dec05
REMOTE_HEAD_EXACT                    = YES

C_HISTORICAL_SCOPE_SEARCHED          = YES
C_GO_WEBSITE_PRESENT                 = YES
C_GO_WEBSITE_GIT_REPO               = YES  (HEAD 415a321db, branch runtime-restore-01b-apply; history filter-repo'd 2026-06-19)
HISTORICAL_GIT_TREE_RECOVERABLE      = YES  (via git archive, read-only)

EXACT_FROZEN_QUESTIONS_JSON_FOUND    = NO
EXACT_SNAPSHOT_PATH                  = (none)
EXACT_SNAPSHOT_SHA256               = (none in C: history; frozen 88da3e43 present only in D:\go-website\questions.json)

CANDIDATE_TREE_COUNT                 = 3 C: git-tree states in the 2026-06-10/11 window (de7cd979d8 group / b162f9e72 group / 716846e2c) + 7 distinct 42,804-record questions.json blobs

BEST_CANDIDATE_ROOT                  = C:\go-website  ::  de7cd979d8:SGF題庫  (path tree)  +  b162f9e72:SGF題庫 / blob 09ea97d28125  (exact content parent)
BEST_CANDIDATE_FORM                  = HISTORICAL_GIT_TREE
BEST_CANDIDATE_GIT_COMMIT            = de7cd979d838b441bd570e4d0eec3b3a46ef0c5c  (content parent: b162f9e72b93b73c08c1b044f365cb9287efae70)
BEST_CANDIDATE_GIT_TREE              = de7cd979d8:SGF題庫  tree_manifest_sha256 d73c18ddcdb01c69b17bacdae40a636cc8bb87ef5ef97f018016973a6e54f247
                                       b162f9e72:SGF題庫  tree_manifest_sha256 12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53

SGF_TREE_FILE_COUNT                  = 42,802 (de7cd979d8)  |  42,804 (b162f9e72)
PATH_MATCH_COUNT                     = 42,802 / 42,804 (de7cd979d8, exact subset)  |  41,886 / 42,804 (b162f9e72)
MATCHED_TO_SOURCE_TREE               = 42,802 (de7cd979d8)   [+2 resolve at b162f9e72 as 07征子｜Ladder/{56,58}.sgf → 42,804 under option P1]
MISSING_SOURCE                       = 2 (de7cd979d8; folder-number-prefix only, data present at child commit)  |  918 (b162f9e72; documented 新手村 reorg renames)
AMBIGUOUS_SOURCE                     = 0
CANONICAL_PATH_COLLISIONS            = 0 (both trees)

BYTE_EXACT_COUNT                     = 0  (frozen content vs raw SGF bytes, either tree)
EXPECTED_BUILDER_TRANSFORM_COUNT     = 332  (frozen content == read_sgf(decode+strip) of de7cd979d8 tree)   [content lineage is corpus→corpus, not tree→corpus]
UNEXPLAINED_DRIFT_COUNT              = 0 unexplained — every delta is attributed: 2,640 = de7cd979d8→b162f9e72 SGF edits; 918 = 新手村 folder reorg; ~929 = D:-side field edits; 11 = duplicate-id groups

STRONG_PROVENANCE_BINDING_TO_88DA3E43 = YES  (contemporaneous, multi-signal: origin repo + exact content parent + subset path tree + real builder + 2h window)
EXACT_BUILD_BINDING                  = NO   (no 42,804-complete+path-exact+content-exact single commit; frozen content not tree-derivable; frozen artifact assembled on D:; no 88da3e43 receipt in C:)

ACTUAL_SOURCE_TREE_TRACED            = YES  (SOURCE_TREE_FORM = HISTORICAL_GIT_TREE; C:\go-website; de7cd979d8 → b162f9e72 boundary)

TREE_MANIFEST_SHA256                 = d73c18ddcdb01c69b17bacdae40a636cc8bb87ef5ef97f018016973a6e54f247  (de7cd979d8:SGF題庫)
                                       12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53  (b162f9e72:SGF題庫)

C_GO_WEBSITE_MUTATED                 = NO
SGF_SOURCE_FILES_MUTATED            = 0
CORPUS_MUTATION                     = NO
QUESTION_RECORD_MUTATION            = NO
SOURCE_RECORD_UUID_BACKFILL         = NO
APP_PY_CHANGED                      = NO
SCHEMA_CHANGED                      = NO
MIGRATION_CHANGED                   = NO
PRODUCTION_QUERY                    = NO
PRODUCTION_MUTATION                 = NO
DEPLOY                              = NO

TESTS                               = tests/test_lc012_sgf_source_tree_genesis_freeze.py — 19 passed  (no tool code changed)
TASK_INTRODUCED_FAILURES            = 0

WHAT_WAS_FOUND                      = The frozen 42,804-record corpus's genesis SGF source tree is in C:\go-website git history — path-authoritative at de7cd979d8:SGF題庫 (42,802, exact subset of frozen sources) and content-exact at commit b162f9e72 / blob 09ea97d28125 (100% of records byte-equal, 41,875/42,804 fully identical). The real builder build_questions.py is tracked there.
WHAT_HISTORICAL_PROVENANCE_PROVES   = The frozen corpus is a light D:-side reconciliation of the 2026-06-11 00:23 C: state: same content, ~918 source paths reverted to the pre-新手村-reorg layout, ~929 minor field edits, 11 dup-id groups, + D:-side KataGo enrichment. Every content/path delta is attributed; none is unexplained.
WHETHER_88DA3E43_GENESIS_TREE_IS_RECOVERABLE = YES as a historical git tree (Rank B), pending one owner tree-pin decision (P1 de7cd979d8+2-file graft, or P2 b162f9e72+918 rename map). NOT recoverable as a deterministic byte-for-byte rebuild — frozen content is corpus-lineage, not tree-derived, and the frozen artifact was assembled on D:.
WHAT_REMAINS                        = Owner picks P1 or P2 → LC012-B materialises that commit's SGF題庫 (git archive, read-only) → emits SGF_SOURCE_TREE_GENESIS_MANIFEST → records sgf_tree_manifest_sha256 into the LC011 GENESIS_BOOTSTRAP_ONCE_ONLY tuple. Frozen content accepted as authoritative artifact; build_questions.py@de7cd979d8 as documented transform. No UUID backfill.

RESULT                              = HISTORICAL_PROVENANCE_SUBSTANTIALLY_RECOVERED — GENESIS_SGF_TREE_TRACED_RANK_B (C:\go-website de7cd979d8 → b162f9e72); OWNER_TREE_PIN_DECISION_REQUIRED (P1 / P2)
READY_FOR_COORDINATOR_LC012_R1_REVIEW = YES
```
