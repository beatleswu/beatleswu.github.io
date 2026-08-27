# LC008 — Content-Duplicate Identity & Review-Fanout Audit

Branch base: `4738f619fb9fedf9fb7cd912f02689e086a15087` (LC009 authoritative head)
Canonical master at task time: `c2a1dab3125cdef0cff381815d3d995bdd340538`
Type: **audit / evidence**. No corpus mutation. No `source_record_uuid`
generation. No LC009-semantics change. No record merge.

Artifacts:
- `tools/lc008_content_duplicate_identity_audit.py` — deterministic read-only auditor
- `docs/planning/lc008_content_duplicate_manifest.json` — per-group manifest (404 groups); sha256 `eb8aad34b0628a904c45efe339ada0ccf903fa9416b3c8cbe4410fc44cc0de89`
- `tests/test_lc008_content_duplicate_identity_audit.py` — 15 tests

## 1. Executive summary

The snapshot has **404 exact-content duplicate groups** covering **940
records**. **None of them can support a safe human-review fan-out today**, and
the potential manual-review saving is **0**, for one decisive reason: the
owner-locked canonical identity field **`source_record_uuid` does not exist in
a single record** (0 / 42,804). Per the owner identity model (§2), *identical
content does not imply identical canonical identity*, and there is no field in
the corpus that can prove it does. On top of that, **403 / 404** groups carry
metadata drift and **271 / 404** carry KataGo-provenance drift (**80** of those
on the *substantive* recorded answer — `katago_best_move` / `answer_source` /
report status — the rest only on run artefacts) — independent reasons a
one-member adjudication may not transfer.

The 13 `DUPLICATE_IDENTITY_BLOCKED` records from the LC005/LC009 census are a
**different mechanism** — legacy-`id` collisions between records with *distinct*
content — and are fully reconciled here (none overlap the 404 content groups).

**Recommended next step:** an owner-approved `source_record_uuid` population +
identity-reconciliation task is a prerequisite for *any* review-fanout saving.
Only after that, and only for groups it confirms as one canonical identity with
no answer-authority drift, could a bounded saving (ceiling ≈ 142 secondary
reviews, §7) be realised. LC008 proposes no corpus change.

## 2. Exact census (`DUPLICATE_CENSUS_REPRODUCED = PASS`)

| metric | value |
|---|---:|
| `CORPUS_RECORD_COUNT` | 42,804 |
| `SNAPSHOT_SHA256` | `88da3e43…f654ff` — **match** |
| `DISTINCT_CONTENT_HASHES` | 42,268 |
| `CONTENT_DUPLICATE_GROUPS` | **404** |
| `CONTENT_DUPLICATE_RECORDS` | **940** |
| records in no duplicate group | 41,864 |

`content_sha256 = sha256(record["content"].encode("utf-8"))` — see §8.

## 3. Duplicate-group size distribution

| group size | # groups | # records |
|---:|---:|---:|
| 2 | 278 | 556 |
| 3 | 121 | 363 |
| 4 | 4 | 16 |
| 5 | 1 | 5 |
| **total** | **404** | **940** |

`DUPLICATE_GROUP_SIZE_MIN = 2` · `DUPLICATE_GROUP_SIZE_MAX = 5`.

## 4. Fields actually available (spec §5 — no invented fields)

