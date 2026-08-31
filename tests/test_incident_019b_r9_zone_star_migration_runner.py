"""Disposable-state contracts for the Incident019B Zone-star migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from migrations.adventure_zone_star_progression_v1 import (
    EARNINGS_TABLE_NAME,
    PROGRESS_TABLE_NAME,
    SchemaMismatch,
)
from tools import incident_019b_zone_star_migration as runner


CANONICAL_SOURCE_SHA = "0bbbc6ae40d37df5c94cf9485e33802c7b545f36"


def _db(tmp_path, *, existing_data: bool = False) -> sqlite3.Connection:
    path = tmp_path / "incident019b-r9.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    if existing_data:
        conn.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY);
            CREATE TABLE review_log (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                grade INTEGER NOT NULL,
                reviewed_at TEXT NOT NULL,
                source_context TEXT
            );
            CREATE TABLE srs_cards (
                user_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                last_grade INTEGER,
                progress_credited INTEGER,
                updated_at TEXT,
                PRIMARY KEY (user_id, question_id)
            );
            CREATE TABLE adventure_boss_progress (
                user_id INTEGER NOT NULL,
                zone_key TEXT NOT NULL,
                cleared INTEGER NOT NULL DEFAULT 0,
                stars INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                best_score INTEGER NOT NULL DEFAULT 0,
                cooldown_until_seen INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                cleared_at TEXT,
                updated_at TEXT,
                PRIMARY KEY (user_id, zone_key)
            );
            CREATE TABLE adventure_historical_mastery (
                user_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                baseline_version TEXT NOT NULL,
                source_mask INTEGER NOT NULL,
                entitlement_source TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                cutoff_literal TEXT NOT NULL,
                PRIMARY KEY (user_id, question_id, baseline_version)
            );
            CREATE TABLE adventure_historical_mastery_baseline (
                baseline_version TEXT PRIMARY KEY NOT NULL,
                cutoff_literal TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                frozen_at TEXT NOT NULL,
                status TEXT NOT NULL,
                membership_count INTEGER NOT NULL
            );
            INSERT INTO users VALUES (7);
            INSERT INTO review_log VALUES (1, 7, 1001, 5, '2026-08-01T00:00:00', 'practice');
            INSERT INTO srs_cards VALUES (7, 1001, 5, 1, '2026-08-01T00:00:00');
            INSERT INTO adventure_boss_progress
                (user_id, zone_key, cleared, stars, attempts, best_score)
                VALUES (7, 'k26_30', 1, 2, 3, 88);
            INSERT INTO adventure_historical_mastery
                (user_id, question_id, baseline_version, source_mask,
                 entitlement_source, captured_at, cutoff_literal)
                VALUES (7, 1001, 'INCIDENT019B_B050_COMPAT_V1', 1,
                        'pre_cutoff_review', '2026-08-01T00:00:00', '2026-08-01');
            INSERT INTO adventure_historical_mastery_baseline
                (baseline_version, cutoff_literal, captured_at, frozen_at,
                 status, membership_count)
                VALUES ('INCIDENT019B_B050_COMPAT_V1', '2026-08-01',
                        '2026-08-01T00:00:00', '2026-08-01T00:00:00', 'FROZEN', 1);
            """
        )
    conn.commit()
    return conn


def _tables(conn):
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


class _FailingConnection:
    def __init__(self, needle: str):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self.needle = needle

    def execute(self, sql, parameters=()):
        if self.needle in sql:
            raise RuntimeError("injected failure")
        return self._conn.execute(sql, parameters)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


def _apply(conn):
    return runner.apply_migration(
        conn,
        canonical_source_sha=CANONICAL_SOURCE_SHA,
        migration_id=runner.MIGRATION_ID,
        owner_gate=runner.OWNER_GATE,
        execute=True,
    )


