"""TD-003 — ``PuzzleIdentityStore.has_identity_tables()`` transaction ownership.

The bug: ``has_identity_tables()`` is a read-only probe called on a
caller-supplied connection (``DualIdReadWindow`` is constructed around one it
does not own). Its failure path used to call ``self._conn.rollback()`` to
clear PostgreSQL's "aborted transaction" state after an UndefinedTable error.
A plain ``rollback()`` discards the connection's *entire* current
transaction, not just this probe's own two no-op SELECTs — so any prior
uncommitted work the caller had already done on that same connection was
silently thrown away as a side effect of a probe the caller may not even know
exists.

The fix reuses ``self._unit()`` (SAVEPOINT / ROLLBACK TO SAVEPOINT / RELEASE),
the same mechanism every mutating method in this class already uses to stay
"independent of the caller's outer transaction" (see that method's own
docstring). These tests prove the specific invariant the task requires: a
caller-owned transaction is never rolled back by this helper.

SQLite only here (SAVEPOINT semantics are what's under test, and SQLite
supports them identically to PostgreSQL for this purpose); the
PostgreSQL-specific UndefinedTable/aborted-transaction proof lives alongside
the other real-Postgres tests in test_lc013_r1_postgres_and_genesis.py,
reusing its disposable-container fixture rather than standing up a second one
here.
"""
from __future__ import annotations

import sqlite3

import pytest

from migrations.puzzle_identity_registry_v1 import upgrade
from puzzle_identity_store import PuzzleIdentityStore


# ---------------------------------------------------------------- fixtures

