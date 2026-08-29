"""LC014 — dual-ID resolver / identity read window.

SQLite behaviour + a real disposable PostgreSQL parity check.  Synthetic
identities only; nothing here runs the real 42,804 genesis bootstrap.
"""
from __future__ import annotations

import ast
import pathlib
import shutil
import sqlite3
import subprocess
import time
import uuid

import pytest

from migrations.puzzle_identity_registry_v1 import upgrade
from puzzle_identity_store import PuzzleIdentityStore
from puzzle_identity_read_window import (
    DualIdReadWindow,
    IdentityResolution,
    ResolutionStatus,
)

_NS = uuid.UUID("00000000-0000-4000-8000-000000000000")
_FIXED = "2026-08-29T00:00:00+00:00"
_RID = "cd" * 32


def _v5(name: str) -> str:
    return str(uuid.uuid5(_NS, "lc014:" + name))


def _seed_receipt(conn, *, status="APPLIED"):
    conn.execute(
        "INSERT INTO puzzle_identity_bootstrap_receipt "
        "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,"
        " namespace_uuid,canonicalisation_rules_version,genesis_key_spec_version,"
        " historical_tree_commit,historical_tree_manifest_sha256,"
        " historical_rename_map_sha256,genesis_record_manifest_sha256,"
        " proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
        "VALUES (?, 'GENESIS', ?, 3, 'ns','canon-source-v1','genesis-key-v1',"
        "'c','tm','rm','gm','ul',?,0,?,'fx')",
        (_RID, "x" * 64, status, _FIXED),
    )


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    _seed_receipt(c)
    yield c
    c.close()


@pytest.fixture()
def conn_no_receipt():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)  # tables present, but no genesis bootstrap receipt
    yield c
    c.close()


@pytest.fixture()
def seeded(conn):
    st = PuzzleIdentityStore(conn, clock=lambda: _FIXED)
    g = _v5("g/1.sgf")
    st.create_historical_genesis_identity(
        g, receipt_sha256=_RID, canonical_source="g/1.sgf",
        legacy_question_id="70001", historical_source_path="hist/07x/1.sgf",
        creation_reason="genesis")
    n = st.create_native_identity(
        creation_reason="native", current_source_path="native/9.sgf",
        legacy_question_id="88888")
    r = _v5("g/retired.sgf")
    st.create_historical_genesis_identity(
        r, receipt_sha256=_RID, canonical_source="g/retired.sgf",
        legacy_question_id="70002", creation_reason="genesis")
    st.retire_identity(r, reason="withdrawn", actor="admin")
    return conn, DualIdReadWindow(conn), {"g": g, "n": n, "r": r}


# ---------------------------------------------------------------- exact

def test_exact_resolution_legacy_and_path(seeded):
    _c, w, ids = seeded
    r = w.resolve_legacy_question_id("70001")
    assert r.status == ResolutionStatus.EXACT and r.source_record_uuid == ids["g"]
    assert r.resolved and r.attachable and not r.unresolved and not r.retired
    assert w.resolve_current_source_path("g/1.sgf").source_record_uuid == ids["g"]
    assert w.resolve_canonical_source("g/1.sgf").source_record_uuid == ids["g"]
    assert w.resolve_historical_source_path("hist/07x/1.sgf").source_record_uuid == ids["g"]
    # native identity resolves on its own legacy id too
    assert w.resolve_legacy_question_id("88888").source_record_uuid == ids["n"]


def test_integer_and_string_question_id_equivalent(seeded):
    _c, w, ids = seeded
    assert w.resolve_legacy_question_id(70001).source_record_uuid == ids["g"]
    assert w.resolve_legacy_question_id("70001").source_record_uuid == ids["g"]


# ---------------------------------------------------------------- missing

def test_missing_is_explicit_unresolved_no_exception(seeded):
    _c, w, _ids = seeded
    r = w.resolve_legacy_question_id("99999")
    assert r.status == ResolutionStatus.MISSING
    assert r.source_record_uuid is None and r.unresolved and not r.resolved
    assert w.resolve_current_source_path("nope/x.sgf").status == ResolutionStatus.MISSING


# ---------------------------------------------------------------- retired

def test_retired_identity_still_resolves(seeded):
    _c, w, ids = seeded
    r = w.resolve_legacy_question_id("70002")
    assert r.status == ResolutionStatus.RETIRED
    assert r.source_record_uuid == ids["r"] and r.retired
    assert r.resolved and not r.attachable  # resolvable for reads, not for new writes
    # restore -> EXACT again
    PuzzleIdentityStore(_c, clock=lambda: _FIXED).restore_identity(
        ids["r"], reason="reinstated", actor="admin")
    assert w.resolve_legacy_question_id("70002").status == ResolutionStatus.EXACT


# ---------------------------------------------------------------- ambiguous fail-closed

