"""LC019-W1 — bootstrap-gated identity reader wired into grimoire_api.py
(non-app.py Learning Core reader).

Proves:
  * hot == False  -> generate_daily_training output is byte-identical whether the
    candidate identity tables are absent or present-but-cold, and the resolver
    (resolve_* on DualIdReadWindow) is never called;
  * hot == True   -> EXACT folds two legacy ids that share a source_record_uuid;
    RETIRED is uuid-history-only / not attachable; AMBIGUOUS stays its own
    ("unresolved", id) bucket and is never merged; MISSING / UNAVAILABLE keep
    the legacy key.

SQLite + a real disposable PostgreSQL parity check for the reader classification.
Synthetic identities only; the real 42,804 genesis bootstrap is never run.
"""
from __future__ import annotations

import contextlib
import shutil
import sqlite3
import subprocess
import time
import uuid

import pytest

import grimoire_api
from identity_read_adapter import (
    BootstrapGatedIdentityReader,
    IdentityKeyKind,
    IdentityNotAttachable,
)
from migrations.puzzle_identity_registry_v1 import upgrade as identity_upgrade
from puzzle_identity_store import PuzzleIdentityStore
import puzzle_identity_read_window as prw

_NS = uuid.UUID("00000000-0000-4000-8000-000000000000")
_FIXED = "2026-08-29T00:00:00+00:00"
_RID = "cd" * 32
_UID = 7


def _v5(name: str) -> str:
    return str(uuid.uuid5(_NS, "lc019w1:" + name))


# ------------------------------------------------------------------ Learning DB

def _new_learning_db() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(
        """
        CREATE TABLE user_stats (
            user_id INTEGER PRIMARY KEY, attr_def INTEGER, attr_atk INTEGER,
            attr_vis INTEGER, attr_prec INTEGER, rank_level TEXT
        );
        CREATE TABLE srs_cards (
            user_id INTEGER, question_id INTEGER, due_date TEXT,
            PRIMARY KEY(user_id, question_id)
        );
        CREATE TABLE review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            question_id INTEGER, grade INTEGER, reviewed_at TEXT,
            topic TEXT, level TEXT
        );
        CREATE TABLE node_mastery (
            user_id INTEGER, question_id INTEGER, is_contaminated INTEGER DEFAULT 0,
            purity REAL, attempt_count INTEGER, last_correct_at TEXT,
            PRIMARY KEY(user_id, question_id)
        );
        """
    )
    c.execute(
        "INSERT INTO user_stats VALUES (?,?,?,?,?,?)",
        (_UID, 5, 9, 3, 4, "LV20"),
    )
    return c


def _seed_receipt(conn):
    conn.execute(
        "INSERT INTO puzzle_identity_bootstrap_receipt "
        "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,"
        " namespace_uuid,canonicalisation_rules_version,genesis_key_spec_version,"
        " historical_tree_commit,historical_tree_manifest_sha256,"
        " historical_rename_map_sha256,genesis_record_manifest_sha256,"
        " proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
        "VALUES (?, 'GENESIS', ?, 3, 'ns','canon-source-v1','genesis-key-v1',"
        "'c','tm','rm','gm','ul','APPLIED',0,?,'fx')",
        (_RID, "x" * 64, _FIXED),
    )


_SYNTH_QUESTIONS = [
    {"id": i, "enabled": True,
     "discipline": ["tesuji", "life_death", "opening_direction", "endgame_counting"][i % 4],
     "grimoire_difficulty": 3, "topic": "T", "level": "L"}
    for i in range(100, 160)
]


@pytest.fixture(autouse=True)
def _patch_grimoire(monkeypatch):
    monkeypatch.setattr(grimoire_api, "_questions_cache", list(_SYNTH_QUESTIONS), raising=False)
    monkeypatch.setattr(grimoire_api, "ensure_node_mastery_table", lambda conn: None)
    # deterministic pick: stable sort instead of shuffle (pools hold dicts or ints)
    monkeypatch.setattr(
        grimoire_api.random, "shuffle",
        lambda seq: seq.sort(key=lambda x: x["id"] if isinstance(x, dict) else x),
    )
    yield


@contextlib.contextmanager
def _as_ctx(conn):
    yield conn


def _run_daily(conn, total=10):
    ctx = lambda: _as_ctx(conn)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(grimoire_api, "get_sdb", ctx)
        mp.setattr(grimoire_api, "get_ldb", ctx)
        return grimoire_api.generate_daily_training(_UID, total)


# ------------------------------------------------------------------ HOT=FALSE

