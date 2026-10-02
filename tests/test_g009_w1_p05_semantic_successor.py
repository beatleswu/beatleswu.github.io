"""P05 semantic successor coverage for the production Map Battle contract.

The historical protected test called the private progression helper directly
from an app context.  This successor keeps the exactly-once assertion at the
product boundary: a real local HTTP server, independent client cookie jars,
the formal application bootstrap, and PostgreSQL transactions.
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.cookiejar import CookieJar
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

from postgres_test_harness import disposable_postgres, docker_available


ROOT = Path(__file__).resolve().parents[1]
QUESTION_ID = 900001
ZONE_KEY = "legacy::g009-w1-p05-successor"
FORMAL_BOOTSTRAP = ROOT / "scripts" / "g008_character_catalog_successor_migrate.py"
QUESTIONS_JSON = ROOT / "tests" / "fixtures" / "acceptance" / "questions.json"


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _runtime_environment(database_url: str, port: int) -> dict[str, str]:
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "PRODUCTION": "0",
            "SECRET_KEY": "g009-p05-successor-local-only-secret",
            "PORT": str(port),
            "SITE_URL": f"http://127.0.0.1:{port}",
            "QUESTIONS_JSON_PATH": str(QUESTIONS_JSON),
            "E10_MAP_BATTLE_V1_MODE": "global",
            "GO_ODYSSEY_ACCEPTANCE_MODE": "1",
            "GO_ODYSSEY_ACCEPTANCE_PUBLISH_DISABLED": "1",
            "GO_ODYSSEY_ACCEPTANCE_SOURCE_SHA": source_sha,
            "APP_GIT_SHA": source_sha,
            "TURNSTILE_SECRET": "",
            "RESEND_API_KEY": "",
            "NEW_USER_NOTIFY_EMAIL": "",
            "ADMIN_NOTIFY_EMAIL": "",
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return environment


def _run_formal_bootstrap(environment: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, str(FORMAL_BOOTSTRAP)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, (
        "formal application bootstrap failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _wait_for_health(base_url: str, process: subprocess.Popen[str], log_dir: Path) -> None:
    deadline = time.monotonic() + 60
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=2) as response:
                if int(response.status) == 200:
                    return
        except Exception as error:  # pragma: no cover - timing dependent
            last_error = repr(error)
        time.sleep(0.25)

    stdout = (log_dir / "app.stdout.log").read_text(encoding="utf-8", errors="replace")
    stderr = (log_dir / "app.stderr.log").read_text(encoding="utf-8", errors="replace")
    raise AssertionError(
        "successor application did not become healthy\n"
        f"last_error={last_error}\nstdout:\n{stdout}\nstderr:\n{stderr}"
    )


@contextmanager
def _formal_local_server(database_url: str):
    """Run the exact source under test behind a local real HTTP server."""

    assert docker_available(), "Docker daemon is required for P05 successor coverage"
    port = _free_local_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = _runtime_environment(database_url, port)
    _run_formal_bootstrap(environment)

    with tempfile.TemporaryDirectory(prefix="g009-w1-p05-successor-") as temp_dir:
        log_dir = Path(temp_dir)
        stdout_path = log_dir / "app.stdout.log"
        stderr_path = log_dir / "app.stderr.log"
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            process = subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                _wait_for_health(base_url, process, log_dir)
                yield base_url, database_url
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=15)


def _clone_cookie_jar(source: CookieJar) -> CookieJar:
    target = CookieJar()
    for cookie in source:
        target.set_cookie(copy.copy(cookie))
    return target


def _http_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    jar: CookieJar | None = None,
) -> dict:
    cookie_jar = jar if jar is not None else CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers.update(
            {
                "Content-Type": "application/json",
                "X-Map-Battle-Client-Protocol": "v1",
            }
        )
    request = urllib.request.Request(
        base_url + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        status = int(error.code)
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = {"raw": raw}
    return {"status": status, "body": body}


def _db_connection(database_url: str, application_name: str):
    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor,
        application_name=application_name,
    )


def _db_rows(connection, sql: str, params=()) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def _db_one(connection, sql: str, params=()) -> dict | None:
    rows = _db_rows(connection, sql, params)
    return rows[0] if rows else None


def _snapshot(database_url: str, user_id: int, battle_id: str) -> dict:
    connection = _db_connection(database_url, "g009-w1-p05-successor-snapshot")
    try:
        return {
            "stats": _db_one(
                connection,
                """SELECT total_correct,current_streak,max_streak,mistake_corrected,
                           xp,combo_streak,max_combo,rank_level,rank_xp,
                           player_hp,player_max_hp
                      FROM user_stats WHERE user_id=%s""",
                (user_id,),
            ),
            "battle": _db_one(
                connection,
                """SELECT id,user_id,zone_key,state,battle_revision,
                           player_hp,player_hp_max,monster_hp,monster_hp_max,
                           completed_at
                      FROM map_battles WHERE id=%s AND user_id=%s""",
                (battle_id, user_id),
            ),
            "attempts": _db_rows(
                connection,
                """SELECT id,battle_id,question_id,state,battle_revision_at_issue,
                           submission_nonce_hash,settled_at
                      FROM map_battle_attempts
                     WHERE battle_id=%s AND user_id=%s
                     ORDER BY created_at,id""",
                (battle_id, user_id),
            ),
            "submissions": _db_rows(
                connection,
                """SELECT id,battle_id,attempt_id,user_id,submission_nonce_hash,
                           request_hash,settlement_state,judge_result,
                           authoritative_grade,damage_to_monster,damage_to_player,
                           monster_hp_before,monster_hp_after,player_hp_before,
                           player_hp_after,battle_revision_before,battle_revision_after
                      FROM map_battle_submissions
                     WHERE battle_id=%s AND user_id=%s
                     ORDER BY created_at,id""",
                (battle_id, user_id),
            ),
            "map_battle_reviews": _db_rows(
                connection,
                """SELECT id,question_id,grade,source_context,submission_id,
                           submission_payload_hash
                      FROM review_log
                     WHERE user_id=%s AND source_context LIKE 'mbv1:%%'
                     ORDER BY id""",
                (user_id,),
            ),
            "srs_cards": _db_rows(
                connection,
                "SELECT * FROM srs_cards WHERE user_id=%s AND question_id=%s",
                (user_id, QUESTION_ID),
            ),
            "mistake_log": _db_rows(
                connection,
                "SELECT * FROM mistake_log WHERE user_id=%s AND question_id=%s",
                (user_id, QUESTION_ID),
            ),
        }
    finally:
        connection.close()


def _state_projection(snapshot: dict) -> dict:
    """Retain persisted authoritative state while ignoring no semantic fields."""

    return {
        "stats": snapshot["stats"],
        "battle": snapshot["battle"],
        "attempts": snapshot["attempts"],
        "submissions": snapshot["submissions"],
        "map_battle_reviews": snapshot["map_battle_reviews"],
        "srs_cards": snapshot["srs_cards"],
        "mistake_log": snapshot["mistake_log"],
    }


def _prepare(base_url: str, jar: CookieJar) -> dict:
    response = _http_json(
        base_url,
        "POST",
        "/api/adventure/map-battles/v1/attempts",
        {"question_id": QUESTION_ID, "zone_key": ZONE_KEY},
        jar,
    )
    assert response["status"] == 200, response
    body = response["body"]
    assert body.get("ok") is True, response
    assert body.get("submission_nonce"), response
    return response


def _answer_payload(prepared: dict, moves: list[dict[str, int]]) -> dict:
    body = prepared["body"]
    battle = body.get("battle") or {}
    attempt = body.get("attempt") or {}
    return {
        "battle_id": body["battle_id"],
        "attempt_id": body["attempt_id"],
        "submission_nonce": body["submission_nonce"],
        "battle_revision": int(
            battle.get("battle_revision", attempt["battle_revision_at_issue"])
        ),
        "question_revision": body["question_revision"],
        "player_color": body["player_color"],
        "transform_id": body["transform_id"],
        "transform_version": body["transform_version"],
        "moves": moves,
    }


def _concurrent_duplicate(
    base_url: str,
    base_jar: CookieJar,
    payload: dict,
    database_url: str,
    battle_id: str,
) -> dict:
    barrier = threading.Barrier(2)
    dispatched = threading.Event()
    counter_lock = threading.Lock()
    dispatch_count = 0

    def worker(client_number: int) -> dict:
        nonlocal dispatch_count
        jar = _clone_cookie_jar(base_jar)
        barrier.wait(timeout=15)
        started = time.perf_counter_ns()
        with counter_lock:
            dispatch_count += 1
            if dispatch_count == 2:
                dispatched.set()
        response = _http_json(
            base_url,
            "POST",
            "/api/adventure/map-battles/v1/answers",
            payload,
            jar,
        )
        response["client_number"] = client_number
        response["client_thread_id"] = threading.get_ident()
        response["client_interval_started_ns"] = started
        response["client_interval_finished_ns"] = time.perf_counter_ns()
        return response

    lock_connection = _db_connection(database_url, "g009-w1-p05-successor-lock-holder")
    lock_cursor = lock_connection.cursor()
    futures = []
    activity: list[dict] = []
    lock_pid = None
    try:
        lock_cursor.execute("BEGIN")
        lock_cursor.execute(
            "SELECT id,battle_revision FROM map_battles WHERE id=%s FOR UPDATE",
            (battle_id,),
        )
        locked_battle = dict(lock_cursor.fetchone())
        lock_pid = int(
            next(
                iter(
                    _db_one(
                        lock_connection,
                        "SELECT pg_backend_pid() AS pid",
                    ).values()
                )
            )
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, number) for number in (1, 2)]
            assert dispatched.wait(timeout=15), "both HTTP clients did not dispatch"

            deadline = time.monotonic() + 15
            lock_waiters: list[dict] = []
            while time.monotonic() < deadline:
                observer = _db_connection(
                    database_url, "g009-w1-p05-successor-activity-observer"
                )
                try:
                    activity = _db_rows(
                        observer,
                        """SELECT pid,state,wait_event_type,wait_event,
                                          left(query,180) AS query
                                   FROM pg_stat_activity
                                  WHERE datname=current_database()
                                    AND pid<>pg_backend_pid()
                                  ORDER BY pid""",
                    )
                finally:
                    observer.close()
                lock_waiters = [
                    row
                    for row in activity
                    if row.get("wait_event_type") == "Lock"
                    and int(row.get("pid")) != lock_pid
                ]
                if lock_waiters:
                    break
                time.sleep(0.1)

            assert lock_waiters, (
                "no PostgreSQL lock waiter observed while the concurrent HTTP "
                f"requests were held; activity={activity}"
            )
            lock_connection.commit()
            results = [future.result(timeout=45) for future in futures]
    finally:
        with contextlib.suppress(Exception):
            lock_connection.rollback()
        lock_cursor.close()
        lock_connection.close()

    overlap = not (
        results[0]["client_interval_finished_ns"]
        <= results[1]["client_interval_started_ns"]
        or results[1]["client_interval_finished_ns"]
        <= results[0]["client_interval_started_ns"]
    )
    return {
        "clients": results,
        "client_intervals_overlap": overlap,
        "lock": {
            "holder_backend_pid": lock_pid,
            "held_battle": locked_battle,
            "lock_waiter_count": len(lock_waiters),
            "activity": activity,
        },
    }


def test_p05_one_logical_submission_has_one_authoritative_effect() -> None:
    """Exercise first, retry, and real concurrent duplicate semantics."""

    with disposable_postgres(
        name_prefix="g009-w1-p05-successor",
        user="p05_successor",
        password="p05_successor_local_password",
        database="g009_w1_p05_successor",
    ) as database:
        database_url = str(database["database_url"])
        with _formal_local_server(database_url) as (base_url, _):
            username = "p05_succ_" + uuid.uuid4().hex[:10]
            password = "P05-successor-local-2026!"
            jar = CookieJar()
            registered = _http_json(
                base_url,
                "POST",
                "/api/auth/register",
                {
                    "username": username,
                    "password": password,
                    "confirm": password,
                    "nickname": "P05 semantic successor",
                    "email": f"{username}@example.test",
                },
                jar,
            )
            assert registered["status"] == 200, registered

            observer = _db_connection(database_url, "g009-w1-p05-successor-user")
            try:
                user_row = _db_one(
                    observer,
                    "SELECT id,username FROM users WHERE username=%s",
                    (username,),
                )
            finally:
                observer.close()
            assert user_row is not None
            user_id = int(user_row["id"])

            first_prepared = _prepare(base_url, jar)
            first_payload = _answer_payload(first_prepared, [{"x": 3, "y": 3}])
            battle_id = str(first_prepared["body"]["battle_id"])
            before_first = _snapshot(database_url, user_id, battle_id)

            first = _http_json(
                base_url,
                "POST",
                "/api/adventure/map-battles/v1/answers",
                first_payload,
                jar,
            )
            assert first["status"] == 200, first
            assert first["body"].get("accepted") is True, first
            assert first["body"].get("duplicate") is False, first
            assert first["body"].get("result") == "CORRECT", first
            after_first = _snapshot(database_url, user_id, battle_id)

            assert len(after_first["submissions"]) == len(
                before_first["submissions"]
            ) + 1
            assert len(after_first["map_battle_reviews"]) == len(
                before_first["map_battle_reviews"]
            ) + 1
            assert after_first["battle"]["battle_revision"] == (
                before_first["battle"]["battle_revision"] + 1
            )
            assert after_first["submissions"][-1]["settlement_state"] == "SETTLED"

            duplicate = _http_json(
                base_url,
                "POST",
                "/api/adventure/map-battles/v1/answers",
                first_payload,
                jar,
            )
            assert duplicate["status"] == 200, duplicate
            assert duplicate["body"].get("accepted") is True, duplicate
            assert duplicate["body"].get("duplicate") is True, duplicate
            after_duplicate = _snapshot(database_url, user_id, battle_id)
            assert _state_projection(after_duplicate) == _state_projection(after_first)

            second_prepared = _prepare(base_url, jar)
            second_payload = _answer_payload(second_prepared, [{"x": 0, "y": 0}])
            before_concurrent = _snapshot(database_url, user_id, battle_id)
            concurrent = _concurrent_duplicate(
                base_url,
                jar,
                second_payload,
                database_url,
                battle_id,
            )
            after_concurrent = _snapshot(database_url, user_id, battle_id)
            clients = concurrent["clients"]

            assert concurrent["client_intervals_overlap"] is True
            assert concurrent["lock"]["lock_waiter_count"] >= 1
            assert len({id(item) for item in clients}) == 2
            assert len({item["client_thread_id"] for item in clients}) == 2
            assert all(item["status"] == 200 for item in clients), concurrent
            assert sorted(bool(item["body"].get("duplicate")) for item in clients) == [
                False,
                True,
            ]
            submission_ids = {item["body"].get("submission_id") for item in clients}
            assert len(submission_ids) == 1
            assert None not in submission_ids

            assert len(after_concurrent["submissions"]) == len(
                before_concurrent["submissions"]
            ) + 1
            assert len(after_concurrent["map_battle_reviews"]) == len(
                before_concurrent["map_battle_reviews"]
            ) + 1
            assert after_concurrent["battle"]["battle_revision"] == (
                before_concurrent["battle"]["battle_revision"] + 1
            )
            assert after_concurrent["submissions"][-1]["settlement_state"] == "SETTLED"
