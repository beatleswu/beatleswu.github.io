"""Unified SGF Admin Workbench persistence and deterministic handoff helpers.

This module is deliberately independent of Flask and the question runtime.  It
adds an evidence projection over the existing player-report and review-queue
tables.  Reports are untrusted observations; only an authenticated admin can
create a staged repair, and staged repairs never write the canonical corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import base64
import gzip
from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import count
from typing import Any, Iterable


WORKBENCH_SOURCES = (
    "PLAYER_REPORT",
    "ADMIN_PLAY",
    "CORPUS_SCAN",
)
WORKBENCH_STATUSES = (
    "OPEN",
    "STAGED",
    "NEEDS_RESEARCH",
    "REJECTED",
    "PUBLISHED",
    "STALE",
)
WORKBENCH_ACTIONS = (
    "ADD_ALTERNATIVE_CORRECT_MOVE",
    "REMOVE_INCORRECT_ACCEPTED_MOVE",
    "REPLACE_ANSWER",
    "DISABLE_BROKEN_QUESTION",
    "NEEDS_RESEARCH",
)
WORKBENCH_REPORT_REASONS = (
    "ALTERNATIVE_CORRECT_MOVE",
    "SYSTEM_ANSWER_INCORRECT",
    "QUESTION_CONTENT_PROBLEM",
    "BOARD_OR_DISPLAY_PROBLEM",
    "OTHER",
)

DIRECT_APPLY_SOURCE = "ADMIN_PLAY_DIRECT"
DIRECT_APPLY_ACTIONS = (
    "ADD_ALTERNATIVE_CORRECT_MOVE",
    "REMOVE_INCORRECT_ACCEPTED_MOVE",
    "REPLACE_ANSWER",
    "EDIT_BOARD_SETUP",
    "CHANGE_SIDE_TO_PLAY",
    "DISABLE_BROKEN_QUESTION",
    "REBUILD_QUESTION",
)

# These records are governed by the existing SGF quality contracts.  They are
# deliberately kept as policy data at the mutation boundary rather than in
# the UI, so a caller cannot promote them by bypassing the browser.
GF003_QUESTION_IDS = frozenset({431})
HISTORICAL_FALLBACK_CONFLICT_QUESTION_IDS = frozenset({15436, 15388, 65095})
_DIRECT_SNAPSHOT_MARKER = "sgf_direct_snapshot_v1"


def _is_sqlite(conn) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _id_type(conn) -> str:
    return "INTEGER PRIMARY KEY AUTOINCREMENT" if _is_sqlite(conn) else "BIGSERIAL PRIMARY KEY"


def _now(value: str | None = None) -> str:
    # Workbench optimistic concurrency uses ``updated_at`` as its existing
    # version token.  Preserve caller-supplied historical timestamps, but keep
    # generated tokens sub-second precise so two admin writes in one second do
    # not become an accidental last-write-wins operation.
    return value or datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _sha256(value: bytes | str) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def canonical_file_sha256(path: str) -> str:
    """Return the byte hash of the canonical JSON file used by Direct Apply."""
    with open(path, "rb") as handle:
        return _sha256(handle.read())


def direct_record_hash(record: Any) -> str:
    """Hash one question record independent of JSON whitespace/key order."""
    return _sha256(_json(record if isinstance(record, dict) else {}))


def _direct_atomic_write(path: str, payload: bytes) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, temp_path = tempfile.mkstemp(prefix="questions-direct-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


@contextmanager
def _canonical_mutation_lock(path: str):
    """Serialize all writers for one canonical file across operation IDs.

    PostgreSQL advisory locking protects processes sharing the Workbench DB;
    this sidecar lock also protects a shared content volume and SQLite/local
    acceptance runs.  The sidecar is intentionally not the corpus itself.
    """
    # Keep the lock marker outside the canonical-content directory so a
    # request cannot leave an untracked sibling beside questions.json.  The
    # absolute path digest makes all local processes targeting the same file
    # share one lock while different acceptance fixtures remain independent.
    lock_name = f"go-odyssey-direct-apply-{_sha256(os.path.abspath(path))[:32]}.lock"
    lock_path = os.path.join(tempfile.gettempdir(), lock_name)
    handle = open(lock_path, "a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _snapshot_payload(record: dict, raw_bytes: bytes) -> dict:
    """Store the old record plus exact whole-file bytes without a new column."""
    compressed = gzip.compress(raw_bytes, compresslevel=6, mtime=0)
    return {
        "_snapshot_marker": _DIRECT_SNAPSHOT_MARKER,
        "record": record,
        "canonical_sha256": _sha256(raw_bytes),
        "canonical_bytes_gzip_b64": base64.b64encode(compressed).decode("ascii"),
    }


def _unwrap_snapshot(value: Any) -> tuple[dict, bytes | None, str | None]:
    """Read new snapshot envelopes and retain compatibility with old rows."""
    if not isinstance(value, dict) or value.get("_snapshot_marker") != _DIRECT_SNAPSHOT_MARKER:
        return value if isinstance(value, dict) else {}, None, None
    record = value.get("record")
    encoded = value.get("canonical_bytes_gzip_b64")
    try:
        raw = gzip.decompress(base64.b64decode(str(encoded), validate=True))
    except (TypeError, ValueError, OSError):
        raw = None
    return record if isinstance(record, dict) else {}, raw, str(value.get("canonical_sha256") or "") or None


def _direct_load_questions(path: str) -> tuple[bytes, list[dict]]:
    with open(path, "rb") as handle:
        raw = handle.read()
    records = json.loads(raw.decode("utf-8"))
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError("questions_json_must_be_list_of_objects")
    return raw, records


def validate_direct_record(record: Any, *, parse_sgf_fn=None) -> dict:
    """Fail-closed structural validation for one proposed question record."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return {"ok": False, "errors": ["record_not_object"]}
    if not isinstance(record.get("id"), int) or int(record["id"]) <= 0:
        errors.append("question_identity_invalid")
    content = str(record.get("content") or record.get("sgf") or "")
    if not content.strip():
        errors.append("sgf_content_missing")
    elif parse_sgf_fn is not None:
        try:
            parse_sgf_fn(content)
        except Exception:
            errors.append("sgf_not_parseable")
    accepted = record.get("accepted_moves")
    if not isinstance(accepted, list) or not accepted:
        errors.append("empty_answer_set")
    seen: set[tuple[int, int]] = set()
    for move in accepted if isinstance(accepted, list) else []:
        normalized = _normalize_move(move)
        if normalized is None or not (0 <= normalized["x"] < 19 and 0 <= normalized["y"] < 19):
            errors.append("accepted_move_invalid")
            continue
        key = (normalized["x"], normalized["y"])
        if key in seen:
            errors.append("duplicate_accepted_move")
        seen.add(key)
    if "enabled" in record and not isinstance(record.get("enabled"), bool):
        errors.append("enabled_invalid")
    return {"ok": not errors, "errors": errors}


def _row_dict(row) -> dict:
    if row is None:
        return {}
    try:
        return dict(row)
    except (TypeError, ValueError):
        return {key: row[key] for key in row.keys()}


class WorkbenchPersistenceError(ValueError):
    """Base error for a Workbench state change rejected by the repository."""


class InvalidWorkbenchState(WorkbenchPersistenceError):
    """The requested lifecycle transition is not allowed."""


class StaleWorkbenchState(WorkbenchPersistenceError):
    """The caller attempted to write from an obsolete review-item version."""


class DirectApplyPolicyError(WorkbenchPersistenceError):
    """The governed SGF policy refuses a canonical direct mutation."""


class DirectApplyRetestFailed(WorkbenchPersistenceError):
    """The mandatory same-question retest failed after a file write."""

    def __init__(self, result: Any, *, before_sha256: str, after_sha256: str):
        super().__init__("direct_retest_failed")
        self.result = result
        self.before_sha256 = before_sha256
        self.after_sha256 = after_sha256


class DirectApplyRecoveryError(WorkbenchPersistenceError):
    """The canonical bytes could not be restored after a failed mutation."""