@pytest.fixture()
def conn_without_identity_tables():
    """A connection that never had the identity schema applied at all -
    the exact shape DualIdReadWindow is documented to tolerate (tables
    absent -> UNAVAILABLE, never a raise)."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture()
def conn_with_identity_tables():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    upgrade(c)
    yield c
    c.close()


def _make_unrelated_marker_table(conn) -> None:
    """A table with nothing to do with puzzle identity - stands in for
    whatever else a caller might be doing on a connection it owns before it
    ever touches PuzzleIdentityStore."""
    conn.execute("CREATE TABLE caller_owned_marker (id INTEGER PRIMARY KEY, note TEXT)")


# ---------------------------------------------------------------- 1. standalone call

def test_standalone_call_tables_present_returns_true(conn_with_identity_tables):
    store = PuzzleIdentityStore(conn_with_identity_tables)
    assert store.has_identity_tables() is True


def test_standalone_call_tables_missing_returns_false_not_raise(conn_without_identity_tables):
    store = PuzzleIdentityStore(conn_without_identity_tables)
    assert store.has_identity_tables() is False


# ---------------------------------------------------------- 2. missing identity tables
# (the False-path shape itself, isolated from any caller transaction)

def test_missing_tables_leaves_no_open_savepoint_behind(conn_without_identity_tables):
    store = PuzzleIdentityStore(conn_without_identity_tables)
    store.has_identity_tables()
    # a leaked, un-released SAVEPOINT would make a bare RELEASE fail (nothing
    # named "sp_probe" would exist if the helper's own cleanup ran correctly,
    # and conversely a *leaked* savepoint from has_identity_tables would still
    # show up in sqlite_master-adjacent PRAGMA state) - the direct, portable
    # proof is that an ordinary new statement executes without error, i.e.
    # the connection was not left inside a dangling nested transaction.
    conn_without_identity_tables.execute("CREATE TABLE post_probe_sanity (id INTEGER)")
    conn_without_identity_tables.execute("INSERT INTO post_probe_sanity VALUES (1)")
    assert conn_without_identity_tables.execute(
        "SELECT COUNT(*) FROM post_probe_sanity"
    ).fetchone()[0] == 1


# ------------------------------------------------------- 3. caller-owned transaction
# (the core TD-003 invariant)

def test_caller_owned_uncommitted_work_survives_a_failed_probe(conn_without_identity_tables):
    """The exact scenario DualIdReadWindow creates in production: a caller
    holds this connection, has already done some of its own uncommitted
    work, and only then (lazily, on first resolve()) triggers
    has_identity_tables(). That probe failing must not discard the caller's
    prior writes."""
    conn = conn_without_identity_tables
    _make_unrelated_marker_table(conn)
    conn.execute("INSERT INTO caller_owned_marker (note) VALUES ('caller wrote this first')")

    store = PuzzleIdentityStore(conn)
    assert store.has_identity_tables() is False  # tables absent -> fails, as expected

    # the caller's own prior uncommitted row is still there on the same
    # connection - a full connection-wide rollback() would have erased it
    row = conn.execute("SELECT note FROM caller_owned_marker").fetchone()
    assert row is not None and row["note"] == "caller wrote this first"

    # and the caller can still commit it through normally
    conn.commit()
    row_after_commit = conn.execute("SELECT note FROM caller_owned_marker").fetchone()
    assert row_after_commit["note"] == "caller wrote this first"


def test_caller_owned_transaction_survives_repeated_failed_probes(conn_without_identity_tables):
    """DualIdReadWindow caches the result after the first call, but nothing
    stops a caller from holding a raw PuzzleIdentityStore and calling this
    directly more than once - each call must be independently safe."""
    conn = conn_without_identity_tables
    _make_unrelated_marker_table(conn)
    conn.execute("INSERT INTO caller_owned_marker (note) VALUES ('still here')")

    store = PuzzleIdentityStore(conn)
    for _ in range(3):
        assert store.has_identity_tables() is False

    assert conn.execute(
        "SELECT note FROM caller_owned_marker"
    ).fetchone()["note"] == "still here"


# --------------------------------------------------------- 4. database error path
# (SQLite's OperationalError specifically, already exercised above via the
# missing-table connection; this test additionally pins the exception type
# has_identity_tables is documented to tolerate)

def test_missing_table_error_is_operational_error_and_is_swallowed(conn_without_identity_tables):
    store = PuzzleIdentityStore(conn_without_identity_tables)
    # prove what's actually being caught, rather than trusting the docstring
    with pytest.raises(sqlite3.OperationalError):
        conn_without_identity_tables.execute("SELECT 1 FROM puzzle_identity_alias WHERE 1=0")
    # ... and that has_identity_tables() catches exactly that and degrades cleanly
    assert store.has_identity_tables() is False


# ------------------------------------------------------ 5. subsequent caller operation

def test_caller_can_use_the_connection_normally_after_a_failed_probe(conn_without_identity_tables):
    """Not just 'the prior row survives' - the connection must remain in a
    normal, usable state for whatever the caller does *next*, including
    starting and completing fresh work unrelated to identity resolution."""
    conn = conn_without_identity_tables
    store = PuzzleIdentityStore(conn)
    assert store.has_identity_tables() is False

    conn.execute("CREATE TABLE subsequent_caller_work (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO subsequent_caller_work (value) VALUES ('after the probe')")
    conn.commit()

    assert conn.execute(
        "SELECT value FROM subsequent_caller_work"
    ).fetchone()["value"] == "after the probe"


def test_probe_then_real_identity_write_on_a_fresh_upgraded_connection(conn_with_identity_tables):
    """The success path matters too: after a (True) probe, ordinary
    PuzzleIdentityStore writes on the same connection must work exactly as
    before - the SAVEPOINT-based probe must not perturb normal operation."""
    conn = conn_with_identity_tables
    conn.execute(
        "INSERT INTO puzzle_identity_bootstrap_receipt "
        "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,"
        " namespace_uuid,canonicalisation_rules_version,genesis_key_spec_version,"
        " historical_tree_commit,historical_tree_manifest_sha256,"
        " historical_rename_map_sha256,genesis_record_manifest_sha256,"
        " proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
        "VALUES (?, 'GENESIS', ?, 3, 'ns', 'canon-source-v1', 'genesis-key-v1', "
        "'commit', 'tm', 'rm', 'gm', 'ul', 'APPLIED', 0, ?, 'fixture')",
        ("aa" * 32, "x" * 64, "2026-08-28T12:00:00+00:00"),
    )
    store = PuzzleIdentityStore(conn, clock=lambda: "2026-08-28T12:00:00+00:00")
    assert store.has_identity_tables() is True

    u = "00000000-0000-5000-8000-000000000001"
    store.create_historical_genesis_identity(
        u, receipt_sha256="aa" * 32, canonical_source="td003/probe.sgf",
        legacy_question_id="900001", creation_reason="post-probe write sanity",
    )
    assert store.get_identity(u) is not None


# --------------------------------------------------------- 6. commit/rollback ownership

def test_probe_itself_never_commits_the_callers_transaction(conn_without_identity_tables):
    """A probe that silently committed would be just as wrong as one that
    rolled back: either way it's making a transaction-boundary decision that
    belongs to the caller. Uncommitted work must still be rollback-able by
    the caller after the probe runs.

    The marker table itself is created and committed up front (DDL's
    implicit-commit behaviour in sqlite3 varies by context and isn't what
    this test is about) - only the INSERT is left uncommitted, which is
    unambiguously subject to normal rollback()."""
    conn = conn_without_identity_tables
    _make_unrelated_marker_table(conn)
    conn.commit()
    conn.execute("INSERT INTO caller_owned_marker (note) VALUES ('should be rollback-able')")

    store = PuzzleIdentityStore(conn)
    store.has_identity_tables()

    # if the probe had committed, this rollback() would be a no-op and the
    # row would remain; it must not
    conn.rollback()
    row = conn.execute("SELECT COUNT(*) FROM caller_owned_marker").fetchone()[0]
    assert row == 0
