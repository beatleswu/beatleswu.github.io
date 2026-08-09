# SGF-ANSWER-REVIEW-QUEUE-001

Status: `READY_FOR_OWNER_VISUAL_REVIEW`

## Scope and safety boundary

This Sprint adds an authenticated, board-first Owner review and repair-staging
surface. It does not repair canonical puzzles. Every proposed answer change is
stored as an `OWNER_APPROVED_REPAIR_PROPOSAL` with canonicality
`STAGED_NOT_APPLIED`.

The implementation does not write SGF bytes, `questions.json`, accepted moves,
historical KataGo values, or player verdicts. KataGo is not run. Production was
not contacted. Content fingerprints are used only to deduplicate the review
surface; they do not create canonical puzzle identity.

Base and workspace:

- Base: `5114b76ba34560e76ec79fd3922cbeb731bd36b7`
- Branch: `codex/sgf-answer-review-queue-001`
- Worktree: `D:\go-website-sgf-answer-review-queue-001`
- Canonical identity: deferred; `IDENTITY_IMPLEMENTED=NO`

## Product surface

The admin-only route is:

`/admin/sgf-answer-review`

It uses the repository's existing `admin_required` session authorization. No
parallel login or public review endpoint was added.

The primary workflow is:

`看棋盤 -> 判斷 -> 點一下 -> 自動保存 -> 下一題`

The page provides:

- server-side dashboard counts and resume position;
- detector-order filters for pending/reviewed status, P0-P3, tenuki,
  duplicates, source issues, and multiple-solution review;
- a large board with current native answer `A`, historical precomputed answer
  `X`, side to move, priority, and short detector reasons;
- one-tap tenuki decisions, including `A 對，X 錯`;
- tap-board flows for replacing a primary answer or adding an equivalent
  answer, with a confirmation step;
- one-tap black/white-to-play proposals, source-position-includes-answer, and
  needs-source-reconstruction proposals;
- audited undo, previous-reviewed navigation, and editing of earlier staged
  proposals;
- a read-only `待套用修正` summary. No apply/batch button exists.

In iPad portrait, the four high-frequency review actions are fixed below the
board and legend. In iPad landscape and desktop, the board and scrollable
controls use a split layout. All important controls are at least 48 CSS pixels
high, and no interaction depends on hover.

## Detector-derived queue source

The bundled queue source is:

`review_data/sgf_answer_review_queue_v1.json`

Evidence identity:

- Detector manifest SHA-256:
  `ea0980a4f7d28b7b18d8596f4c607935ae63f62e00a42ce4e765fc483741a320`
- Review source SHA-256:
  `ccfb20ca81a4daaa83b7b172426c490a7c732287810521caedc5782a8052b51e`
- Exact puzzle snapshot SHA-256:
  `88da3e43b41f297dd24ad3ba7f87f831455867432b7a72f24a4835f6002954ff`
- Source records: 500
- Review groups: 452
- Duplicate groups: 29
- Records represented by duplicate groups: 77
- Largest duplicate group: 3 records

Detector signatures remain:

- Full 13,085 ranking:
  `e0177ab32c7c2888b51c4d0c54c7e3e58e9bd46ade1baf8504f6a3a1174eb501`
- Top-500 selection order:
  `ecd03c63d230749192fe36fb5b4aba7670d3eb07d82992428bf5aaa792aa11ed`
- `DETECTOR_RANKING_CHANGED=false`

The derived artifact includes only board preview stones, answer points,
structural/reason metadata, and `AUDIT_LOCATOR_ONLY` provenance. It contains no
full SGF or detector `content` field.

Reproduction command:

```powershell
python tools\build_sgf_answer_review_source.py `
  --detector-manifest D:\go-website-sgf-answer-suspect-detector-001-artifacts\owner-review-ux-a\top_suspects.json `
  --output review_data\sgf_answer_review_queue_v1.json
```

## Server-side persistence contract

Four additive staging tables are created through `init_db()`:

- `sgf_answer_review_states`
- `sgf_answer_review_progress`
- `sgf_answer_review_mutations`
- `sgf_answer_review_audit`

