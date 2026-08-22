"""Optional disposable-PostgreSQL acceptance for the route-free S1 contract."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from urllib.parse import urlsplit

import pytest

from spirit_lineage_auditor import audit_companion_snapshot, read_snapshot_tables
from test_d007_six_spirit_s1_lineage import _valid_snapshot


def _postgres_url():
    url = os.environ.get("D007_SPIRIT_POSTGRES_URL")
    if not url or os.environ.get("D007_SPIRIT_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d007" not in database:
        pytest.skip("refusing PostgreSQL URL without an explicitly disposable database name")
    return url


def _connect(url):
    import psycopg2

    return psycopg2.connect(url)


def test_postgres_s1_snapshot_audit_and_operation_identity_are_safe():
    url = _postgres_url()
    from psycopg2.extras import Json

    setup = _connect(url)
    try:
        with setup.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS d007_s1_operations")
            cursor.execute("DROP TABLE IF EXISTS d007_s1_snapshot")
            cursor.execute(
                "CREATE TABLE d007_s1_snapshot (id BIGSERIAL PRIMARY KEY, snapshot JSONB NOT NULL)"
            )
            cursor.execute(
                "CREATE TABLE d007_s1_operations ("
                "user_id INTEGER NOT NULL, operation_type TEXT NOT NULL, operation_id TEXT NOT NULL, "
                "request_fingerprint TEXT NOT NULL, PRIMARY KEY(user_id, operation_type, operation_id))"
            )
            cursor.execute(
                "INSERT INTO d007_s1_snapshot(snapshot) VALUES (%s)",
                (Json(_valid_snapshot()),),
            )
        setup.commit()
    finally:
        setup.close()

    reader = _connect(url)
    try:
        with reader.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM d007_s1_snapshot")
            before = cursor.fetchone()[0]
        rows = read_snapshot_tables(reader, {"snapshot_rows": "d007_s1_snapshot"})
        report = audit_companion_snapshot(rows["snapshot_rows"][0]["snapshot"])
        assert report.valid, report.as_dict()
        assert report.auditor_mutation_capability == "NO"
        with reader.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM d007_s1_snapshot")
            after = cursor.fetchone()[0]
        assert before == after == 1
    finally:
        reader.close()

    barrier = Barrier(2)

    def reserve_once():
        conn = _connect(url)
        try:
            barrier.wait(timeout=10)
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO d007_s1_operations(user_id,operation_type,operation_id,request_fingerprint) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING operation_id",
                    (1, "FEED", "same-operation", "same-fingerprint"),
                )
                inserted = cursor.fetchone() is not None
            conn.commit()
            return inserted
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        inserted = list(pool.map(lambda _: reserve_once(), range(2)))
    assert sum(inserted) == 1

    cleanup = _connect(url)
    try:
        with cleanup.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM d007_s1_operations")
            assert cursor.fetchone()[0] == 1
            cursor.execute("DROP TABLE d007_s1_operations")
            cursor.execute("DROP TABLE d007_s1_snapshot")
        cleanup.commit()
    finally:
        cleanup.close()
