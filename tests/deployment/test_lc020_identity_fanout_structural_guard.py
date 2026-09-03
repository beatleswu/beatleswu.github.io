"""Structural guard against LC020 identity-resolution fanout regressing.

The site-wide latency P0 was caused by the Adventure aggregate read resolving
puzzle identity with per-batch fanout: roughly 109 database round trips for one
authenticated page load, against ~4 after the repair.

Wall-clock thresholds would be machine-dependent and flaky, so this module
guards the STRUCTURE that actually caused the cost:

* the number of database round trips a bulk alias resolution issues;
* that duplicate input ids cannot multiply that work;
* that the Adventure aggregate resolves identity in a bounded number of passes
  rather than once per zone.

These are deterministic on any machine. A regression toward per-ID or
per-small-batch fanout fails loudly with the observed count.
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from puzzle_identity_store import (  # noqa: E402
    PuzzleIdentityStore,
    _RESOLVE_BATCH_SIZE_POSTGRES,
    _RESOLVE_BATCH_SIZE_SQLITE,
)

# The accepted structural reference from the LC020 repair. The pre-repair
# aggregate issued ~109 identity round trips; anything approaching that is the
# regression this guard exists to catch.
# Measured: 42,804 ids resolve in 10 round trips on the PostgreSQL batch
# size (5 chunks x 2 statements). The same corpus under the old 400-id
# batching costs 216. The budget sits between them, close to observed.
ACCEPTED_IDENTITY_DB_CALL_BUDGET = 12
PRE_REPAIR_SMALL_BATCH_COST = 216
PRE_REPAIR_OBSERVED_FANOUT = 109


class _BackendShim:
    """Presents a SQLite connection as the chosen backend module.

    ``PuzzleIdentityStore._resolve_batch_size`` unwraps ``conn._conn`` and reads
    that object's ``__class__.__module__`` to pick the batch size, so the shim
    has to sit at that exact position or the PostgreSQL path is never measured.
    """

    def __new__(cls, sqlite_conn, module_name):
        shim_cls = type("connection", (object,), {"__module__": module_name})
        obj = object.__new__(shim_cls)
        object.__setattr__(obj, "_sqlite", sqlite_conn)
        for name in ("execute", "cursor", "commit", "rollback"):
            setattr(shim_cls, name, _BackendShim._delegate(name))
        return obj

    @staticmethod
    def _delegate(name):
        def call(self, *args, **kwargs):
            return getattr(object.__getattribute__(self, "_sqlite"), name)(*args, **kwargs)
        return call


class _CountingConnection:
    """Wraps a connection and counts execute() round trips."""

    def __init__(self, sqlite_conn, module_name):
        # ``_conn`` is what _resolve_batch_size inspects.
        self._conn = _BackendShim(sqlite_conn, module_name)
        self.execute_count = 0
        self.statements = []

    def execute(self, sql, parameters=None):
        self.execute_count += 1
        self.statements.append(sql)
        if parameters is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, parameters)

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()


def _seeded_store(module_name):
    """A store over an in-memory SQLite DB, presenting as *module_name*."""

    from migrations.puzzle_identity_registry_v1 import upgrade as upgrade_identity

    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    # Use the governed migration rather than a hand-rolled schema, so this
    # guard measures the real query shape against the real table definition.
    upgrade_identity(raw)
    raw.commit()
    counting = _CountingConnection(raw, module_name or "sqlite3")
    store = PuzzleIdentityStore(counting)
    return store, counting


def _resolve(store, values, alias_kind="LEGACY_QUESTION_ID"):
    return store.resolve_batch(alias_kind, values, alias_context=None)


# ---------------------------------------------------------------------------
# Batch-size contract
# ---------------------------------------------------------------------------
def test_postgres_batch_size_is_materially_larger_than_sqlite():
    """The repair's core lever: PostgreSQL must not be capped at the SQLite limit."""

    assert _RESOLVE_BATCH_SIZE_SQLITE == 400
    assert _RESOLVE_BATCH_SIZE_POSTGRES >= 10_000
    assert _RESOLVE_BATCH_SIZE_POSTGRES > _RESOLVE_BATCH_SIZE_SQLITE * 10


