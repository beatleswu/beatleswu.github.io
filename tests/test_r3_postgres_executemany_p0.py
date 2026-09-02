"""The R3 baseline writer's batch INSERT must work through the PG wrapper.

Production R3 migration failure (exit 1, transaction rolled back):

    AttributeError: 'psycopg2.extensions.connection' object has no attribute
    'executemany'

``populate_frozen_historical_baseline`` writes its memberships with
``conn.executemany(...)``.  ``PostgresCursorWrapper`` has always implemented a
correct ``executemany``, but ``PostgresConnectionWrapper`` did not, so the call
fell through ``PostgresConnectionWrapper.__getattr__`` to the raw psycopg2
connection -- which has no such method.

Every existing test passed because they drive raw ``sqlite3`` connections, and
``sqlite3.Connection`` provides ``executemany`` natively.  The gap was only ever
reachable against PostgreSQL, i.e. only in Production.

The Docker-backed tests below are the authoritative reproduction; the fake-raw
connection tests pin the same contract without requiring a container.
"""

from __future__ import annotations

import pathlib
import sys

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db import PostgresConnectionWrapper, PostgresCursorWrapper  # noqa: E402


# ---------------------------------------------------------------------------
# A fake raw connection with exactly psycopg2's shape: cursor(), but no
# executemany().  This is what made the production call fall through.
# ---------------------------------------------------------------------------
class _FakeRawCursor:
    def __init__(self, journal):
        self._journal = journal
        self.rowcount = -1
        self.description = None
        self.closed = False

    def execute(self, sql, parameters=None):
        self._journal.append(("execute", sql, parameters))
        self.rowcount = 1

    def executemany(self, sql, seq_of_parameters):
        rows = list(seq_of_parameters)
        self._journal.append(("executemany", sql, rows))
        self.rowcount = len(rows)

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        self.closed = True
        self._journal.append(("cursor_close", None, None))


class _FakeRawConnection:
    """Mirrors psycopg2.extensions.connection: no connection-level executemany."""

    def __init__(self):
        self.journal = []
        self.cursors = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self, *args, **kwargs):
        cursor = _FakeRawCursor(self.journal)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = 1


def _wrapped():
    raw = _FakeRawConnection()
    return raw, PostgresConnectionWrapper(raw, pooled=False)


INSERT_SQL = (
    "INSERT INTO adventure_historical_mastery "
    "(user_id, question_id, baseline_version) VALUES (?, ?, ?) "
    "ON CONFLICT(user_id, question_id, baseline_version) DO NOTHING"
)
BATCH = [(1, 100, "V1"), (1, 101, "V1"), (2, 100, "V1")]


# ---------------------------------------------------------------------------
# The defect itself
# ---------------------------------------------------------------------------
def test_connection_wrapper_defines_executemany_itself():
    """The exact defect: it must be a real method, not a __getattr__ fallthrough.

    ``hasattr`` alone is not evidence -- ``__getattr__`` would answer for any
    name.  The contract is that the wrapper class itself defines it.
    """

    assert "executemany" in vars(PostgresConnectionWrapper), (
        "PostgresConnectionWrapper must define executemany; without it the call "
        "falls through __getattr__ to the raw psycopg2 connection"
    )
    assert callable(PostgresConnectionWrapper.executemany)


def test_raw_psycopg2_connection_still_lacks_executemany():
    """Documents why the __getattr__ fallthrough could never have worked."""

    psycopg2_extensions = pytest.importorskip("psycopg2.extensions")
    assert not hasattr(psycopg2_extensions.connection, "executemany")
    # The cursor is where the driver provides it -- which is what we delegate to.
    assert hasattr(psycopg2_extensions.cursor, "executemany")


def test_executemany_does_not_raise_attribute_error():
    """EXECUTEMANY_SUCCESS -- the exact production failure is closed."""

    raw, conn = _wrapped()
    cursor = conn.executemany(INSERT_SQL, BATCH)
    assert isinstance(cursor, PostgresCursorWrapper)
    assert [entry[0] for entry in raw.journal] == ["executemany"]


def test_executemany_translates_placeholders_and_preserves_batch_order():
    """EXECUTEMANY_PARAMETER_BATCH -- ? becomes %s, rows pass through in order."""

    raw, conn = _wrapped()
    conn.executemany(INSERT_SQL, BATCH)
    kind, sql, rows = raw.journal[0]

    assert kind == "executemany"
    assert "?" not in sql, "placeholders were not translated for PostgreSQL"
    assert sql.count("%s") == 3
    assert "ON CONFLICT" in sql
    assert rows == BATCH, "batch parameters must reach the driver unchanged, in order"


