"""Disposable real-path Lord Trial runtime (E10 auto-next investigation).

Why this exists
---------------
The E10 Lord Trial same-page auto-next investigation was previously blocked
by its own tooling: every existing browser contract script stubs the
authoritative review endpoint, most of them with a literal

    /api/srs/review  ->  {"ok": true}

response (see ``tests/e2e/run_e10_owner_ipad_acceptance_hotfix_002.mjs`` and
``tests/e2e/run_e10_lord_trial_visible_board_recovery_contract.mjs``).  The
real route returns roughly twenty top-level fields, and the whole block of
``submitSRS()`` presentation work that runs *before* the Boss authority
handoff is gated on those fields (``data.monster``, ``data.pet``,
``data.player``, ``data.loot``, ``data.quest_updates``, ...).  Under an
``{"ok": true}``-only response none of that code executes at all, so a
failure originating there is structurally invisible to those scripts.

This module builds the missing runtime instead: a genuinely disposable
instance of the *real* application, so a later trace task can execute

    real WGo click -> real /api/srs/review -> real SRS.review
                   -> real submitSRS -> real Boss authority

with no behaviour substitution anywhere in that chain.

What is real here
-----------------
* Real Flask application object, imported from the repository's own
  ``app.py`` (only the same optional third-party import stubs that every
  existing ``tests/test_*.py`` in this repository already installs).
* Real ``/api/srs/review``, ``/api/adventure/boss/start``,
  ``/api/adventure/boss/finish``, ``/api/questions``, ``/api/auth/login``.
* Real ``index.html`` and ``srs.js``, served by the application's own
  routes.
* Real signed Flask session cookie, produced by the real login route
  against a real password hash.
* Real PostgreSQL, in a disposable throwaway container, with the schema
  created by the application's own ``init_db()``.

What is disposable
------------------
* The PostgreSQL container (``docker run --rm``, random name, random host
  port, removed on exit).  Production is never contacted.
* The question corpus (``QUESTIONS_JSON_PATH`` points at
  ``tests/fixtures/lord_trial_natural/questions.json``; the canonical
  corpus is never read or written).
* The session secret — a deterministic, synthetic, test-only ``SECRET_KEY``
  (see "Secret hygiene" below).
* The user account, created inside the throwaway database only.

Secret hygiene
--------------
``app.py`` resolves its session key at import time, in this order
(``app.py:116-126``):

1. ``SECRET_KEY`` in the environment — the file is never touched at all;
2. otherwise, an existing ``secret_key.txt`` next to ``app.py`` — read;
3. otherwise — **a new ``secret_key.txt`` is generated and written into the
   repository working tree.**

Branch 3 is a real side effect of merely importing ``app`` with no
``SECRET_KEY`` set, and ``secret_key.txt`` is untracked *and* not
gitignored, so a stray one is one careless ``git add`` away from being
committed.  ``tests/test_sgf_answer_review_queue.py`` has a worktree guard
asserting it is absent.

This harness therefore takes branch 1 and makes branches 2 and 3
unreachable, with two independent mechanisms established at *module import*
time — before any code path here can reach ``import app``:

* a deterministic synthetic ``SECRET_KEY`` is injected into the
  environment (matching the existing convention in
  ``tests/test_sgf_answer_review_queue.py:11`` and
  ``tests/test_e10_cinematic_state_foundation.py:58``); and
* a ``sys.addaudithook`` guard **refuses any open() of a path named
  secret_key.txt**, in any mode.  Audit hooks run before the operation, so
  a write is prevented rather than undone, and a read never yields
  contents.  The guard records that an attempt happened and nothing else —
  never a path's contents.

The guard is the belt to the environment variable's braces: even if the
injection were removed or an empty ``SECRET_KEY`` were inherited, this
harness still cannot create or read that file.

Production's secret loading is not modified by any of this; the harness
only supplies the environment input ``app.py`` already supports.

Process model
-------------
``app.py`` reads ``QUESTIONS_JSON_PATH`` and ``SECRET_KEY``, and ``db.py``
reads ``DATABASE_URL``, at *import* time, so this harness must own the
process from before ``import app``.  It is therefore a standalone script
rather than a pytest fixture, and callers drive it as a subprocess:

    python tests/lord_trial_natural_runtime.py serve
        Bring the runtime up, print one line of handshake JSON on stdout,
        then block until stdin closes or the process is terminated.
        Used by tests/e2e/run_e10_lord_autonext_browser_readiness.mjs.

    python tests/lord_trial_natural_runtime.py selfcheck
        Bring the runtime up, run the foundation-validation probes against
        it over real HTTP, print one JSON report on stdout, tear down.
        Used by tests/test_e10_lord_autonext_harness_foundation.py.

Neither mode mutates the repository, the canonical corpus, or Production.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_DIR = REPO_ROOT / 'tests' / 'fixtures' / 'lord_trial_natural'

# Disposable corpora. `single_ply` answers resolve immediately, so
# onBoardClick takes its synchronous submitSRS(3) branch. `multi_ply`
# answers carry one opponent reply, so the click goes through
# `answering = true` and the 400ms setTimeout before submitSRS(3) -- a
# different call stack and a different async ordering, which is the highest
# ranked environmental delta from Production.
QUESTIONS_FIXTURES = {
    'single_ply': _FIXTURE_DIR / 'questions.json',
    'multi_ply': _FIXTURE_DIR / 'questions_multi_ply.json',
}
DEFAULT_FIXTURE = 'single_ply'
QUESTIONS_FIXTURE = QUESTIONS_FIXTURES[DEFAULT_FIXTURE]

# Zone 1 / Lord Trial.  ADVENTURE_ZONES[0] in app.py; its books are the
# topics the disposable question fixture uses.
LORD_TRIAL_ZONE_KEY = 'k26_30'

# Enough credited questions to clear BOSS_UNLOCK_PCT (30) against the
# 30-question disposable corpus without pre-answering the whole zone.
SEEDED_CORRECT_QUESTIONS = 10

POSTGRES_IMAGE = 'postgres:16-alpine'

# ---------------------------------------------------------------------------
# Secret hygiene — established at module import, before anything here can
# reach ``import app``.  See the "Secret hygiene" section of the module
# docstring for why both mechanisms exist.
# ---------------------------------------------------------------------------

SECRET_KEY_FILE_NAME = 'secret_key.txt'

# app.py:578 defines CACHE_DB = 'katago_cache.db' -- a *relative* path, so
# sqlite3.connect(CACHE_DB) (app.py:8098, 8260) creates it in the process
# CWD, i.e. the repository root when this harness runs. That file is
# untracked and not gitignored, the same hygiene class as secret_key.txt.
# CACHE_DB is read at call time, so the harness redirects it to an in-memory
# database after import; app.py itself is not modified.
KATAGO_CACHE_FILE_NAME = 'katago_cache.db'
KATAGO_CACHE_TEST_BACKEND = ':memory:'
KATAGO_CACHE_ACCESS_ATTEMPTS = []

# Deterministic and obviously synthetic.  Deliberately assigned rather than
# ``setdefault``-ed: an inherited real SECRET_KEY would make this disposable
# runtime non-deterministic, and an inherited *empty* one would leave
# app.py's ``if os.environ.get('SECRET_KEY')`` falsy and send it straight to
# the file-writing branch.
SYNTHETIC_TEST_SECRET_KEY = 'e10-lord-trial-disposable-runtime-synthetic-test-secret-not-a-production-key'

# Every refused access, as {'mode': ..., 'blocked': True}.  Contents are
# never read, so nothing sensitive can land here.
SECRET_FILE_ACCESS_ATTEMPTS = []

# Recorded before the injection below, so a caller that had already imported
# app under some other configuration is detected instead of assumed away.
APP_IMPORTED_BEFORE_HARNESS_CONFIG = 'app' in sys.modules


def _secret_file_audit_hook(event, args):
    """Refuse any open() of a file named secret_key.txt.

    Audit hooks run *before* the operation, so raising here prevents the
    access entirely: no file is created, and no content is ever read.
    """
    if event != 'open':
        return
    try:
        path = args[0]
        name = os.path.basename(path) if isinstance(path, (str, bytes, os.PathLike)) else ''
        if isinstance(name, bytes):
            name = name.decode('utf-8', errors='replace')
    except Exception:
        return
    if name.lower() != SECRET_KEY_FILE_NAME:
        return
    SECRET_FILE_ACCESS_ATTEMPTS.append({'mode': str(args[1]), 'blocked': True})
    raise PermissionError(
        'lord_trial_natural_runtime: refusing to open secret_key.txt; the '
        'disposable runtime must use the synthetic SECRET_KEY instead'
    )


def _katago_cache_audit_hook(event, args):
    """Refuse any sqlite connection aimed at the repo-root KataGo cache.

    Scoped to that one filename: every other sqlite3.connect (shadow event
    storage, deployment fixtures, ...) passes through untouched. Like the
    secret guard, this raises before the connection is made, so the file is
    neither created nor opened.
    """
    if event != 'sqlite3.connect':
        return
    try:
        target = args[0]
        name = os.path.basename(os.fspath(target)) if isinstance(
            target, (str, bytes, os.PathLike)) else ''
        if isinstance(name, bytes):
            name = name.decode('utf-8', errors='replace')
    except Exception:
        return
    if name.lower() != KATAGO_CACHE_FILE_NAME:
        return
    KATAGO_CACHE_ACCESS_ATTEMPTS.append({'blocked': True})
    raise PermissionError(
        'lord_trial_natural_runtime: refusing to open katago_cache.db; the '
        'disposable runtime must use an in-memory KataGo cache instead'
    )


def install_secret_hygiene():
    """Inject the synthetic key and arm both guards. Safe to call repeatedly."""
    os.environ['SECRET_KEY'] = SYNTHETIC_TEST_SECRET_KEY
    if not getattr(install_secret_hygiene, '_hook_installed', False):
        sys.addaudithook(_secret_file_audit_hook)
        sys.addaudithook(_katago_cache_audit_hook)
        install_secret_hygiene._hook_installed = True


install_secret_hygiene()


# ---------------------------------------------------------------------------
# Companion modules
#
# The existing tests/test_*.py convention unconditionally replaces seven
# companion modules with stubs.  That is right for a source-level contract
# test, but a stub is a behaviour substitution, and this harness exists
# precisely to remove those.  All seven modules are present in this
# repository and import cleanly, so the harness imports the real ones and
# only falls back to a stub if a module genuinely cannot be imported here
# (e.g. a native dependency is absent on this machine).  Whatever ends up
# stubbed is reported, never silently assumed to be irrelevant.
# ---------------------------------------------------------------------------

COMPANION_MODULES = (
    'katago_explain',
    'explain_overrides',
    'grimoire_api',
    'question_taxonomy',
    'monster_taxonomy',
    'chapter_i18n',
    'backend_i18n',
)


def _stub_for(name, reason):
    module = types.ModuleType(name)
    module.__lord_trial_runtime_stub__ = reason
    if name == 'katago_explain':
        module.KataGoExplainer = type('KataGoExplainer', (), {})
    elif name == 'explain_overrides':
        module.get_override = lambda *args, **kwargs: None
    elif name == 'grimoire_api':
        from flask import Blueprint
        module.grimoire_bp = Blueprint('grimoire_stub_lord_trial_runtime', __name__)
        module.ensure_node_mastery_table = lambda *args, **kwargs: None
        module.calc_node_purity = lambda *args, **kwargs: None
    elif name == 'question_taxonomy':
        module.get_taxonomy = lambda *args, **kwargs: {}
    elif name == 'monster_taxonomy':
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
    elif name == 'chapter_i18n':
        module.localize_topic = lambda *args, **kwargs: ''
        module.localize_level = lambda *args, **kwargs: ''
    elif name == 'backend_i18n':
        module.badge_en = lambda *args, **kwargs: ''
        module.skill_node_en = lambda *args, **kwargs: ''
        module.title_en = lambda *args, **kwargs: ''
    return module


def resolve_companion_modules():
    """Import every companion module for real; report any that were stubbed."""
    stubbed = {}
    for name in COMPANION_MODULES:
        if name in sys.modules:
            continue
        try:
            __import__(name)
        except Exception as exc:  # pragma: no cover - environment dependent
            stubbed[name] = f'{type(exc).__name__}: {exc}'
            sys.modules[name] = _stub_for(name, stubbed[name])
    return stubbed


# ---------------------------------------------------------------------------
# Disposable PostgreSQL
#
# Same shape as the pre-existing disposable-Postgres pattern in
# tests/test_community_leaderboard_weekly_scheduler.py.
# ---------------------------------------------------------------------------

class HarnessUnavailable(RuntimeError):
    """The runtime cannot be built in this environment (not a defect)."""


def docker_available() -> bool:
    if shutil.which('docker') is None:
        return False
    try:
        result = subprocess.run(
            ['docker', 'version', '--format', '{{.Server.Version}}'],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _wait_for_port(host, port, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.2)
    raise HarnessUnavailable(f'timed out waiting for {host}:{port}')


def _wait_for_postgres(database_url, timeout=90.0):
    import psycopg2

    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(database_url)
            conn.close()
            return
        except Exception as exc:  # pragma: no cover - retried below
            last_error = exc
            time.sleep(0.5)
    raise HarnessUnavailable(f'disposable PostgreSQL never became ready: {last_error}')


@contextlib.contextmanager
def disposable_postgres():
    if not docker_available():
        raise HarnessUnavailable('docker server unavailable for the disposable Lord Trial runtime')
    container_name = f'go-odyssey-lord-trial-runtime-{uuid.uuid4().hex[:10]}'
    run = subprocess.run(
        [
            'docker', 'run', '--rm', '-d',
            '--name', container_name,
            '-e', 'POSTGRES_PASSWORD=go',
            '-e', 'POSTGRES_USER=go',
            '-e', 'POSTGRES_DB=go_odyssey',
            '-p', '127.0.0.1::5432',
            POSTGRES_IMAGE,
        ],
        capture_output=True, text=True,
    )
    if run.returncode != 0:
        raise HarnessUnavailable(f'could not start disposable PostgreSQL: {run.stderr.strip()}')
    container_id = run.stdout.strip()
    try:
        port_result = subprocess.run(
            ['docker', 'port', container_id, '5432/tcp'],
            capture_output=True, text=True, check=True,
        )
        host, port_text = port_result.stdout.strip().splitlines()[0].rsplit(':', 1)
        port = int(port_text)
        _wait_for_port(host, port)
        database_url = f'postgresql://go:go@{host}:{port}/go_odyssey'
        _wait_for_postgres(database_url)
        yield {
            'container_id': container_id,
            'container_name': container_name,
            'host': host,
            'port': port,
            'database_url': database_url,
        }
    finally:
        subprocess.run(['docker', 'rm', '-f', container_id], capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Real application, disposable environment
# ---------------------------------------------------------------------------

def _configure_disposable_environment(database_url, scratch_dir, questions_fixture):
    """Point the real application at throwaway resources only.

    Every value written here is process-local.  ``secret_key.txt``, ``.env``
    and the canonical ``questions.json`` are neither read nor written.
    """
    os.environ['DATABASE_URL'] = database_url
    os.environ['QUESTIONS_JSON_PATH'] = str(questions_fixture)
    # Re-assert the module-import-time injection, so this function is
    # self-sufficient if it is ever called from somewhere else.
    install_secret_hygiene()
    os.environ['SHADOW_EVENTS_PATH'] = str(Path(scratch_dir) / 'shadow_events.jsonl')
    # The application derives SESSION_COOKIE_SECURE from SITE_URL's scheme.
    # A loopback http origin is a configuration the application already
    # supports; without it the real session cookie is Secure-only and no
    # http client (urllib or Chrome) would ever send it back.
    os.environ['SITE_URL'] = 'http://127.0.0.1'
    # Live-static overlay is a deployment concern; the harness serves the
    # repository's own index.html/srs.js through the application routes.
    os.environ.pop('GO_ODYSSEY_LIVE_STATIC_ROOT', None)


def _import_real_app():
    # Fail closed rather than let app.py fall through to its
    # secret_key.txt-writing branch, or let an app imported under some other
    # configuration be mistaken for this runtime's.
    if os.environ.get('SECRET_KEY') != SYNTHETIC_TEST_SECRET_KEY:
        raise HarnessUnavailable(
            'synthetic SECRET_KEY is not in the environment; refusing to '
            'import app, which would otherwise write secret_key.txt'
        )
    if APP_IMPORTED_BEFORE_HARNESS_CONFIG:
        raise HarnessUnavailable(
            'app was already imported before this harness configured the '
            'disposable environment; run the harness as its own process'
        )
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    stubbed = resolve_companion_modules()
    import app as app_module
    return app_module, stubbed


def _apply_reviewed_migrations(database_url):
    """Run the repository's own reviewed migrations against the throwaway DB."""
    from migrations.sgf_admin_workbench_v1 import main as sgf_workbench_migration

    exit_code = sgf_workbench_migration(['--database-url', database_url, '--apply'])
    if exit_code != 0:
        raise HarnessUnavailable(
            f'sgf_admin_workbench_v1 migration failed with exit code {exit_code}'
        )


