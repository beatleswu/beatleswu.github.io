# Question Management Center Legacy Retirement Manifest

Status: convergence preparation only.  No historical route, table, audit
record, or correction authority is removed by this candidate.

The Owner-facing primary entry is `/admin/questions`.  The entries below stay
available until the unified center has independently carried the specialised
workflow and a later retirement task proves that removal is safe.

| Legacy route / UI | Owner-facing treatment now | Retirement classification | Data migration required now | Reason / boundary |
| --- | --- | --- | --- | --- |
| `/admin/sgf-answer-review` and `?mode=legacy` | Keep as a compatibility/advanced link from the center's details path | `KEEP_INTERNAL` | No | System C board-first bulk, history, rollback and advanced editing remain useful. |
| `sgf_answer_review.html` | Not a primary product; link back to `/admin/questions` | `DEPRECATE_AFTER_VALIDATION` | No | Existing specialised workbench must not be deleted before center parity is proven. |
| `/admin` / `admin.html` question-related panels | Link to the center as the first question-management action | `KEEP_INTERNAL` | No | The page also owns unrelated administrative functions. |
| `/api/admin/sgf-workbench/*` | Not exposed as primary Owner navigation | `KEEP_INTERNAL` | No | System C is the sole web correction, staging, validation, retest, history and rollback authority. |
| `/api/admin/sgf-answer-review/v2a/*` | Read/verdict data is projected under 題庫瀏覽 and related sections | `KEEP_INTERNAL` | No | System B remains a useful read/verdict capability; no replacement write authority is added. |
| `/api/admin/question-problem-reports/*` | Projected under 玩家回報 with human reason labels | `KEEP_INTERNAL` | No | System D intake and its existing bridge into System C are preserved. |
| `/api/admin/question-alternative-reports/*` | Projected under 玩家回報 with the 可能還有其他正解 reason | `KEEP_INTERNAL` | No | System E intake and its existing bridge into System C are preserved. |
| `/api/admin/review-queue/*` | Read-only relevant items are projected under 待處理 | `KEEP_INTERNAL` | No | System F has not been proven empty or fully representable; the center adds no F writes. |
| `tools/content_remote_publish.py` | Not used by `/admin/questions` | `DO_NOT_REMOVE` | No | Separate host-level Production mutation authority; governance debt requires its own security/reconciliation task. |

## System F retirement proof status

`SYSTEM_F_RETIREMENT_READY=NO`.

This candidate does not claim retirement readiness because a live, complete
census of unique actionable `corpus_review_queue` rows and their representability
in the D/C model has not been established.  Existing application routes still
write that legacy table for existing problem-report resolution and import
compatibility.  The new center only reads it through the existing database
connection and returns `system_f_new_writes=false`; it contains no F insert,
update, delete, import, or resolve operation.

Before any later removal, a separate task must prove: remaining unique rows,
all writers, parity with D/C, route compatibility, audit/history retention, and
whether schema removal would require a reviewed migration.  No such migration
is part of this candidate.

## Authority invariants

- `DUPLICATE_CORRECTION_AUTHORITY_CREATED=NO`.
- `QUESTION_IDENTITY_MIGRATION=NO`.
- `BACKEND_CORRECTION_AUTHORITY_REPLACED=NO`.
- `/admin/questions` uses exact System C locator resolution and fails closed on
  ambiguous or stale identity.
- Direct apply remains separately gated OFF; ordinary Owner saves stage and
  validate without mutating the canonical question source.
