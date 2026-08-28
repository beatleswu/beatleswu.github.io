"""D036 player-experience closure checks for the server-driven Spirit path."""

import datetime as dt
import contextlib
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import pytest


TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import test_d030_r2_spirit_adventure_milestone_wiring as d030  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
HERO = ROOT / "hero.html"
PRESENTATION = ROOT / "js" / "e9" / "adventure_spirit_unlock_presentation.js"
STYLES = ROOT / "css" / "e9" / "adventure_spirit_unlock.css"
FIXTURE = ROOT / "tests" / "e2e" / "fixtures" / "d031_spirit_unlock_presentation.html"


@pytest.fixture(scope="module")
def app_module():
    d030._install_app_import_stubs()
    import app as module

    return module


@pytest.fixture()
def runtime(app_module, monkeypatch):
    conn = d030._new_db()
    state = {"zone_key": "k11_15"}

    def fake_get_db():
        return d030._DbContext(conn)

    def fake_adventure_state(_uid):
        return [{
            "key": state["zone_key"],
            "seen": 50,
            "unlocked": True,
            "cleared": False,
        }]

    monkeypatch.setattr(app_module, "get_db", fake_get_db)
    monkeypatch.setattr(app_module, "_adventure_state", fake_adventure_state)
    monkeypatch.setattr(app_module, "_adventure_map_state", lambda *args, **kwargs: {})
    app_module.app.config["TESTING"] = True
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = True
    try:
        yield conn, state
    finally:
        conn.close()


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id


def _prepare_pass(client, conn, user_id, *, zone_key, attempt_id, start_id):
    question_ids = list(range(start_id, start_id + 20))
    started_at = (dt.datetime.now() - dt.timedelta(minutes=5)).isoformat()
    with client.session_transaction() as session:
        session["adventure_boss_exam"] = {
            "zone_key": zone_key,
            "question_ids": question_ids,
            "started_at": started_at,
            "attempt_id": attempt_id,
        }
    reviewed_at = (dt.datetime.fromisoformat(started_at) + dt.timedelta(seconds=30)).isoformat()
    for question_id in question_ids:
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
            "VALUES(?,?,?,?,?)",
            (user_id, question_id, 5, reviewed_at, f"boss_trial:{attempt_id}"),
        )
    conn.commit()


def _prepare_fail(client, conn, user_id, *, zone_key, attempt_id, start_id):
    question_ids = list(range(start_id, start_id + 20))
    started_at = (dt.datetime.now() - dt.timedelta(minutes=5)).isoformat()
    with client.session_transaction() as session:
        session["adventure_boss_exam"] = {
            "zone_key": zone_key,
            "question_ids": question_ids,
            "started_at": started_at,
            "attempt_id": attempt_id,
        }
    reviewed_at = (dt.datetime.fromisoformat(started_at) + dt.timedelta(seconds=30)).isoformat()
    conn.executemany(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES(?,?,?,?,?)",
        [
            (user_id, question_id, 0, reviewed_at, f"boss_trial:{attempt_id}")
            for question_id in question_ids
        ],
    )
    conn.commit()