| category | fields present in every/most record | notes |
|---|---|---|
| canonical identity | **none** | `source_record_uuid` / `uuid` / `source_uuid` / `record_uuid` / `canonical_id` — **all ABSENT** |
| legacy identity | `id` | 42,793 distinct → 11 duplicate-`id` groups (22 records) |
| ingestion locator | *(array position only)* | no stored `record_index` field |
| provenance | `source` | a per-file SGF path, e.g. `"…\\1-6 全局问题\\24.sgf"` — **unique in every one of the 42,804 records** |
| answer authority | `katago_best_move` (45.6%), `answer_source` (43.9%), `katago_full_report_status`, `katago_full_previous_answer`, `katago_full_score_gap`, `katago_full_visits`, `katago_full_applied_at`, `katago_full_report`, `katago_auto_*` (1.7%), `answer*` (≤0.02%), `score_gap`, `katago_match` | which move the corpus records as "the answer" and how it was derived |
| metadata | `topic`/`topic_en`, `level`/`level_en`, `difficulty`, `rank`, `stage`, `discipline`/`discipline_label`, `grimoire_id`, `grimoire_difficulty`, `difficulty_score`, `tags`, `map_id`/`map_name`/`map_chapter`, `weakness_topic`, `monster_*`, `encounter_type`, `boss_level`, `sort_order`, `display_name`, `enabled` | curatorial classification / game framing |
| authoring | `comment` (top-level, ~always null), `manual_restore_note` (17.7%) | `comment` is NOT part of `content_sha256` |

## 5. Identity taxonomy — all 404 groups

| primary identity classification | groups |
|---|---:|
| `SAME_CONTENT_IDENTITY_INCOMPLETE` | **404** |
| *(every other class)* | 0 |

Secondary flags (a group may carry several):