def test_executemany_makes_no_implicit_commit():
    """NO_IMPLICIT_COMMIT -- the caller owns the transaction boundary."""

    raw, conn = _wrapped()
    conn.executemany(INSERT_SQL, BATCH)
    assert raw.commits == 0
    assert raw.rollbacks == 0
    # Committing stays an explicit caller action, exactly as for execute().
    conn.commit()
    assert raw.commits == 1


def test_executemany_matches_execute_transaction_shape():
    """EXISTING_EXECUTE_BEHAVIOR_UNCHANGED -- same shape, same non-commit."""

    raw, conn = _wrapped()
    execute_cursor = conn.execute("SELECT 1")
    executemany_cursor = conn.executemany(INSERT_SQL, BATCH)

    assert type(execute_cursor) is type(executemany_cursor) is PostgresCursorWrapper
    assert raw.commits == 0 and raw.rollbacks == 0
    assert [entry[0] for entry in raw.journal] == ["execute", "executemany"]


def test_executemany_exposes_rowcount_from_its_cursor():
    """rowcount is part of the existing cursor API; executemany must expose it."""

    _raw, conn = _wrapped()
    assert conn.executemany(INSERT_SQL, BATCH).rowcount == len(BATCH)


def test_executemany_uses_a_fresh_cursor_per_call():
    """CURSOR_LIFECYCLE -- one cursor per call, tied to the connection, closable."""

    raw, conn = _wrapped()
    first = conn.executemany(INSERT_SQL, BATCH)
    second = conn.executemany(INSERT_SQL, BATCH)

    assert first is not second
    assert len(raw.cursors) == 2
    first.close()
    assert raw.cursors[0].closed is True
    # The context-manager form closes deterministically, as for execute().
    with conn.executemany(INSERT_SQL, BATCH):
        pass
    assert raw.cursors[2].closed is True


def test_wrapper_context_manager_rolls_back_a_failed_batch():
    """ROLLBACK_ON_EXCEPTION -- a raising batch must not commit."""

    raw = _FakeRawConnection()

    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        with PostgresConnectionWrapper(raw, pooled=False) as conn:
            conn.executemany(INSERT_SQL, BATCH)
            raise _Boom("baseline capture failed mid-transaction")

    assert raw.rollbacks == 1
    assert raw.commits == 0


def test_wrapper_context_manager_commits_a_clean_batch():
    raw = _FakeRawConnection()
    with PostgresConnectionWrapper(raw, pooled=False) as conn:
        conn.executemany(INSERT_SQL, BATCH)
    assert raw.commits == 1
    assert raw.rollbacks == 0


# ---------------------------------------------------------------------------
# Authoritative reproduction against a real PostgreSQL server
# ---------------------------------------------------------------------------
def _real_wrapper(database_url):
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(database_url)
    raw.autocommit = False
    raw.cursor_factory = DictCursor
    return raw, PostgresConnectionWrapper(raw, pooled=False)


