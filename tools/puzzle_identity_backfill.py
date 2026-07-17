"""Local/test-only canonical puzzle identity alias backfill.

This utility has no default corpus or database.  It accepts an explicitly
named synthetic questions-list JSON file and an explicitly named SQLite file,
and refuses either path unless it resolves beneath ``--ephemeral-root``. The
command accepts only the ``local-test`` scope, has no Production connection
support, and is not authorized for Production use.

The source identity contract matches the application corpus exactly:
``record_index`` is the zero-based position in the JSON list and
``legacy_question_id`` is that record's ``id``.  No SGF/content field is read
or used.  Existing aliases are immutable; the backfill only inserts missing
composite keys and never updates or replaces a mapping.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from migrations.puzzle_identity_alias_v1 import upgrade  # noqa: E402


_INTEGER_RE = re.compile(r"-?\d+\Z")
_MAX_UUID_ATTEMPTS = 16


def _coerce_legacy_question_id(value) -> int:
    if isinstance(value, bool):
        raise ValueError("question id must be an integer, not boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _INTEGER_RE.fullmatch(value.strip()):
        return int(value.strip())
    raise ValueError("question id must be an integer")


def load_source_records(input_path: Path) -> list[tuple[int, int]]:
    """Load only the ordinal/index and legacy ``id`` from a questions list."""

    with input_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("input JSON must be a top-level questions list")

    records: list[tuple[int, int]] = []
    for record_index, record in enumerate(payload):
        if not isinstance(record, dict):
            raise ValueError(f"record {record_index} must be an object")
        if "id" not in record:
            raise ValueError(f"record {record_index} is missing id")
        legacy_question_id = _coerce_legacy_question_id(record["id"])
        records.append((record_index, legacy_question_id))
    return records


def _uuid4_text(value) -> str:
    try:
        parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("uuid factory did not return a UUID") from exc
    if parsed.version != 4 or parsed.variant != uuid.RFC_4122:
        raise ValueError("uuid factory must return an RFC 4122 UUIDv4")
    return str(parsed)


def _existing_alias(connection, record_index: int, legacy_question_id: int):
    return connection.execute(
        """
        SELECT canonical_puzzle_id
          FROM puzzle_identity_alias
         WHERE record_index=? AND legacy_question_id=?
         LIMIT 2
        """,
        (record_index, legacy_question_id),
    ).fetchall()


def backfill_missing_aliases(
    connection,
    records: list[tuple[int, int]],
    *,
    uuid_factory=uuid.uuid4,
) -> dict[str, int]:
    """Insert missing aliases and preserve every existing mapping verbatim.

    Transaction ownership stays with the caller.  A UUID collision is retried
    with a fresh UUID, while a concurrent insert of the same composite key is
    accepted only after reading and validating the winner's UUIDv4.
    """

    inserted = 0
    preserved = 0
    for record_index, legacy_question_id in records:
        rows = _existing_alias(connection, record_index, legacy_question_id)
        if len(rows) > 1:
            raise ValueError("composite alias lookup returned multiple rows")
        if rows:
            _uuid4_text(rows[0][0])
            preserved += 1
            continue

        for _attempt in range(_MAX_UUID_ATTEMPTS):
            canonical_puzzle_id = _uuid4_text(uuid_factory())
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO puzzle_identity_alias
                        (record_index, legacy_question_id, canonical_puzzle_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(record_index, legacy_question_id) DO NOTHING
                    """,
                    (record_index, legacy_question_id, canonical_puzzle_id),
                )
            except sqlite3.IntegrityError:
                # A UUID collision must never overwrite either mapping.  A
                # racing insert of this same composite key is safe to adopt.
                rows = _existing_alias(connection, record_index, legacy_question_id)
                if rows:
                    _uuid4_text(rows[0][0])
                    preserved += 1
                    break
                continue

            if cursor.rowcount == 1:
                inserted += 1
                break

            rows = _existing_alias(connection, record_index, legacy_question_id)
            if len(rows) != 1:
                raise RuntimeError("alias insert lost without a persisted winner")
            _uuid4_text(rows[0][0])
            preserved += 1
            break
        else:
            raise RuntimeError("could not allocate a unique UUIDv4")

    return {
        "source_records": len(records),
        "inserted": inserted,
        "preserved": preserved,
    }


def deterministic_snapshot_bytes(connection) -> bytes:
    """Return a canonical, stable byte snapshot of all alias mappings."""

    rows = connection.execute(
        """
        SELECT record_index, legacy_question_id, canonical_puzzle_id
          FROM puzzle_identity_alias
         ORDER BY record_index, legacy_question_id
        """
    ).fetchall()
    mappings = []
    for row in rows:
        mappings.append(
            {
                "canonical_puzzle_id": _uuid4_text(row[2]),
                "legacy_question_id": int(row[1]),
                "record_index": int(row[0]),
            }
        )
    payload = {"mappings": mappings, "schema_version": 1}
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _resolve_ephemeral_root(raw_root: str) -> Path:
    root = Path(raw_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("--ephemeral-root must name an existing directory")
    return root


def _resolve_under_root(
    root: Path,
    raw_path: str,
    *,
    label: str,
    must_exist: bool,
) -> Path:
    supplied = Path(raw_path).expanduser()
    candidate = supplied if supplied.is_absolute() else root / supplied
    if candidate.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must remain under --ephemeral-root") from exc
    if must_exist and not resolved.is_file():
        raise ValueError(f"{label} must name an existing regular file")
    if not must_exist and not resolved.parent.is_dir():
        raise ValueError(f"{label} parent directory must already exist")
    return resolved


def _write_snapshot_once(path: Path, snapshot: bytes) -> None:
    if path.exists():
        if not path.is_file() or path.read_bytes() != snapshot:
            raise ValueError("existing snapshot differs from deterministic result")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(snapshot)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="puzzle_identity_backfill",
        description=(
            "Local/test-only insert-missing canonical puzzle alias backfill. "
            "No production scope or default input/database exists."
        ),
    )
    parser.add_argument("--scope", required=True)
    parser.add_argument("--ephemeral-root", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--snapshot-output")
    return parser


def run(args) -> dict:
    if args.scope != "local-test":
        raise ValueError("--scope must be exactly 'local-test'")
    root = _resolve_ephemeral_root(args.ephemeral_root)
    input_path = _resolve_under_root(
        root, args.input, label="input", must_exist=True
    )
    database_path = _resolve_under_root(
        root, args.database, label="database", must_exist=False
    )
    if database_path == input_path:
        raise ValueError("input and database paths must differ")
    snapshot_path = None
    if args.snapshot_output:
        snapshot_path = _resolve_under_root(
            root,
            args.snapshot_output,
            label="snapshot output",
            must_exist=False,
        )
        if snapshot_path in (input_path, database_path):
            raise ValueError("snapshot output must differ from input and database")

    records = load_source_records(input_path)
    connection = sqlite3.connect(str(database_path), timeout=5.0)
    try:
        upgrade(connection)
        result = backfill_missing_aliases(connection, records)
        snapshot = deterministic_snapshot_bytes(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    if snapshot_path is not None:
        _write_snapshot_once(snapshot_path, snapshot)
    result["snapshot_sha256"] = hashlib.sha256(snapshot).hexdigest()
    return result


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except (json.JSONDecodeError, OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