def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def _seed_disposable_user(app_module, username, password, plan, questions_fixture):
    """Create the single throwaway account and its zone progress evidence."""
    from werkzeug.security import generate_password_hash

    questions = json.loads(questions_fixture.read_text(encoding='utf-8'))
    credited = [q['id'] for q in questions[:SEEDED_CORRECT_QUESTIONS]]
    now = _now()

    with app_module.get_db() as conn:
        row = conn.execute(
            'INSERT INTO users(username, password_hash, is_admin, plan, created_at) '
            'VALUES(?,?,?,?,?) RETURNING id',
            (username, generate_password_hash(password), 0, plan, now),
        ).fetchone()
        uid = int(row['id'])
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        for qid in credited:
            conn.execute(
                'INSERT INTO srs_cards(user_id,question_id,ease_factor,interval,repetitions,'
                'due_date,last_grade,updated_at,progress_credited) VALUES(?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(user_id,question_id) DO NOTHING',
                (uid, qid, 2.5, 1, 1, datetime.date.today().isoformat(), 5, now, 1),
            )
            conn.execute(
                'INSERT INTO review_log(user_id,question_id,grade,topic,level,difficulty,'
                'reviewed_at,source_context) VALUES(?,?,?,?,?,?,?,?)',
                (uid, qid, 5, '1圍棋新手村', 'LV1', '30k',
                 # Dated before today so the seeded mastery evidence never
                 # consumes the free-tier daily allowance of the run itself.
                 (datetime.datetime.now() - datetime.timedelta(days=3)).isoformat(timespec='seconds'),
                 'practice'),
            )
        conn.commit()
    return uid, credited