| flag | groups |
|---|---:|
| `SAME_CONTENT_DIFFERENT_LEGACY_ID` (all members' `id` distinct) | 404 / 404 |
| `SAME_CONTENT_DIFFERENT_SOURCE_IDENTITY` (all members' `source` path distinct; no `source_record_uuid` to reconcile) | 404 / 404 |
| `SAME_CONTENT_WITH_METADATA_DRIFT` | 403 |
| `SAME_CONTENT_WITH_PROVENANCE_DRIFT` (any KataGo-provenance field differs; 80 differ on the substantive answer) | 271 |
| `SAME_CONTENT_WITH_AUTHORING_DRIFT` (`comment` / `manual_restore_note` differ) | 13 |
| `SAME_CONTENT_SAME_LEGACY_ID` | 0 |
| `SAME_CONTENT_SAME_SOURCE_IDENTITY` | 0 (unprovable — no UUID) |

Exactly **1** group has zero drift on metadata + answer-authority + authoring
(members differ only by `source` path and `id`) — and it is still
`IDENTITY_INCOMPLETE` because no `source_record_uuid` exists to confirm the two
files are one canonical question. Typical shape: the same tesuji SGF filed
under two chapters of one workbook (`…\1.3征\4.sgf` and `…\1.4罩\4.sgf`).

## 6. Fanout taxonomy — all 404 groups

| fanout classification | groups |
|---|---:|
| `BLOCKED_BY_INCOMPLETE_IDENTITY` | **404** |
| `SAFE_REVIEW_FANOUT` | **0** |
| `REQUIRES_INDEPENDENT_REVIEW` / `BLOCKED_BY_SOURCE_IDENTITY` / `BLOCKED_BY_METADATA` / `BLOCKED_BY_PROVENANCE` / `BLOCKED_BY_AUTHORING_CONTEXT` / `BLOCKED_OTHER` | 0 |

Fail-closed rule (spec §6/§7): the absence of `source_record_uuid` is checked
first and blocks every group — you cannot prove members share canonical
identity. Had a UUID existed, the auditor would then have blocked on
answer-authority drift (271), metadata drift (403 − overlap), or authoring
drift (13), and downgraded the rest to `REQUIRES_INDEPENDENT_REVIEW` because
distinct `source` paths leave "independent intent" unproven.
**`SAFE_REVIEW_FANOUT` is never a record merge** (spec §8): even a green group
would keep 2–5 separate canonical records.

## 7. Manual-review savings (conservative)

| metric | value |
|---|---:|
| `MANUAL_RECORDS_IN_DUPLICATE_GROUPS` | **923** (of 940: + 15 `MALFORMED_SOURCE`, 2 `AMBIGUOUS_AUTOREPLY`) |
| `SAFE_FANOUT_GROUPS` | **0** |
| `SAFE_FANOUT_RECORDS` | **0** |
| `SAFE_FANOUT_PRIMARY_REVIEWS_REQUIRED` | 0 |
| **`POTENTIAL_MANUAL_REVIEW_DEDUP_SAVINGS`** | **0** |

Savings counts only records that would not need a second independent semantic
review *when `SAFE_REVIEW_FANOUT` is proven*. It is proven for 0 groups, so the
saving is 0. Identity-incomplete, drift, malformed and ambiguous records are
excluded by definition.

**Non-binding ceiling** (what a future `source_record_uuid` task could unlock):
133 groups have neither answer-authority nor authoring drift; if a UUID
population confirmed each as one canonical identity, at most **142** secondary
MANUAL reviews (Σ over those groups of `MANUAL_members − 1`, across 277
records) could be fanned out. This number is contingent on two things that do
not exist today and is **not** an LC008 result.

## 8. content_sha256 semantics (`CONTENT_HASH_SEMANTICS_DOCUMENTED = PASS`)

| aspect | value |
|---|---|
| algorithm | SHA-256 |
| input | `record["content"]` encoded UTF-8 — **the SGF string only** |
| excludes | `comment` (a sibling top-level field), **all** metadata fields, **all** provenance/`source` fields, **all** answer-authority / `katago_*` fields |
| normalisation | **none** (raw bytes) |
| equal hash implies | byte-identical SGF content **and nothing else** — not identical metadata, not identical recorded answer, not identical provenance, not identical canonical identity |

Because equal hash says nothing about identity or answer authority, it is a
necessary but nowhere-near-sufficient basis for review fanout.

## 9. The 13 `DUPLICATE_IDENTITY_BLOCKED` records (spec §12)

`DUPLICATE_IDENTITY_BLOCKED_RECORDS = 13` — indexes `16715, 16716, 16751,
16786, 16787, 17094, 32194, 33715, 41082, 41155, 41283, 41321, 41467`; legacy
ids span **11** groups (`40479, 40511, 40512, 40513, 62011, 63382, 70450,
70752, 71238, 71240, 71244`; ids `40511` and `40513` each cover 2 of the 13).

`DUPLICATE_IDENTITY_BLOCKED_GROUPS = 11` (legacy-`id` groups).
`ALL_13_ACCOUNTED_FOR = PASS`.

- All 13 have **distinct `content_sha256`** from one another (13 hashes).
- **0** of the 13 fall inside any of the 404 content-duplicate groups.
- They are blocked by the LC005 classifier because their legacy `id` is
  non-unique — two records were ingested under the *same* `id` while carrying
  *different* SGF content (a legacy-alias collision, not a content duplicate).
  This is the opposite pattern to the 404 groups (same content, different id).
- LC008 does not alter their identity. They remain correctly blocked pending a
  legacy-`id` disambiguation that only an owner identity task can perform.

## 10. `source_record_uuid` readiness (spec §13)

| metric | value |
|---|---:|
| `SOURCE_RECORD_UUID_PRESENT_COUNT` | **0** |
| `SOURCE_RECORD_UUID_MISSING_COUNT` | **42,804** |
| `SOURCE_RECORD_UUID_DUPLICATE_COUNT` | 0 |
| `SOURCE_RECORD_UUID_COLLISION_COUNT` | 0 |
| `SOURCE_RECORD_UUID_FORMAT_ANOMALY_COUNT` | 0 |
| `SOURCE_RECORD_UUID_GENERATED` | **NO** |

The canonical identity field is **entirely unpopulated**. Nothing in the
current snapshot approximates it: `id` collides (11 groups), `source` is a
raw per-file path, `record_index` is positional only. Canonical identity is
**not ready**; a dedicated owner-approved population task is required before
identity-aware dedup or review-fanout is possible.

## 11. Risk analysis

| risk | assessment |
|---|---|
| Treating equal content as equal identity | **High if acted on.** 404 groups, distinct `id` + distinct `source` in every one; §2 forbids it and no field can confirm it. LC008 does not. |
| Fanning a review across answer-authority drift | 271 groups differ on some KataGo-provenance field; 80 record a *different* `katago_best_move` / `answer_source` / status between members — a review of one is not evidence about the other. Blocked. |
| Fanning across metadata drift | 403 groups differ on discipline/chapter/difficulty framing; the SGF board is identical but the curatorial intent is not proven identical. Blocked/independent. |
| Collapsing canonical records | Not proposed. `CONTENT_DEDUP_DOES_NOT_REWRITE_IDENTITY = PASS`; `SAFE_REVIEW_FANOUT ≠ RECORD_MERGE`. |
| Mixing the two duplicate mechanisms | The 13 legacy-`id` collisions are explicitly separated from the 404 content groups (§9). |

## 12. Recommended next step

1. **Owner-approved `source_record_uuid` population + identity reconciliation**
   task (separate from LC008). Only this can make any fanout saving real.
2. After UUIDs exist, re-run this audit; groups it confirms as one canonical
   identity **and** that carry no answer-authority / authoring drift become
   candidates for review-labour fanout (ceiling ≈ 142 secondary reviews).
3. Separately, a legacy-`id` disambiguation for the 11 collision groups (13
   blocked records) — unrelated to content duplication.

No corpus mutation is proposed or performed.

## 13. Determinism & independent recount

`MANIFEST_SHA256 = eb8aad34b0628a904c45efe339ada0ccf903fa9416b3c8cbe4410fc44cc0de89`
— byte-identical on rerun from the same snapshot (`DETERMINISTIC_RERUN = PASS`).

**`INDEPENDENT_RECOUNT = PASS`.** LC8-E re-derived everything from scratch
(own grouping, own drift comparison, own fail-closed rule; no manifest / no
`tools/lc008_*` import) and independently confirmed: 42,804 records / 42,268
distinct hashes / **404** groups / **940** duplicate records (size 2→278,
3→121, 4→4, 5→1); accounting `42,268 = 41,864 singletons + 404 groups` and
`42,804 = 41,864 + 940`; `source_record_uuid` present 0 / missing 42,804 /
collisions 0; 404/404 groups diverge on both legacy `id` and `source` path,
403/404 on metadata, 80/404 on the substantive KataGo answer, 1/404 with no
field drift (still identity-incomplete); **`SAFE_REVIEW_FANOUT_GROUPS = 0`**,
**`POTENTIAL_MANUAL_REVIEW_DEDUP_SAVINGS = 0`**; `MANUAL_RECORDS_IN_DUPLICATE_GROUPS
= 923` (940 = 923 MANUAL + 15 MALFORMED + 2 AMBIGUOUS); the 13
`DUPLICATE_IDENTITY_BLOCKED` records have 13 distinct content hashes, sit in
**0** content-duplicate groups (each `content_group_size == 1`), span 11
legacy-`id` groups, and the 11 groups (22 records) resolve as 13 blocked + 6
`AMBIGUOUS_AUTOREPLY` + 3 `MALFORMED_SOURCE` — `ALL_13_ACCOUNTED_FOR = PASS`.
LC8-E's own script was deterministic across two runs.

## 14. Swarm

- **LC8-A** exact duplicate census + size distribution — Lead
- **LC8-B** identity / `source_record_uuid` / provenance comparison — Lead
- **LC8-C** safe review-fanout classification — Lead (fail-closed rule)
- **LC8-D** 13 `DUPLICATE_IDENTITY_BLOCKED` reconciliation — Lead (§9)
- **LC8-E** independent recount + savings verification — subagent (no manifest import); **PASS**, all figures reproduced (see §13)
