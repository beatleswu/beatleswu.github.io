# G076 R3-B: gated question exposure contract

Date: 2026-10-23. Worker: `g076-r3b-codex-security`.
Base HEAD: `138ef4a9fc0fc987065570b0af7817090dc8699d`.
Workspace: `D:\go-odyssey-g076-r3-codex-security-20261023`.

Stage result: implemented and locally tested; **ENFORCEMENT / PRODUCT ROLLOUT HOLD**.
`G076_ANSWER_PRIVACY_ENFORCED` remains default OFF, using the existing
`g076_question_privacy.privacy_enforced` parser (`1`, `true`, `on` enable it).
No environment/configuration setting was changed. OFF preserves legacy responses,
including their known answer exposure. This is not a claim of current site privacy.

## Source audit and treatment

| Surface | Finding / classification | Gate ON behavior |
| --- | --- | --- |
| GET `/api/mistakes` | Full solution SGF; even a corrected past mistake is a replayable practice question. Existing per-user and premium/free-content checks apply. | Board projection for accessible records; locked content remains empty; no new question fields or solution metadata. |
| GET `/api/daily-challenge/today` | Full solution SGF before submission. Existing attempt issuance and submit server verification are separate from display. | Board projection for both submitted and unsubmitted states; free-text `note` removed. Attempt identity/hash and authoritative source remain intact. |
| GET `/api/daily-challenge/history/<date_str>` | Premium and past-date checks, but no per-user settlement requirement. A question can be reused in another challenge/trial. Not a safe unrestricted solution archive. | Board projection, including past unanswered challenges; `note` removed. Premium/date checks unchanged. |
| GET `/api/daily-challenge/history` | No SGF, but challenge notes are free text. | `note` removed; history/statistics retained. |
| GET `/api/rating_test/resume/<sid>` | `_strip_question` returned transformed full solution SGF and transformed accepted moves. Authenticated sessions enforce owner matching; anonymous sessions intentionally use the SID as capability. | Shared serializer projects before geometric transformation and omits accepted moves. Token/transform/identity remain unchanged. |
| POST `/api/rating_test/start`, `/api/rating_test/answer` | Also send the next unanswered question using `_strip_question`. Returning the next question after settling the previous one is still pre-answer exposure. | Same shared projection. Grading/session writers unchanged. |
| GET `/api/grimoire/training/daily` | Registered `grimoire_api.py` Blueprint returns full solution SGF in `questions`. | Exact-path, GET-only successful-response projection in `app.py`; no Blueprint or persistence changes. |
| GET `/api/training/contaminated` | Registered Blueprint returns full solution SGF in `contaminated`; prior failure does not authorize future answers. | Same bounded response projection. Existing authorization/errors preserved. |
| GET `/api/question/<qid>` | Already has G076 board view and global gate at the base SHA. | Reused unchanged; its existing privacy tests included in regression. |
| GET `/api/questions`, `/api/training/daily` | Explicit metadata/queue summaries; no solution SGF/accepted move list in returned question entries. `/api/questions` uses an empty `katago_best_move`. | No changes. Distinguish `/api/training/daily` from the Blueprint `/api/grimoire/training/daily`. |
| Admin workbench/direct-context, manage/questions, alternative-report context, answer-review and question-management Blueprints | Admin-authorized editorial/answer review, not a player pre-answer contract. | Existing admin authorization and payloads unchanged. |
| GET `/api/rating_test/result/<sid>` and completed resume | Completed-session statistics / answer verdict summaries; result requires completed status and checks owner for identified users. No full solution question envelope. | No changes. |
| GET `/api/game-records/<record_id>/sgf`, `/api/profile/<username>/games/<record_id>/sgf` | Stored played-game SGF export; private export checks owner, profile export is intentionally public. Separate from question-bank display. | No changes; not claimed as confidential question storage or proof of question settlement. |

The audit inspected route bodies and question-content helpers in `app.py` and
registered question-serving Blueprints. No `katago_answer` field is emitted by
these player question envelopes; fixture records deliberately contain it to
check that projection does not introduce it. Existing metadata (including board
labels and display titles) is retained; arbitrary metadata editorial content is
not certified answer-free by this work. This is a bounded source audit, not a
live deployment/static-hosting or all-services security admission.

## Projection / failure contract

- Reuses `board_only_sgf`, preserving initial board/setup, side to play and board
  annotations. Removes SGF moves/variations/comments/analysis. Root move ambiguity,
  malformed SGF, unsupported size and multiple games fail closed.
