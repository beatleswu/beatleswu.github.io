# P0 non-admin review toolbar authorization trace

## Authority

- Fresh `origin/master`: `ba31e8840eb6f90e2d000a41ceca570da944b815`
- Fresh tree: `77af1d1a2ade97079fe72a8349e7cd03f966bced`
- Isolated implementation commit: `c2023160497f5502fb361c997117c559c0ff9bb7`
- Product file changed: `sgf_report_widget.js`
- `app.py` changed: no

## DOM and visibility source

| Item | Evidence |
|---|---|
| Toolbar source | `sgf_report_widget.js` |
| DOM markers | `[data-sgf-inline-review-bar]`, `[data-sgf-inline-action]` |
| Creation function | `ensureHost()` (line 458) |
| Previous visibility function | `renderInlineReview()` (line 210) |
| Current visibility authority | `/api/auth/me` authoritative `logged_in` and `is_admin`, followed by `/api/admin/sgf-workbench/bootstrap` security evidence |
| Current admin mount | `mountAdminControls()` (line 444), called only after the two checks in `loadAdminCapabilities()` (line 552) |

The six labels are the five action buttons inside the inline review bar:
`CORRECT`, `REPLACE_ANSWER`, `EDIT_QUESTION`, `ADD_ALTERNATIVE_CORRECT_MOVE`, and
`UNSURE`; `快速檢查` is their title. The player report control remains separate.

## Handler and server boundary

| Control/action | Client handler | Server endpoint | Method | Persistent domain | Server guard |
|---|---|---|---|---|---|
| 沒問題 / 稍後 | `beginInlineAction()` → `classifyInline()` | `/api/admin/sgf-answer-review/v2a/reviews` | POST | reviewer/audit state only; `canonical_questions_mutated=false` | `@admin_required`, CSRF/origin/throttle |
| 改答案 / 改題目 / 補正解 | `beginInlineAction()` → `commitInlineEdit()` | `/api/admin/sgf-workbench/flag` → `/items/<id>/stage` → `/validate` | POST | staged review/correction workflow | `@admin_required` and workbench guards |
| 修正此題 | `openDirectWorkbench()` | `/admin/questions?...` | navigation | admin workbench | `@admin_required` |
| 補正解 direct path | `directApplyLastMove()` | `/api/admin/sgf-workbench/direct-context/<id>` → `/direct-apply` | GET/POST | explicit admin direct-apply path | `@admin_required` and direct-apply guards |
| staged retest | `retestStaged()` | `/api/admin/sgf-workbench/items/<id>/retest` | POST | staged retest only | `@admin_required` |

`app.py:6223-6235` returns API 401 for anonymous requests and API 403 when
`session['is_admin']` is false. `app.py:9955-10019` re-reads `users.is_admin`
for `/api/auth/me`; the client does not invent an identity or permission.
The V2-A review/progress routes are also `@admin_required` in
`sgf_workbench_v2a_routes.py:326-364`.

## Decision

The isolated Flask test client returned 403 for every privileged route tested
with `user_id=991111, is_admin=False`, and 401 for anonymous bootstrap. No
non-admin persistent mutation was found or exercised in Production.

`NONADMIN_PRIVILEGED_MUTATION_REJECTED=YES`

`CLASSIFICATION=UI_AUTHORIZATION_VISIBILITY_LEAK`