def _prime_badge_threshold(app_module, uid):
    """Sit the account exactly one correct answer below a real badge.

    ``BADGE_DEFS``' lowest streak badge is ``streak_3`` (awarded at
    ``current_streak >= 3``, app.py:5334), and ``check_and_award()`` reads
    ``user_stats``.  Priming ``current_streak`` to 2 therefore makes the next
    *credited* correct review cross that threshold through the application's
    own award path.  No HTTP response is faked, no response JSON is edited,
    and ``onNewBadge`` is never called directly -- the badge has to come back
    in the real ``new_badges`` array or the probe reports that it did not.
    """
    with app_module.get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        conn.execute(
            'UPDATE user_stats SET current_streak=?, max_streak=? WHERE user_id=?',
            (2, 2, uid),
        )
        conn.commit()
    return {
        'mechanism': 'user_stats.current_streak = 2',
        'expected_badge_trigger': 'streak_3 (current_streak >= 3)',
    }


def _prime_rank_threshold(app_module, uid):
    """Sit the account one correct answer below a real LV promotion.

    ``_srs_review_operation`` sets ``ranked_up`` when
    ``xp_to_lv(xp) > xp_to_lv(xp - xp_gain)`` (app.py:11968-11974), and
    LV_THRESHOLDS[1] is 120.  Seeding ``xp = 119`` means any positive
    ``xp_gain`` promotes LV1 -> LV2 through the application's own path,
    which additionally runs ``give_rank_appearance()`` and can populate
    ``new_appearance_items``.  Nothing is faked; if the promotion does not
    happen, the probe reports ``ranked_up`` false.
    """
    threshold = int(app_module.LV_THRESHOLDS[1])
    seeded_xp = threshold - 1
    with app_module.get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        conn.execute(
            'UPDATE user_stats SET xp=?, rank_level=?, rank_xp=? WHERE user_id=?',
            (seeded_xp, 'LV1', seeded_xp, uid),
        )
        conn.commit()
    return {
        'mechanism': f'user_stats.xp = {seeded_xp}',
        'expected_trigger': f'ranked_up LV1 -> LV2 at xp >= {threshold}',
    }