# ---------------------------------------------------------------------------
# LC020_QUERY_COUNT_GUARD
# ---------------------------------------------------------------------------
def test_corpus_sized_resolution_stays_within_the_call_budget_on_postgres():
    """A corpus-sized resolve must not fan out into dozens of round trips."""

    store, counting = _seeded_store("psycopg2.extensions")
    corpus = [str(i) for i in range(42_804)]

    _resolve(store, corpus)

    # Contrast against the small-batch shape that caused the P0, measured on
    # the same corpus through the same code path.
    legacy_store, legacy_counting = _seeded_store("sqlite3")
    _resolve(legacy_store, corpus)
    assert legacy_counting.execute_count == PRE_REPAIR_SMALL_BATCH_COST
    assert counting.execute_count * 10 < legacy_counting.execute_count, (
        "the PostgreSQL batch size is no longer materially reducing round trips"
    )

    assert counting.execute_count <= ACCEPTED_IDENTITY_DB_CALL_BUDGET, (
        f"identity resolution issued {counting.execute_count} round trips for "
        f"{len(corpus)} ids; the pre-repair regression looked like "
        f"~{PRE_REPAIR_OBSERVED_FANOUT}. Budget is "
        f"{ACCEPTED_IDENTITY_DB_CALL_BUDGET}."
    )


def test_sqlite_keeps_its_conservative_parameter_limited_batching():
    """The SQLite host-parameter limit must still be respected."""

    store, counting = _seeded_store(None)
    _resolve(store, [str(i) for i in range(1200)])
    # 1200 ids / 400 per batch = 3 chunks, 2 statements each. Proves the SQLite
    # path did not silently adopt the PostgreSQL batch size and blow the
    # host-parameter limit.
    assert counting.execute_count == 6


# ---------------------------------------------------------------------------
# LC020_DUPLICATE_RESOLUTION_GUARD
# ---------------------------------------------------------------------------
def test_duplicate_ids_do_not_multiply_database_work():
    """Repeated ids must be de-duplicated before batching, not resolved twice."""

    unique = [str(i) for i in range(5_000)]

    store_unique, counting_unique = _seeded_store("psycopg2.extensions")
    _resolve(store_unique, unique)

    store_dupes, counting_dupes = _seeded_store("psycopg2.extensions")
    _resolve(store_dupes, unique * 4)  # same distinct set, 4x the input length

    assert counting_dupes.execute_count == counting_unique.execute_count, (
        "duplicate input ids increased database round trips; the resolver is "
        "not de-duplicating before batching"
    )


def test_duplicate_input_preserves_result_semantics():
    """De-duplication must not change what the caller gets back."""

    store, _counting = _seeded_store("psycopg2.extensions")
    values = ["7", "7", "9", "7", "9"]
    result = _resolve(store, values)

    assert set(result) == {"7", "9"}
    for entry in result.values():
        assert entry["status"] == "MISSING"
        assert entry["source_record_uuid"] is None


# ---------------------------------------------------------------------------
# Aggregate-level bound
# ---------------------------------------------------------------------------
def test_adventure_aggregate_resolves_identity_in_one_pass():
    """The Adventure aggregate must fold identity once, not once per zone.

    The pre-repair shape recomputed the per-zone question sets inside the loop
    and re-resolved identity for each; the repair hoists a single
    ``zone_question_sets`` map and performs one ``_identity_group_key_map``
    call. Guarding this in source keeps the aggregate from drifting back
    without needing a live authenticated request here (the E2E gate covers the
    behavioural half).
    """

    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def _adventure_state(")
    end = source.index("def _set_adventure_state_cache(", start)
    body = source[start:end]

    assert body.count("_identity_group_key_map(") == 1, (
        "the Adventure aggregate must resolve identity exactly once per request"
    )
    assert "zone_question_sets" in body, (
        "per-zone question sets must be computed once and reused"
    )
    # The expensive per-zone recomputation must not come back inside the loop.
    assert body.count("_questions_for_adventure_zone(qs,") <= 1, (
        "per-zone question filtering reappeared in the aggregate loop"
    )