def test_empty_schema_apply_creates_exact_schema_and_receipt(tmp_path):
    conn = _db(tmp_path)
    result = _apply(conn)

    assert result["status"] == "APPLIED"
    assert runner.verify_expected_schema(conn)["tables"] == [
        PROGRESS_TABLE_NAME,
        EARNINGS_TABLE_NAME,
    ]
    receipt = conn.execute(
        f"SELECT migration_id, migration_version, migration_sha256, "
        f"canonical_source_sha, execution_status FROM {runner.RECEIPT_TABLE_NAME}"
    ).fetchone()
    assert tuple(receipt) == (
        runner.MIGRATION_ID,
        runner.SCHEMA_VERSION,
        runner.EXPECTED_MIGRATION_SHA256,
        CANONICAL_SOURCE_SHA,
        "APPLIED",
    )
    assert conn.execute(f"SELECT COUNT(*) FROM {PROGRESS_TABLE_NAME}").fetchone()[0] == 0
    assert conn.execute(f"SELECT COUNT(*) FROM {EARNINGS_TABLE_NAME}").fetchone()[0] == 0
    conn.close()


def test_exact_rerun_is_noop_and_receipt_is_unique(tmp_path):
    conn = _db(tmp_path)
    first = _apply(conn)
    second = _apply(conn)

    assert first["status"] == "APPLIED"
    assert second["status"] == "ALREADY_APPLIED"
    assert conn.execute(
        f"SELECT COUNT(*) FROM {runner.RECEIPT_TABLE_NAME}"
    ).fetchone()[0] == 1
    conn.close()


def test_receipt_hash_mismatch_fails_closed(tmp_path):
    conn = _db(tmp_path)
    _apply(conn)
    conn.execute(
        f"UPDATE {runner.RECEIPT_TABLE_NAME} SET migration_sha256=?",
        ("0" * 64,),
    )
    conn.commit()

    with pytest.raises(runner.ReceiptConflict):
        _apply(conn)
    conn.close()


def test_receipt_canonical_source_mismatch_fails_closed(tmp_path):
    conn = _db(tmp_path)
    _apply(conn)

    with pytest.raises(runner.ReceiptConflict):
        runner.apply_migration(
            conn,
            canonical_source_sha="1" * 40,
            migration_id=runner.MIGRATION_ID,
            owner_gate=runner.OWNER_GATE,
            execute=True,
        )
    conn.close()


def test_incomplete_receipt_fails_closed(tmp_path):
    conn = _db(tmp_path)
    _apply(conn)
    conn.execute(
        f"UPDATE {runner.RECEIPT_TABLE_NAME} SET execution_status='STARTED'"
    )
    conn.commit()

    with pytest.raises(runner.ReceiptConflict):
        _apply(conn)
    conn.close()


def test_partial_zone_schema_fails_closed_without_receipt(tmp_path):
    conn = _db(tmp_path)
    conn.execute(
        f"CREATE TABLE {PROGRESS_TABLE_NAME} (user_id INTEGER PRIMARY KEY)"
    )
    conn.commit()

    with pytest.raises(SchemaMismatch):
        _apply(conn)
    assert runner.RECEIPT_TABLE_NAME not in _tables(conn)
    assert EARNINGS_TABLE_NAME not in _tables(conn)
    conn.close()


