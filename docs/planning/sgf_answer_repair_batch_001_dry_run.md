# SGF-ANSWER-REPAIR-BATCH-001 — Phase 1 Dry Run

Status: READY_FOR_OWNER_DRY_RUN_REVIEW

這是 Production staged proposals 的唯讀快照與隔離修正模擬。沒有任何 canonical SGF、questions.json、accepted moves、玩家判題或 Production DB 寫入。

## Snapshot identity

- Proposal snapshot timestamp: 2026-08-09T11:20:32.116Z
- Proposal snapshot SHA-256: 5897644200246f5bdecf7c291054f3db982a78ba402956ba563bea804d400b2c
- Reviewed questions snapshot SHA-256: 88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff
- Current target evidence SHA-256: 64e40182906485e740354f45bb767c97777ec4ca6d321551a1f79cd0d1256778
- Current Production questions SHA-256: 4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28
- Current Production question count: 41591
- Repair plan SHA-256: 98ff42be00f181740b46a2c413e4ac12977293fcbcff7f2957117bc611f4d70b

## Batch totals

| Metric | Count |
| --- | ---: |
| Active proposals | 108 |
| Active review groups | 107 |
| Affected question records | 118 |
| Auto applyable | 54 |
| Manual reconstruction required | 1 |
| Stale or conflicted | 5 |
| Unresolved | 47 |
| No-op | 0 |
| Duplicate groups | 6 |
| Multi-record repair groups | 6 |
| Duplicate fan-out records | 11 |
| Duplicate group conflicts | 0 |
| Planned canonical source references changed | 65 |
| Planned question records changed | 65 |
| Precomputed fallbacks cleared | 61 |
| Precomputed fallbacks preserved | 4 |
| Replacement/fallback conflicts | 3 |

Classification totals are review-group counts. Planned question records include exact duplicate fan-out.

## Isolated validation summary

| Check | Result |
| --- | --- |
| Isolated repaired records | 65 |
| SGF parse before/after | PASS |
| Native desired/removed move judging | PASS |
| Initial position/root/surviving variations | PASS |
| Multi-answer repaired records | 6 |
| Multi-answer exact-set validation | PASS |

### Fail-closed reason counts

| Reason code | Groups |
| --- | ---: |
| `ISOLATED_REPAIR_VALIDATION_PASSED` | 54 |
| `MISSING_CURRENT_SOURCE` | 47 |
| `SIMULATION_VALIDATION_FAILED` | 3 |
| `SOURCE_PATH_CHANGED` | 2 |
| `SOURCE_POSITION_INCLUDES_ANSWER` | 1 |
| `UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET` | 3 |

## Question 15436 regression reference

- Present: True
- Classification: STALE_OR_CONFLICTED
- Current: A2, B1
- After repair: B1
- Historical precomputed fallback: Q4
- Classification reasons: SIMULATION_VALIDATION_FAILED, UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET
- Intended operation: remove A2 from the native answer set and preserve B1. This is replacement semantics, not add B1.

Question 15436 is fail-closed: the native rewrite itself is valid, but current verdict logic would still accept Q4. A later apply batch needs an explicit Owner decision on that historical fallback; this dry run does not infer one.

## Owner-friendly repair plan