def test_hot_false_identical_tables_absent_vs_cold_and_no_resolver_query(monkeypatch):
    # scenario: player has SRS-due 101/102, recently answered 105/106
    def _seed(conn):
        conn.execute("INSERT INTO srs_cards VALUES (?,?,?)", (_UID, 101, "2000-01-01"))
        conn.execute("INSERT INTO srs_cards VALUES (?,?,?)", (_UID, 102, "2000-01-01"))
        for qid in (105, 106):
            conn.execute(
                "INSERT INTO review_log(user_id,question_id,grade,reviewed_at) VALUES (?,?,?,?)",
                (_UID, qid, 4, "2999-01-01"))

    # (a) identity tables ABSENT
    a = _new_learning_db(); _seed(a)
    out_absent = _run_daily(a)

    # (b) identity tables PRESENT but genesis COLD  + resolver poisoned
    b = _new_learning_db(); _seed(b)
    identity_upgrade(b)
    called = {"n": 0}
    orig = prw.DualIdReadWindow.resolve_many_legacy_question_ids

    def _poison(self, ids):
        called["n"] += 1
        raise AssertionError("resolver must NOT be queried at hot=False")

    monkeypatch.setattr(prw.DualIdReadWindow, "resolve_many_legacy_question_ids", _poison)
    monkeypatch.setattr(prw.DualIdReadWindow, "resolve_legacy_question_id",
                        lambda self, q: (_ for _ in ()).throw(AssertionError("no resolver at hot=False")))
    out_cold = _run_daily(b)
    monkeypatch.setattr(prw.DualIdReadWindow, "resolve_many_legacy_question_ids", orig)

    assert out_absent == out_cold, (out_absent, out_cold)          # HOT_FALSE_OUTPUT_BYTE_IDENTICAL
    assert called["n"] == 0                                        # HOT_FALSE_RESOLVER_QUERY_COUNT = 0
    assert len(out_absent) == 10
    assert 105 not in out_absent and 106 not in out_absent          # recent-answered excluded
    a.close(); b.close()


def test_hot_false_reader_group_key_is_legacy(monkeypatch):
    b = _new_learning_db()
    identity_upgrade(b)
    r = BootstrapGatedIdentityReader(b)
    assert r.hot is False
    for qid in (101, "101", 999999):
        k = r.key_for(qid)
        assert k.kind == IdentityKeyKind.LEGACY and k.group_key == ("legacy", str(qid))
    b.close()


# ------------------------------------------------------------------ HOT=TRUE

def _make_hot(conn):
    identity_upgrade(conn)
    _seed_receipt(conn)
    return PuzzleIdentityStore(conn, clock=lambda: _FIXED)


def test_hot_true_exact_folds_two_legacy_ids(monkeypatch):
    conn = _new_learning_db()
    st = _make_hot(conn)
    # one native identity, two legacy aliases: 500 and 777 are the SAME puzzle
    u = st.create_native_identity(creation_reason="w1", legacy_question_id="500")
    st._insert_alias(u, "LEGACY_QUESTION_ID", "777",
                     context="post-genesis", confidence="RECORDED",
                     recorded_by="w1", when=_FIXED)
    # synthetic questions include 500 and 777
    monkeypatch.setattr(grimoire_api, "_questions_cache",
                        _SYNTH_QUESTIONS + [
                            {"id": 500, "enabled": True, "discipline": "tesuji", "grimoire_difficulty": 3},
                            {"id": 777, "enabled": True, "discipline": "tesuji", "grimoire_difficulty": 3},
                        ])
    # player recently answered 500
    conn.execute("INSERT INTO review_log(user_id,question_id,grade,reviewed_at) VALUES (?,?,?,?)",
                 (_UID, 500, 4, "2999-01-01"))

    r = BootstrapGatedIdentityReader(conn)
    assert r.hot is True
    assert r.key_for("500").group_key == r.key_for("777").group_key == ("uuid", u)

    out = _run_daily(conn, total=20)
    assert 500 not in out and 777 not in out    # 777 folded out because 500 (same uuid) is excluded
    conn.close()


def test_hot_true_retired_uuid_history_only_not_attachable():
    conn = _new_learning_db()
    st = _make_hot(conn)
    rr = _v5("retired")
    st.create_historical_genesis_identity(
        rr, receipt_sha256=_RID, canonical_source="g/r.sgf",
        legacy_question_id="600", creation_reason="genesis")
    st.retire_identity(rr, reason="withdrawn", actor="admin")
    r = BootstrapGatedIdentityReader(conn)
    k = r.key_for("600")
    assert k.kind == IdentityKeyKind.UUID and k.value == rr
    assert k.retired and not k.attachable and k.group_key == ("uuid", rr)
    with pytest.raises(IdentityNotAttachable):
        r.assert_attachable("600")
    conn.close()


def test_hot_true_ambiguous_never_merged():
    conn = _new_learning_db()
    st = _make_hot(conn)
    a = st.create_native_identity(creation_reason="a")
    b = st.create_native_identity(creation_reason="b")
    # two current identities claiming legacy 900 in different contexts — the
    # partial-unique index permits one current binding per (kind,value,context),
    # so a genuine cross-context ambiguity is constructed this way.
    st._insert_alias(a, "LEGACY_QUESTION_ID", "900", context="genesis-v1",
                     confidence="RECORDED", recorded_by="w1", when=_FIXED)
    st._insert_alias(b, "LEGACY_QUESTION_ID", "900", context="post-genesis",
                     confidence="RECORDED", recorded_by="w1", when=_FIXED)
    r = BootstrapGatedIdentityReader(conn)
    k = r.key_for("900")
    assert k.kind == IdentityKeyKind.UNRESOLVED
    assert k.group_key == ("unresolved", "900")          # never ("uuid", …)
    assert set(k.candidates) == {a, b}
    with pytest.raises(IdentityNotAttachable):
        r.assert_attachable("900")
    conn.close()