- Accessible malformed content returns HTTP 422 with only
  `error` / `code` = `question_preview_unavailable`. No raw source, parser detail,
  or fallback full answer. A malformed list item rejects the entire response.
- ON payloads add `board_only: true`; Rating Trial does not return
  `accepted_moves`. Existing allowlists exclude comments/KataGo answers.
- Successful projections and projection failures use `Cache-Control: no-store`;
  the existing global API response policy additionally sets `private, no-store`.
- Projection never replaces the question object used by attempt issuance or
  server judgement. All eight trial transforms retain the same transform ID and
  token. No new DB writes, grading branch, or authentication policy was added.
- Some original GET handlers already create challenge/training cache state or
  ensure tables. The **projection** is read-only; the entire legacy GET is not
  claimed to be read-only. The test providers use synthetic cached/local data.

## Rollout blockers and replay caveats

`mistakes.html`, `daily_challenge.html`, and `rating_test.html` still traverse
solution-tree children to judge/advance moves locally. They were intentionally
not migrated here. Turning the gate on now removes that required input and does
not deliver playable student flows. Enabling it requires client migration and
verified server-owned step/reply judgement for each surface, including stale
token/attempt handling, retries, next-question responses, and settlement.

Daily Challenge already has submit-time server verification and Rating Trial has
server replay verification; these do not replace live client tree traversal.
This stage does not certify those legacy judges for all SGF semantics. In
particular, Rating Trial grading is computed before the existing session-owner /
stale-token admission checks; no attempt was made to reorder auth and grading in
this display-only worker. Anonymous trial SID capability behavior is retained.

Rating start/answer can persist session progression before serializing the next
question. If its projection is unavailable, the response fails closed after
that original operation; it does not roll back or promise exactly-once recovery.
This is another migration/recovery qualification requirement, not a reason to
return a solution. Tests cover shared serialization, resume owner rejection and
completed resume, not full PostgreSQL start/answer transactions.

Neither a past date, previous error, `correct_after`, nor today's submitted bit
unlocks a reusable solution under this gate. A future authorized solution-history
feature needs explicit settlement/reuse policy. Previously downloaded answers,
user-published game SGFs, and old browser caches cannot be revoked by projection.
No deploy, server configuration, production data, live browser play, iPad/Safari,
or Owner acceptance was performed or claimed.

## Validation receipts

Final command (PowerShell, existing local Python 3.12; no package installation):

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\beatl\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_g076_r3b_exposure.py tests/test_g076_answer_privacy_contract.py tests/test_g076_server_step_authority.py tests/test_g076_step_http_isolated.py tests/test_g076_step_ledger_sqlite.py tests/test_g076_step_concurrency.py -q -p no:cacheprovider --basetemp=artifacts/g076-r3b-pytest-final-tmp --junitxml=artifacts/g076-r3b/pytest.xml
```

Result: **175 passed in 12.67s** (101 new exposure tests, 74 selected existing
G076 tests). Earlier iterations: 90 exposure tests passed; then 164 combined
tests passed, before adding malformed-envelope/error preservation coverage.

The final suite executes actual extracted route/helper bodies, existing login
decorators, and the actual Grimoire route bodies through a local Flask test
client with in-memory SQLite. It avoids importing application startup and its
external integrations. Includes OFF/unknown flag compatibility, ON URL bypass
attempts, malformed/ambiguous/multiple-game SGF, cross-user ownership, premium
locks, prior corrected mistakes, submitted daily reuse, history bypass, all eight
trial transforms, immutable server inputs, authority errors, atomic list failure,
and unchanged Blueprint error status. Provider stubs are explicit in the tests.

`artifacts/g076-r3b/pytest.txt` and `pytest.xml` contain final test output.
`artifacts/g076-r3b/source-receipt.json` binds source SHA256 values and verifies
that `login_required`, `dc_submit`, `get_or_create_daily_challenge`,
`_rt_server_verify`, `rt_start`, `rt_answer`, `rt_resume`, and `rt_result` retain
exact source text from the base. It also verifies unchanged `index.html` bytes.
`git diff --check` passed. Code was syntax-parsed as part of every test fixture.

All edits are inside the authorized worker checkout. The initial untracked
`G076_CODEX_TASK_20261023.md` was preserved and excluded from the commit. No
credentials or remote service was accessed; no push/merge/deploy or primary
worktree change was performed. Local commit metadata is reported with handoff.