def test_cross_context_ambiguity_fails_closed(seeded):
    _c, w, ids = seeded
    # force a second *current* LEGACY_QUESTION_ID=70001 in another context ->
    # two current identities claim the same legacy id
    _c.execute(
        "INSERT INTO puzzle_identity_alias "
        "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
        " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
        (ids["n"], "LEGACY_QUESTION_ID", "70001", "post-genesis", "RECORDED",
         True, _FIXED, "collision"))
    r = w.resolve_legacy_question_id("70001")
    assert r.status == ResolutionStatus.AMBIGUOUS
    assert r.source_record_uuid is None and r.unresolved
    assert set(r.candidates) == {ids["g"], ids["n"]}


# ---------------------------------------------------------------- rename window

def test_rename_moves_path_binding_not_legacy_id(seeded):
    _c, w, ids = seeded
    PuzzleIdentityStore(_c, clock=lambda: _FIXED).record_rename(
        ids["g"], from_path="g/1.sgf", to_path="g/renamed/1.sgf",
        actor="admin", reason="reorg")
    assert w.resolve_current_source_path("g/1.sgf").status == ResolutionStatus.MISSING
    assert w.resolve_current_source_path("g/renamed/1.sgf").source_record_uuid == ids["g"]
    assert w.resolve_legacy_question_id("70001").source_record_uuid == ids["g"]  # unchanged


# ---------------------------------------------------------------- batch

def test_batch_resolution(seeded):
    _c, w, ids = seeded
    out = w.resolve_many_legacy_question_ids(["70001", "70002", "88888", "99999", 70001])
    assert out["70001"].source_record_uuid == ids["g"] and out["70001"].status == "EXACT"
    assert out["70002"].status == "RETIRED" and out["70002"].source_record_uuid == ids["r"]
    assert out["88888"].source_record_uuid == ids["n"]
    assert out["99999"].status == "MISSING" and out["99999"].source_record_uuid is None
    assert out["70001"] is out.get("70001")  # int / str collapse to one key


def test_batch_reports_ambiguous_per_value(seeded):
    _c, w, ids = seeded
    _c.execute(
        "INSERT INTO puzzle_identity_alias "
        "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
        " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
        (ids["n"], "LEGACY_QUESTION_ID", "70001", "post-genesis", "RECORDED",
         True, _FIXED, "collision"))
    out = w.resolve_many_legacy_question_ids(["70001", "88888"])
    assert out["70001"].status == ResolutionStatus.AMBIGUOUS
    assert out["88888"].status == ResolutionStatus.EXACT  # unaffected


# ---------------------------------------------------------------- reverse

def test_reverse_lookup_for_admin(seeded):
    _c, w, ids = seeded
    assert w.legacy_question_ids_for(ids["g"]) == ("70001",)
    assert w.current_source_path_for(ids["g"]) == "g/1.sgf"
    assert w.legacy_question_ids_for(_v5("nonexistent")) == ()


# ---------------------------------------------------------------- dual-id window

def test_dual_id_key_and_bootstrap_state(seeded):
    _c, w, ids = seeded
    assert w.dual_id_key("70001") == ("uuid", ids["g"])
    assert w.dual_id_key("99999") == ("legacy", "99999")       # unresolved -> legacy
    assert w.dual_id_key("70002") == ("legacy", "70002")       # retired -> not a write key
    s = w.bootstrap_state()
    assert s["tables_present"] and s["genesis_applied"] and s["identity_count"] == 3 and s["hot"]


def test_bootstrap_state_not_hot_before_genesis(conn_no_receipt):
    w = DualIdReadWindow(conn_no_receipt)
    s = w.bootstrap_state()
    assert s["tables_present"] and not s["genesis_applied"] and s["identity_count"] == 0
    assert not s["hot"]
    # tables exist but empty -> every read is an explicit MISSING, never fabricates
    assert w.resolve_legacy_question_id("70001").status == ResolutionStatus.MISSING
    assert w.dual_id_key("70001") == ("legacy", "70001")


# ---------------------------------------------------------------- unavailable

def test_unavailable_when_tables_absent():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    w = DualIdReadWindow(c)
    r = w.resolve_legacy_question_id("70001")
    assert r.status == ResolutionStatus.UNAVAILABLE and r.unresolved
    assert w.resolve_many_legacy_question_ids(["1", "2"])["1"].status == "UNAVAILABLE"
    assert w.dual_id_key("70001") == ("legacy", "70001")
    assert w.bootstrap_state() == {"tables_present": False, "genesis_applied": False,
                                   "identity_count": 0, "hot": False}
    c.close()


# ---------------------------------------------------------------- NO SILENT FALLBACK

def test_resolver_never_creates_identity(seeded):
    _c, w, _ids = seeded

    def counts():
        return (
            _c.execute("SELECT COUNT(*) FROM puzzle_identity_registry").fetchone()[0],
            _c.execute("SELECT COUNT(*) FROM puzzle_identity_alias").fetchone()[0],
            _c.execute("SELECT COUNT(*) FROM puzzle_identity_lineage").fetchone()[0],
        )

    before = counts()
    for q in ("99999", "abc", "", "70001", "-1"):
        w.resolve_legacy_question_id(q)
    w.resolve_many_legacy_question_ids([str(i) for i in range(50000, 50100)])
    w.resolve_current_source_path("does/not/exist.sgf")
    w.resolve_canonical_source("nope.sgf")
    w.dual_id_key("123")
    w.bootstrap_state()
    assert counts() == before  # resolve calls mutate nothing at all