def _d036_postgres_schema(conn):
    for table in (
        "domain_event_outbox",
        "companion_operations",
        "pet_action_log",
        "pet_inventory",
        "pet_collection",
        "user_pets",
        "currency_log",
        "user_stats",
        "adventure_boss_progress",
        "adventure_zone_unlocks",
        "review_log",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    conn.execute(
        """CREATE TABLE review_log(
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            source_context TEXT NOT NULL DEFAULT 'practice'
        )"""
    )
    conn.execute(
        """CREATE TABLE adventure_boss_progress(
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
            PRIMARY KEY(user_id, zone_key)
        )"""
    )
    conn.execute(
        """CREATE TABLE adventure_zone_unlocks(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'placement',
            PRIMARY KEY(user_id, zone_key)
        )"""
    )
    conn.execute(
        """CREATE TABLE user_stats(
            user_id INTEGER PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE currency_log(
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE user_pets(
            user_id INTEGER PRIMARY KEY,
            pet_key TEXT NOT NULL,
            nickname TEXT,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            fullness INTEGER NOT NULL DEFAULT 60,
            affection INTEGER NOT NULL DEFAULT 10,
            selected_at TEXT NOT NULL,
            last_fed_at TEXT,
            last_interacted_at TEXT,
            updated_at TEXT,
            last_pet_at TEXT,
            last_train_at TEXT,
            daily_key TEXT,
            daily_bond INTEGER NOT NULL DEFAULT 0,
            daily_train_xp INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE pet_inventory(
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, item_key)
        )"""
    )
    conn.execute(
        """CREATE TABLE pet_action_log(
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE pet_collection(
            user_id INTEGER NOT NULL,
            pet_key TEXT NOT NULL,
            nickname TEXT,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            fullness INTEGER NOT NULL DEFAULT 60,
            affection INTEGER NOT NULL DEFAULT 10,
            selected_at TEXT NOT NULL,
            last_fed_at TEXT,
            last_interacted_at TEXT,
            last_pet_at TEXT,
            last_train_at TEXT,
            daily_key TEXT,
            daily_bond INTEGER NOT NULL DEFAULT 0,
            daily_train_xp INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, pet_key)
        )"""
    )
    from migrations.companion_operations_v1 import upgrade as upgrade_companion_schema
    from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox

    upgrade_outbox(conn)
    upgrade_companion_schema(conn)
    conn.commit()


def _load_postgres_helpers():
    helper_path = TESTS_DIR / "test_map_battle_persistence.py"
    spec = importlib.util.spec_from_file_location("d036_postgres_helpers", helper_path)
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    return helpers


@contextlib.contextmanager
def _d036_postgres_container(helpers):
    """Start disposable PostgreSQL with the proven bounded readiness window."""

    if not helpers._docker_available():
        pytest.skip("Docker server unavailable for D036 disposable PostgreSQL proof")
    name = f"go-odyssey-d036-pg-{uuid.uuid4().hex[:10]}"
    run = subprocess.run(
        [
            "docker", "run", "--rm", "-d", "--name", name,
            "-e", "POSTGRES_PASSWORD=go", "-e", "POSTGRES_USER=go",
            "-e", "POSTGRES_DB=go_odyssey", "-p", "127.0.0.1::5432",
            "postgres:16-alpine",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    container_id = run.stdout.strip()

    def wait_for_port(host, port, timeout=90.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(0.5)
                if sock.connect_ex((host, port)) == 0:
                    return
            time.sleep(0.25)
        raise TimeoutError(f"D036 disposable PostgreSQL port did not become ready: {host}:{port}")

    def wait_for_postgres(database_url, timeout=90.0):
        import psycopg2

        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                probe = psycopg2.connect(database_url, connect_timeout=3)
                probe.close()
                return
            except Exception as exc:  # pragma: no cover - environment timing
                last_error = exc
                time.sleep(0.5)
        raise last_error

    try:
        port_result = subprocess.run(
            ["docker", "port", container_id, "5432/tcp"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        host, port_text = port_result.stdout.strip().rsplit(":", 1)
        port = int(port_text)
        wait_for_port(host, port)
        database_url = f"postgresql://go:go@{host}:{port}/go_odyssey"
        wait_for_postgres(database_url)
        yield database_url
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_id],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


def test_disposable_postgres_d036_unlock_response_and_status_rehydrate(
    app_module, monkeypatch
):
    """Run the integrated Adventure -> Spirit -> status path on real PostgreSQL."""

    helpers = _load_postgres_helpers()
    with _d036_postgres_container(helpers) as database_url:
        seed = helpers._postgres_wrapper(database_url)
        try:
            _d036_postgres_schema(seed)
        finally:
            seed.close()

        class _PgDbContext:
            def __enter__(self):
                self.conn = helpers._postgres_wrapper(database_url)
                return self.conn

            def __exit__(self, exc_type, exc, tb):
                if exc_type is None:
                    self.conn.commit()
                else:
                    self.conn.rollback()
                self.conn.close()
                return False

        original_get_db = app_module.get_db
        original_state = app_module._adventure_state
        original_map_state = app_module._adventure_map_state
        app_module.get_db = _PgDbContext
        app_module._adventure_state = lambda _uid: [{
            "key": "k11_15",
            "seen": 50,
            "unlocked": True,
            "cleared": False,
        }]
        app_module._adventure_map_state = lambda *args, **kwargs: {}
        try:
            client = app_module.app.test_client()
            user_id = 36002
            _login(client, user_id)
            setup = helpers._postgres_wrapper(database_url)
            try:
                _prepare_pass(
                    client,
                    setup,
                    user_id,
                    zone_key="k11_15",
                    attempt_id="d036-postgres-first-clear",
                    start_id=36300,
                )
            finally:
                setup.close()

            first = client.post("/api/adventure/boss/finish", json={})
            assert first.status_code == 200
            first_body = first.get_json()
            assert first_body["passed"] is True
            assert first_body["adventure_spirit_unlock_results"][0]["status"] == "UNLOCKED"
            assert first_body["adventure_spirit_unlock_results"][0]["spirit_id"] == (
                "starpath_antlerling"
            )

            status = client.get("/api/pet/status")
            assert status.status_code == 200
            status_body = status.get_json()
            assert [item["key"] for item in status_body["collection"]["collection"]] == [
                "starpath_antlerling"
            ]
            owned = next(
                item for item in status_body["spirit_projection"]["spirits"]
                if item["spirit_id"] == "starpath_antlerling"
            )
            assert owned["owned"] is True

            setup = helpers._postgres_wrapper(database_url)
            try:
                _prepare_pass(
                    client,
                    setup,
                    user_id,
                    zone_key="k11_15",
                    attempt_id="d036-postgres-replay",
                    start_id=36400,
                )
            finally:
                setup.close()
            replay = client.post("/api/adventure/boss/finish", json={})
            assert replay.status_code == 200
            replay_body = replay.get_json()
            assert replay_body["replay"] is True
            assert replay_body["adventure_spirit_unlock_results"][0]["status"] == "REPLAY"

            verify = helpers._postgres_wrapper(database_url)
            try:
                assert verify.execute(
                    "SELECT COUNT(*) AS n FROM pet_collection "
                    "WHERE user_id=? AND pet_key=?",
                    (user_id, "starpath_antlerling"),
                ).fetchone()["n"] == 1
                assert verify.execute(
                    "SELECT COUNT(*) AS n FROM companion_operations WHERE user_id=?",
                    (user_id,),
                ).fetchone()["n"] == 1
            finally:
                verify.close()
        finally:
            app_module.get_db = original_get_db
            app_module._adventure_state = original_state
            app_module._adventure_map_state = original_map_state


def test_runtime_unlock_status_replay_and_failed_attempt_are_server_owned(
    app_module, client, runtime
):
    conn, state = runtime
    user_id = 36001
    _login(client, user_id)
    state["zone_key"] = "k11_15"

    _prepare_pass(
        client,
        conn,
        user_id,
        zone_key="k11_15",
        attempt_id="d036-first-clear",
        start_id=36000,
    )
    first = client.post("/api/adventure/boss/finish", json={})
    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body["passed"] is True
    unlocks = first_body["adventure_spirit_unlock_results"]
    assert [item["result_state"] for item in unlocks] == [
        "UNLOCKED", "NOT_ELIGIBLE", "NOT_ELIGIBLE"
    ]
    assert unlocks[0]["spirit_id"] == "starpath_antlerling"
    assert unlocks[0]["ownership_store"] == "pet_collection"

    status_after_unlock = client.get("/api/pet/status")
    assert status_after_unlock.status_code == 200
    status_body = status_after_unlock.get_json()
    collection = status_body["collection"]["collection"]
    assert [item["key"] for item in collection] == ["starpath_antlerling"]
    assert status_body["spirit_projection"]["active_spirit_id"] is None
    projection_item = next(
        item for item in status_body["spirit_projection"]["spirits"]
        if item["spirit_id"] == "starpath_antlerling"
    )
    assert projection_item["owned"] is True

    owned_before_replay = conn.execute(
        "SELECT COUNT(*) FROM pet_collection WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    operations_before_replay = conn.execute(
        "SELECT COUNT(*) FROM companion_operations WHERE user_id=?", (user_id,)
    ).fetchone()[0]

    _prepare_pass(
        client,
        conn,
        user_id,
        zone_key="k11_15",
        attempt_id="d036-replay",
        start_id=36100,
    )
    replay = client.post("/api/adventure/boss/finish", json={})
    assert replay.status_code == 200
    replay_body = replay.get_json()
    assert replay_body["passed"] is True
    assert replay_body["replay"] is True
    replay_result = replay_body["adventure_spirit_unlock_results"][0]
    assert replay_result["status"] == "REPLAY"
    assert replay_result["result_state"] == "NO_OP"
    assert replay_result["replay"] is True
    assert conn.execute(
        "SELECT COUNT(*) FROM pet_collection WHERE user_id=?", (user_id,)
    ).fetchone()[0] == owned_before_replay
    assert conn.execute(
        "SELECT COUNT(*) FROM companion_operations WHERE user_id=?", (user_id,)
    ).fetchone()[0] == operations_before_replay

    reloaded_status = client.get("/api/pet/status").get_json()
    assert [item["key"] for item in reloaded_status["collection"]["collection"]] == [
        "starpath_antlerling"
    ]

    _prepare_fail(
        client,
        conn,
        user_id,
        zone_key="k1_5",
        attempt_id="d036-failed",
        start_id=36200,
    )
    failed = client.post("/api/adventure/boss/finish", json={})
    assert failed.status_code == 200
    failed_body = failed.get_json()
    assert failed_body["passed"] is False
    assert failed_body["adventure_spirit_unlock_results"] == []
    assert conn.execute(
        "SELECT COUNT(*) FROM pet_collection WHERE user_id=? AND pet_key='fatty'",
        (user_id,),
    ).fetchone()[0] == 0


def test_index_refreshes_server_owned_pet_surface_after_result_completion():
    source = INDEX.read_text(encoding="utf-8")
    assert "fetch('/api/pet/status', { credentials:'include', cache:'no-store' })" in source
    assert "function refreshPetStatusFromServer()" in source
    assert "_petStatusPromise = null;" in source
    assert "adventure-spirit-unlock-complete" in source
    assert "applyHeroCombatAvatarToIndex();" in source


def test_hero_reloads_collection_on_reentry_and_renders_collection_without_active_pet():
    source = HERO.read_text(encoding="utf-8")
    assert "fetch('/api/pet/status', { credentials:'include', cache:'no-store' })" in source
    assert "const collection = _petState.collection || {};" in source
    assert "petRosterHTML(collection, { showSingle: true })" in source
    assert "if (canonical === 'pet')" in source
    assert "_petLoaded = true;" in source
    assert "loadPetStatus();" in source
    assert "adventure-spirit-unlock-complete" in source


def test_presentation_requires_the_accepted_d032_wire_and_rejects_ambiguous_batches():
    source = PRESENTATION.read_text(encoding="utf-8")
    for marker in (
        "ADVENTURE_SPIRIT_UNLOCK_RESULT_TRANSPORT_V1",
        "raw.result_state",
        "raw.ownership_created",
        "raw.already_owned",
        "raw.reason_code",
        "COMPLETION_EVENT",
        "SYNC_CHANNEL_NAME",
        "BroadcastChannel",
        "return actionable;",
        "many[j - 1].zoneKey",
    ):
        assert marker in source


def test_d036_static_revisions_follow_d031_cache_contract():
    index_source = INDEX.read_text(encoding="utf-8")
    fixture_source = FIXTURE.read_text(encoding="utf-8")
    assert "adventure_spirit_unlock.css?v=20260828d036" in index_source
    assert "adventure_spirit_unlock_presentation.js?v=20260828d036r2" in index_source
    assert "adventure_spirit_unlock_presentation.js?v=20260828d036r2" in fixture_source
    for path in (INDEX, FIXTURE):
        source = path.read_text(encoding="utf-8")
        assert "20260827d031" not in source
    source = STYLES.read_text(encoding="utf-8")
    assert "env(safe-area-inset-top)" in source
    assert "min-width: 44px" in source


def test_player_surfaces_do_not_create_client_owned_spirit_state():
    for path in (INDEX, HERO, PRESENTATION):
        source = path.read_text(encoding="utf-8")
        assert "pet_collection" not in source or path == PRESENTATION
        assert "adventure-spirit-unlock-complete" in source or path == PRESENTATION