class _ServerThread:
    """Real WSGI server for the real Flask app on an ephemeral local port."""

    def __init__(self, app, host='127.0.0.1'):
        from werkzeug.serving import make_server

        self._server = make_server(host, 0, app, threaded=True)
        self.host = host
        self.port = int(self._server.server_port)
        self.base_url = f'http://{host}:{self.port}'
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        _wait_for_port(self.host, self.port, timeout=30.0)

    def stop(self):
        with contextlib.suppress(Exception):
            self._server.shutdown()
        with contextlib.suppress(Exception):
            self._server.server_close()


@contextlib.contextmanager
def lord_trial_runtime(plan='premium', fixture=DEFAULT_FIXTURE, badge_priming=False,
                       rank_priming=False):
    """Yield a live, disposable, real-path Lord Trial runtime descriptor."""
    if fixture not in QUESTIONS_FIXTURES:
        raise HarnessUnavailable(f'unknown fixture: {fixture}')
    questions_fixture = QUESTIONS_FIXTURES[fixture]
    if not questions_fixture.is_file():
        raise HarnessUnavailable(f'missing disposable question fixture: {questions_fixture}')

    with disposable_postgres() as postgres, tempfile.TemporaryDirectory(
        prefix='lord-trial-runtime-'
    ) as scratch_dir:
        _configure_disposable_environment(
            postgres['database_url'], scratch_dir, questions_fixture
        )
        app_module, stubbed_modules = _import_real_app()

        # init_db() deliberately fails closed rather than creating the SGF
        # workbench tables at request time: on PostgreSQL their authority is
        # the already-reviewed PR332 migration.  Apply that same reviewed
        # migration to the throwaway database first, through its own CLI
        # entry point, exactly as an operator would.
        _apply_reviewed_migrations(postgres['database_url'])

        # Redirect the KataGo explanation cache away from the repository
        # root. app.py reads CACHE_DB at call time (app.py:8098, 8260), so
        # rebinding the module attribute is enough; app.py is not modified
        # and the cache functions are not stubbed.
        app_module.CACHE_DB = KATAGO_CACHE_TEST_BACKEND

        # The application's own schema creation, against the throwaway DB.
        app_module.init_db()

        username = f'lord-trial-runtime-{uuid.uuid4().hex[:8]}'
        password = secrets.token_urlsafe(18)
        uid, credited = _seed_disposable_user(
            app_module, username, password, plan, questions_fixture
        )
        badge_priming_state = (
            _prime_badge_threshold(app_module, uid) if badge_priming else None
        )
        rank_priming_state = (
            _prime_rank_threshold(app_module, uid) if rank_priming else None
        )

        questions = json.loads(questions_fixture.read_text(encoding='utf-8'))
        server = _ServerThread(app_module.app)
        server.start()
        try:
            yield {
                'base_url': server.base_url,
                'database_url': postgres['database_url'],
                'postgres_container': postgres['container_name'],
                'questions_json_path': str(questions_fixture),
                'badge_priming': badge_priming_state,
                'rank_priming': rank_priming_state,
                'zone_key': LORD_TRIAL_ZONE_KEY,
                'user_id': uid,
                'username': username,
                'password': password,
                'plan': plan,
                'question_ids': [q['id'] for q in questions],
                'seeded_correct_question_ids': credited,
                'accepted_moves': {str(q['id']): q['accepted_moves'] for q in questions},
                'boss_exam_size': int(app_module.BOSS_EXAM_SIZE),
                'boss_pass_score': int(app_module.BOSS_PASS_SCORE),
                'boss_unlock_pct': int(app_module.BOSS_UNLOCK_PCT),
                'stubbed_companion_modules': stubbed_modules,
                'secret_key_source': 'synthetic_test_env',
                'secret_key_is_synthetic': (
                    os.environ.get('SECRET_KEY') == SYNTHETIC_TEST_SECRET_KEY
                    and app_module.app.secret_key == SYNTHETIC_TEST_SECRET_KEY
                ),
                'secret_file_access_attempts': list(SECRET_FILE_ACCESS_ATTEMPTS),
                'katago_cache_backend': app_module.CACHE_DB,
                'katago_cache_access_attempts': list(KATAGO_CACHE_ACCESS_ATTEMPTS),
                'fixture': fixture,
                'app_module': app_module,
            }
        finally:
            server.stop()