def _create_source_tables(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS srs_cards ("
        " user_id INTEGER NOT NULL, question_id INTEGER NOT NULL,"
        " last_grade INTEGER, progress_credited INTEGER DEFAULT 0,"
        " updated_at TEXT, PRIMARY KEY (user_id, question_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS review_log ("
        " id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,"
        " question_id INTEGER NOT NULL, grade INTEGER NOT NULL,"
        " reviewed_at TEXT NOT NULL, source TEXT, source_context TEXT)"
    )


@pytest.fixture(scope="module")
def postgres_database():
    from postgres_test_harness import disposable_postgres

    with disposable_postgres(name_prefix="go-odyssey-r3-executemany") as database:
        yield database


def test_real_postgres_executemany_inserts_the_batch(postgres_database):
    """The production call shape, against a real psycopg2 connection."""

    raw, conn = _real_wrapper(postgres_database["database_url"])
    try:
        conn.execute("DROP TABLE IF EXISTS executemany_probe")
        conn.execute(
            "CREATE TABLE executemany_probe ("
            " user_id INTEGER NOT NULL, question_id INTEGER NOT NULL,"
            " baseline_version TEXT NOT NULL,"
            " PRIMARY KEY (user_id, question_id, baseline_version))"
        )
        conn.commit()

        cursor = conn.executemany(
            "INSERT INTO executemany_probe (user_id, question_id, baseline_version) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, question_id, baseline_version) DO NOTHING",
            BATCH,
        )
        assert cursor.rowcount == len(BATCH)

        # NO_IMPLICIT_COMMIT: a second connection must not see uncommitted rows.
        other_raw, other = _real_wrapper(postgres_database["database_url"])
        try:
            assert (
                other.execute("SELECT COUNT(*) FROM executemany_probe").fetchone()[0]
                == 0
            ), "executemany committed implicitly"
        finally:
            other.close()
            other_raw.close()

        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM executemany_probe").fetchone()[0] == 3
    finally:
        conn.close()
        raw.close()


def test_real_postgres_batch_rolls_back_on_exception(postgres_database):
    """TRANSACTION_FAILURE_ROLLBACK against a real server."""

    raw, conn = _real_wrapper(postgres_database["database_url"])
    try:
        conn.execute("DROP TABLE IF EXISTS executemany_rollback_probe")
        conn.execute(
            "CREATE TABLE executemany_rollback_probe ("
            " user_id INTEGER NOT NULL, question_id INTEGER NOT NULL)"
        )
        conn.commit()

        conn.executemany(
            "INSERT INTO executemany_rollback_probe (user_id, question_id) "
            "VALUES (?, ?)",
            [(1, 10), (2, 20)],
        )
        conn.rollback()

        assert (
            conn.execute(
                "SELECT COUNT(*) FROM executemany_rollback_probe"
            ).fetchone()[0]
            == 0
        ), "rolled-back batch rows survived"
    finally:
        conn.close()
        raw.close()


def test_real_postgres_baseline_writer_completes_the_batch_insert(postgres_database):
    """BASELINE_BATCH_INSERT_PATH -- the exact former failure point, end to end."""

    from adventure_progress_compatibility import (
        BASELINE_VERSION,
        populate_frozen_historical_baseline,
    )
    from migrations.adventure_historical_mastery_v1 import (
        TABLE_NAME,
        upgrade as upgrade_mastery,
    )

    raw, conn = _real_wrapper(postgres_database["database_url"])
    try:
        conn.execute(f"DROP TABLE IF EXISTS public.{TABLE_NAME}")
        conn.execute("DROP TABLE IF EXISTS public.adventure_historical_mastery_baseline")
        conn.execute("DROP TABLE IF EXISTS srs_cards")
        conn.execute("DROP TABLE IF EXISTS review_log")
        conn.commit()

        _create_source_tables(conn)
        upgrade_mastery(conn)
        conn.commit()

        question_ids = set(range(100, 110))
        conn.executemany(
            "INSERT INTO srs_cards(user_id, question_id, last_grade, progress_credited)"
            " VALUES (?, ?, ?, ?)",
            [(uid, qid, 0, 1) for uid in (1, 2, 3) for qid in sorted(question_ids)],
        )
        conn.commit()

        # This is the call that raised AttributeError in Production.
        result = populate_frozen_historical_baseline(
            conn, question_ids=question_ids, captured_at="2026-08-01T00:00:00"
        )
        conn.commit()

        assert result["baseline_version"] == BASELINE_VERSION
        written = conn.execute(
            f"SELECT COUNT(*) FROM public.{TABLE_NAME} WHERE baseline_version=?",
            (BASELINE_VERSION,),
        ).fetchone()[0]
        assert written == 30, f"expected 3 users x 10 questions, got {written}"
    finally:
        conn.close()
        raw.close()


def test_real_postgres_baseline_writer_rolls_back_when_the_caller_fails(
    postgres_database,
):
    """A failure after the batch must leave no partial baseline behind."""

    from adventure_progress_compatibility import (
        BASELINE_VERSION,
        populate_frozen_historical_baseline,
    )
    from migrations.adventure_historical_mastery_v1 import (
        TABLE_NAME,
        upgrade as upgrade_mastery,
    )

    raw, conn = _real_wrapper(postgres_database["database_url"])
    try:
        conn.execute(f"DROP TABLE IF EXISTS public.{TABLE_NAME}")
        conn.execute("DROP TABLE IF EXISTS public.adventure_historical_mastery_baseline")
        conn.execute("DROP TABLE IF EXISTS srs_cards")
        conn.execute("DROP TABLE IF EXISTS review_log")
        conn.commit()

        _create_source_tables(conn)
        upgrade_mastery(conn)
        conn.commit()

        question_ids = set(range(200, 205))
        conn.executemany(
            "INSERT INTO srs_cards(user_id, question_id, last_grade, progress_credited)"
            " VALUES (?, ?, ?, ?)",
            [(9, qid, 0, 1) for qid in sorted(question_ids)],
        )
        conn.commit()

        populate_frozen_historical_baseline(
            conn, question_ids=question_ids, captured_at="2026-08-01T00:00:00"
        )
        # The caller aborts instead of committing, exactly as the runner does on
        # any later failure.
        conn.rollback()

        assert (
            conn.execute(
                f"SELECT COUNT(*) FROM public.{TABLE_NAME} WHERE baseline_version=?",
                (BASELINE_VERSION,),
            ).fetchone()[0]
            == 0
        ), "an aborted capture left partial baseline rows behind"
    finally:
        conn.close()
        raw.close()
