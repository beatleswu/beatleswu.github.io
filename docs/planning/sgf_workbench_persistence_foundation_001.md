# SGF Workbench persistence foundation

This note records the bounded persistence authority for the existing Admin
Workbench. It does not make the seven tables authoritative for questions.json
or enable Direct Apply.

| table | repository/service operation | lifecycle role | transaction boundary | audit behavior |
| --- | --- | --- | --- | --- |
| `sgf_workbench_reports` | `capture_workbench_report` | immutable PLAYER_REPORT / ADMIN_PLAY / CORPUS_SCAN evidence | report insert plus semantic group rebuild | source evidence is preserved; downstream mutations are audited |
| `sgf_workbench_review_items` | `list_workbench_items`, `get_workbench_item`, `resolve_workbench_item` | `OPEN` to `STAGED`, `NEEDS_RESEARCH`, or `REJECTED` | locked state transition with optional expected `updated_at` | resolution and staging audit are atomic |
| `sgf_workbench_staged_repairs` | `stage_workbench_repair` | `STAGED` to `BATCHED` handoff state | repair insert plus review-item transition | required `STAGED_REPAIR` audit is in the same savepoint |
| `sgf_workbench_batches` | `create_workbench_batch` | deterministic repair/content-release handoff | batch, items, repair transitions, and audit | `BATCH_CREATED` is atomic with all batch rows |
| `sgf_workbench_batch_items` | `create_workbench_batch` | ordered membership of a batch | same batch transaction | covered by the parent batch audit |
| `sgf_workbench_audit` | `_audit` / `WorkbenchRepository.audit` | append-only mutation evidence | required audit failure rolls back its mutation | target, actor, action, detail, and timestamp are recorded |
| `sgf_workbench_direct_versions` | `apply_direct_question_edit`, `rollback_direct_question_edit` | snapshot/version/rollback history | version and audit are atomic; file is restored on failure | `DIRECT_APPLY` / `ROLLBACK` reference version identity |

The PostgreSQL schema remains governed by `migrations/sgf_admin_workbench_v1.py`.
The persistence layer validates that schema on PostgreSQL and only creates
SQLite fixture tables for tests. Canonical question content remains governed
by the existing corpus/content-release path.
