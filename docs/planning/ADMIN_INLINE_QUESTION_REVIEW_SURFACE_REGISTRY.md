# Admin Inline Question Review Surface Registry

Status: forensic census complete; this branch is an owner-UX convergence on
the existing inline review system, not a new review-system rollout.

The authoritative census confirms inline review is already present on all
7/7 real question-answering surface groups. `community.html` and `play.html`
are intentionally not counted because they do not present corpus-backed
questions.

This registry records where a real Go question is answered and how the shared
`SGFReportWidget` receives the exact question locator.  It is a projection of
existing runtime identity; it does not create or migrate question identities.

## Shared authority

- Frontend entry: `sgf_report_widget.js`.
- Owner-facing central entry: `/admin/questions` with the read-only
  presentation adapter `admin_question_center.py` and the same shared widget
  mounted in its detail workspace.
- Human classification: existing V2-A review route at
  `/api/admin/sgf-answer-review/v2a/reviews`.
- Correction staging and validation: existing SGF Workbench routes
  `/api/admin/sgf-workbench/flag`,
  `/api/admin/sgf-workbench/items/<item_id>/stage`, and
  `/api/admin/sgf-workbench/items/<item_id>/validate`.
- Exact locator: existing
  `/api/admin/sgf-workbench/direct-context/<question_id>` with
  `record_index`; ambiguous legacy IDs fail closed.
- Direct apply remains a separate, gated Workbench capability and is not used
  by the inline save flow.

## Runtime surface census

| Surface | Runtime entry | Existing admin triage | Identity supplied to shared layer | Inline behavior | Notes |
| --- | --- | --- | --- | --- | --- |
| Main practice / Learn | `index.html` | Yes: shared report widget and Workbench actions | `question_id` + `record_index` from `/api/questions` / question loader | Full bar, board answer selection, side-to-play question edit, save-and-next | Ordinary next-question handler is allowed. |
| Guild quest | `index.html` | Yes: same shared widget | Same corpus question context | Full bar; no independent progression from inline save | Gameplay/Guild authority remains in the existing runtime. |
| Map / world battle | `index.html` | Yes: same shared widget | Same question context plus surface | Full bar and answer-board seam; save-and-next is disabled | Map Battle settlement remains server-owned. |
| Boss / Lord question flow | `index.html` | Yes: same shared widget | Same question context plus surface | Full bar and answer-board seam; save-and-next is disabled | Lord pass/retry authority remains server-owned. |
| Adventure answering | `index.html` | Yes: same shared widget | Same question context plus surface | Full bar and answer-board seam; save-and-next is disabled | Adventure progression is not changed by review UI. |
| Wrong-answer review | `mistakes.html` | Yes: existing report widget | `question_id` + unique `record_index` + content hash from `/api/mistakes` | Full bar, board answer selection, save-and-next to `nextQ()` | Duplicate legacy IDs fail closed at the exact-context endpoint. |
| Daily challenge | `daily_challenge.html` | Yes: existing report widget | `question_id` + unique `record_index` + content hash from daily endpoint | Full bar and board answer selection | No alternate daily-question authority is introduced. |
| Rating / placement test | `rating_test.html` | Yes: existing report widget | `question_id` + `record_index` + transform metadata from rating pool | Full bar with canonical move conversion | Display symmetry is converted before staging; rating scoring is unchanged. |
| Friend challenge / live social | `play.html`, `community.html` | Existing widget only | No canonical corpus question context in the live board | Bar remains hidden until a real corpus context is supplied | These pages do not invent an attachable question identity. |
| AI match | `bot.html` | No attachable corpus review context | None | Not admitted to inline corpus review | AI-match positions are outside the question-correction authority. |
| Central question management | `/admin/questions` | Yes: one Owner-facing entry over the existing authorities | Exact `question_id` + `record_index` + content hash; deep links are resolved through System C | Same quick controls, board preview, staged validation and save-next handoff | Primary daily Owner workflow; no new correction store. |
| Central Workbench / queue | `sgf_answer_review.html` and existing V2-A pages | Yes: authoritative workbench | Exact `record_index` + legacy ID + full-record hash | Existing board-first staged/direct workflow retained | Compatibility/advanced surface for bulk, history, rollback and details. |

## Fail-closed rules

1. The shared layer never derives an identity from board pixels or a legacy ID
   alone.
2. A missing, duplicate, stale, retired, or otherwise unresolved locator shows
   `這題目前無法安全修改`; reporting/flagging remains available where the
   existing surface supports it.
3. Inline edits stage and validate only. They do not mutate canonical question
   files or enable direct apply.
4. Lord, Map Battle, Guild, and Adventure gameplay completion and settlement
   authorities are not delegated to presentation or inline review state.

## Legacy reuse classification

| Existing capability | Classification |
| --- | --- |
| `sgf_report_widget.js` report context and admin triage | Shared UI component, extended in place |
| `sgf_admin_workbench.py` identity, report, stage, validation, audit | Reuses existing authority |
| `sgf_workbench_v2a.py` / V2-A routes | Reuses existing authority for `沒問題` / `稍後` |
| `sgf_admin_workbench_ux_v2.js` board/setup/direct gate | Reused as the central advanced path; no second direct-apply authority |
| `app.py` workbench routes | Thin adapter only for structured inline locator/content projection |
| Legacy `/api/save-question` and `/api/set-explanation` | Not reused; outside the safe correction authority |

`DUPLICATE_SYSTEM_CREATED=NO`.
`QUESTION_IDENTITY_MIGRATION=NO`.
`BACKEND_CORRECTION_AUTHORITY_REPLACED=NO`.
`UNIFIED_MANAGEMENT_ROUTE=/admin/questions`.
`SYSTEM_C_SOLE_WEB_CORRECTION_AUTHORITY=YES`.
