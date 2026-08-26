import sqlite3

import pytest

from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from spirit_lineage import (
    KNOWN_SPIRIT_IDS,
    SPIRIT_EFFECT_EVENT_TYPE,
    SPIRIT_EFFECT_SOURCE_AUTHORITY,
    SpiritContractError,
    SpiritOperationConflict,
    append_spirit_effect_event,
    build_spirit_effect_payload,
    validate_spirit_effect_event,
)


def _database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upgrade_outbox(conn)
    conn.commit()
    return conn


class _TrackingConnection:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self.commit_calls = 0

    def commit(self):
        self.commit_calls += 1
        return self._conn.commit()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _tracking_database() -> _TrackingConnection:
    conn = _TrackingConnection()
    upgrade_outbox(conn)
    conn.commit()
    return conn


def _request(**overrides):
    request = {
        "user_id": 7,
        "spirit_id": "ink_drop_kelpie",
        "source_settlement_id": "map-settlement-1",
        "effect_id": "kelpie-outgoing-bonus",
        "effect_policy_version": "spirit_combat_v1",
        "evolution_stage": "STAGE_III",
        "encounter_class": "NORMAL_MONSTER",
        "encounter_context": {"zone_key": "zone_08"},
        "damage_before_spirit": 100,
        "damage_after_spirit": 109,
        "modifier_delta": 9,
        "player_hp_before": 100,
        "monster_hp_before": 1000,
    }
    request.update(overrides)
    return request


@pytest.mark.parametrize("spirit_id", KNOWN_SPIRIT_IDS)
def test_all_six_spirits_build_server_authored_effect_payloads(spirit_id):
    payload = build_spirit_effect_payload(
        **_request(spirit_id=spirit_id, source_settlement_id=f"settlement-{spirit_id}")
    )

    assert payload is not None
    assert payload["contract_version"] == "SPIRIT_EFFECT_EVENT_V1"
    assert payload["server_authored"] is True
    assert payload["source_authority"] == SPIRIT_EFFECT_SOURCE_AUTHORITY
    assert payload["spirit_id"] == spirit_id
    assert payload["source_settlement_id"] == f"settlement-{spirit_id}"
    assert payload["trigger_phase"] == "POST_JUDGE"
    assert payload["before_judge"] is False
    assert validate_spirit_effect_event(payload)


def test_each_triggered_spirit_effect_uses_the_shared_outbox():
    conn = _database()
    try:
        events = [
            append_spirit_effect_event(
                conn,
                **_request(spirit_id=spirit_id, source_settlement_id=f"settlement-{index}")
            )
            for index, spirit_id in enumerate(KNOWN_SPIRIT_IDS, start=1)
        ]

        assert all(event["event_type"] == SPIRIT_EFFECT_EVENT_TYPE for event in events)
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type=?",
            (SPIRIT_EFFECT_EVENT_TYPE,),
        ).fetchone()[0] == len(KNOWN_SPIRIT_IDS)
    finally:
        conn.close()


def test_noop_invalid_projection_and_lord_emit_no_effect_event():
    conn = _database()
    try:
        assert append_spirit_effect_event(conn, **_request(triggered=False)) is None
        assert append_spirit_effect_event(conn, **_request(ownership_validated=False)) is None
        assert append_spirit_effect_event(conn, **_request(enabled=False)) is None
        assert append_spirit_effect_event(conn, **_request(active=False)) is None
        assert append_spirit_effect_event(conn, **_request(encounter_class="LORD")) is None
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type=?",
            (SPIRIT_EFFECT_EVENT_TYPE,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_non_triggered_policy_result_is_a_noop_without_an_event():
    conn = _database()
    try:
        assert append_spirit_effect_event(
            conn,
            **_request(effect_result={"spirit_id": "ink_drop_kelpie", "triggered": False}),
        ) is None
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type=?",
            (SPIRIT_EFFECT_EVENT_TYPE,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    "overrides",
    [
        {"spirit_id": "unknown-spirit"},
        {"source_settlement_id": None},
        {"effect_id": None},
        {"before_judge": True},
        {"trigger_phase": "JUDGE_INPUT"},
        {"trigger_phase": "BEFORE_JUDGE"},
        {"evolution_stage": "STAGE_IV"},
    ],
)
def test_invalid_effect_identity_or_phase_fails_closed(overrides):
    with pytest.raises(SpiritContractError):
        build_spirit_effect_payload(**_request(**overrides))


def test_validation_rejects_client_authority_and_invalid_lord_event():
    payload = build_spirit_effect_payload(**_request())
    assert payload is not None

    for field, value in (
        ("server_authored", False),
        ("ownership_validated", False),
        ("enabled", False),
        ("active", False),
        ("answer_correct", True),
        ("client_correctness", True),
        ("encounter_class", "LORD"),
    ):
        invalid = dict(payload)
        invalid[field] = value
        assert not validate_spirit_effect_event(invalid)

    legacy_without_marker = dict(payload)
    legacy_without_marker.pop("server_authored")
    legacy_without_marker.pop("source_authority")
    legacy_without_marker["contract_version"] = "LEGACY"
    assert validate_spirit_effect_event(legacy_without_marker) is True


def test_same_settlement_replay_returns_original_event_without_new_row():
    conn = _database()
    try:
        first = append_spirit_effect_event(conn, **_request())
        conn.commit()

        replay = append_spirit_effect_event(conn, **_request())

        assert replay["event_id"] == first["event_id"]
        assert replay["duplicate"] is True
        assert replay["replayed"] is True
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type=?",
            (SPIRIT_EFFECT_EVENT_TYPE,),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_changed_payload_with_same_settlement_identity_fails_closed():
    conn = _database()
    try:
        append_spirit_effect_event(conn, **_request())
        conn.commit()

        with pytest.raises(SpiritOperationConflict):
            append_spirit_effect_event(conn, **_request(damage_after_spirit=110))

        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type=?",
            (SPIRIT_EFFECT_EVENT_TYPE,),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_caller_rollback_rolls_back_effect_event_with_open_transaction():
    conn = _database()
    try:
        conn.execute("BEGIN")
        event = append_spirit_effect_event(conn, **_request())
        assert event["replayed"] is False
        assert conn.in_transaction
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type=?",
            (SPIRIT_EFFECT_EVENT_TYPE,),
        ).fetchone()[0] == 1

        conn.rollback()

        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type=?",
            (SPIRIT_EFFECT_EVENT_TYPE,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_append_does_not_create_a_second_connection_or_commit():
    conn = _tracking_database()
    try:
        commits_before = conn.commit_calls
        conn.execute("BEGIN")
        result = append_spirit_effect_event(conn, **_request())

        assert result["replayed"] is False
        assert conn.commit_calls == commits_before
        assert conn.in_transaction
    finally:
        conn.close()
