import os

import pytest

from migrations.sgf_admin_workbench_v1 import (
    TABLE_SPECS,
    SchemaMismatch,
    upgrade,
    validate_schema,
)


def _connect_or_skip():
    if os.environ.get("SGF_SCHEMA_MIGRATION_DISPOSABLE") != "1":
        pytest.skip("requires an explicitly-marked disposable PostgreSQL database")
    url = os.environ.get("SGF_SCHEMA_MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("SGF_SCHEMA_MIGRATION_DATABASE_URL is not set")
    import psycopg2

    return psycopg2.connect(url)


def _drop_workbench(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            "DROP TABLE IF EXISTS "
            + ", ".join(f"public.{name}" for name in reversed(tuple(TABLE_SPECS)))
            + " CASCADE"
        )
    conn.commit()


def test_contract_is_exactly_the_seven_pr331_tables():
    assert tuple(TABLE_SPECS) == (
        "sgf_workbench_reports",
        "sgf_workbench_review_items",
        "sgf_workbench_staged_repairs",
        "sgf_workbench_batches",
        "sgf_workbench_batch_items",
        "sgf_workbench_audit",
        "sgf_workbench_direct_versions",
    )


def test_dry_run_is_non_mutating_and_rerun_is_idempotent():
    conn = _connect_or_skip()
    try:
        _drop_workbench(conn)
        dry = upgrade(conn, dry_run=True)
        assert dry["dry_run"] is True
        assert dry["planned_create"] == list(TABLE_SPECS)
        assert validate_schema(conn)["present"] == []
        result = upgrade(conn)
        conn.commit()
        assert set(result["created"]) == set(TABLE_SPECS)
        second = upgrade(conn)
        conn.commit()
        assert second["created"] == []
        assert second["missing"] == []
    finally:
        conn.close()


def test_existing_shape_mismatch_fails_closed_without_partial_creation():
    conn = _connect_or_skip()
    try:
        _drop_workbench(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE public.sgf_workbench_reports "
                "(id BIGSERIAL PRIMARY KEY, source TEXT NOT NULL, unexpected TEXT)"
            )
        conn.commit()
        with pytest.raises(SchemaMismatch, match="columns differ"):
            upgrade(conn)
        conn.rollback()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name LIKE 'sgf_workbench_%' "
                "ORDER BY table_name"
            )
            assert [row[0] for row in cursor.fetchall()] == ["sgf_workbench_reports"]
    finally:
        conn.close()


def test_failed_transaction_does_not_leave_new_tables():
    conn = _connect_or_skip()
    try:
        _drop_workbench(conn)
        # A mismatch is discovered before any CREATE, so rollback is explicit
        # and the empty-table contract remains observable after failure.
        with conn.cursor() as cursor:
            cursor.execute("CREATE TABLE public.sgf_workbench_reports (id BIGINT PRIMARY KEY)")
        conn.commit()
        with pytest.raises(SchemaMismatch):
            upgrade(conn)
        conn.rollback()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name LIKE 'sgf_workbench_%' "
                "ORDER BY table_name"
            )
            assert [row[0] for row in cursor.fetchall()] == ["sgf_workbench_reports"]
    finally:
        conn.close()