def test_hot_true_missing_and_unavailable():
    conn = _new_learning_db()
    _make_hot(conn)
    r = BootstrapGatedIdentityReader(conn)
    assert r.key_for("123456").kind == IdentityKeyKind.LEGACY          # MISSING -> legacy
    for t in ("puzzle_identity_alias", "puzzle_identity_lineage",
              "puzzle_identity_registry", "puzzle_identity_bootstrap_receipt"):
        conn.execute(f"DROP TABLE {t}")
    r2 = BootstrapGatedIdentityReader(conn)
    r2._hot = True                                                    # force the hot path
    assert r2.key_for("123456").kind == IdentityKeyKind.UNAVAILABLE
    # grimoire's own guard keeps it on the legacy path when tables are gone
    assert grimoire_api._identity_tables_present(conn) is False
    conn.close()


# ------------------------------------------------------------------ firewalls

def test_scope_firewalls():
    src = __import__("pathlib").Path(grimoire_api.__file__).read_text(encoding="utf-8")
    # read-only: grimoire's new code adds no identity write
    for tok in ("create_historical_genesis_identity", "GenesisBootstrap",
                "mint_genesis_uuid", "INSERT INTO puzzle_identity",
                "UPDATE puzzle_identity"):
        assert tok not in src, tok


# ------------------------------------------------------------------ PostgreSQL parity

_PG_IMAGE = "postgres:16.14-alpine"
_PG_U, _PG_P, _PG_D = "lc019w1", "lc019w1_disposable", "lc019w1"


def _docker(*a):
    return subprocess.run(["docker", *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture(scope="module")
def pg_url():
    if shutil.which("docker") is None:
        pytest.skip("docker unavailable; PostgreSQL parity skipped")
    name = f"lc019w1-pg-{uuid.uuid4().hex[:12]}"
    run = _docker("run", "--rm", "--detach", "--name", name,
                  "--env", f"POSTGRES_USER={_PG_U}", "--env", f"POSTGRES_PASSWORD={_PG_P}",
                  "--env", f"POSTGRES_DB={_PG_D}", "--publish", "127.0.0.1::5432", _PG_IMAGE)
    if run.returncode != 0:
        pytest.skip(f"disposable PostgreSQL unavailable: {run.stderr.strip()}")
    try:
        port = _docker("inspect", "--format",
                       '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}',
                       name).stdout.strip()
        assert port.isdigit()
        url = f"postgresql://{_PG_U}:{_PG_P}@127.0.0.1:{port}/{_PG_D}"
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            r = _docker("exec", name, "psql", "-U", _PG_U, "-d", _PG_D, "-tAc", "SELECT 1")
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


def test_pg_parity_reader_and_grimoire_guard(pg_url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(pg_url, cursor_factory=DictCursor)
    conn = PostgresConnectionWrapper(raw, pooled=False)
    try:
        # grimoire's catalog guard: false before, true after upgrade — never aborts the tx
        assert grimoire_api._identity_tables_present(conn) is False
        conn.execute("SELECT 1")            # tx still usable
        identity_upgrade(conn)
        _seed_receipt(conn)
        assert grimoire_api._identity_tables_present(conn) is True

        st = PuzzleIdentityStore(conn, clock=lambda: _FIXED)
        u = st.create_native_identity(creation_reason="pg", legacy_question_id="500")
        st._insert_alias(u, "LEGACY_QUESTION_ID", "777", context="post-genesis",
                         confidence="RECORDED", recorded_by="pg", when=_FIXED)
        rr = st.create_historical_genesis_identity(
            _v5("pgr"), receipt_sha256=_RID, canonical_source="g/pgr.sgf",
            legacy_question_id="600", creation_reason="genesis")
        st.retire_identity(rr, reason="w", actor="a")
        amb1 = st.create_native_identity(creation_reason="amb1")
        amb2 = st.create_native_identity(creation_reason="amb2")
        st._insert_alias(amb1, "LEGACY_QUESTION_ID", "900", context="genesis-v1",
                         confidence="RECORDED", recorded_by="pg", when=_FIXED)
        st._insert_alias(amb2, "LEGACY_QUESTION_ID", "900", context="post-genesis",
                         confidence="RECORDED", recorded_by="pg", when=_FIXED)

        r = BootstrapGatedIdentityReader(conn)
        assert r.hot is True
        assert r.key_for("500").group_key == r.key_for("777").group_key == ("uuid", u)
        k600 = r.key_for("600")
        assert k600.group_key == ("uuid", rr) and k600.retired and not k600.attachable
        assert r.key_for("900").group_key == ("unresolved", "900")
        assert r.key_for("123456").kind == IdentityKeyKind.LEGACY
    finally:
        conn.rollback()
        conn.close()
