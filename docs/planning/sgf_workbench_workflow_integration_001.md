# SGF Workbench workflow integration

This workflow is an evidence and handoff path only:

`report → review item → admin review → staged repair → validation → batch → READY_FOR_APPLY`

`READY_FOR_APPLY` is not an apply operation. Canonical SGF/question content remains owned by
the existing governed corpus and is not written by these operations.

| Table | Service operation | Lifecycle role | Transaction/audit boundary |
| --- | --- | --- | --- |
| `sgf_workbench_reports` | `capture_workbench_report` | Immutable player/admin/scan observation | Report insert and `REPORT_CAPTURED` audit are atomic |
| `sgf_workbench_review_items` | `list_workbench_items`, `get_workbench_item`, `resolve_workbench_item` | Aggregated review state (`OPEN`, `STAGED`, `STALE`, etc.) | Review transitions use the existing row lock, stale token, and audit |
| `sgf_workbench_staged_repairs` | `stage_workbench_repair`, `validate_staged_repair` | Proposed change plus canonical basis and dry-run result | Repair, review transition, validation evidence, and audit are savepoint-atomic |
| `sgf_workbench_batches` | `create_workbench_batch`, `mark_batch_ready_for_apply` | Deterministic handoff package (`STAGED` → `READY_FOR_APPLY`) | Batch, items, repair transitions, manifest update, and audit are atomic |
| `sgf_workbench_batch_items` | batch creation/inspection | Explicit staged-repair membership and order | Unique membership is inserted in the batch transaction |
| `sgf_workbench_audit` | repository audit sink | Append-only report → review → stage → validate → batch provenance | Required audit failure rolls back its enclosing mutation |
| `sgf_workbench_direct_versions` | existing Direct Apply version/rollback services | Separate version/snapshot authority for the already-gated Admin Play path | Not created by staging or READY_FOR_APPLY; Production Direct Apply remains OFF |

Validation is fail-closed for missing or changed content/record bases, malformed SGF, invalid
answer transitions, stale review state, and candidate conflicts. It records `PASS`, `FAIL`,
`STALE`, or `CONFLICT` evidence without mutating the canonical corpus. The batch route requires
`PASS` evidence and the ready gate rechecks the current basis before transitioning.