def direct_apply_policy_check(current: dict, proposed: dict) -> None:
    """Reject locked or unresolved authority before any canonical write."""
    try:
        question_id = int(current.get("id"))
    except (TypeError, ValueError):
        question_id = None
    source = str(current.get("source") or current.get("fixture") or "").strip().lower()
    if question_id in GF003_QUESTION_IDS or source in {"fixture431", "gf003", "gf-003"}:
        raise DirectApplyPolicyError("gf003_direct_apply_denied")

    # The known historical-conflict class is intentionally hard blocked until
    # an explicit governed resolution exists.  A non-empty fallback remains
    # part of effective runtime authority; without a resolution marker, any
    # mutation (including disable/setup metadata) must fail closed.
    fallback = str(current.get("katago_best_move") or "").strip()
    if question_id in HISTORICAL_FALLBACK_CONFLICT_QUESTION_IDS or (fallback and proposed != current):
        raise DirectApplyPolicyError("historical_fallback_conflict")


def _retest_result_ok(result: Any) -> bool:
    if result is True:
        return True
    if isinstance(result, dict):
        return result.get("ok") is True or result.get("passed") is True
    return False


_SAVEPOINTS = count(1)


class WorkbenchRepository:
    """Small transaction-aware repository facade for the seven Workbench tables.

    Routes continue to use the existing module-level service functions, while
    all governed multi-table writes use this facade for savepoints, row locks,
    and audit insertion.  It never owns canonical question content and never
    enables Direct Apply.
    """

    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def atomic(self, label: str):
        """Make one logical Workbench operation atomic inside the caller txn."""
        safe_label = "".join(ch if ch.isalnum() else "_" for ch in str(label))[:24] or "operation"
        name = f"sgf_wb_{safe_label}_{next(_SAVEPOINTS)}"
        self.conn.execute(f"SAVEPOINT {name}")
        try:
            yield
        except BaseException:
            try:
                self.conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
                self.conn.execute(f"RELEASE SAVEPOINT {name}")
            except Exception:
                # The caller's connection context remains the final rollback
                # authority if the database has already entered a failed txn.
                try:
                    self.conn.rollback()
                except Exception:
                    pass
            raise
        else:
            self.conn.execute(f"RELEASE SAVEPOINT {name}")

    def lock_review_item(self, item_id: int):
        sql = "SELECT * FROM sgf_workbench_review_items WHERE id=?"
        if not _is_sqlite(self.conn):
            sql += " FOR UPDATE"
        return self.conn.execute(sql, (int(item_id),)).fetchone()

    def lock_staged_repairs(self):
        sql = """SELECT * FROM sgf_workbench_staged_repairs
                  WHERE status='STAGED' ORDER BY review_item_id, id"""
        if not _is_sqlite(self.conn):
            sql += " FOR UPDATE"
        return self.conn.execute(sql).fetchall()

    def lock_staged_repair(self, repair_id: int):
        sql = "SELECT * FROM sgf_workbench_staged_repairs WHERE id=?"
        if not _is_sqlite(self.conn):
            sql += " FOR UPDATE"
        return self.conn.execute(sql, (int(repair_id),)).fetchone()

    def lock_batch(self, batch_id: int):
        sql = "SELECT * FROM sgf_workbench_batches WHERE id=?"
        if not _is_sqlite(self.conn):
            sql += " FOR UPDATE"
        return self.conn.execute(sql, (int(batch_id),)).fetchone()

    def lock_direct_operation(self, operation_id: str, question_id: int) -> None:
        """Serialize retries for one direct operation/question on PostgreSQL."""
        if _is_sqlite(self.conn):
            return
        digest = hashlib.sha256(f"{operation_id}:{int(question_id)}".encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], "big", signed=True)
        self.conn.execute("SELECT pg_advisory_xact_lock(?)", (lock_key,)).fetchone()

    def lock_canonical_source(self, questions_path: str) -> None:
        """Serialize all Direct Apply writers for one canonical source.

        The operation-id lock above only deduplicates retries of one request.
        This second lock is deliberately path-scoped so distinct operation IDs
        cannot race through a read/modify/write cycle.
        """
        if _is_sqlite(self.conn):
            return
        digest = hashlib.sha256(os.path.abspath(questions_path).encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], "big", signed=True)
        self.conn.execute("SELECT pg_advisory_xact_lock(?)", (lock_key,)).fetchone()

    def audit(self, target_type: str, target_id: int | None, actor_id: int | None,
              action: str, detail: Any, now: str) -> None:
        _audit(self.conn, target_type, target_id, actor_id, action, detail, now)

    def schema_status(self) -> dict:
        """Return the governed seven-table schema status without creating it."""
        if _is_sqlite(self.conn):
            return {"schema_version": "sqlite-test", "valid": True, "missing": []}
        from migrations.sgf_admin_workbench_v1 import validate_schema

        return validate_schema(self.conn)

    def require_schema(self) -> dict:
        result = self.schema_status()
        if result.get("missing"):
            raise RuntimeError("sgf_workbench_schema_missing:" + ",".join(result["missing"]))
        return result

    def staged_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM sgf_workbench_staged_repairs "
            "WHERE status IN ('STAGED','BATCHED')"
        ).fetchone()
        return int(row["n"] if isinstance(row, dict) or hasattr(row, "keys") else row[0])

    def list_batches(self, limit: int = 100) -> list[dict]:
        bounded = max(1, min(int(limit), 500))
        rows = self.conn.execute(
            "SELECT id,batch_key,status,manifest_sha256,staged_count,created_at "
            "FROM sgf_workbench_batches ORDER BY id DESC LIMIT ?", (bounded,)
        ).fetchall()
        return [_row_dict(row) for row in rows]


def workbench_persistence_map() -> dict[str, dict[str, str]]:
    """Concise authority map used by the review artifact and diagnostics."""
    return {
        "reports": {
            "table": "sgf_workbench_reports",
            "operation": "capture_workbench_report",
            "lifecycle": "immutable PLAYER_REPORT/ADMIN_PLAY/CORPUS_SCAN evidence",
            "transaction": "report insert + semantic group rebuild",
            "audit": "source evidence remains immutable; review mutations are audited",
        },
        "review_items": {
            "table": "sgf_workbench_review_items",
            "operation": "list_workbench_items/get_workbench_item/resolve_workbench_item",
            "lifecycle": "OPEN -> STAGED/NEEDS_RESEARCH/REJECTED (published is terminal)",
            "transaction": "locked state transition with stale check",
            "audit": "resolution and staging audit rows are atomic",
        },
        "staged_repairs": {
            "table": "sgf_workbench_staged_repairs",
            "operation": "stage_workbench_repair/validate_staged_repair",
            "lifecycle": "STAGED -> BATCHED; validation evidence stays in provenance",
            "transaction": "repair insert + review-item transition",
            "audit": "STAGED_REPAIR and VALIDATION audit are in the same transaction",
        },
        "batches": {
            "table": "sgf_workbench_batches",
            "operation": "create_workbench_batch/mark_batch_ready_for_apply",
            "lifecycle": "STAGED -> READY_FOR_APPLY; no canonical apply",
            "transaction": "batch + items + repair transitions",
            "audit": "BATCH_CREATED and READY_FOR_APPLY are atomic with validation evidence",
        },
        "batch_items": {
            "table": "sgf_workbench_batch_items",
            "operation": "create_workbench_batch",
            "lifecycle": "ordered membership of one deterministic batch",
            "transaction": "same batch transaction",
            "audit": "covered by parent batch audit",
        },
        "audit": {
            "table": "sgf_workbench_audit",
            "operation": "_audit/WorkbenchRepository.audit",
            "lifecycle": "append-only mutation evidence",
            "transaction": "mutation fails if required audit insert fails",
            "audit": "self-describing target/action/detail record",
        },
        "direct_versions": {
            "table": "sgf_workbench_direct_versions",
            "operation": "apply_direct_question_edit/rollback_direct_question_edit",
            "lifecycle": "snapshot -> validate -> version/audit -> gated apply",
            "transaction": "version + audit are atomic; file is restored on failure",
            "audit": "DIRECT_APPLY/ROLLBACK audit references version identity",
        },
    }


