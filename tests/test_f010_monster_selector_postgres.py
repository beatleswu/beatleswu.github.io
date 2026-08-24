from __future__ import annotations

import threading

import pytest

from migrations import monster_encounter_selector_state_v1 as selector_schema
from monster_encounter_selector import MonsterEncounterCandidate
from monster_encounter_selector_runtime import select_durable_monster_encounter


try:
    from test_map_battle_persistence import _postgres_container, _postgres_wrapper
except ImportError:  # pragma: no cover - depends on pytest import path
    from tests.test_map_battle_persistence import _postgres_container, _postgres_wrapper


def _catalog(count: int = 3):
    return tuple(
        MonsterEncounterCandidate(
            monster_id=f"zone_01_monster_{index}",
            zone_key="zone_01",
            encounter_class="COMMON",
            family_id=f"family_{index}",
        )
        for index in range(1, count + 1)
    )


def _worker(database_url, *, user_id, zone_key, operation_id, barrier, results):
    conn = _postgres_wrapper(database_url)
    try:
        barrier.wait(timeout=15)
        result = select_durable_monster_encounter(
            conn,
            user_id=user_id,
            zone_key=zone_key,
            encounter_operation_id=operation_id,
            candidates=_catalog(),
        )
        conn.commit()
        results.append(result)
    except Exception as error:  # assertion below reports the exact worker error
        conn.rollback()
        results.append(error)
    finally:
        conn.close()


def test_postgres_16_durable_selector_concurrency_replay_and_isolation():
    """Exercise real PostgreSQL row locks, replay keys, and cycle state."""

    with _postgres_container() as database_url:
        import psycopg2

        version_conn = psycopg2.connect(database_url)
        version_cursor = version_conn.cursor()
        version_cursor.execute("SHOW server_version")
        version = version_cursor.fetchone()[0]
        version_cursor.close()
        version_conn.close()
        assert str(version).startswith("16.")

        setup = _postgres_wrapper(database_url)
        assert selector_schema.upgrade(setup)["present"] is True
        setup.commit()
        setup.close()

        # Two genuinely new operations for one user/zone serialize against the
        # same state row and cannot both apply a stale cursor.
        barrier = threading.Barrier(2)
        results = []
        threads = [
            threading.Thread(
                target=_worker,
                args=(database_url,),
                kwargs={
                    "user_id": 101,
                    "zone_key": "zone_01",
                    "operation_id": f"new-operation-{index}",
                    "barrier": barrier,
                    "results": results,
                },
            )
            for index in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert not any(isinstance(result, Exception) for result in results), results
        assert len({result.monster_id for result in results}) == 2

        # Same new operation racing from two connections: one commits the
        # selection, the other waits and replays it without a second advance.
        barrier = threading.Barrier(2)
        replay_results = []
        threads = [
            threading.Thread(
                target=_worker,
                args=(database_url,),
                kwargs={
                    "user_id": 101,
                    "zone_key": "zone_01",
                    "operation_id": "same-operation-race",
                    "barrier": barrier,
                    "results": replay_results,
                },
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert not any(isinstance(result, Exception) for result in replay_results), replay_results
        assert len({result.monster_id for result in replay_results}) == 1
        assert sum(not result.replayed for result in replay_results) == 1
        assert sum(result.replayed for result in replay_results) == 1

        inspect = _postgres_wrapper(database_url)
        operation_count = inspect.execute(
            "SELECT COUNT(*) AS count FROM monster_encounter_selection_operation "
            "WHERE user_id=? AND zone_key=?",
            (101, "zone_01"),
        ).fetchone()["count"]
        state = inspect.execute(
            "SELECT cycle_generation, seen_monster_ids FROM monster_encounter_selector_state "
            "WHERE user_id=? AND zone_key=?",
            (101, "zone_01"),
        ).fetchone()
        assert operation_count == 3
        assert len(state["seen_monster_ids"]) == 3

        # The same operation key is scoped by both user and zone.
        for user_id, zone_key in ((202, "zone_01"), (101, "zone_02")):
            result = select_durable_monster_encounter(
                inspect,
                user_id=user_id,
                zone_key=zone_key,
                encounter_operation_id="same-operation-race",
                candidates=(
                    _catalog()
                    if zone_key == "zone_01"
                    else tuple(
                        MonsterEncounterCandidate(
                            f"zone_02_monster_{index}",
                            "zone_02",
                            "COMMON",
                            f"family_2_{index}",
                        )
                        for index in range(1, 4)
                    )
                ),
            )
            assert result.replayed is False
        inspect.commit()
        inspect.close()


def test_postgres_selector_rolls_back_operation_and_state_together():
    """A failure after either write cannot leave a half-selection behind."""

    with _postgres_container() as database_url:
        conn = _postgres_wrapper(database_url)
        selector_schema.upgrade(conn)
        conn.commit()
        conn.execute(
            """CREATE OR REPLACE FUNCTION f010_fail_operation_insert()
               RETURNS trigger LANGUAGE plpgsql AS $$
               BEGIN RAISE EXCEPTION 'f010 operation insert failure'; END;
               $$"""
        )
        conn.execute(
            """CREATE TRIGGER f010_fail_operation_insert_trigger
               BEFORE INSERT ON monster_encounter_selection_operation
               FOR EACH ROW EXECUTE FUNCTION f010_fail_operation_insert()"""
        )
        conn.commit()
        with pytest.raises(Exception, match="f010 operation insert failure"):
            select_durable_monster_encounter(
                conn,
                user_id=101,
                zone_key="zone_01",
                encounter_operation_id="rollback-insert",
                candidates=_catalog(count=1),
            )
        conn.rollback()
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM monster_encounter_selector_state"
        ).fetchone()["count"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM monster_encounter_selection_operation"
        ).fetchone()["count"] == 0
        conn.execute("DROP TRIGGER f010_fail_operation_insert_trigger ON monster_encounter_selection_operation")
        conn.execute("DROP FUNCTION f010_fail_operation_insert()")
        conn.commit()

        conn.execute(
            """CREATE OR REPLACE FUNCTION f010_fail_state_update()
               RETURNS trigger LANGUAGE plpgsql AS $$
               BEGIN RAISE EXCEPTION 'f010 state update failure'; END;
               $$"""
        )
        conn.execute(
            """CREATE TRIGGER f010_fail_state_update_trigger
               BEFORE UPDATE ON monster_encounter_selector_state
               FOR EACH ROW EXECUTE FUNCTION f010_fail_state_update()"""
        )
        conn.commit()
        with pytest.raises(Exception, match="f010 state update failure"):
            select_durable_monster_encounter(
                conn,
                user_id=101,
                zone_key="zone_01",
                encounter_operation_id="rollback-update",
                candidates=_catalog(count=1),
            )
        conn.rollback()
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM monster_encounter_selector_state"
        ).fetchone()["count"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM monster_encounter_selection_operation"
        ).fetchone()["count"] == 0
        conn.execute("DROP TRIGGER f010_fail_state_update_trigger ON monster_encounter_selector_state")
        conn.execute("DROP FUNCTION f010_fail_state_update()")
        conn.commit()
        conn.close()
