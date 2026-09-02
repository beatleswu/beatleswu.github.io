"""LC019-W2 — canonical-identity reader folding wired into app.py.

Covers the 7 required semantic reader sites:
  1. training_daily            GET /api/training/daily
  2. recommend_questions       POST /api/recommend
  3. _adventure_correct_question_ids / _adventure_state
  4. curriculum_summary        GET /api/curriculum/summary
  5. map_progress              GET /api/map-progress
  6. _stage_completion_state / quest_board_progress
                               GET /api/quest-board , GET /api/quest-board/progress
  7. srs_due                   GET /api/srs/due

Contract:
  * hot == False (identity tables absent OR present-but-cold): every route/function
    output is byte-identical to the raw-integer form and the dual-id resolver is
    never queried  -> HOT_FALSE_ALL_ROUTE_OUTPUTS_IDENTICAL / _TOTAL_RESOLVER_QUERY_COUNT = 0
  * hot == True: two legacy ids that resolve to one source_record_uuid fold to a
    single identity for dedup / membership / counting.  RETIRED folds to the uuid
    bucket (history only).  AMBIGUOUS keeps its own ("unresolved", id) bucket and
    is never merged.  MISSING / UNAVAILABLE keep the legacy raw-id behaviour.
  * returned answer ids stay raw integers; write paths are untouched.

Synthetic identities only — the real 42,804 genesis bootstrap is never run.
SQLite + a real disposable PostgreSQL 16.x parity check.
"""
from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import types
import uuid
from pathlib import Path

import pytest

from migrations.puzzle_identity_registry_v1 import upgrade as identity_upgrade
import puzzle_identity_read_window as prw
from identity_read_adapter import BootstrapGatedIdentityReader, IdentityKeyKind
from puzzle_identity_store import PuzzleIdentityStore

REPO_ROOT = Path(__file__).resolve().parent.parent
_UID = 7
_FIXED = "2026-08-29T00:00:00+00:00"
_RID = "cd" * 32
_NS = uuid.UUID("00000000-0000-4000-8000-000000000000")


def _v5(name: str) -> str:
    return str(uuid.uuid5(_NS, "lc019w2:" + name))


# --------------------------------------------------------------- app import

def _install_app_import_stubs():
    for name, attrs in {
        "katago_explain": {"KataGoExplainer": type("KataGoExplainer", (), {})},
        "explain_overrides": {"get_override": lambda *a, **k: None},
        "question_taxonomy": {"get_taxonomy": lambda *a, **k: {}},
        "monster_taxonomy": {"get_monster_taxonomy": lambda *a, **k: {},
                              "mark_encounters": lambda *a, **k: None},
        "chapter_i18n": {"localize_topic": lambda *a, **k: "",
                         "localize_level": lambda *a, **k: ""},
        "backend_i18n": {"badge_en": lambda *a, **k: "", "skill_node_en": lambda *a, **k: "",
                         "title_en": lambda *a, **k: ""},
    }.items():
        if name not in sys.modules:
            m = types.ModuleType(name)
            for k, v in attrs.items():
                setattr(m, k, v)
            sys.modules[name] = m
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint
        m = types.ModuleType("grimoire_api")
        m.grimoire_bp = Blueprint("grimoire_stub_lc019w2", __name__)
        m._identity_tables_present = lambda conn: False
        sys.modules["grimoire_api"] = m


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module


# --------------------------------------------------------------- learning DB

_SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY, elo_rating REAL);
CREATE TABLE user_stats (
    user_id INTEGER PRIMARY KEY, attr_atk INTEGER, attr_def INTEGER,
    attr_vis INTEGER, attr_prec INTEGER, go_rank TEXT, rank_level TEXT,
    coins INTEGER DEFAULT 0, xp INTEGER DEFAULT 0
);
CREATE TABLE srs_cards (
    user_id INTEGER, question_id INTEGER, interval INTEGER DEFAULT 0,
    ease_factor REAL DEFAULT 2.5, repetitions INTEGER DEFAULT 0,
    due_date TEXT, last_grade INTEGER, progress_credited INTEGER DEFAULT 0,
    PRIMARY KEY(user_id, question_id)
);
CREATE TABLE review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, question_id INTEGER,
    grade INTEGER, reviewed_at TEXT, source_context TEXT DEFAULT 'practice',
    source TEXT DEFAULT '', topic TEXT, level TEXT, discipline TEXT, difficulty TEXT
);
CREATE TABLE mistake_log (
    user_id INTEGER, question_id INTEGER, wrong_count INTEGER DEFAULT 0,
    correct_after INTEGER DEFAULT 0, last_wrong_at TEXT,
    PRIMARY KEY(user_id, question_id)
);
CREATE TABLE daily_training_queue (
    user_id INTEGER, date TEXT, question_ids TEXT, sources TEXT,
    generated_at TEXT, PRIMARY KEY(user_id, date)
);
CREATE TABLE adventure_boss_progress (
    user_id INTEGER, zone_key TEXT, cleared INTEGER DEFAULT 0,
    cooldown_until_seen INTEGER DEFAULT 0, stars INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0, best_score INTEGER DEFAULT 0,
    last_attempt_at TEXT, cleared_at TEXT, updated_at TEXT,
    PRIMARY KEY(user_id, zone_key)
);
CREATE TABLE adventure_zone_unlocks (
    user_id INTEGER, zone_key TEXT, source TEXT, start_zone_key TEXT,
    PRIMARY KEY(user_id, zone_key)
);
CREATE TABLE reward_claimed (
    user_id INTEGER, stage_key TEXT, coins INTEGER, xp INTEGER, claimed_at TEXT,
    PRIMARY KEY(user_id, stage_key)
);
CREATE TABLE quest_accepted (
    user_id INTEGER, quest_key TEXT, accepted_at TEXT,
    PRIMARY KEY(user_id, quest_key)
);
"""


def _mk_conn(with_identity: bool) -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    c.execute("INSERT INTO users VALUES (?,?)", (_UID, 1500.0))
    c.execute(
        "INSERT INTO user_stats "
        "(user_id,attr_atk,attr_def,attr_vis,attr_prec,go_rank,rank_level,coins,xp) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (_UID, 5, 5, 5, 5, "10k", "LV20", 0, 0),
    )
    if with_identity:
        identity_upgrade(c)
    return c


# 30 questions across 2 topics / 2 stages; ids 100..129
_QS = []
for i in range(100, 130):
    _QS.append({
        "id": i, "enabled": True,
        "discipline": ["tesuji", "life_death", "fuseki", "endgame_counting"][i % 4],
        "topic": "BookA" if i < 115 else "BookB",
        "level": "L1", "stage": "LV2" if i < 115 else "LV3",
        "rank": "25k", "difficulty": "25k", "grimoire_difficulty": 3,
        "map_id": "mapA" if i < 115 else "mapB",
        "map_name": "MapA" if i < 115 else "MapB",
        "encounter_type": "normal", "source": f"b/{i}.sgf",
    })


@contextlib.contextmanager
def _ctx(conn):
    yield conn


class _ResolverProbe:
    """Counts (and optionally forbids) any dual-id resolver call."""

    def __init__(self, forbid: bool):
        self.count = 0
        self._forbid = forbid
        self._orig = {}

    def __enter__(self):
        for name in ("resolve_many_legacy_question_ids", "resolve_legacy_question_id",
                     "resolve_current_source_path", "resolve_canonical_source",
                     "resolve_historical_source_path"):
            self._orig[name] = getattr(prw.DualIdReadWindow, name)

            def _mk(orig):
                def _wrapped(inner_self, *a, **k):
                    self.count += 1
                    if self._forbid:
                        raise AssertionError(
                            "dual-id resolver queried while bootstrap is cold")
                    return orig(inner_self, *a, **k)
                return _wrapped

            setattr(prw.DualIdReadWindow, name, _mk(self._orig[name]))
        return self

    def __exit__(self, *exc):
        for name, orig in self._orig.items():
            setattr(prw.DualIdReadWindow, name, orig)


def _patch_common(mp, app_module, conn):
    app = app_module
    mp.setattr(app, "get_db", lambda: _ctx(conn))
    mp.setattr(app, "_load_questions", lambda: [dict(q) for q in _QS])
    if hasattr(app, "_load_questions_fresh"):
        mp.setattr(app, "_load_questions_fresh", lambda: [dict(q) for q in _QS])
    mp.setattr(app, "is_premium", lambda uid=None: False)
    mp.setattr(app, "_load_current_premium_entitlement", lambda uid: False, raising=False)
    # recommend_questions uses an unseeded random.random() tiebreak; pin it so the
    # golden comparison is about identity folding, not tie ordering.
    import random as _r
    mp.setattr(_r, "random", lambda: 0.5)


@contextlib.contextmanager
def _client(app_module, conn):
    with pytest.MonkeyPatch.context() as mp:
        _patch_common(mp, app_module, conn)
        cl = app_module.app.test_client()
        with cl.session_transaction() as s:
            s["user_id"] = _UID
        yield cl


# --------------------------------------------------------------- scenario

def _seed(conn):
    # SRS: 100 due, 101 mastered, 104 has a card (not due)
    conn.execute("INSERT INTO srs_cards(user_id,question_id,due_date,ease_factor,repetitions,last_grade) "
                 "VALUES (?,?,?,?,?,?)", (_UID, 100, "2000-01-01", 2.5, 1, 2))
    conn.execute("INSERT INTO srs_cards(user_id,question_id,due_date,ease_factor,repetitions,last_grade) "
                 "VALUES (?,?,?,?,?,?)", (_UID, 101, "2999-01-01", 2.6, 4, 3))
    conn.execute("INSERT INTO srs_cards(user_id,question_id,due_date,ease_factor,repetitions,last_grade) "
                 "VALUES (?,?,?,?,?,?)", (_UID, 104, "2999-01-01", 2.5, 1, 2))
    # review_log: 100 & 102 answered today; 102 & 103 map-battle correct
    conn.execute("INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
                 "VALUES (?,?,?,?,?)", (_UID, 100, 4, "2999-01-01T08:00:00", "practice"))
    conn.execute("INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
                 "VALUES (?,?,?,?,?)", (_UID, 102, 4, "2999-01-01T09:00:00", "practice"))
    for qid in (102, 103):
        conn.execute("INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
                     "VALUES (?,?,?,?,?)", (_UID, qid, 4, "2999-01-01T09:00:00", "mbv1:x"))
    # mistake_log
    conn.execute("INSERT INTO mistake_log(user_id,question_id,wrong_count) VALUES (?,?,?)", (_UID, 105, 3))
    conn.commit()


_ROUTES = [
    ("GET", "/api/srs/due", None),
    ("GET", "/api/map-progress", None),
    ("GET", "/api/curriculum/summary", None),
    ("GET", "/api/quest-board", None),
    ("POST", "/api/recommend", {"questionId": 106}),
    ("GET", "/api/training/daily", None),
]


def _call(cl, method, path, body):
    if method == "POST":
        return cl.post(path, json=body)
    return cl.get(path)


# ============================================================ HOT == FALSE

@pytest.mark.parametrize("method,path,body", _ROUTES, ids=[r[1] for r in _ROUTES])
def test_hot_false_route_output_byte_identical(app_module, method, path, body):
    absent = _mk_conn(with_identity=False); _seed(absent)
    with _client(app_module, absent) as cl:
        r_absent = _call(cl, method, path, body)
    absent.close()

    cold = _mk_conn(with_identity=True); _seed(cold)      # tables present, genesis COLD
    with _client(app_module, cold) as cl, _ResolverProbe(forbid=True) as probe:
        r_cold = _call(cl, method, path, body)
    cold.close()

    assert r_absent.status_code == r_cold.status_code == 200, (path, r_absent.status_code)
    assert r_absent.get_json() == r_cold.get_json(), path      # BYTE_IDENTICAL
    assert probe.count == 0, path                              # ZERO_RESOLVER_QUERY


def test_hot_false_quest_board_progress_identical(app_module):
    # needs a concrete quest_key from the segment map
    cold0 = _mk_conn(with_identity=True); _seed(cold0)
    with _client(app_module, cold0) as cl:
        seg_keys = [q["quest_key"] for q in cl.get("/api/quest-board").get_json()["open_quests"]]
    cold0.close()
    assert seg_keys, "expected at least one open guild quest"
    key = seg_keys[0]

    absent = _mk_conn(with_identity=False); _seed(absent)
    with _client(app_module, absent) as cl:
        a = cl.get(f"/api/quest-board/progress?quest_key={key}").get_json()
    absent.close()

    cold = _mk_conn(with_identity=True); _seed(cold)
    with _client(app_module, cold) as cl, _ResolverProbe(forbid=True) as probe:
        b = cl.get(f"/api/quest-board/progress?quest_key={key}").get_json()
    cold.close()
    assert a == b
    assert probe.count == 0


def test_hot_false_total_resolver_query_count_zero(app_module):
    cold = _mk_conn(with_identity=True); _seed(cold)
    with _client(app_module, cold) as cl, _ResolverProbe(forbid=False) as probe:
        for method, path, bod in _ROUTES:
            assert _call(cl, method, path, bod).status_code == 200
    cold.close()
    assert probe.count == 0        # HOT_FALSE_TOTAL_RESOLVER_QUERY_COUNT


# ============================================================ helper primitive

def _make_hot(conn):
    _seed_receipt(conn)
    return PuzzleIdentityStore(conn, clock=lambda: _FIXED)


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


def _import_app_helpers():
    _install_app_import_stubs()
    import app as a
    return a


def test_identity_keyed_set_cold_is_raw_bijection():
    a = _import_app_helpers()
    conn = _mk_conn(with_identity=True)
    gkm = a._identity_group_key_map(conn, [100, 101, 102])   # cold -> {}
    assert gkm == {}
    s = a._IdentityKeyedSet([100, 101], gkm)
    assert 100 in s and 101 in s and 102 not in s
    assert len(s) == 2
    assert s & {100, 102} == {("legacy", "100")}
    s.add(102)
    assert 102 in s and len(s) == 3
    conn.close()


def test_identity_keyed_set_hot_folds_exact_and_alias():
    a = _import_app_helpers()
    conn = _mk_conn(with_identity=True)
    st = _make_hot(conn)
    u = st.create_native_identity(creation_reason="w2", legacy_question_id="500")
    st._insert_alias(u, "LEGACY_QUESTION_ID", "777", context="post-genesis",
                     confidence="RECORDED", recorded_by="w2", when=_FIXED)
    gkm = a._identity_group_key_map(conn, [500, 777, 900])
    assert gkm["500"] == gkm["777"] == ("uuid", u)          # EXACT + LEGACY_ALIAS_EXACT
    s = a._IdentityKeyedSet([500], gkm)
    assert 777 in s and len(s) == 1                         # folded
    conn.close()


def test_identity_keyed_set_hot_retired_ambiguous_missing_unavailable():
    a = _import_app_helpers()
    conn = _mk_conn(with_identity=True)
    st = _make_hot(conn)
    rr = _v5("ret")
    st.create_historical_genesis_identity(
        rr, receipt_sha256=_RID, canonical_source="g/r.sgf",
        legacy_question_id="600", creation_reason="genesis")
    st.retire_identity(rr, reason="w", actor="a")
    a1 = st.create_native_identity(creation_reason="a1")
    a2 = st.create_native_identity(creation_reason="a2")
    st._insert_alias(a1, "LEGACY_QUESTION_ID", "900", context="genesis-v1",
                     confidence="RECORDED", recorded_by="w2", when=_FIXED)
    st._insert_alias(a2, "LEGACY_QUESTION_ID", "900", context="post-genesis",
                     confidence="RECORDED", recorded_by="w2", when=_FIXED)
    gkm = a._identity_group_key_map(conn, [600, 900, 123456])
    assert gkm["600"] == ("uuid", rr)                       # RETIRED -> uuid bucket
    assert gkm["900"] == ("unresolved", "900")              # AMBIGUOUS -> own bucket
    assert gkm["123456"] == ("legacy", "123456")            # MISSING -> legacy
    # a RETIRED id is still a set member (history), but two distinct ambiguous
    # ids never collapse together
    s = a._IdentityKeyedSet([600, 900], gkm)
    assert 600 in s and 900 in s and len(s) == 2
    # UNAVAILABLE: tables dropped mid-connection
    for t in ("puzzle_identity_alias", "puzzle_identity_lineage",
              "puzzle_identity_registry", "puzzle_identity_bootstrap_receipt"):
        conn.execute(f"DROP TABLE {t}")
    assert a._identity_tables_present(conn) is False        # guard -> raw-int path
    conn.close()


# ============================================================ HOT == TRUE folding, route level

def test_hot_true_map_progress_folds_duplicate(app_module):
    """A content-duplicate question earns 'practiced' credit from its pair."""
    conn = _mk_conn(with_identity=True); _seed(conn)
    st = _make_hot(conn)
    # id 106 and id 107 are the SAME puzzle; player only has a card for 106
    u = st.create_native_identity(creation_reason="dup", legacy_question_id="106")
    st._insert_alias(u, "LEGACY_QUESTION_ID", "107", context="post-genesis",
                     confidence="RECORDED", recorded_by="w2", when=_FIXED)
    conn.execute("INSERT INTO srs_cards(user_id,question_id,due_date,ease_factor,repetitions) "
                 "VALUES (?,?,?,?,?)", (_UID, 106, "2999-01-01", 2.5, 1))
    conn.commit()

    with _client(app_module, conn) as cl:
        hot = cl.get("/api/map-progress").get_json()
    conn.close()

    conn2 = _mk_conn(with_identity=True); _seed(conn2)
    conn2.execute("INSERT INTO srs_cards(user_id,question_id,due_date,ease_factor,repetitions) "
                  "VALUES (?,?,?,?,?)", (_UID, 106, "2999-01-01", 2.5, 1))
    conn2.commit()
    with _client(app_module, conn2) as cl:
        cold = cl.get("/api/map-progress").get_json()
    conn2.close()

    def _practiced(js, mid):
        return next(m["practiced"] for m in js if m["map_id"] == mid)
    # cold: only 106 counts; hot: 106 + folded 107 both count in mapA
    assert _practiced(hot, "mapA") == _practiced(cold, "mapA") + 1


def test_hot_true_srs_due_suppresses_duplicate_synthetic_card(app_module):
    conn = _mk_conn(with_identity=True); _seed(conn)
    st = _make_hot(conn)
    u = st.create_native_identity(creation_reason="dup", legacy_question_id="108")
    st._insert_alias(u, "LEGACY_QUESTION_ID", "109", context="post-genesis",
                     confidence="RECORDED", recorded_by="w2", when=_FIXED)
    conn.execute("INSERT INTO srs_cards(user_id,question_id,due_date) VALUES (?,?,?)",
                 (_UID, 108, "2000-01-01"))
    conn.commit()
    with _client(app_module, conn) as cl:
        due_ids = {d["question_id"] for d in cl.get("/api/srs/due").get_json()["due"]}
    conn.close()
    # 108 has a real due card; 109 (same identity) must NOT also appear as a
    # synthesized default card
    assert 108 in due_ids
    assert 109 not in due_ids


# ============================================================ scope firewall

def test_scope_firewall_app_py_reader_only():
    src = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    # the W2 helper block + the 7 wired sites add no identity write / mint / bootstrap
    for tok in ("GenesisBootstrap", "mint_genesis_uuid",
                "INSERT INTO puzzle_identity", "UPDATE puzzle_identity",
                "create_native_identity(", "create_historical_genesis_identity("):
        assert tok not in src, tok
    # reward granting stays on raw-id semantics
    assert "_stage_completion_state(\n            uid, conn, fold_identity=False\n        )" in src \
        or "fold_identity=False" in src
    # returned answer ids stay integers (no uuid substituted into a response id)
    assert "'id':           qid," in src or "'id': qid" in src


def test_optional_sites_not_touched():
    src = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    for fn in ("_newbie_daily_completed_count", "_training_contaminated_total",
               "_load_rt_calibration"):
        body = src.split(f"def {fn}(", 1)[1].split("\ndef ", 1)[0]
        assert "_IdentityKeyedSet" not in body and "_identity_group_key_map" not in body, fn


# ============================================================ PostgreSQL parity

_PG_IMAGE = "postgres:16.14-alpine"
_PG_U = _PG_P = _PG_D = "lc019w2"


def _docker(*a):
    return subprocess.run(["docker", *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture(scope="module")
def pg_url():
    if shutil.which("docker") is None:
        pytest.skip("docker unavailable; PostgreSQL parity skipped")
    name = f"lc019w2-pg-{uuid.uuid4().hex[:12]}"
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


def test_pg_parity_identity_folding_primitive(pg_url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    a = _import_app_helpers()
    raw = psycopg2.connect(pg_url, cursor_factory=DictCursor)
    conn = PostgresConnectionWrapper(raw, pooled=False)
    try:
        # cold: guard False, no resolver, bijection semantics
        assert a._identity_tables_present(conn) is False
        conn.execute("SELECT 1")
        assert a._identity_group_key_map(conn, [1, 2, 3]) == {}
        identity_upgrade(conn)
        _seed_receipt(conn)
        assert a._identity_tables_present(conn) is True

        st = PuzzleIdentityStore(conn, clock=lambda: _FIXED)
        u = st.create_native_identity(creation_reason="pg", legacy_question_id="500")
        st._insert_alias(u, "LEGACY_QUESTION_ID", "777", context="post-genesis",
                         confidence="RECORDED", recorded_by="pg", when=_FIXED)
        rr = st.create_historical_genesis_identity(
            _v5("pgret"), receipt_sha256=_RID, canonical_source="g/pgr.sgf",
            legacy_question_id="600", creation_reason="genesis")
        st.retire_identity(rr, reason="w", actor="a")
        b1 = st.create_native_identity(creation_reason="amb1")
        b2 = st.create_native_identity(creation_reason="amb2")
        st._insert_alias(b1, "LEGACY_QUESTION_ID", "900", context="genesis-v1",
                         confidence="RECORDED", recorded_by="pg", when=_FIXED)
        st._insert_alias(b2, "LEGACY_QUESTION_ID", "900", context="post-genesis",
                         confidence="RECORDED", recorded_by="pg", when=_FIXED)

        gkm = a._identity_group_key_map(conn, [500, 777, 600, 900, 123456])
        assert gkm["500"] == gkm["777"] == ("uuid", u)
        assert gkm["600"] == ("uuid", rr)
        assert gkm["900"] == ("unresolved", "900")
        assert gkm["123456"] == ("legacy", "123456")
        s = a._IdentityKeyedSet([500, 900], gkm)
        assert 777 in s and 900 in s and len(s) == 2
    finally:
        conn.rollback()
        conn.close()


def test_resolve_batch_deduplicates_inputs_without_changing_missing_semantics(monkeypatch):
    conn = _mk_conn(with_identity=True)
    st = _make_hot(conn)
    calls = []
    original_all = PuzzleIdentityStore._all

    def observed_all(store, sql, params=()):
        if "puzzle_identity_alias" in sql:
            kind = "current" if "is_current" in sql else "historical"
            calls.append((kind, len(tuple(params))))
        return original_all(store, sql, params)

    monkeypatch.setattr(PuzzleIdentityStore, "_all", observed_all)
    wanted = list(range(100000, 100801)) + list(range(100000, 100400))
    out = st.resolve_batch(
        "LEGACY_QUESTION_ID",
        wanted,
        alias_context=None,
    )
    assert list(out) == [str(value) for value in range(100000, 100801)]
    assert all(row["status"] == "MISSING" for row in out.values())
    assert calls == [
        ("current", 402), ("current", 402), ("current", 3),
        ("historical", 400), ("historical", 400), ("historical", 1),
    ]
    conn.close()


def test_pg_resolve_batch_uses_bounded_large_chunks(pg_url, monkeypatch):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(pg_url, cursor_factory=DictCursor)
    conn = PostgresConnectionWrapper(raw, pooled=False)
    try:
        identity_upgrade(conn)
        _seed_receipt(conn)
        calls = []
        original_all = PuzzleIdentityStore._all

        def observed_all(store, sql, params=()):
            if "puzzle_identity_alias" in sql:
                kind = "current" if "is_current" in sql else "historical"
                calls.append((kind, len(tuple(params))))
            return original_all(store, sql, params)

        monkeypatch.setattr(PuzzleIdentityStore, "_all", observed_all)
        wanted = list(range(100000, 100801))
        out = PuzzleIdentityStore(conn).resolve_batch(
            "LEGACY_QUESTION_ID", wanted, alias_context=None
        )
        assert len(out) == len(wanted)
        assert all(row["status"] == "MISSING" for row in out.values())
        assert calls == [("current", 803), ("historical", 801)]
    finally:
        conn.rollback()
        conn.close()