# ---------------------------------------------------------------------------
# HTTP probes (real network calls against the disposable server)
# ---------------------------------------------------------------------------

class _HttpSession:
    """Minimal cookie-carrying HTTP client, so the signed session cookie the
    real login route issues is the one every later request presents."""

    def __init__(self, base_url):
        import http.cookiejar

        self.base_url = base_url.rstrip('/')
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def request(self, method, path, payload=None, headers=None):
        url = f'{self.base_url}{path}'
        data = None
        request_headers = dict(headers or {})
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            request_headers.setdefault('Content-Type', 'application/json')
        req = urllib.request.Request(url, data=data, method=method, headers=request_headers)
        try:
            with self.opener.open(req, timeout=60) as response:
                body = response.read().decode('utf-8', errors='replace')
                return response.status, dict(response.headers), body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            return exc.code, dict(exc.headers), body

    def json(self, method, path, payload=None, headers=None):
        status, response_headers, body = self.request(method, path, payload, headers)
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
        return status, response_headers, parsed, body

    def cookie_names(self):
        return sorted({cookie.name for cookie in self.jar})


def _json_type_map(payload):
    return {key: type(value).__name__ for key, value in sorted(payload.items())}


def run_foundation_validation(runtime):
    """Phase 4/6 probes: prove the runtime is not another synthetic shortcut."""
    report = {
        'base_url': runtime['base_url'],
        'zone_key': runtime['zone_key'],
        'checks': {},
        'evidence': {},
    }
    session = _HttpSession(runtime['base_url'])

    # --- real authenticated session -------------------------------------
    status, _, login, _raw = session.json('POST', '/api/auth/login', {
        'username': runtime['username'],
        'password': runtime['password'],
    })
    report['evidence']['login_status'] = status
    report['evidence']['session_cookie_names'] = session.cookie_names()
    report['checks']['AUTH_SESSION_REAL'] = bool(
        status == 200 and isinstance(login, dict) and login.get('ok') is True
        and 'session' in session.cookie_names()
    )

    # A wrong password against the same real route must fail, proving the
    # session above came from real credential verification.
    rejected = _HttpSession(runtime['base_url'])
    reject_status, _, _, _ = rejected.json('POST', '/api/auth/login', {
        'username': runtime['username'],
        'password': runtime['password'] + 'x',
    })
    report['evidence']['wrong_password_status'] = reject_status
    report['checks']['AUTH_REJECTS_BAD_CREDENTIAL'] = reject_status == 401

    # --- disposable database -------------------------------------------
    report['evidence']['database_url_host'] = runtime['database_url'].split('@', 1)[-1]
    report['evidence']['postgres_container'] = runtime['postgres_container']
    report['checks']['DISPOSABLE_DB_REAL'] = bool(
        '127.0.0.1' in runtime['database_url'] and runtime['postgres_container']
    )

    # --- real index.html / srs.js --------------------------------------
    index_status, _, index_html = session.request('GET', '/')
    report['evidence']['index_status'] = index_status
    report['checks']['REAL_INDEX_SUBMITSRS_PRESENT'] = bool(
        index_status == 200
        and 'async function submitSRS(grade){' in index_html
        and 'await _handleBossAnswer(grade, bossAnswerContext);' in index_html
    )
    report['evidence']['index_bytes'] = len(index_html)

    srs_status, _, srs_js = session.request('GET', '/srs.js')
    report['evidence']['srs_js_status'] = srs_status
    # B3 (ReviewTransport) moved the literal '/api/srs/review' endpoint string
    # out of srs.js and into js/game/review_transport.js; srs.js's own
    # review() is now a thin delegate to window.ReviewTransport.legacyReview.
    # Check for that delegation instead of the pre-B3 literal, which would no
    # longer appear in a genuinely current, non-stubbed srs.js.
    report['checks']['REAL_SRS_JS_LOADED'] = bool(
        srs_status == 200
        and 'window.ReviewTransport' in srs_js
        and '_reviewTransport.legacyReview' in srs_js
    )
    report['evidence']['srs_js_bytes'] = len(srs_js)

    # --- real signed Boss attempt --------------------------------------
    status, _, start, _raw = session.json('POST', '/api/adventure/boss/start', {
        'zone_key': runtime['zone_key'],
    })
    report['evidence']['boss_start_status'] = status
    report['evidence']['boss_start_body'] = start
    attempt_id = (start or {}).get('attempt_id')
    question_ids = (start or {}).get('question_ids') or []
    report['checks']['BOSS_ATTEMPT_REAL'] = bool(
        status == 200 and (start or {}).get('ok') is True
        and len(question_ids) == runtime['boss_exam_size']
    )
    report['checks']['BOSS_ATTEMPT_SIGNED'] = bool(
        isinstance(attempt_id, str) and attempt_id
    )

    # A forged attempt marker must be rejected by the real route, proving the
    # accepted marker is the server's signed session state and not a value the
    # client can choose.
    forged_status, _, forged, _raw = session.json('POST', '/api/srs/review', {
        'question_id': question_ids[0] if question_ids else runtime['question_ids'][0],
        'grade': 5,
        'source_context': 'boss_trial:forged-attempt-id',
    })
    report['evidence']['forged_boss_context_status'] = forged_status
    report['evidence']['forged_boss_context_error'] = (forged or {}).get('error')
    report['checks']['BOSS_ATTEMPT_CONTEXT_ENFORCED'] = forged_status == 400

    # --- real /api/srs/review -------------------------------------------
    first_qid = question_ids[0] if question_ids else None
    review_status, _, review, review_raw = session.json('POST', '/api/srs/review', {
        'question_id': first_qid,
        'grade': 5,
        'source_context': f'boss_trial:{attempt_id}',
        'response_ms': 4200,
    })
    report['evidence']['review_status'] = review_status
    report['evidence']['review_question_id'] = first_qid
    report['checks']['REAL_REVIEW_ROUTE_REACHABLE'] = bool(
        review_status == 200 and isinstance(review, dict) and review.get('ok') is True
    )
    if isinstance(review, dict):
        report['evidence']['REVIEW_RESPONSE_KEYS'] = sorted(review.keys())
        report['evidence']['REVIEW_RESPONSE_TYPES'] = _json_type_map(review)
        report['evidence']['review_response_bytes'] = len(review_raw)
        report['checks']['REVIEW_RESPONSE_IS_ONLY_OK_TRUE'] = (
            sorted(review.keys()) == ['ok']
        )
        # Which of submitSRS()'s pre-Boss-authority presentation gates this
        # response is capable of opening.  Not a claim about which one fails.
        gated = ('monster', 'pet', 'practice', 'player', 'sp', 'loot',
                 'appearance_loot', 'new_appearance_items', 'quest_updates',
                 'stats', 'new_badges', 'xp_gain', 'combo_mult', 'combo_streak',
                 'ranked_up', 'shield_used', 'pet_xp_gained', 'pet_xp_added')
        report['evidence']['submitsrs_gated_fields_present'] = sorted(
            key for key in gated if key in review
        )
        report['evidence']['submitsrs_gated_fields_absent'] = sorted(
            key for key in gated if key not in review
        )
    else:
        report['evidence']['REVIEW_RESPONSE_KEYS'] = []
        report['evidence']['REVIEW_RESPONSE_TYPES'] = {}
        report['checks']['REVIEW_RESPONSE_IS_ONLY_OK_TRUE'] = None

    # The review must be a real durable commit, not a 200 with no write.
    status, _, resumed, _raw = session.json('POST', '/api/adventure/boss/start', {
        'zone_key': runtime['zone_key'],
    })
    report['evidence']['boss_resume_body'] = resumed
    report['checks']['REVIEW_COMMITS_SERVER_SIDE'] = bool(
        status == 200 and (resumed or {}).get('resumed') is True
        and int((resumed or {}).get('answered_count') or 0) == 1
        and (resumed or {}).get('attempt_id') == attempt_id
    )

    report['checks']['REAL_FLASK_APP'] = bool(index_status == 200 and srs_status == 200)

    # --- secret hygiene -------------------------------------------------
    # The real session cookie above was signed by the synthetic key, so the
    # runtime demonstrably never needed secret_key.txt.
    report['evidence']['secret_file_access_attempts'] = list(SECRET_FILE_ACCESS_ATTEMPTS)
    report['checks']['SYNTHETIC_SECRET_IN_USE'] = bool(runtime['secret_key_is_synthetic'])
    report['checks']['NO_SECRET_KEY_FILE_ACCESS'] = not SECRET_FILE_ACCESS_ATTEMPTS
    report['ok'] = all(
        value is True for key, value in report['checks'].items()
        if key != 'REVIEW_RESPONSE_IS_ONLY_OK_TRUE'
    ) and report['checks'].get('REVIEW_RESPONSE_IS_ONLY_OK_TRUE') is False
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _public_descriptor(runtime):
    return {
        key: value for key, value in runtime.items()
        if key not in ('app_module',)
    }