def test_injected_ddl_failure_rolls_back_all_new_schema():
    conn = _FailingConnection(
        f"CREATE TABLE IF NOT EXISTS {EARNINGS_TABLE_NAME}"
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        _apply(conn)
    assert runner.RECEIPT_TABLE_NAME not in _tables(conn._conn)
    assert PROGRESS_TABLE_NAME not in _tables(conn._conn)
    assert EARNINGS_TABLE_NAME not in _tables(conn._conn)
    conn.close()


def test_injected_receipt_failure_rolls_back_schema_too():
    conn = _FailingConnection(f"INSERT INTO {runner.RECEIPT_TABLE_NAME}")

    with pytest.raises(RuntimeError, match="injected failure"):
        _apply(conn)
    assert runner.RECEIPT_TABLE_NAME not in _tables(conn._conn)
    assert PROGRESS_TABLE_NAME not in _tables(conn._conn)
    assert EARNINGS_TABLE_NAME not in _tables(conn._conn)
    conn.close()


def test_existing_boss_and_historical_state_is_unchanged_and_no_backfill(tmp_path):
    conn = _db(tmp_path, existing_data=True)
    before = runner.snapshot_state(conn)
    result = _apply(conn)
    after = runner.snapshot_state(conn)

    assert result["status"] == "APPLIED"
    assert before["fingerprint"] == after["fingerprint"]
    assert before["data"]["boss_progress"] == after["data"]["boss_progress"]
    assert before["data"]["historical_mastery"] == after["data"]["historical_mastery"]
    assert before["data"]["historical_baseline"] == after["data"]["historical_baseline"]
    assert after["data"]["zone_progress"]["row_count"] == 0
    assert after["data"]["zone_earnings"]["row_count"] == 0
    conn.close()


def test_inspect_mode_is_read_only(tmp_path, capsys):
    conn = _db(tmp_path)
    conn.close()
    path = tmp_path / "incident019b-r9.sqlite"
    assert runner.main(["--inspect", "--sqlite-path", str(path)]) == 0
    capsys.readouterr()
    conn = sqlite3.connect(path)
    assert runner.RECEIPT_TABLE_NAME not in _tables(conn)
    assert PROGRESS_TABLE_NAME not in _tables(conn)
    conn.close()


def test_inspect_mode_rejects_missing_target_without_creating_it(tmp_path):
    path = tmp_path / "missing.sqlite"
    assert runner.main(["--inspect", "--sqlite-path", str(path)]) == 2
    assert not path.exists()


def test_exact_contract_is_required_by_direct_execution_api(tmp_path):
    conn = _db(tmp_path)

    with pytest.raises(runner.RunnerUsageError):
        runner.apply_migration(conn, canonical_source_sha=CANONICAL_SOURCE_SHA)

    assert runner.RECEIPT_TABLE_NAME not in _tables(conn)
    assert PROGRESS_TABLE_NAME not in _tables(conn)
    conn.close()


def test_execute_flag_absence_is_read_only_even_with_other_execution_fields(
    tmp_path, capsys
):
    path = tmp_path / "no-execute.sqlite"
    sqlite3.connect(path).close()
    result = runner.main(
        [
            "--sqlite-path",
            str(path),
            "--migration-id",
            runner.MIGRATION_ID,
            "--canonical-source-sha",
            CANONICAL_SOURCE_SHA,
        ]
    )
    assert result == 0
    capsys.readouterr()
    conn = sqlite3.connect(path)
    assert runner.RECEIPT_TABLE_NAME not in _tables(conn)
    assert PROGRESS_TABLE_NAME not in _tables(conn)
    conn.close()


def test_runner_is_operator_only_and_has_no_compatibility_or_startup_call():
    runner_source = Path(runner.__file__).read_text(encoding="utf-8")
    app_source = (Path(runner.__file__).parents[1] / "app.py").read_text(
        encoding="utf-8"
    )

    assert "if __name__ == \"__main__\"" in runner_source
    assert "init_db(" not in runner_source
    assert "GO_DEPLOY" not in runner_source
    assert "adventure_progress_compatibility" not in runner_source
    assert "adventure_historical_mastery_v1" not in runner_source
    assert "incident_019b_zone_star_migration" not in app_source


@pytest.mark.parametrize(
    "extra",
    [
        ["--migration-id", runner.MIGRATION_ID, "--canonical-source-sha", CANONICAL_SOURCE_SHA],
        ["--migration-id", runner.MIGRATION_ID, "--canonical-source-sha", CANONICAL_SOURCE_SHA,
         "--owner-gate", "GO_WRONG"],
        ["--canonical-source-sha", CANONICAL_SOURCE_SHA, "--owner-gate", runner.OWNER_GATE],
    ],
)
def test_execution_without_exact_gate_contract_is_rejected(tmp_path, extra):
    path = tmp_path / "rejected.sqlite"
    conn = sqlite3.connect(path)
    conn.close()

    with pytest.raises(SystemExit):
        runner.main(["--execute", "--sqlite-path", str(path), *extra])
    conn = sqlite3.connect(path)
    assert runner.RECEIPT_TABLE_NAME not in _tables(conn)
    assert PROGRESS_TABLE_NAME not in _tables(conn)
    conn.close()


def test_cli_exact_execution_contract_applies_once(tmp_path, capsys):
    path = tmp_path / "cli.sqlite"
    result = runner.main(
        [
            "--execute",
            "--sqlite-path",
            str(path),
            "--migration-id",
            runner.MIGRATION_ID,
            "--owner-gate",
            runner.OWNER_GATE,
            "--canonical-source-sha",
            CANONICAL_SOURCE_SHA,
        ]
    )
    assert result == 0
    assert '"status": "APPLIED"' in capsys.readouterr().out
    conn = sqlite3.connect(path)
    assert conn.execute(
        f"SELECT COUNT(*) FROM {runner.RECEIPT_TABLE_NAME}"
    ).fetchone()[0] == 1
    conn.close()
