"""LC015 — bootstrap-gated dual-ID read adoption.

SQLite behaviour + a real disposable PostgreSQL parity check for the
classification matrix.  Synthetic identities only; the real 42,804 genesis
bootstrap is never run and ``bootstrap_state().hot`` stays False unless a test
seeds an APPLIED receipt + identities.
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
from identity_read_adapter import (
    BootstrapGatedIdentityReader,
    IdentityKey,
    IdentityKeyKind,
    IdentityNotAttachable,
    admin_identity_lookup,
    identity_key_for_read,
    identity_keys_for_aggregate,
)

_NS = uuid.UUID("00000000-0000-4000-8000-000000000000")
_FIXED = "2026-08-29T00:00:00+00:00"
_RID = "cd" * 32


def _v5(name: str) -> str:
    return str(uuid.uuid5(_NS, "lc015:" + name))


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
def hot_conn():
    """tables + APPLIED receipt + 3 identities -> bootstrap_state().hot == True"""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    _seed_receipt(c)
    st = PuzzleIdentityStore(c, clock=lambda: _FIXED)
    g = _v5("g/1.sgf")
    st.create_historical_genesis_identity(
        g, receipt_sha256=_RID, canonical_source="g/1.sgf",
        legacy_question_id="70001", historical_source_path="hist/07x/1.sgf",
        creation_reason="genesis")
    rr = _v5("g/retired.sgf")
    st.create_historical_genesis_identity(
        rr, receipt_sha256=_RID, canonical_source="g/retired.sgf",
        legacy_question_id="70002", creation_reason="genesis")
    st.retire_identity(rr, reason="withdrawn", actor="admin")
    n = st.create_native_identity(
        creation_reason="native", current_source_path="native/9.sgf",
        legacy_question_id="88888")
    yield c, {"g": g, "r": rr, "n": n}
    c.close()


@pytest.fixture()
def cold_conn():
    """tables present, NO receipt, NO identities -> hot == False"""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    yield c
    c.close()


# --------------------------------------------------------- HOT_FALSE

def test_hot_false_is_pure_legacy_and_touches_nothing(cold_conn):
    r = BootstrapGatedIdentityReader(cold_conn)
    assert r.hot is False
    counts = lambda: tuple(
        cold_conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("puzzle_identity_registry", "puzzle_identity_alias", "puzzle_identity_lineage"))
    before = counts()
    for q in (70001, "70001", "abc", "", 99999):
        k = r.key_for(q)
        assert k.kind == IdentityKeyKind.LEGACY
        assert k.value == str(q) and k.legacy_question_id == str(q)
        assert not k.attachable and k.group_key == ("legacy", str(q))
    assert r.keys_for([1, 2, 2, 3]) == {
        "1": IdentityKey(IdentityKeyKind.LEGACY, "1", "1", reason="bootstrap_state().hot is False"),
        "2": IdentityKey(IdentityKeyKind.LEGACY, "2", "2", reason="bootstrap_state().hot is False"),
        "3": IdentityKey(IdentityKeyKind.LEGACY, "3", "3", reason="bootstrap_state().hot is False"),
    }
    assert counts() == before  # zero mutation


def test_hot_false_when_receipt_not_applied(cold_conn):
    _seed_receipt(cold_conn, status="ABORTED")
    r = BootstrapGatedIdentityReader(cold_conn)
    assert r.hot is False
    assert r.key_for("70001").kind == IdentityKeyKind.LEGACY


# --------------------------------------------------------- HOT_TRUE matrix

def test_hot_true_exact_gives_uuid_key_attachable(hot_conn):
    c, ids = hot_conn
    r = BootstrapGatedIdentityReader(c)
    assert r.hot is True
    k = r.key_for("70001")
    assert k.kind == IdentityKeyKind.UUID and k.value == ids["g"]
    assert k.attachable and not k.retired and k.group_key == ("uuid", ids["g"])
    assert r.assert_attachable("70001") == ids["g"]
    # native identity resolves on its own legacy id
    assert r.key_for("88888").value == ids["n"]


def test_hot_true_retired_uuid_history_only_not_attachable(hot_conn):
    c, ids = hot_conn
    r = BootstrapGatedIdentityReader(c)
    k = r.key_for("70002")
    assert k.kind == IdentityKeyKind.UUID and k.value == ids["r"]
    assert k.retired and not k.attachable
    assert k.group_key == ("uuid", ids["r"])          # still resolvable for history
    with pytest.raises(IdentityNotAttachable):
        r.assert_attachable("70002")


def test_hot_true_ambiguous_fails_closed_never_merged(hot_conn):
    c, ids = hot_conn
    # a second current LEGACY_QUESTION_ID=70001 in another context
    c.execute(
        "INSERT INTO puzzle_identity_alias "
        "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
        " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
        (ids["n"], "LEGACY_QUESTION_ID", "70001", "post-genesis", "RECORDED",
         True, _FIXED, "collision"))
    r = BootstrapGatedIdentityReader(c)
    k = r.key_for("70001")
    assert k.kind == IdentityKeyKind.UNRESOLVED and k.value == "70001"
    assert not k.attachable
    assert k.group_key == ("unresolved", "70001")     # NOT ("uuid", …) — never merged
    assert set(k.candidates) == {ids["g"], ids["n"]}
    with pytest.raises(IdentityNotAttachable):
        r.assert_attachable("70001")


def test_hot_true_missing_is_compatibility_legacy_key(hot_conn):
    c, _ids = hot_conn
    k = BootstrapGatedIdentityReader(c).key_for("99999")
    assert k.kind == IdentityKeyKind.LEGACY and k.value == "99999"
    assert not k.attachable and k.group_key == ("legacy", "99999")


def test_hot_true_unavailable_when_tables_dropped(hot_conn):
    c, _ids = hot_conn
    r = BootstrapGatedIdentityReader(c)
    assert r.hot is True
    for t in ("puzzle_identity_alias", "puzzle_identity_lineage",
              "puzzle_identity_registry", "puzzle_identity_bootstrap_receipt"):
        c.execute(f"DROP TABLE {t}")
    r2 = BootstrapGatedIdentityReader(c)
    assert r2.hot is False               # bootstrap_state degrades to not-hot
    k = r2.key_for("70001")
    assert k.kind == IdentityKeyKind.LEGACY   # hot False -> legacy, never an UNAVAILABLE surprise
    # if a caller forces the hot path, an unavailable resolution -> UNAVAILABLE key
    r2._hot = True
    k2 = r2.key_for("70001")
    assert k2.kind == IdentityKeyKind.UNAVAILABLE and k2.group_key == ("unavailable", "70001")


# --------------------------------------------------------- aggregate

def test_aggregate_keying_mixed_and_collision_fail_closed(hot_conn):
    c, ids = hot_conn
    c.execute(
        "INSERT INTO puzzle_identity_alias "
        "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
        " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
        (ids["n"], "LEGACY_QUESTION_ID", "70001", "post-genesis", "RECORDED",
         True, _FIXED, "collision"))
    r = BootstrapGatedIdentityReader(c)
    keys = r.keys_for(["70001", "70002", "88888", "99999", "70001"])
    assert keys["70001"].kind == IdentityKeyKind.UNRESOLVED      # ambiguous
    assert keys["70002"].kind == IdentityKeyKind.UUID and keys["70002"].retired
    assert keys["88888"].kind == IdentityKeyKind.UUID and keys["88888"].value == ids["n"]
    assert keys["99999"].kind == IdentityKeyKind.LEGACY
    gk = r.group_keys_for(["70001", "70002", "88888", "99999"])
    buckets = list(gk.values())
    assert len(set(buckets)) == 4                                # nothing merged
    assert gk["70001"] == ("unresolved", "70001")
    assert gk["88888"] == ("uuid", ids["n"])
    # a caller re-bucketing rows: ambiguous 70001 rows stay on their own key,
    # never folded into the 88888 uuid bucket
    assert gk["70001"] != gk["88888"]


def test_batch_dedupes_inputs(hot_conn):
    c, ids = hot_conn
    keys = identity_keys_for_aggregate(c, ["70001", "70001", "70001"])
    assert list(keys) == ["70001"] and keys["70001"].value == ids["g"]


# --------------------------------------------------------- admin lookup (§11)

def test_admin_lookup_all_four_selectors(hot_conn):
    c, ids = hot_conn
    by_legacy = admin_identity_lookup(c, legacy_question_id="70001")
    assert by_legacy["status"] == "EXACT" and by_legacy["source_record_uuid"] == ids["g"]
    assert by_legacy["legacy_question_ids"] == ["70001"]
    assert by_legacy["current_source_path"] == "g/1.sgf"

    by_uuid = admin_identity_lookup(c, source_record_uuid=ids["g"])
    assert by_uuid["status"] == "EXACT" and by_uuid["source_record_uuid"] == ids["g"]

    by_cur = admin_identity_lookup(c, current_source_path="g/1.sgf")
    assert by_cur["status"] == "EXACT" and by_cur["source_record_uuid"] == ids["g"]

    by_hist = admin_identity_lookup(c, historical_source_path="hist/07x/1.sgf")
    assert by_hist["status"] == "EXACT" and by_hist["source_record_uuid"] == ids["g"]


def test_admin_lookup_ambiguous_fail_closed_and_unknown(hot_conn):
    c, ids = hot_conn
    c.execute(
        "INSERT INTO puzzle_identity_alias "
        "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
        " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
        (ids["n"], "LEGACY_QUESTION_ID", "70001", "post-genesis", "RECORDED",
         True, _FIXED, "collision"))
    amb = admin_identity_lookup(c, legacy_question_id="70001")
    assert amb["status"] == "AMBIGUOUS"
    assert set(amb["candidates"]) == {ids["g"], ids["n"]}
    assert "source_record_uuid" not in amb                        # never auto-picks

    assert admin_identity_lookup(c, legacy_question_id="55555")["status"] == "MISSING"
    assert admin_identity_lookup(c, source_record_uuid=_v5("nope"))["status"] == "MISSING"
    assert admin_identity_lookup(c)["status"] == "BAD_REQUEST"
    assert admin_identity_lookup(c, legacy_question_id="1",
                                 current_source_path="x")["status"] == "BAD_REQUEST"


def test_admin_lookup_retired_by_uuid(hot_conn):
    c, ids = hot_conn
    r = admin_identity_lookup(c, source_record_uuid=ids["r"])
    assert r["status"] == "RETIRED" and r["retired"] and not r["attachable"]


# --------------------------------------------------------- renamed path

def test_renamed_path_old_missing_new_exact_legacy_unchanged(hot_conn):
    c, ids = hot_conn
    PuzzleIdentityStore(c, clock=lambda: _FIXED).record_rename(
        ids["g"], from_path="g/1.sgf", to_path="g/renamed/1.sgf",
        actor="admin", reason="reorg")
    r = BootstrapGatedIdentityReader(c)
    assert admin_identity_lookup(c, current_source_path="g/1.sgf")["status"] == "MISSING"
    assert admin_identity_lookup(c, current_source_path="g/renamed/1.sgf"
                                 )["source_record_uuid"] == ids["g"]
    assert r.key_for("70001").value == ids["g"]     # legacy id keying unchanged


# --------------------------------------------------------- NO WRITE AUTHORITY (§14)

def test_no_fabricated_identity_and_no_write_imports(hot_conn):
    c, _ids = hot_conn
    counts = lambda: tuple(
        c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("puzzle_identity_registry", "puzzle_identity_alias", "puzzle_identity_lineage",
                  "puzzle_identity_bootstrap_receipt"))
    before = counts()
    r = BootstrapGatedIdentityReader(c)
    for q in ("70001", "70002", "88888", "99999", "abc", "", "-1"):
        r.key_for(q)
        try:
            r.assert_attachable(q)
        except IdentityNotAttachable:
            pass
    r.keys_for([str(i) for i in range(40000, 40200)])
    r.group_keys_for(["70001", "99999"])
    admin_identity_lookup(c, legacy_question_id="70001")
    admin_identity_lookup(c, source_record_uuid=_v5("nope"))
    assert counts() == before

    src = pathlib.Path(__file__).resolve().parents[1] / "identity_read_adapter.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                imported.add(a.name)
    assert not (imported & {"GenesisBootstrap", "GenesisReceiptVerifier",
                            "mint_genesis_uuid", "puzzle_identity_genesis_bootstrap",
                            "PuzzleIdentityStore"})
    body = src.read_text(encoding="utf-8")
    for tok in ("create_historical_genesis_identity", "create_native_identity",
                "record_rename", "record_replacement", "_append_lineage",
                "INSERT INTO", "UPDATE puzzle_identity", "DELETE FROM"):
        assert tok not in body, tok


def test_functional_entry_points(hot_conn):
    c, ids = hot_conn
    assert identity_key_for_read(c, "70001").value == ids["g"]
    assert identity_keys_for_aggregate(c, ["70001", "88888"])["88888"].value == ids["n"]


# --------------------------------------------------------- real PostgreSQL parity

_PG_IMAGE = "postgres:16.14-alpine"
_PG_USER, _PG_PW, _PG_DB = "lc015", "lc015_disposable", "lc015"


def _docker(*a):
    return subprocess.run(["docker", *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture(scope="module")
def pg_url():
    if shutil.which("docker") is None:
        pytest.skip("docker unavailable; PostgreSQL parity skipped")
    name = f"lc015-pg-{uuid.uuid4().hex[:12]}"
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


def test_pg_parity_gate_matrix(pg_url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(pg_url, cursor_factory=DictCursor)
    conn = PostgresConnectionWrapper(raw, pooled=False)
    try:
        upgrade(conn)
        # cold: hot False -> legacy
        cold = BootstrapGatedIdentityReader(conn)
        assert cold.hot is False
        assert cold.key_for("60001").kind == IdentityKeyKind.LEGACY

        _seed_receipt(conn)
        st = PuzzleIdentityStore(conn, clock=lambda: _FIXED)
        g = _v5("pg/g.sgf")
        st.create_historical_genesis_identity(
            g, receipt_sha256=_RID, canonical_source="pg/g.sgf",
            legacy_question_id="60001", creation_reason="genesis")
        rr = _v5("pg/r.sgf")
        st.create_historical_genesis_identity(
            rr, receipt_sha256=_RID, canonical_source="pg/r.sgf",
            legacy_question_id="60002", creation_reason="genesis")
        st.retire_identity(rr, reason="w", actor="a")
        n = st.create_native_identity(creation_reason="native", legacy_question_id="60003")

        hot = BootstrapGatedIdentityReader(conn)
        assert hot.hot is True
        assert hot.key_for("60001") == IdentityKey(
            IdentityKeyKind.UUID, g, "60001", attachable=True, reason="exact single binding")
        assert hot.key_for("60002").retired and not hot.key_for("60002").attachable
        assert hot.key_for("60999").kind == IdentityKeyKind.LEGACY          # MISSING -> legacy
        # cross-context ambiguity fails closed on PG
        conn.execute(
            "INSERT INTO puzzle_identity_alias "
            "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
            " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,?,?,?)",
            (n, "LEGACY_QUESTION_ID", "60001", "post-genesis", "RECORDED",
             True, _FIXED, "collision"))
        k = hot.key_for("60001")
        assert k.kind == IdentityKeyKind.UNRESOLVED and k.group_key == ("unresolved", "60001")
        with pytest.raises(IdentityNotAttachable):
            hot.assert_attachable("60001")
        agg = hot.group_keys_for(["60001", "60002", "60003", "60999"])
        assert len(set(agg.values())) == 4
        assert admin_identity_lookup(conn, legacy_question_id="60001")["status"] == "AMBIGUOUS"
        assert admin_identity_lookup(conn, source_record_uuid=g)["status"] == "EXACT"
    finally:
        conn.rollback()
        conn.close()