| Question(s) | Current native | After native | Historical fallback | Classification | Action | Dry-run |
| --- | --- | --- | --- | --- | --- | --- |
| 65170 | — | — | D16（保留） | MANUAL_RECONSTRUCTION_REQUIRED | 人工重建／題面或先後手證據審查 | N/A |
| 74535 | — | — | — | STALE_OR_CONFLICTED | stale/conflict；必須重新審題 | FAIL CLOSED |
| 35389 | — | — | — | STALE_OR_CONFLICTED | stale/conflict；必須重新審題 | FAIL CLOSED |
| 8413 | O19 | O19 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 51664 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 52036 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51607 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 8189、41862、41960 | Q17 | Q17 | Q4、D17 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 15436 | A2、B1 | B1 | Q4（保留） | STALE_OR_CONFLICTED | stale/conflict；必須重新審題 | FAIL CLOSED |
| 51744 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 7958 | S18 | S18 | R4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 7993 | S17 | S17 | D17 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 51603 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51638 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51811 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51814 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 39728 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 7956 | F3 | F3 | D17 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8117 | O19 | O19 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 7989 | E2 | E2 | D16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 51729 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 73069 | E1 | E1 | D16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 73632 | D2 | D2 | Q16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 37624 | N18、S18 | N18、S18 | D4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 39714 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 8057 | E2 | E2、Q16 | Q16（保留） | AUTO_APPLYABLE | 重寫 native root answer set | PASS |
| 8092 | E1 | E1、Q17 | Q17（保留） | AUTO_APPLYABLE | 重寫 native root answer set | PASS |
| 8100 | P18 | P18、Q4 | Q4（保留） | AUTO_APPLYABLE | 重寫 native root answer set | PASS |
| 7998 | C2 | C2、C16 | C16（保留） | AUTO_APPLYABLE | 重寫 native root answer set | PASS |
| 15388 | D2、B2 | B2 | Q4（保留） | STALE_OR_CONFLICTED | stale/conflict；必須重新審題 | FAIL CLOSED |
| 51598 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51681 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51878 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51897 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 65095 | R18、S18、Q19 | R18 | D17（保留） | STALE_OR_CONFLICTED | stale/conflict；必須重新審題 | FAIL CLOSED |
| 65063 | A4 | A4 | C16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 73096 | A2 | A2 | D16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 73121 | C1 | C1 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 73212 | E2 | E2 | Q16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8069 | S19 | S19 | R4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8122 | P17 | P17 | R4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8134 | E3 | E3 | Q16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8137 | Q19 | Q19 | D17 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 7961 | B2 | B2 | C16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 7980 | S18 | S18 | D17 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 7999 | S17 | S17 | R4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8005 | E4 | E4 | C16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8009 | C1 | C1 | Q16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8020 | B2 | B2 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8033 | E4 | E4 | C16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8188、41959 | E3 | E3 | C16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 41931、8163、41833 | J19 | J19 | R5、Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 41951、8181、41853 | C2 | C2 | D16、Q3、Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 51625 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51645 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51650 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51651 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51655 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51666 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51679 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51689 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51742 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51754 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51757 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51877 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51906 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51917 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 64952 | S19 | S19 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 65106 | B1、B4 | B1、B4 | Q3 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 72868 | B1 | B1 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 73581 | B1 | B1 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8095 | S19 | S19 | D17 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8128 | B6 | B6 | D16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8001 | S19 | S19 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8012 | A2 | A2 | Q3 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8056 | T17 | T17 | R4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8088 | C2 | C2 | Q3 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8091 | T18 | T18 | R4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8097 | F1 | F1 | C16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8112 | C2 | C2 | Q3 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8124 | S18 | S18 | D16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8129 | R18 | R18 | D16 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8132 | A2 | A2 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 7960 | P18 | P18 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 7969 | Q18 | Q18 | D17 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8036 | C2 | C2 | Q3 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8040 | C2 | C2 | Q3 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8162、41832、41930 | D1 | D1 | Q3 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 8209、41884、41982 | P18 | P18 | Q4 → 清除 | AUTO_APPLYABLE | 清除歷史預先計算 fallback | PASS |
| 51674 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51578 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51596 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51605 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51614 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51656 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51579 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51707 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51740 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51708 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51716 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51752 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51794 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51791 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51810 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51831 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51910 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |
| 51912 | — | — | — | UNRESOLVED | current corpus 找不到對應題目；不可套用 | N/A |

<details>
<summary>Technical classification notes</summary>

- AUTO_APPLYABLE means only that an isolated copy parsed and matched the exact Owner-approved answer semantics. It is not permission to apply.
- MANUAL_RECONSTRUCTION_REQUIRED covers side-to-move/source-position/reconstruction proposals where no deterministic authoring transformation is proven.
- UNRESOLVED means the exact reviewed legacy record is absent from the current Production corpus. No ID/index guess was made.
- Content fingerprints and legacy IDs are bounded locator evidence only; canonical identity remains deferred.
- A replacement fails closed when a non-rejected historical precomputed fallback remains outside the desired answer set. That stored fallback still affects the current player verdict; the dry run never infers permission to clear it.
- planned_canonical_files_changed counts unique source SGF references among applyable records; the current authoritative runtime representation remains the corresponding questions.json records.

</details>

## Reproduction

The committed proposal snapshot and the local-only current-target evidence are immutable inputs. The latter contains the minimum 71 target SGFs needed for simulation and is intentionally not committed.

```powershell
python tools\sgf_answer_repair_batch.py --proposal-snapshot docs\planning\sgf_answer_repair_batch_001_proposal_snapshot.json --reviewed-questions D:\go-website\questions.json --current-targets D:\go-website-sgf-answer-repair-batch-001-artifacts\current_canonical_targets.json --manifest docs\planning\sgf_answer_repair_batch_001_manifest.json --report docs\planning\sgf_answer_repair_batch_001_dry_run.md --simulation-dir D:\go-website-sgf-answer-repair-batch-001-artifacts\isolated-repairs-final
```

Before any later apply phase, take a fresh current-source snapshot and require the same locator/content/source preconditions again. This report is not an apply authorization.

## Safety assertions

    CANONICAL_SGF_MUTATED=NO
    QUESTIONS_JSON_MUTATED=NO
    ACCEPTED_MOVES_MUTATED=NO
    PRODUCTION_DB_MUTATED=NO
    PLAYER_VERDICT_MUTATED=NO
    KATAGO_RUN=NONE
    IDENTITY_IMPLEMENTED=NO
    DEPLOY=NO