def _cmd_serve(args):
    with lord_trial_runtime(
        plan=args.plan, fixture=args.fixture, badge_priming=args.badge_priming,
        rank_priming=args.rank_priming,
    ) as runtime:
        handshake = dict(_public_descriptor(runtime))
        handshake['ready'] = True
        print(json.dumps(handshake), flush=True)
        # Held open for the browser driver; closing stdin (or terminating the
        # process) tears the whole disposable runtime down.
        try:
            sys.stdin.read()
        except KeyboardInterrupt:
            pass


def _cmd_selfcheck(args):
    with lord_trial_runtime(
        plan=args.plan, fixture=args.fixture, badge_priming=args.badge_priming,
        rank_priming=args.rank_priming,
    ) as runtime:
        report = run_foundation_validation(runtime)
        report['runtime'] = {
            key: value for key, value in _public_descriptor(runtime).items()
            if key not in ('password', 'accepted_moves')
        }
        print(json.dumps(report, indent=2, sort_keys=False), flush=True)
    return 0 if report.get('ok') else 1


def main(argv=None):
    # Zone labels and messages are Chinese/emoji; a Windows cp950 console
    # would otherwise abort the run on the report itself.  JSON payloads are
    # additionally emitted ASCII-escaped so any consumer can parse them.
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('serve', 'selfcheck'))
    parser.add_argument('--plan', default='premium', choices=('free', 'premium'))
    parser.add_argument('--fixture', default=DEFAULT_FIXTURE, choices=tuple(QUESTIONS_FIXTURES))
    parser.add_argument(
        '--badge-priming', action='store_true',
        help='seed real user_stats one step below the streak_3 threshold',
    )
    parser.add_argument(
        '--rank-priming', action='store_true',
        help='seed real user_stats one step below the LV1->LV2 promotion',
    )
    args = parser.parse_args(argv)
    try:
        if args.mode == 'serve':
            _cmd_serve(args)
            return 0
        return _cmd_selfcheck(args)
    except HarnessUnavailable as exc:
        print(json.dumps({'ok': False, 'unavailable': True, 'reason': str(exc)}), flush=True)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
