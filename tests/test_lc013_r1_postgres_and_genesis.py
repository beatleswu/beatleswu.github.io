"""LC013-R1 — the puzzle-identity storage MUST execute on real PostgreSQL.

A disposable ``postgres:16.14-alpine`` container is started per module.  The
readiness wait tolerates the cold-start window where the published port already
forwards but the target database is still being created / the server is
restarting ("database ... does not exist" / "server closed the connection
unexpectedly").  If Docker or the image is unavailable the module skips; a
container that never becomes ready is a FAILURE (RESULT=BLOCKED_POSTGRES_INFRA),
never a silent pass.
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import time
import uuid

import pytest

from db import PostgresConnectionWrapper
from migrations.puzzle_identity_registry_v1 import (
    _table_ddl,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)
from puzzle_identity_store import PuzzleIdentityError, PuzzleIdentityStore

_IMAGE = "postgres:16.14-alpine"
_USER, _PW, _DB = "lc13r1", "lc13r1_disposable", "lc13r1"
_FIXED = "2026-08-28T12:00:00+00:00"
_SYNTH_NS = uuid.UUID("00000000-0000-4000-8000-000000000000")


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8")


def _wait_ready(name: str, url: str, *, budget: float = 360.0) -> None:
    """Cold-start on Windows Docker publishes the port well before the target
    DB exists / the entrypoint's temp server has been swapped for the real one.
    Gate on `pg_isready` + an in-container `SELECT 1` on the target DB first, then
    confirm the host psycopg2 path — tolerating the transient error states.
    """
    import psycopg2

    deadline = time.monotonic() + budget
    last = None
    # 1) server + target DB reachable from inside the container
    while time.monotonic() < deadline:
        r = _docker("exec", name, "psql", "-U", _USER, "-d", _DB, "-tAc", "SELECT 1")
        if r.returncode == 0 and r.stdout.strip() == "1":
            break
        last = (r.stderr or r.stdout).strip()
        time.sleep(2.0)
    else:
        logs = _docker("logs", "--tail", "40", name).stdout
        raise RuntimeError(f"disposable PostgreSQL never served target DB: {last}\n{logs}")
    # 2) host -> published port
    while time.monotonic() < deadline:
        try:
            c = psycopg2.connect(url, connect_timeout=4)
            cur = c.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            c.close()
            return
        except Exception as err:  # noqa: BLE001 - transient cold-start states
            last = err
            time.sleep(1.5)
    logs = _docker("logs", "--tail", "40", name).stdout
    raise RuntimeError(f"disposable PostgreSQL host connect never succeeded: {last}\n{logs}")


@pytest.fixture(scope="module")
def pg_url():
    if shutil.which("docker") is None:
        pytest.skip("docker unavailable; real-PostgreSQL proof skipped")
    name = f"lc13r1-pg-{uuid.uuid4().hex[:12]}"
    run = _docker(
        "run", "--rm", "--detach", "--name", name,
        "--env", f"POSTGRES_USER={_USER}",
        "--env", f"POSTGRES_PASSWORD={_PW}",
        "--env", f"POSTGRES_DB={_DB}",
        "--publish", "127.0.0.1::5432", _IMAGE,
    )
    if run.returncode != 0:
        pytest.skip(f"disposable PostgreSQL unavailable: {run.stderr.strip() or run.stdout.strip()}")
    try:
        insp = _docker("inspect", "--format",
                       '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}', name)
        port = insp.stdout.strip()
        assert port.isdigit(), f"no published port: {insp.stderr}"
        url = f"postgresql://{_USER}:{_PW}@127.0.0.1:{port}/{_DB}"
        _wait_ready(name, url)
        yield url
    finally:
        _docker("rm", "--force", name)


@pytest.fixture()
def pg_conn(pg_url):
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(pg_url, cursor_factory=DictCursor)
    conn = PostgresConnectionWrapper(raw, pooled=False)
    try:
        yield conn
    finally:
        try:
            downgrade_for_isolated_test(conn)
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()


def _seed_receipt(conn) -> str:
    rid = (uuid.uuid4().hex + uuid.uuid4().hex)[:64]  # 64 hex chars
    conn.execute(
        "INSERT INTO puzzle_identity_bootstrap_receipt "
        "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,"
        " namespace_uuid,canonicalisation_rules_version,genesis_key_spec_version,"
        " historical_tree_commit,historical_tree_manifest_sha256,"
        " historical_rename_map_sha256,genesis_record_manifest_sha256,"
        " proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
        "VALUES (?, 'GENESIS', ?, 3, 'ns', 'canon-source-v1', 'genesis-key-v1', "
        "'commit', 'tm', 'rm', 'gm', 'ul', 'APPLIED', 0, ?, 'fixture')",
        (rid, "x" * 64, _FIXED),
    )
    return rid


def _v5(name: str) -> str:
    return str(uuid.uuid5(_SYNTH_NS, "lc13r1:" + name))


# ------------------------------------------------------------------ schema (§5/§7)

def test_pg_fk_creation_order_and_schema(pg_conn):
    res = upgrade(pg_conn)
    assert res["dialect"] == "postgres"
    assert res["valid"], res
    v = validate_schema(pg_conn)
    assert not v["missing_tables"] and not v["missing_columns"] and not v["missing_triggers"]


def test_pg_fk_order_statement_sequence():
    ddl = _table_ddl("postgres")
    # bootstrap_receipt parent must be created before the registry that FKs it
    assert "CREATE TABLE IF NOT EXISTS puzzle_identity_bootstrap_receipt" in ddl[0]
    assert "CREATE TABLE IF NOT EXISTS puzzle_identity_registry" in ddl[1]
    assert "REFERENCES puzzle_identity_bootstrap_receipt(receipt_sha256)" in ddl[1]


# ------------------------------------------------------------------ boolean (§6)

def test_pg_boolean_ddl_insert_update_resolve(pg_conn):
    upgrade(pg_conn)
    rid = _seed_receipt(pg_conn)
    st = PuzzleIdentityStore(pg_conn, clock=lambda: _FIXED)
    u = _v5("bool/1.sgf")
    st.create_historical_genesis_identity(
        u, receipt_sha256=rid, canonical_source="bool/1.sgf",
        legacy_question_id="7001", creation_reason="pg bool")
    # BOOLEAN column really is boolean
    row = pg_conn.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='puzzle_identity_alias' AND column_name='is_current'"
    ).fetchone()
    assert row[0] == "boolean"
    # insert wrote TRUE; a superseded alias is FALSE; resolve() sees the current one
    st.record_rename(u, from_path="bool/1.sgf", to_path="bool/2.sgf",
                     actor="admin", reason="reorg")
    cur_true = pg_conn.execute(
        "SELECT COUNT(*) FROM puzzle_identity_alias "
        "WHERE alias_kind='CURRENT_SOURCE_PATH' AND is_current AND source_record_uuid=?",
        (u,)).fetchone()[0]
    cur_false = pg_conn.execute(
        "SELECT COUNT(*) FROM puzzle_identity_alias "
        "WHERE alias_kind='CURRENT_SOURCE_PATH' AND NOT is_current AND source_record_uuid=?",
        (u,)).fetchone()[0]
    assert cur_true == 1 and cur_false == 1
    assert st.resolve("CURRENT_SOURCE_PATH", "bool/2.sgf",
                      alias_context="post-genesis")["source_record_uuid"] == u


def test_pg_partial_unique_alias_index(pg_conn):
    upgrade(pg_conn)
    rid = _seed_receipt(pg_conn)
    st = PuzzleIdentityStore(pg_conn, clock=lambda: _FIXED)
    u1 = _v5("p/1.sgf")
    st.create_historical_genesis_identity(
        u1, receipt_sha256=rid, canonical_source="p/1.sgf",
        legacy_question_id="8001", creation_reason="x")
    u2 = st.create_native_identity(creation_reason="second")
    import psycopg2
    with pytest.raises(psycopg2.errors.UniqueViolation):
        pg_conn.execute(
            "INSERT INTO puzzle_identity_alias "
            "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
            " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
            (u2, "LEGACY_QUESTION_ID", "8001", "genesis-v1", "RECORDED",
             True, _FIXED, "attacker"))
    pg_conn.rollback()


# ------------------------------------------------------------------ repository (§7)

def test_pg_repository_lifecycle(pg_conn):
    upgrade(pg_conn)
    rid = _seed_receipt(pg_conn)
    st = PuzzleIdentityStore(pg_conn, clock=lambda: _FIXED)

    g = _v5("life/1.sgf")
    st.create_historical_genesis_identity(
        g, receipt_sha256=rid, canonical_source="life/1.sgf",
        legacy_question_id="9001", creation_reason="genesis")
    n = st.create_native_identity(creation_reason="native", current_source_path="new/1.sgf")
    assert uuid.UUID(n).version == 4

    st.record_rename(g, from_path="life/1.sgf", to_path="life/2.sgf",
                     actor="admin", reason="rename")
    st.record_move(g, from_path="life/2.sgf", to_path="lifeB/2.sgf",
                   actor="admin", reason="move")
    assert st.resolve("LEGACY_QUESTION_ID", "9001")["source_record_uuid"] == g

    st.retire_identity(g, reason="withdrawn", actor="admin")
    assert st.resolve("LEGACY_QUESTION_ID", "9001")["status"] == "RETIRED"
    st.restore_identity(g, reason="reinstated", actor="admin")
    assert st.resolve("LEGACY_QUESTION_ID", "9001")["status"] == "EXACT"
    assert [e["event_type"] for e in st.get_lineage(g)][:3] == ["GENESIS", "RENAME", "MOVE"]


# ------------------------------------------------------------------ triggers (§7)

def test_pg_triggers_enforce_immutability_and_append_only(pg_conn):
    import psycopg2
    upgrade(pg_conn)
    rid = _seed_receipt(pg_conn)
    st = PuzzleIdentityStore(pg_conn, clock=lambda: _FIXED)
    u = _v5("trg/1.sgf")
    st.create_historical_genesis_identity(
        u, receipt_sha256=rid, canonical_source="trg/1.sgf",
        legacy_question_id="9100", creation_reason="genesis")
    pg_conn.commit()  # survive the rollbacks each trigger assertion forces

    def _rejected(sql, params=()):
        with pytest.raises(psycopg2.errors.RaiseException):
            pg_conn.execute(sql, params)
        pg_conn.rollback()

    _rejected("UPDATE puzzle_identity_registry SET source_record_uuid=? WHERE source_record_uuid=?",
              (_v5("other"), u))
    _rejected("UPDATE puzzle_identity_registry SET identity_kind='NATIVE_UUIDV4' "
              "WHERE source_record_uuid=?", (u,))
    _rejected("UPDATE puzzle_identity_alias SET alias_value='hacked' WHERE source_record_uuid=?", (u,))
    _rejected("UPDATE puzzle_identity_lineage SET reason='x' WHERE source_record_uuid=?", (u,))
    _rejected("DELETE FROM puzzle_identity_lineage WHERE source_record_uuid=?", (u,))
    _rejected("UPDATE puzzle_identity_bootstrap_receipt SET status='ABORTED'")
    _rejected("DELETE FROM puzzle_identity_bootstrap_receipt")

    # identity + its creation lineage survived every rejected write
    assert st.get_identity(u)["identity_kind"] == "HISTORICAL_GENESIS"
    assert [e["event_type"] for e in st.get_lineage(u)] == ["GENESIS"]


# ------------------------------------------------------------------ rename/move fail-closed (§15) — both dialects

@pytest.fixture()
def sqlite_store():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    c.execute(
        "INSERT INTO puzzle_identity_bootstrap_receipt "
        "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,"
        " namespace_uuid,canonicalisation_rules_version,genesis_key_spec_version,"
        " historical_tree_commit,historical_tree_manifest_sha256,"
        " historical_rename_map_sha256,genesis_record_manifest_sha256,"
        " proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
        "VALUES (?, 'GENESIS', ?, 3, 'ns','canon-source-v1','genesis-key-v1',"
        "'c','tm','rm','gm','ul','APPLIED',0,?,'fx')",
        ("a1" * 32, "x" * 64, _FIXED),
    )
    st = PuzzleIdentityStore(c, clock=lambda: _FIXED)
    st.create_historical_genesis_identity(
        _v5("fc/1.sgf"), receipt_sha256="a1" * 32, canonical_source="fc/1.sgf",
        legacy_question_id="9200", creation_reason="genesis")
    return c, st, _v5("fc/1.sgf")


def test_correct_from_path_rename_and_move(sqlite_store):
    _c, st, u = sqlite_store
    st.record_rename(u, from_path="fc/1.sgf", to_path="fc/2.sgf", actor="a", reason="r")
    st.record_move(u, from_path="fc/2.sgf", to_path="fcB/2.sgf", actor="a", reason="m")
    cur = [a["alias_value"] for a in st.list_aliases(u, current_only=True)
           if a["alias_kind"] == "CURRENT_SOURCE_PATH"]
    assert cur == ["fcB/2.sgf"]


def test_stale_from_path_rename_fails_closed(sqlite_store):
    _c, st, u = sqlite_store
    before = st.get_lineage(u)
    with pytest.raises(PuzzleIdentityError):
        st.record_rename(u, from_path="WRONG/1.sgf", to_path="fc/2.sgf", actor="a", reason="r")
    assert st.get_lineage(u) == before  # zero mutation
    assert [a["alias_value"] for a in st.list_aliases(u, current_only=True)
            if a["alias_kind"] == "CURRENT_SOURCE_PATH"] == ["fc/1.sgf"]


def test_stale_from_path_move_fails_closed(sqlite_store):
    _c, st, u = sqlite_store
    before = st.get_lineage(u)
    with pytest.raises(PuzzleIdentityError):
        st.record_move(u, from_path="fabricated.sgf", to_path="fc/2.sgf", actor="a", reason="m")
    assert st.get_lineage(u) == before