def ensure_sgf_workbench_tables(conn) -> None:
    """Keep SQLite fixtures convenient and fail closed on PostgreSQL drift.

    PostgreSQL schema authority is the already-reviewed PR332 migration.  The
    application must not silently create a partial/unknown Production shape at
    request time; missing or mismatched tables are an operator-visible error.
    """
    if not _is_sqlite(conn):
        from migrations.sgf_admin_workbench_v1 import SchemaMismatch, validate_schema

        status = validate_schema(conn)
        if status.get("missing"):
            raise SchemaMismatch("workbench schema missing: " + ",".join(status["missing"]))
        return
    identifier = _id_type(conn)
    conn.execute(f"""CREATE TABLE IF NOT EXISTS sgf_workbench_reports (
        id {identifier},
        source TEXT NOT NULL,
        legacy_report_type TEXT,
        legacy_report_id BIGINT,
        reporter_id BIGINT,
        question_id BIGINT NOT NULL,
        record_index BIGINT,
        issue_type TEXT NOT NULL,
        candidate_move_json TEXT,
        observed_system_verdict TEXT,
        gameplay_surface TEXT,
        sgf_identity TEXT,
        node_identity TEXT,
        position_identity TEXT NOT NULL,
        board_state_json TEXT,
        comment TEXT NOT NULL DEFAULT '',
        question_content_sha256 TEXT,
        source_provenance_json TEXT NOT NULL DEFAULT '{{}}',
        external_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgw_reports_group ON sgf_workbench_reports(question_id, position_identity, issue_type)")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS sgf_workbench_review_items (
        id {identifier},
        group_key TEXT NOT NULL UNIQUE,
        question_id BIGINT NOT NULL,
        record_index BIGINT,
        issue_type TEXT NOT NULL,
        candidate_move_json TEXT,
        position_identity TEXT NOT NULL,
        source_types_json TEXT NOT NULL,
        report_count BIGINT NOT NULL DEFAULT 0,
        gameplay_surfaces_json TEXT NOT NULL DEFAULT '[]',
        first_report_at TEXT NOT NULL,
        last_report_at TEXT NOT NULL,
        authority_json TEXT NOT NULL DEFAULT '{{}}',
        provenance_json TEXT NOT NULL DEFAULT '{{}}',
        status TEXT NOT NULL DEFAULT 'OPEN',
        stale_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgw_items_status ON sgf_workbench_review_items(status, updated_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgw_items_source ON sgf_workbench_review_items(question_id, issue_type)")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS sgf_workbench_staged_repairs (
        id {identifier},
        review_item_id BIGINT NOT NULL,
        reviewer_id BIGINT NOT NULL,
        action TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        original_state_json TEXT NOT NULL,
        proposed_state_json TEXT NOT NULL,
        candidate_move_json TEXT,
        source_provenance_json TEXT NOT NULL DEFAULT '{{}}',
        baseline_sha256 TEXT,
        mutation_key TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'STAGED',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgw_repairs_item ON sgf_workbench_staged_repairs(review_item_id, status)")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS sgf_workbench_batches (
        id {identifier},
        batch_key TEXT NOT NULL UNIQUE,
        created_by BIGINT NOT NULL,
        status TEXT NOT NULL DEFAULT 'STAGED',
        manifest_json TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL,
        staged_count BIGINT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS sgf_workbench_batch_items (
        id {identifier},
        batch_id BIGINT NOT NULL,
        staged_repair_id BIGINT NOT NULL,
        order_index BIGINT NOT NULL,
        UNIQUE(batch_id, staged_repair_id)
    )""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS sgf_workbench_audit (
        id {identifier},
        target_type TEXT NOT NULL,
        target_id BIGINT,
        actor_id BIGINT,
        action TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgw_audit_target ON sgf_workbench_audit(target_type, target_id, created_at DESC)")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS sgf_workbench_direct_versions (
        id {identifier},
        question_id BIGINT NOT NULL,
        record_index BIGINT NOT NULL,
        predecessor_hash TEXT NOT NULL,
        new_hash TEXT NOT NULL,
        predecessor_version TEXT NOT NULL,
        new_version TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE,
        action_type TEXT NOT NULL,
        actor_id BIGINT NOT NULL,
        old_record_json TEXT NOT NULL,
        new_record_json TEXT NOT NULL,
        validation_result_json TEXT NOT NULL,
        rollback_reference BIGINT,
        source TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'APPLIED',
        created_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgw_direct_versions_question ON sgf_workbench_direct_versions(question_id, record_index, id DESC)")
    # V2-A human review is an independent, additive lifecycle.  SQLite test
    # fixtures install it locally; PostgreSQL is created only by its governed
    # migrations/sgf_human_review_v2a.py artifact (never at request time).
    conn.execute("""CREATE TABLE IF NOT EXISTS sgf_human_review_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reviewer_id BIGINT NOT NULL,
        record_index BIGINT NOT NULL,
        legacy_question_id TEXT NOT NULL,
        reviewed_record_sha256 TEXT NOT NULL,
        classification TEXT NOT NULL CHECK (classification IN
            ('CORRECT','WRONG_ROOT','MISSING_ANSWER','MISSING_VARIATION','SPECIAL','UNSURE')),
        reviewed_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(reviewer_id, record_index, legacy_question_id, reviewed_record_sha256)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgfh_current_locator ON sgf_human_review_state(reviewer_id, record_index, legacy_question_id, updated_at DESC)")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgf_human_review_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reviewer_id BIGINT NOT NULL,
        snapshot_sha256 TEXT NOT NULL,
        record_index BIGINT NOT NULL,
        legacy_question_id TEXT NOT NULL,
        record_sha256 TEXT NOT NULL,
        revision BIGINT NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        UNIQUE(reviewer_id, snapshot_sha256)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgfh_progress_locator ON sgf_human_review_progress(reviewer_id, record_index, updated_at DESC)")


def _normalize_move(move: Any) -> dict | None:
    if not isinstance(move, dict):
        return None
    try:
        x, y = int(move.get("x")), int(move.get("y"))
    except (TypeError, ValueError):
        return None
    result = {"x": x, "y": y}
    if move.get("color") in ("B", "W"):
        result["color"] = move["color"]
    return result


def _serialize_direct_version(row: Any) -> dict:
    result = _row_dict(row)
    for key in ("old_record_json", "new_record_json", "validation_result_json"):
        target = key.removesuffix("_json")
        result[target] = _loads(result.pop(key, None), {})
    result["old_record"], _raw_snapshot, snapshot_sha = _unwrap_snapshot(result["old_record"])
    if snapshot_sha:
        result["canonical_snapshot_sha256"] = snapshot_sha
    return result


def get_direct_version(conn, version_id: int) -> dict | None:
    ensure_sgf_workbench_tables(conn)
    row = conn.execute("SELECT * FROM sgf_workbench_direct_versions WHERE id=?", (int(version_id),)).fetchone()
    return _serialize_direct_version(row) if row else None


def list_direct_versions(conn, *, question_id: int, record_index: int | None = None, limit: int = 50) -> list[dict]:
    ensure_sgf_workbench_tables(conn)
    bounded = max(1, min(int(limit), 100))
    if record_index is None:
        rows = conn.execute(
            "SELECT * FROM sgf_workbench_direct_versions WHERE question_id=? ORDER BY id DESC LIMIT ?",
            (int(question_id), bounded),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sgf_workbench_direct_versions WHERE question_id=? AND record_index=? ORDER BY id DESC LIMIT ?",
            (int(question_id), int(record_index), bounded),
        ).fetchall()
    return [_serialize_direct_version(row) for row in rows]


def apply_direct_question_edit(conn, *, questions_path: str, actor_id: int,
                               question_id: int, record_index: int,
                               expected_predecessor_hash: str,
                               expected_canonical_sha256: str,
                               action_type: str, proposed_record: dict,
                               operation_id: str, retest_fn,
                               parse_sgf_fn=None,
                               now: str | None = None) -> dict:
    """Apply one Admin Play edit only after a mandatory same-question retest.

    The canonical file lock and the path-scoped PostgreSQL advisory lock are
    both held across the read/verify/write/version/audit sequence.  This makes
    the predecessor and whole-file SHA a real CAS boundary for distinct
    operation IDs, not merely an idempotency check for one retry.
    """
    ensure_sgf_workbench_tables(conn)
    action = str(action_type or "").strip().upper()
    if action not in DIRECT_APPLY_ACTIONS or action == "REBUILD_QUESTION":
        raise ValueError("direct_action_not_supported")
    operation = str(operation_id or "").strip()
    if not operation or len(operation) > 180:
        raise ValueError("operation_id_required")
    expected = str(expected_predecessor_hash or "").strip().lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise ValueError("predecessor_hash_required")
    expected_source = str(expected_canonical_sha256 or "").strip().lower()
    if len(expected_source) != 64 or any(ch not in "0123456789abcdef" for ch in expected_source):
        raise ValueError("canonical_basis_sha256_required")
    if not callable(retest_fn):
        raise ValueError("retest_required")

    repo = WorkbenchRepository(conn)
    with _canonical_mutation_lock(questions_path):
        repo.lock_canonical_source(questions_path)
        repo.lock_direct_operation(operation, int(question_id))
        existing = conn.execute(
            "SELECT * FROM sgf_workbench_direct_versions WHERE operation_id=?", (operation,)
        ).fetchone()
        if existing:
            result = _serialize_direct_version(existing)
            result["duplicate"] = True
            return result

        raw_before, records = _direct_load_questions(questions_path)
        canonical_before_sha256 = _sha256(raw_before)
        if canonical_before_sha256 != expected_source:
            raise ValueError("stale_canonical_basis")
        record_count_before = len(records)
        matches = [(idx, row) for idx, row in enumerate(records) if row.get("id") == int(question_id)]
        if len(matches) != 1:
            raise LookupError("question_identity_not_unique")
        actual_index, old_record = matches[0]
        if int(record_index) != actual_index:
            raise ValueError("record_index_mismatch")
        predecessor_hash = direct_record_hash(old_record)
        if predecessor_hash != expected:
            raise ValueError("stale_predecessor")
        if not isinstance(proposed_record, dict) or int(proposed_record.get("id", 0)) != int(question_id):
            raise ValueError("question_identity_changed")
        proposed = json.loads(_json(proposed_record))
        direct_apply_policy_check(old_record, proposed)
        validation = validate_direct_record(proposed, parse_sgf_fn=parse_sgf_fn)
        if not validation["ok"]:
            raise ValueError(";".join(validation["errors"]))
        if len(records) != record_count_before:
            raise ValueError("record_count_changed")
        new_hash = direct_record_hash(proposed)
        if new_hash == predecessor_hash:
            raise ValueError("no_change")
        records[actual_index] = proposed
        raw_after = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        canonical_after_sha256 = _sha256(raw_after)
        validation["canonical_before_sha256"] = canonical_before_sha256
        validation["canonical_after_sha256"] = canonical_after_sha256

        _direct_atomic_write(questions_path, raw_after)
        try:
            try:
                retest_result = retest_fn(proposed)
            except Exception as error:
                retest_result = {"ok": False, "error": "retest_exception", "type": type(error).__name__}
            if not _retest_result_ok(retest_result):
                raise DirectApplyRetestFailed(
                    retest_result,
                    before_sha256=canonical_before_sha256,
                    after_sha256=canonical_after_sha256,
                )
            validation["retest"] = retest_result if isinstance(retest_result, dict) else {"ok": True}
            timestamp = _now(now)
            predecessor_version = f"{predecessor_hash[:16]}:{actual_index}"
            new_version = f"{new_hash[:16]}:{actual_index}"
            with repo.atomic("direct_version"):
                row = conn.execute("""INSERT INTO sgf_workbench_direct_versions
                    (question_id, record_index, predecessor_hash, new_hash,
                     predecessor_version, new_version, operation_id, action_type,
                     actor_id, old_record_json, new_record_json, validation_result_json,
                     rollback_reference, source, status, created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *""", (
                    int(question_id), actual_index, predecessor_hash, new_hash,
                    predecessor_version, new_version, operation, action, int(actor_id),
                    _json(_snapshot_payload(old_record, raw_before)), _json(proposed),
                    _json(validation), None, DIRECT_APPLY_SOURCE, "APPLIED", timestamp,
                )).fetchone()
                version = _serialize_direct_version(row)
                repo.audit("sgf_workbench_direct_version", version["id"], actor_id,
                           "DIRECT_APPLY", {
                               "question_id": int(question_id), "action_type": action,
                               "predecessor_hash": predecessor_hash, "new_hash": new_hash,
                               "canonical_before_sha256": canonical_before_sha256,
                               "canonical_after_sha256": canonical_after_sha256,
                               "operation_id": operation, "validation": validation,
                               "source": DIRECT_APPLY_SOURCE,
                           }, timestamp)
            # Direct Apply is a transaction root: do not return APPLIED while
            # the version/audit rows are still waiting for an outer request
            # context to commit.  If this commit fails, the exception path
            # below restores the exact canonical bytes.
            conn.commit()
            return version
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                _direct_atomic_write(questions_path, raw_before)
            except Exception as restore_error:
                raise DirectApplyRecoveryError("direct_apply_restore_failed") from restore_error
            raise


def rollback_direct_question_edit(conn, *, questions_path: str, actor_id: int,
                                  version_id: int, operation_id: str,
                                  parse_sgf_fn=None, now: str | None = None) -> dict:
    ensure_sgf_workbench_tables(conn)
    raw_version = conn.execute(
        "SELECT * FROM sgf_workbench_direct_versions WHERE id=?", (int(version_id),)
    ).fetchone()
    original = _serialize_direct_version(raw_version) if raw_version else None
    if not original or not raw_version:
        raise LookupError("direct_version_not_found")
    operation = str(operation_id or "").strip()
    if not operation:
        raise ValueError("operation_id_required")
    stored_old = _loads(raw_version["old_record_json"], {})
    restored, exact_snapshot, snapshot_sha = _unwrap_snapshot(stored_old)
    if exact_snapshot is None or not snapshot_sha:
        raise ValueError("rollback_snapshot_missing")
    if _sha256(exact_snapshot) != str(snapshot_sha).lower():
        raise ValueError("rollback_snapshot_invalid")
    expected_after = (original.get("validation_result") or {}).get("canonical_after_sha256")
    if not expected_after:
        raise ValueError("rollback_snapshot_metadata_missing")

    repo = WorkbenchRepository(conn)
    with _canonical_mutation_lock(questions_path):
        repo.lock_canonical_source(questions_path)
        repo.lock_direct_operation(operation, int(original["question_id"]))
        existing = conn.execute(
            "SELECT * FROM sgf_workbench_direct_versions WHERE operation_id=?", (operation,)
        ).fetchone()
        if existing:
            result = _serialize_direct_version(existing)
            result["duplicate"] = True
            return result
        raw_before, records = _direct_load_questions(questions_path)
        if _sha256(raw_before) != str(expected_after).lower():
            raise ValueError("rollback_stale_canonical_basis")
        matches = [(idx, row) for idx, row in enumerate(records) if row.get("id") == int(original["question_id"])]
        if len(matches) != 1 or matches[0][0] != int(original["record_index"]):
            raise LookupError("question_identity_not_unique")
        idx, current = matches[0]
        if direct_record_hash(current) != original["new_hash"]:
            raise ValueError("rollback_stale_predecessor")
        try:
            snapshot_records = json.loads(exact_snapshot.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("rollback_snapshot_invalid") from error
        if not isinstance(snapshot_records, list) or len(snapshot_records) != len(records):
            raise ValueError("rollback_snapshot_invalid")
        if idx >= len(snapshot_records) or direct_record_hash(snapshot_records[idx]) != original["predecessor_hash"]:
            raise ValueError("rollback_snapshot_identity_mismatch")
        restored = json.loads(_json(snapshot_records[idx]))
        validation = validate_direct_record(restored, parse_sgf_fn=parse_sgf_fn)
        if not validation["ok"]:
            raise ValueError("rollback_record_invalid")
        # Rollback is also a canonical mutation.  Reapply the same authority
        # boundary so an old/legacy version cannot be used to promote GF003 or
        # silently bypass an unresolved fallback conflict.
        direct_apply_policy_check(current, restored)
        validation["canonical_before_sha256"] = _sha256(raw_before)
        validation["canonical_after_sha256"] = snapshot_sha
        _direct_atomic_write(questions_path, exact_snapshot)
        timestamp = _now(now)
        try:
            with repo.atomic("rollback_version"):
                row = conn.execute("""INSERT INTO sgf_workbench_direct_versions
                    (question_id, record_index, predecessor_hash, new_hash,
                    predecessor_version, new_version, operation_id, action_type,
                    actor_id, old_record_json, new_record_json, validation_result_json,
                    rollback_reference, source, status, created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *""", (
                    int(original["question_id"]), idx, original["new_hash"], original["predecessor_hash"],
                    original["new_version"], original["predecessor_version"], operation,
                    "ROLLBACK", int(actor_id), _json(_snapshot_payload(current, raw_before)),
                    _json(restored), _json(validation), int(version_id), DIRECT_APPLY_SOURCE,
                    "APPLIED", timestamp,
                )).fetchone()
                result = _serialize_direct_version(row)
                repo.audit("sgf_workbench_direct_version", result["id"], actor_id,
                           "ROLLBACK", {
                               "rollback_reference": int(version_id),
                               "restored_hash": original["predecessor_hash"],
                               "canonical_before_sha256": _sha256(raw_before),
                               "canonical_after_sha256": snapshot_sha,
                           }, timestamp)
            conn.commit()
            return result
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                _direct_atomic_write(questions_path, raw_before)
            except Exception as restore_error:
                raise DirectApplyRecoveryError("rollback_restore_failed") from restore_error
            raise


def build_position_identity(*, question_id: int, record_index: int | None,
                            issue_type: str, candidate_move: Any = None,
                            node_identity: str | None = None,
                            board_state: Any = None) -> str:
    """Return a semantic grouping identity, never just an array position."""
    payload = {
        "question_id": int(question_id),
        "record_index": record_index,
        "issue_type": issue_type,
        "candidate_move": _normalize_move(candidate_move),
        "node_identity": str(node_identity or ""),
        "board_state": board_state if board_state is not None else {},
    }
    return _sha256(_json(payload))


def _serialize_item(row: dict) -> dict:
    item = dict(row)
    for key in ("source_types_json", "gameplay_surfaces_json", "authority_json", "provenance_json", "candidate_move_json"):
        target = key.removesuffix("_json")
        item[target] = _loads(item.pop(key, None), [] if target in ("source_types", "gameplay_surfaces") else (None if target == "candidate_move" else {}))
    return item


def _serialize_report(row: dict) -> dict:
    report = dict(row)
    for key in ("candidate_move_json", "board_state_json", "source_provenance_json"):
        target = key.removesuffix("_json")
        report[target] = _loads(report.pop(key, None), {} if target != "candidate_move" else None)
    return report


def _serialize_repair(row: dict) -> dict:
    repair = dict(row)
    for key in ("original_state_json", "proposed_state_json", "candidate_move_json", "source_provenance_json"):
        target = key.removesuffix("_json")
        repair[target] = _loads(repair.pop(key, None), {} if target not in ("candidate_move",) else None)
    return repair


def _validation_from_repair(repair: dict) -> dict | None:
    provenance = repair.get("source_provenance")
    if not isinstance(provenance, dict):
        return None
    workflow = provenance.get("workflow")
    if not isinstance(workflow, dict):
        return None
    validation = workflow.get("validation")
    return validation if isinstance(validation, dict) else None


def _merge_proposed_record(current_record: dict, proposed_state: Any) -> dict:
    """Overlay the staged state on a fresh canonical record for dry-run checks."""
    proposed = json.loads(json.dumps(current_record if isinstance(current_record, dict) else {}))
    if isinstance(proposed_state, dict):
        for key in ("content", "sgf", "accepted_moves", "enabled", "solution_state"):
            if key in proposed_state:
                proposed[key] = proposed_state[key]
    return proposed


def _rebuild_group(conn, group_key: str, now: str) -> dict:
    rows = conn.execute("SELECT * FROM sgf_workbench_reports WHERE position_identity=? ORDER BY id", (group_key,)).fetchall()
    if not rows:
        return {}
    reports = [_row_dict(row) for row in rows]
    sources = sorted({str(row.get("source") or "") for row in reports if row.get("source")})
    surfaces = sorted({str(row.get("gameplay_surface") or "") for row in reports if row.get("gameplay_surface")})
    first = min(str(row.get("created_at") or now) for row in reports)
    last = max(str(row.get("created_at") or now) for row in reports)
    first_row = reports[0]
    conn.execute("""UPDATE sgf_workbench_review_items SET
        source_types_json=?, report_count=?, gameplay_surfaces_json=?,
        first_report_at=?, last_report_at=?, updated_at=?
        WHERE group_key=?""", (_json(sources), len(reports), _json(surfaces), first, last, now, group_key))
    row = conn.execute("SELECT * FROM sgf_workbench_review_items WHERE group_key=?", (group_key,)).fetchone()
    return _serialize_item(_row_dict(row))


def capture_workbench_report(conn, *, source: str, reporter_id: int | None,
                             question_id: int, issue_type: str,
                             record_index: int | None = None,
                             candidate_move: Any = None,
                             observed_system_verdict: str | None = None,
                             gameplay_surface: str | None = None,
                             sgf_identity: str | None = None,
                             node_identity: str | None = None,
                             board_state: Any = None,
                             question_content_sha256: str | None = None,
                             authority: Any = None,
                             comment: str = "", source_provenance: Any = None,
                             legacy_report_type: str | None = None,
                             legacy_report_id: int | None = None,
                             external_key: str | None = None,
                             now: str | None = None) -> dict:
    """Capture one immutable observation and upsert its semantic group."""
    ensure_sgf_workbench_tables(conn)
    source = str(source or "").strip().upper()
    issue_type = str(issue_type or "OTHER").strip().upper()
    if source not in WORKBENCH_SOURCES:
        raise ValueError("invalid_workbench_source")
    if issue_type not in WORKBENCH_REPORT_REASONS and source != "CORPUS_SCAN":
        raise ValueError("invalid_workbench_issue_type")
    if not isinstance(question_id, int) or question_id <= 0:
        raise ValueError("invalid_question_id")
    timestamp = _now(now)
    move = _normalize_move(candidate_move)
    group_key = build_position_identity(
        question_id=question_id, record_index=record_index, issue_type=issue_type,
        candidate_move=move, node_identity=node_identity, board_state=board_state,
    )
    external_key = str(external_key or f"{source.lower()}:{question_id}:{group_key}:{timestamp}")
    provenance = source_provenance if isinstance(source_provenance, dict) else {}
    repo = WorkbenchRepository(conn)
    with repo.atomic("capture_report"):
        existing_report = conn.execute(
            "SELECT id FROM sgf_workbench_reports WHERE external_key=?", (external_key,)
        ).fetchone()
        conn.execute("""INSERT INTO sgf_workbench_reports
            (source, legacy_report_type, legacy_report_id, reporter_id, question_id,
             record_index, issue_type, candidate_move_json, observed_system_verdict,
             gameplay_surface, sgf_identity, node_identity, position_identity,
             board_state_json, comment, question_content_sha256, source_provenance_json,
             external_key, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(external_key) DO NOTHING""", (
            source, legacy_report_type, legacy_report_id, reporter_id, question_id,
            record_index, issue_type, _json(move) if move else None,
            observed_system_verdict, gameplay_surface, sgf_identity, node_identity,
            group_key, _json(board_state if board_state is not None else {}),
            str(comment or "")[:1000], question_content_sha256, _json(provenance),
            external_key, timestamp,
        ))
        existing = conn.execute("SELECT * FROM sgf_workbench_review_items WHERE group_key=?", (group_key,)).fetchone()
        if not existing:
            conn.execute("""INSERT INTO sgf_workbench_review_items
                (group_key, question_id, record_index, issue_type, candidate_move_json,
                 position_identity, source_types_json, report_count,
                 gameplay_surfaces_json, first_report_at, last_report_at,
                 authority_json, provenance_json, status, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(group_key) DO NOTHING""", (
                group_key, question_id, record_index, issue_type,
                _json(move) if move else None, group_key, _json([source]), 0,
                _json([gameplay_surface] if gameplay_surface else []), timestamp,
                timestamp, _json({}), _json(provenance), "OPEN", timestamp, timestamp,
            ))
        item = _rebuild_group(conn, group_key, timestamp)
        if isinstance(authority, dict):
            conn.execute(
                "UPDATE sgf_workbench_review_items SET authority_json=?, provenance_json=? WHERE group_key=?",
                (_json(authority), _json(provenance), group_key),
            )
            item = _serialize_item(_row_dict(conn.execute(
                "SELECT * FROM sgf_workbench_review_items WHERE group_key=?", (group_key,)
            ).fetchone()))
        report_row = conn.execute("SELECT * FROM sgf_workbench_reports WHERE external_key=?", (external_key,)).fetchone()
        if not existing_report and report_row:
            repo.audit(
                "sgf_workbench_report", int(report_row["id"]), reporter_id,
                "REPORT_CAPTURED", {
                    "review_item_id": item.get("id"),
                    "source": source,
                    "question_id": question_id,
                    "group_key": group_key,
                }, timestamp,
            )
        return {
            "report": _serialize_report(_row_dict(report_row)),
            "item": item,
            "review_item_id": item.get("id"),
            "group_key": group_key,
            "report_count": item.get("report_count", 0),
        }


def list_workbench_items(conn, *, source: str | None = None,
                         status: str | None = None, limit: int = 200) -> list[dict]:
    ensure_sgf_workbench_tables(conn)
    clauses, params = [], []
    if source:
        clauses.append("source_types_json LIKE ?")
        params.append(f'%"{str(source).upper()}"%')
    if status:
        clauses.append("status=?")
        params.append(str(status).upper())
    sql = "SELECT * FROM sgf_workbench_review_items"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    return [_serialize_item(_row_dict(row)) for row in conn.execute(sql, tuple(params)).fetchall()]


def get_workbench_item(conn, item_id: int) -> dict | None:
    ensure_sgf_workbench_tables(conn)
    row = conn.execute("SELECT * FROM sgf_workbench_review_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        return None
    item = _serialize_item(_row_dict(row))
    reports = conn.execute("SELECT * FROM sgf_workbench_reports WHERE position_identity=? ORDER BY created_at, id", (row["position_identity"],)).fetchall()
    repairs = conn.execute("SELECT * FROM sgf_workbench_staged_repairs WHERE review_item_id=? ORDER BY created_at, id", (item_id,)).fetchall()
    item["reports"] = [_serialize_report(_row_dict(report)) for report in reports]
    item["staged_repairs"] = [_serialize_repair(_row_dict(repair)) for repair in repairs]
    return item


def _audit(conn, target_type: str, target_id: int | None, actor_id: int | None,
           action: str, detail: Any, now: str) -> None:
    conn.execute("""INSERT INTO sgf_workbench_audit
        (target_type, target_id, actor_id, action, detail, created_at)
        VALUES(?,?,?,?,?,?)""", (target_type, target_id, actor_id, action, _json(detail) if not isinstance(detail, str) else detail[:2000], now))


def stage_workbench_repair(conn, *, item_id: int, reviewer_id: int,
                           action: str, original_state: Any,
                           proposed_state: Any, candidate_move: Any = None,
                           reason: str = "", source_provenance: Any = None,
                           baseline_sha256: str | None = None,
                           mutation_key: str | None = None,
                           now: str | None = None,
                           expected_item_updated_at: str | None = None) -> dict:
    ensure_sgf_workbench_tables(conn)
    action = str(action or "").strip().upper()
    if action not in WORKBENCH_ACTIONS:
        raise ValueError("invalid_workbench_action")
    timestamp = _now(now)
    mutation_key = str(mutation_key or _sha256(_json({"item": item_id, "action": action, "proposed": proposed_state})))
    provenance = source_provenance if isinstance(source_provenance, dict) else {}
    repo = WorkbenchRepository(conn)
    with repo.atomic("stage_repair"):
        item = repo.lock_review_item(item_id)
        if not item:
            raise LookupError("workbench_item_not_found")
        item_status = str(item["status"] or "OPEN").upper()
        if expected_item_updated_at is not None and str(item["updated_at"]) != str(expected_item_updated_at):
            raise StaleWorkbenchState("stale_workbench_item")
        if item_status in {"REJECTED", "PUBLISHED"}:
            raise InvalidWorkbenchState(f"invalid_state_transition:{item_status}->STAGED")
        existing = conn.execute(
            "SELECT * FROM sgf_workbench_staged_repairs WHERE mutation_key=?", (mutation_key,)
        ).fetchone()
        if existing:
            result = _serialize_repair(_row_dict(existing))
            result["duplicate"] = True
            return result
        conn.execute("""INSERT INTO sgf_workbench_staged_repairs
            (review_item_id, reviewer_id, action, reason, original_state_json,
             proposed_state_json, candidate_move_json, source_provenance_json,
             baseline_sha256, mutation_key, status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(mutation_key) DO NOTHING""", (
            item_id, reviewer_id, action, str(reason or "")[:1000], _json(original_state if original_state is not None else {}),
            _json(proposed_state if proposed_state is not None else {}),
            _json(_normalize_move(candidate_move)) if _normalize_move(candidate_move) else None,
            _json(provenance), baseline_sha256, mutation_key, "STAGED", timestamp, timestamp,
        ))
        repair = conn.execute("SELECT * FROM sgf_workbench_staged_repairs WHERE mutation_key=?", (mutation_key,)).fetchone()
        if not repair:
            raise RuntimeError("staged_repair_insert_missing")
        conn.execute("UPDATE sgf_workbench_review_items SET status='STAGED', updated_at=? WHERE id=?", (timestamp, item_id))
        repo.audit("sgf_workbench_review_item", item_id, reviewer_id, "STAGED_REPAIR", {"action": action, "repair_id": repair["id"]}, timestamp)
        return _serialize_repair(_row_dict(repair))


def validate_staged_repair(conn, *, repair_id: int, actor_id: int,
                           current_record: dict | None,
                           current_content_sha256: str | None,
                           current_record_hash: str | None = None,
                           parse_sgf_fn=None, verdict_fn=None,
                           now: str | None = None) -> dict:
    """Dry-run one staged repair against the currently loaded canonical record.

    Validation is deliberately an evidence operation: it writes only the
    validation result/provenance and audit row.  It never receives a corpus
    path and therefore cannot mutate canonical question content.
    """
    ensure_sgf_workbench_tables(conn)
    timestamp = _now(now)
    repo = WorkbenchRepository(conn)
    with repo.atomic("validate_repair"):
        repair_row = repo.lock_staged_repair(repair_id)
        if not repair_row:
            raise LookupError("staged_repair_not_found")
        repair = _serialize_repair(_row_dict(repair_row))
        item_row = repo.lock_review_item(int(repair["review_item_id"]))
        if not item_row:
            raise LookupError("workbench_item_not_found")
        item = _row_dict(item_row)
        action = str(repair.get("action") or "").upper()
        provenance = repair.get("source_provenance")
        if not isinstance(provenance, dict):
            provenance = {}
        result = {
            "status": "PASS",
            "ok": True,
            "repair_id": int(repair_id),
            "review_item_id": int(repair["review_item_id"]),
            "action": action,
            "canonical_mutation": False,
            "checks": {},
            "basis": {
                "content_sha256": current_content_sha256,
                "record_hash": current_record_hash,
            },
        }
        errors: list[str] = []
        # The corpus/content and full-record identity are both checked.  The
        # latter catches accepted-move metadata changes that do not alter SGF
        # bytes.
        baseline = repair.get("baseline_sha256")
        if not baseline or not current_content_sha256:
            result["status"] = "FAIL"
            errors.append("canonical_basis_missing")
        elif str(baseline) != str(current_content_sha256):
            result["status"] = "STALE"
            errors.append("canonical_content_basis_changed")
        staged_basis = provenance.get("canonical_record_hash")
        if staged_basis and not current_record_hash:
            result["status"] = "FAIL"
            errors.append("canonical_record_basis_missing")
        elif staged_basis and str(staged_basis) != str(current_record_hash):
            result["status"] = "STALE"
            errors.append("canonical_record_basis_changed")
        if not isinstance(current_record, dict):
            result["status"] = "FAIL"
            errors.append("current_record_unavailable")
        else:
            proposed = _merge_proposed_record(current_record, repair.get("proposed_state"))
            structural = validate_direct_record(proposed, parse_sgf_fn=parse_sgf_fn)
            result["checks"]["sgf_structural_validation"] = structural
            if not structural.get("ok"):
                result["status"] = "FAIL"
                errors.extend(str(error) for error in structural.get("errors", []))
            original = repair.get("original_state") if isinstance(repair.get("original_state"), dict) else {}
            original_moves = {_json(_normalize_move(move)) for move in (original.get("accepted_moves") or []) if _normalize_move(move)}
            current_moves = {_json(_normalize_move(move)) for move in (current_record.get("accepted_moves") or []) if _normalize_move(move)}
            if "accepted_moves" in original and original_moves != current_moves:
                result["status"] = "CONFLICT"
                errors.append("original_answer_state_changed")
            if "enabled" in original and bool(original.get("enabled")) != bool(current_record.get("enabled", True)):
                result["status"] = "CONFLICT"
                errors.append("original_enabled_state_changed")
            if "solution_state" in original and original.get("solution_state") != current_record.get("solution_state"):
                result["status"] = "CONFLICT"
                errors.append("original_solution_state_changed")
            proposed_moves = {_json(_normalize_move(move)) for move in (proposed.get("accepted_moves") or []) if _normalize_move(move)}
            candidate = _normalize_move(repair.get("candidate_move"))
            candidate_key = _json(candidate) if candidate else None
            result["checks"]["question_identity_preserved"] = proposed.get("id") == current_record.get("id")
            if not result["checks"]["question_identity_preserved"]:
                result["status"] = "FAIL"
                errors.append("question_identity_changed")
            if action == "NEEDS_RESEARCH":
                result["status"] = "FAIL"
                errors.append("needs_research_not_batchable")
            elif candidate_key is None and action in {
                "ADD_ALTERNATIVE_CORRECT_MOVE", "REMOVE_INCORRECT_ACCEPTED_MOVE", "REPLACE_ANSWER"
            }:
                result["status"] = "FAIL"
                errors.append("candidate_move_missing")
            elif action == "ADD_ALTERNATIVE_CORRECT_MOVE":
                if candidate_key in original_moves:
                    result["status"] = "CONFLICT"
                    errors.append("alternative_already_accepted")
                elif candidate_key not in proposed_moves:
                    result["status"] = "FAIL"
                    errors.append("alternative_not_in_proposed_answers")
            elif action == "REMOVE_INCORRECT_ACCEPTED_MOVE":
                if candidate_key not in original_moves:
                    result["status"] = "CONFLICT"
                    errors.append("remove_candidate_not_in_original_answers")
                elif candidate_key in proposed_moves:
                    result["status"] = "FAIL"
                    errors.append("removed_answer_still_present")
                if not proposed_moves:
                    result["status"] = "FAIL"
                    errors.append("empty_answer_set")
            elif action == "REPLACE_ANSWER":
                if candidate_key not in proposed_moves:
                    result["status"] = "FAIL"
                    errors.append("replacement_not_in_proposed_answers")
                if len(proposed_moves) != 1:
                    result["status"] = "FAIL"
                    errors.append("replacement_answer_set_not_singleton")
            elif action == "DISABLE_BROKEN_QUESTION":
                if proposed.get("enabled", True) is not False:
                    result["status"] = "FAIL"
                    errors.append("disable_state_missing")
            if verdict_fn is not None and candidate is not None:
                before = verdict_fn(current_record, candidate)
                after = verdict_fn(proposed, candidate)
                result["checks"]["same_question_regression"] = {"before": before, "after": after}
                if action in {"ADD_ALTERNATIVE_CORRECT_MOVE", "REPLACE_ANSWER"} and after is not True:
                    result["status"] = "FAIL"
                    errors.append("candidate_not_accepted_by_runtime")
                if action == "REMOVE_INCORRECT_ACCEPTED_MOVE" and after is True:
                    result["status"] = "CONFLICT"
                    errors.append("removed_candidate_still_accepted_by_runtime")
            result["checks"]["validation_record_hash"] = direct_record_hash(proposed)
        result["errors"] = sorted(set(errors))
        result["ok"] = result["status"] == "PASS"
        validation_provenance = dict(provenance)
        validation_provenance["workflow"] = {
            "validation": result,
            "validated_at": timestamp,
            "validated_by": actor_id,
        }
        conn.execute(
            "UPDATE sgf_workbench_staged_repairs SET source_provenance_json=?, updated_at=? WHERE id=?",
            (_json(validation_provenance), timestamp, int(repair_id)),
        )
        if result["status"] == "STALE":
            conn.execute(
                "UPDATE sgf_workbench_review_items SET status='STALE', stale_reason=?, updated_at=? WHERE id=?",
                (_json(result["errors"]), timestamp, int(repair["review_item_id"])),
            )
        repo.audit(
            "sgf_workbench_staged_repair", int(repair_id), actor_id,
            "VALIDATION_" + result["status"], result, timestamp,
        )
        result["repair"] = _serialize_repair(_row_dict(conn.execute(
            "SELECT * FROM sgf_workbench_staged_repairs WHERE id=?", (int(repair_id),)
        ).fetchone()))
        return result


def resolve_workbench_item(conn, *, item_id: int, reviewer_id: int,
                           status: str, note: str = "", now: str | None = None,
                           expected_item_updated_at: str | None = None) -> dict:
    ensure_sgf_workbench_tables(conn)
    status = str(status or "").strip().upper()
    if status not in ("NEEDS_RESEARCH", "REJECTED"):
        raise ValueError("invalid_workbench_resolution")
    timestamp = _now(now)
    repo = WorkbenchRepository(conn)
    with repo.atomic("resolve_item"):
        row = repo.lock_review_item(item_id)
        if not row:
            raise LookupError("workbench_item_not_found")
        current = str(row["status"] or "OPEN").upper()
        if expected_item_updated_at is not None and str(row["updated_at"]) != str(expected_item_updated_at):
            raise StaleWorkbenchState("stale_workbench_item")
        if current == status:
            return {"id": item_id, "status": status, "updated_at": row["updated_at"], "duplicate": True}
        if current in {"REJECTED", "PUBLISHED"}:
            raise InvalidWorkbenchState(f"invalid_state_transition:{current}->{status}")
        provenance = _loads(row["provenance_json"], {})
        if not isinstance(provenance, dict):
            provenance = {}
        provenance.update({"resolution_note": str(note or "")[:1000], "reviewer_id": reviewer_id})
        conn.execute("UPDATE sgf_workbench_review_items SET status=?, provenance_json=?, updated_at=? WHERE id=?", (status, _json(provenance), timestamp, item_id))
        repo.audit("sgf_workbench_review_item", item_id, reviewer_id, status, note, timestamp)
        return {"id": item_id, "status": status, "updated_at": timestamp}


def create_workbench_batch(conn, *, created_by: int, baseline_sha256: str | None = None,
                           now: str | None = None, idempotency_key: str | None = None,
                           require_validation: bool = False) -> dict:
    ensure_sgf_workbench_tables(conn)
    timestamp = _now(now)
    requested_key = str(idempotency_key or "").strip()
    if len(requested_key) > 180:
        raise ValueError("idempotency_key_too_long")
    repo = WorkbenchRepository(conn)
    with repo.atomic("create_batch"):
        if requested_key:
            existing = conn.execute("SELECT * FROM sgf_workbench_batches WHERE batch_key=?", (requested_key,)).fetchone()
            if existing:
                result = _row_dict(existing)
                result["manifest"] = _loads(result.get("manifest_json"), {})
                result.pop("manifest_json", None)
                result["duplicate"] = True
                return result
        rows = repo.lock_staged_repairs()
        repairs = [_serialize_repair(_row_dict(row)) for row in rows]
        if not repairs:
            raise ValueError("no_staged_repairs")
        if require_validation:
            invalid = [
                int(repair["id"])
                for repair in repairs
                if (_validation_from_repair(repair) or {}).get("status") != "PASS"
            ]
            if invalid:
                raise InvalidWorkbenchState("validation_required:" + ",".join(map(str, invalid)))
        manifest = {
            "schema_version": "sgf-admin-workbench-batch-v1",
            "baseline_sha256": baseline_sha256,
            "created_at": timestamp,
            "source": "SGF_ADMIN_WORKBENCH",
            "staged_repair_count": len(repairs),
            "validation_required": bool(require_validation),
            "repairs": repairs,
            "handoff": {
                "repair_batch_tool": "tools/sgf_answer_repair_batch.py",
                "content_release_validator": "PR318_SGF_CONTENT_RELEASE_INFRASTRUCTURE",
                "production_mutation": False,
            },
        }
        manifest_sha = _sha256(_json(manifest))
        batch_key = requested_key or f"sgf-workbench-{manifest_sha[:24]}"
        existing = conn.execute("SELECT * FROM sgf_workbench_batches WHERE batch_key=?", (batch_key,)).fetchone()
        if existing:
            result = _row_dict(existing)
            result["manifest"] = _loads(result.get("manifest_json"), {})
            result.pop("manifest_json", None)
            result["duplicate"] = True
            return result
        conn.execute("""INSERT INTO sgf_workbench_batches
            (batch_key, created_by, status, manifest_json, manifest_sha256, staged_count, created_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(batch_key) DO NOTHING""", (
            batch_key, created_by, "STAGED", _json(manifest), manifest_sha, len(repairs), timestamp,
        ))
        batch = conn.execute("SELECT * FROM sgf_workbench_batches WHERE batch_key=?", (batch_key,)).fetchone()
        if not batch:
            raise RuntimeError("batch_insert_missing")
        for order, repair in enumerate(repairs):
            conn.execute("""INSERT INTO sgf_workbench_batch_items(batch_id, staged_repair_id, order_index)
                VALUES(?,?,?) ON CONFLICT(batch_id, staged_repair_id) DO NOTHING""", (batch["id"], repair["id"], order))
            conn.execute("UPDATE sgf_workbench_staged_repairs SET status='BATCHED', updated_at=? WHERE id=?", (timestamp, repair["id"]))
        repo.audit("sgf_workbench_batch", batch["id"], created_by, "BATCH_CREATED", {"manifest_sha256": manifest_sha, "count": len(repairs)}, timestamp)
        return {
            "id": batch["id"], "batch_key": batch_key, "manifest": manifest,
            "manifest_sha256": manifest_sha, "staged_count": len(repairs),
            "status": batch["status"],
        }


def get_workbench_batch(conn, batch_id: int) -> dict | None:
    ensure_sgf_workbench_tables(conn)
    row = conn.execute("SELECT * FROM sgf_workbench_batches WHERE id=?", (int(batch_id),)).fetchone()
    if not row:
        return None
    batch = _row_dict(row)
    batch["manifest"] = _loads(batch.pop("manifest_json", None), {})
    rows = conn.execute(
        """SELECT bi.id AS batch_item_id, bi.order_index,
                  bi.staged_repair_id, sr.review_item_id, sr.status AS repair_status,
                  sr.action, sr.source_provenance_json, sr.baseline_sha256,
                  ri.question_id, ri.record_index, ri.status AS review_status,
                  ri.group_key
             FROM sgf_workbench_batch_items bi
             JOIN sgf_workbench_staged_repairs sr ON sr.id=bi.staged_repair_id
             JOIN sgf_workbench_review_items ri ON ri.id=sr.review_item_id
            WHERE bi.batch_id=? ORDER BY bi.order_index, bi.id""",
        (int(batch_id),),
    ).fetchall()
    items = []
    for row in rows:
        item = _row_dict(row)
        item["source_provenance"] = _loads(item.pop("source_provenance_json", None), {})
        item["validation"] = _validation_from_repair({"source_provenance": item.get("source_provenance")})
        items.append(item)
    batch["items"] = items
    return batch


def mark_batch_ready_for_apply(conn, *, batch_id: int, actor_id: int,
                               current_bases: dict[int, dict[str, str | None]],
                               now: str | None = None) -> dict:
    """Advance a validated batch to READY_FOR_APPLY without applying content."""
    ensure_sgf_workbench_tables(conn)
    timestamp = _now(now)
    repo = WorkbenchRepository(conn)
    with repo.atomic("ready_batch"):
        batch_row = repo.lock_batch(batch_id)
        if not batch_row:
            raise LookupError("workbench_batch_not_found")
        batch = _row_dict(batch_row)
        current_status = str(batch.get("status") or "STAGED").upper()
        if current_status == "READY_FOR_APPLY":
            result = get_workbench_batch(conn, batch_id) or batch
            result["duplicate"] = True
            return result
        if current_status != "STAGED":
            raise InvalidWorkbenchState(f"invalid_batch_transition:{current_status}->READY_FOR_APPLY")
        rows = conn.execute(
            """SELECT bi.staged_repair_id, sr.review_item_id, sr.status AS repair_status,
                      sr.source_provenance_json, sr.baseline_sha256,
                      ri.question_id, ri.record_index, ri.status AS review_status
                 FROM sgf_workbench_batch_items bi
                 JOIN sgf_workbench_staged_repairs sr ON sr.id=bi.staged_repair_id
                 JOIN sgf_workbench_review_items ri ON ri.id=sr.review_item_id
                WHERE bi.batch_id=? ORDER BY bi.order_index, bi.id""",
            (int(batch_id),),
        ).fetchall()
        if not rows:
            raise InvalidWorkbenchState("empty_batch")
        failures = []
        for row in rows:
            item = _row_dict(row)
            repair = {"source_provenance": _loads(item.get("source_provenance_json"), {})}
            validation = _validation_from_repair(repair) or {}
            if item.get("repair_status") != "BATCHED":
                failures.append({"repair_id": item["staged_repair_id"], "reason": "repair_not_batched"})
            if validation.get("status") != "PASS":
                failures.append({"repair_id": item["staged_repair_id"], "reason": "validation_not_pass"})
            basis = current_bases.get(int(item["review_item_id"])) or {}
            if not item.get("baseline_sha256") or basis.get("content_sha256") != item.get("baseline_sha256"):
                failures.append({"repair_id": item["staged_repair_id"], "reason": "canonical_content_basis_changed"})
            validated_hash = (validation.get("basis") or {}).get("record_hash")
            if not validated_hash or not basis.get("record_hash") or validated_hash != basis.get("record_hash"):
                failures.append({"repair_id": item["staged_repair_id"], "reason": "canonical_record_basis_changed"})
            if str(item.get("review_status") or "").upper() in {"STALE", "REJECTED", "PUBLISHED"}:
                failures.append({"repair_id": item["staged_repair_id"], "reason": "review_item_not_ready"})
        if failures:
            repo.audit(
                "sgf_workbench_batch", int(batch_id), actor_id,
                "READY_FOR_APPLY_REJECTED", {"failures": failures}, timestamp,
            )
            return {"id": int(batch_id), "status": "BLOCKED", "ready_for_apply": False,
                    "canonical_mutation": False, "failures": failures}
        manifest = _loads(batch.get("manifest_json"), {})
        if not isinstance(manifest, dict):
            manifest = {}
        manifest["ready_for_apply"] = True
        manifest["ready_at"] = timestamp
        manifest["ready_by"] = actor_id
        manifest["canonical_mutation"] = False
        manifest_sha = _sha256(_json(manifest))
        conn.execute(
            "UPDATE sgf_workbench_batches SET status='READY_FOR_APPLY', manifest_json=?, manifest_sha256=? WHERE id=?",
            (_json(manifest), manifest_sha, int(batch_id)),
        )
        repo.audit(
            "sgf_workbench_batch", int(batch_id), actor_id,
            "READY_FOR_APPLY", {"manifest_sha256": manifest_sha, "canonical_mutation": False}, timestamp,
        )
        result = get_workbench_batch(conn, batch_id) or {}
        result["ready_for_apply"] = True
        result["canonical_mutation"] = False
        result["apply_enabled"] = False
        return result


def workbench_constants() -> dict:
    return {
        "sources": list(WORKBENCH_SOURCES),
        "statuses": list(WORKBENCH_STATUSES),
        "actions": list(WORKBENCH_ACTIONS),
        "report_reasons": list(WORKBENCH_REPORT_REASONS),
        "production_mutation": False,
        "canonical_mutation": False,
        "validation_statuses": ["PASS", "FAIL", "STALE", "CONFLICT"],
        "ready_status": "READY_FOR_APPLY",
        "apply_enabled": False,
        "future_source_ready": "CORPUS_SCAN",
        "direct_apply_source": DIRECT_APPLY_SOURCE,
        "direct_apply_actions": list(DIRECT_APPLY_ACTIONS),
        "direct_apply_requires_acceptance_gate": True,
        "human_review_classifications": [
            "CORRECT", "WRONG_ROOT", "MISSING_ANSWER", "MISSING_VARIATION", "SPECIAL", "UNSURE",
        ],
        "human_review_identity": "VERSION_SCOPED_RECORD_LOCATOR",
        "canonical_identity_decision": "DEFERRED",
    }