State is keyed by Owner account, exact source snapshot, and review-group content
fingerprint. Saves use a client mutation ID plus an expected revision. Replaying
the same mutation is idempotent; reusing an ID with different content or saving
against a stale revision fails closed with HTTP 409. Every save and undo records
before/after JSON in the audit table.

The browser adds an operation to account-and-snapshot-scoped `localStorage`
immediately before transmission. This entry is retry protection only. The
server remains authoritative. A failed save shows `尚未同步`, leaves the Owner
on the same board, and retries the same mutation after reconnect without
creating duplicate state or proposals.

## Proposal contract for a future governed batch

Supported staged proposal types are:

- `REPLACE_PRIMARY_ANSWER`
- `ADD_EQUIVALENT_SOLUTION`
- `REJECT_HISTORICAL_PRECOMPUTED_FALLBACK`
- `SET_SIDE_TO_MOVE`
- `SOURCE_POSITION_INCLUDES_ANSWER`
- `NEEDS_SOURCE_RECONSTRUCTION`

The server, rather than the browser, supplies Owner ID, timestamp, original
answers, exact snapshot and detector pack IDs, every linked legacy question ID,
and every `AUDIT_LOCATOR_ONLY`. A future separately authorized
`SGF-ANSWER-REPAIR-BATCH-001` can consume these records, but this Sprint does
not implement that consumer or any canonical mutation.

## Browser acceptance evidence

The final measured matrix used the real Flask route and a disposable local
SQLite review-state database:

| Viewport | Board width | Min touch height | Portrait quick actions | Board/legend overlap | Horizontal overflow |
| --- | ---: | ---: | --- | --- | --- |
| Desktop 1440x900 | 540px | 48px | n/a | none | none |
| iPad portrait 768x1024 | 575px | 48px | visible | none | none |
| iPad portrait 820x1180 | 699px | 48px | visible | none | none |
| iPad landscape 1024x768 | 408px | 48px | split controls | none | none |
| iPad landscape 1180x820 | 460px | 48px | split controls | none | none |

Interactive checks completed:

- A board tap outside edit mode was inert.
- Replace-answer edit mode mapped a board tap to `F14`, retained that candidate
  through portrait-to-landscape rotation, and saved a structured proposal.
- Reload restored the saved review and proposal from the server.
- Add-equivalent mapped a different board tap to `K10` and saved it without
  canonical mutation.
- Side-to-move, source-position-includes-answer, and audited undo all persisted.
- `A 對，X 錯` saved the exact global-tenuki decision and advanced one item.
- A two-record duplicate group appeared as one board and one review action.
- Two independent browser tabs showed identical account-scoped state after
  iPad-equivalent and desktop-equivalent updates in both directions.
- Simulated offline save showed `尚未同步`, did not advance, retained the same
  board, then safely synchronized that decision on reconnect.
- Browser console error/warning log was empty.

Local visual QA command:

```powershell
python tools\run_sgf_answer_review_queue_qa.py --port 8877
```

The harness binds only to `127.0.0.1`, sets a synthetic secret before importing
the application so `secret_key.txt` is not read, creates a disposable SQLite
state database, and prints a local Owner-login URL. It never contacts
Production.

## Known limitations and deferred work

- This queue covers the detector's current top-500 validation pack, not all
  13,085 suspects.
- Review grouping is intentionally not canonical identity.
- Player-report data remains whatever was safely present in the detector
  evidence; this Sprint does not fabricate or fetch Production report rows.
- Rank calibration remains deferred.
- No canonical repair batch, deploy, Production access, or E10 cinematic/audio
  work is included.

## Final assertions

```text
QUESTIONS_MUTATED=0
SGF_BYTES_MUTATED=0
QUESTIONS_JSON_MUTATED=0
ACCEPTED_MOVES_MUTATED=0
PLAYER_VERDICT_MUTATED=0
KATAGO_RUN=NONE
IDENTITY_IMPLEMENTED=NO
PRODUCTION_CONTACT=NONE
E10_CINEMATIC_TOUCHED=NO
RANK_CALIBRATION_FIX=DEFERRED
CANONICAL_REPAIR_BATCH_STARTED=NO
MERGE=NOT_AUTHORIZED
DEPLOY=NO
```