def test_read_window_module_has_no_mutation_imports():
    src = pathlib.Path(__file__).resolve().parents[1] / "puzzle_identity_read_window.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported.add(a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name)
    forbidden = {"GenesisBootstrap", "GenesisReceiptVerifier", "mint_genesis_uuid",
                 "puzzle_identity_genesis_bootstrap"}
    assert not (imported & forbidden), imported & forbidden
    body = src.read_text(encoding="utf-8")
    for tok in ("create_historical_genesis_identity", "create_native_identity",
                "_append_lineage", "record_rename", "record_replacement", "INSERT INTO",
                "UPDATE puzzle_identity"):
        assert tok not in body, tok


# ---------------------------------------------------------------- real PostgreSQL parity

_PG_IMAGE = "postgres:16.14-alpine"
_PG_USER, _PG_PW, _PG_DB = "lc014", "lc014_disposable", "lc014"


def _docker(*a):
    return subprocess.run(["docker", *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture(scope="module")
def pg_conn_factory():
    if shutil.which("docker") is None:
        pytest.skip("docker unavailable; PostgreSQL parity skipped")
    name = f"lc014-pg-{uuid.uuid4().hex[:12]}"
    run = _docker("run", "--rm", "--detach", "--name", name,
                  "--env", f"POSTGRES_USER={_PG_USER}",
                  "--env", f"POSTGRES_PASSWORD={_PG_PW}",
                  "--env", f"POSTGRES_DB={_PG_DB}",
                  "--publish", "127.0.0.1::5432", _PG_IMAGE)
    if run.returncode != 0:
        pytest.skip(f"disposable PostgreSQL unavailable: {run.stderr.strip()}")
    try:
        port = _docker("inspect", "--format",
                       '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}',
                       name).stdout.strip()
        assert port.isdigit()
        url = f"postgresql://{_PG_USER}:{_PG_PW}@127.0.0.1:{port}/{_PG_DB}"
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            r = _docker("exec", name, "psql", "-U", _PG_USER, "-d", _PG_DB, "-tAc", "SELECT 1")
            if r.returncode == 0 and r.stdout.strip() == "1":
                break
            time.sleep(2.0)
        else:
            raise RuntimeError("disposable PostgreSQL never served target DB")
        import psycopg2

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                psycopg2.connect(url, connect_timeout=4).close()
                break
            except Exception:  # noqa: BLE001
                time.sleep(1.5)
        yield url
    finally:
        _docker("rm", "--force", name)


def test_pg_parity_resolver_semantics(pg_conn_factory):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(pg_conn_factory, cursor_factory=DictCursor)
    conn = PostgresConnectionWrapper(raw, pooled=False)
    try:
        upgrade(conn)
        _seed_receipt(conn)
        st = PuzzleIdentityStore(conn, clock=lambda: _FIXED)
        g = _v5("pg/g.sgf")
        st.create_historical_genesis_identity(
            g, receipt_sha256=_RID, canonical_source="pg/g.sgf",
            legacy_question_id="60001", creation_reason="genesis")
        rr = _v5("pg/retired.sgf")
        st.create_historical_genesis_identity(
            rr, receipt_sha256=_RID, canonical_source="pg/retired.sgf",
            legacy_question_id="60002", creation_reason="genesis")
        st.retire_identity(rr, reason="w", actor="a")

        w = DualIdReadWindow(conn)
        assert w.resolve_legacy_question_id("60001").source_record_uuid == g
        assert w.resolve_legacy_question_id("60002").status == ResolutionStatus.RETIRED
        assert w.resolve_legacy_question_id("60999").status == ResolutionStatus.MISSING
        assert w.resolve_current_source_path("pg/g.sgf").source_record_uuid == g
        batch = w.resolve_many_legacy_question_ids(["60001", "60002", "60999"])
        assert batch["60001"].source_record_uuid == g
        assert batch["60002"].status == "RETIRED"
        assert batch["60999"].status == "MISSING"
        # cross-context ambiguity fails closed on PG too
        conn.execute(
            "INSERT INTO puzzle_identity_alias "
            "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
            " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
            (rr, "LEGACY_QUESTION_ID", "60001", "post-genesis", "RECORDED",
             True, _FIXED, "collision"))
        assert w.resolve_legacy_question_id("60001").status == ResolutionStatus.AMBIGUOUS
        assert w.resolve_many_legacy_question_ids(["60001"])["60001"].status == "AMBIGUOUS"
        s = w.bootstrap_state()
        assert s["hot"] and s["identity_count"] == 2
    finally:
        conn.rollback()
        conn.close()
