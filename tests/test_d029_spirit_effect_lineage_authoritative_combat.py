"""D029 proof that Map Battle settlement emits D028 Spirit lineage facts."""

from __future__ import annotations

import json
import sqlite3

import pytest

import map_battle_runtime
from map_battle_persistence import (
    create_map_battle,
    ensure_map_battle_tables,
)
from map_battle_runtime import (
    ForbiddenClientAuthority,
    JudgeOutcome,
    ensure_submission_lifecycle_schema,
    issue_attempt_for_context,
    issue_submission_nonce_for_attempt,
    settle_answer,
)
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from monster_combat_profiles import MonsterCombatProfile
from spirit_lineage import (
    SPIRIT_EFFECT_EVENT_TYPE,
    SpiritOperationConflict,
    append_spirit_effect_event,
)


USER_ID = 2901
QUESTION = {
    "id": 9029,
    "source": "d029/authoritative-settlement.sgf",
    "content": "(;SZ[19];B[dd];W[ee])",
}
QUESTION_REVISION = "d029-question-revision"


def _projection(spirit_id: str, stage: str = "STAGE_III") -> dict[str, object]:
    return {
        "active_spirit_id": spirit_id,
        "ownership_validated": True,
        "evolution_stage": stage,
        "progression_level": 25,
        "effect_profile_id": None,
        "effect_policy_version": None,
        "enabled": True,
        "single_active_spirit": True,
        "source": "SERVER_B022_D008_PROJECTION",
    }


def _profile(encounter_class: str) -> MonsterCombatProfile:
    return MonsterCombatProfile(
        canonical_monster_id="d029-monster",
        zone_key="d029::settlement",
        roster_slot=None,
        encounter_class=encounter_class,
        max_hp=1000,
        attack=6,
        profile_id="d029-profile",
        stat_source="d029-test-fixture",
        compatibility_mode="D029_TEST_ONLY",
    )


def _database(
    *,
    spirit_id: str = "ink_drop_kelpie",
    encounter_class: str = "NORMAL_MONSTER",
    monster_hp: int = 1000,
    player_hp: int = 100,
    battle_id: str = "d029-battle",
):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES (?)", (USER_ID,))
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    upgrade_outbox(conn)
    create_map_battle(
        conn,
        battle_id=battle_id,
        user_id=USER_ID,
        zone_key="d029::settlement",
        player_hp=player_hp,
        player_hp_max=100,
        monster_hp=monster_hp,
        monster_hp_max=1000,
        now="2026-08-27T00:00:00+00:00",
    )
    attempt_id = f"{battle_id}:attempt"
    issue_attempt_for_context(
        conn,
        user_id=USER_ID,
        battle_id=battle_id,
        question=QUESTION,
        initial_position_identity=f"{battle_id}:position",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        attempt_id=attempt_id,
        issued_at="2026-08-27T00:00:00+00:00",
        expires_at="2026-08-28T00:00:00+00:00",
    )
    issued = issue_submission_nonce_for_attempt(
        conn,
        user_id=USER_ID,
        attempt_id=attempt_id,
        now="2026-08-27T00:01:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )
    conn.commit()
    return conn, issued["submission_nonce"], spirit_id, encounter_class


def _payload(conn: sqlite3.Connection, nonce: str, *, moves, revision: int = 0):
    attempt = conn.execute(
        "SELECT * FROM map_battle_attempts WHERE id LIKE '%:attempt'"
    ).fetchone()
    return {
        "battle_id": attempt["battle_id"],
        "attempt_id": attempt["id"],
        "submission_nonce": nonce,
        "battle_revision": revision,
        "question_revision": attempt["question_revision"],
        "player_color": "black",
        "transform_id": attempt["transform_id"],
        "transform_version": attempt["transform_version"],
        "moves": moves,
    }


def _settle(
    conn,
    nonce: str,
    spirit_id: str,
    encounter_class: str,
    *,
    moves,
    revision: int = 0,
    battle_id: str = "d029-battle",
    projection_resolver=None,
    payload_override=None,
    judge=None,
):
    payload = payload_override or _payload(conn, nonce, moves=moves, revision=revision)
    return settle_answer(
        conn,
        user_id=USER_ID,
        payload=payload,
        question_loader=lambda question_id: QUESTION if question_id == QUESTION["id"] else None,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-08-27T00:02:00+00:00",
        judge=judge,
        monster_profile_resolver=lambda _conn, _user_id, _battle_id: _profile(encounter_class),
        spirit_projection_resolver=projection_resolver
        or (lambda _conn, _user_id: _projection(spirit_id)),
    )


def _events(conn):
    rows = conn.execute(
        "SELECT * FROM domain_event_outbox WHERE event_type=? ORDER BY created_at",
        (SPIRIT_EFFECT_EVENT_TYPE,),
    ).fetchall()
    return [
        {**dict(row), "payload": json.loads(row["payload"])}
        for row in rows
    ]


@pytest.mark.parametrize(
    ("spirit_id", "moves", "encounter_class", "monster_hp", "player_hp", "effect_type"),
    [
        (
            "ink_drop_kelpie",
            [{"x": 3, "y": 3}],
            "NORMAL_MONSTER",
            1000,
            100,
            "OUTGOING_DAMAGE_PERCENT_BONUS",
        ),
        (
            "whispering_void_kit",
            [{"x": 0, "y": 0}],
            "NORMAL_MONSTER",
            1000,
            100,
            "INCOMING_DAMAGE_PERCENT_REDUCTION_MIN_ONE",
        ),
        (
            "star_shell_hatchling",
            [{"x": 3, "y": 3}],
            "BATTLEFIELD_BOSS",
            1000,
            100,
            "OUTGOING_DAMAGE_PERCENT_BONUS",
        ),
        (
            "starpath_antlerling",
            [{"x": 3, "y": 3}],
            "NORMAL_MONSTER",
            1000,
            100,
            "OUTGOING_DAMAGE_PERCENT_BONUS",
        ),
        (
            "fatty",
            [{"x": 3, "y": 3}],
            "NORMAL_MONSTER",
            350,
            100,
            "OUTGOING_DAMAGE_PERCENT_BONUS",
        ),
        (
            "obsidian_bastion",
            [{"x": 0, "y": 0}],
            "NORMAL_MONSTER",
            1000,
            35,
            "INCOMING_DAMAGE_PERCENT_REDUCTION",
        ),
    ],
)
def test_all_six_real_settlements_append_one_server_lineage_event(
    spirit_id,
    moves,
    encounter_class,
    monster_hp,
    player_hp,
    effect_type,
):
    conn, nonce, spirit_id, encounter_class = _database(
        spirit_id=spirit_id,
        encounter_class=encounter_class,
        monster_hp=monster_hp,
        player_hp=player_hp,
        battle_id=f"d029-{spirit_id}",
    )
    try:
        result = _settle(
            conn,
            nonce,
            spirit_id,
            encounter_class,
            moves=moves,
            battle_id=f"d029-{spirit_id}",
        )

        events = _events(conn)
        assert result["submission_state"] == "SETTLED"
        assert result["submission_id"] == events[0]["source_event_id"]
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["server_authored"] is True
        assert payload["source_authority"] == "server_combat_settlement"
        assert payload["spirit_id"] == spirit_id
        assert payload["effect_id"] == f"spirit_combat:{spirit_id}:{effect_type}"
        assert payload["source_settlement_id"] == result["submission_id"]
        assert payload["trigger_phase"] == "POST_JUDGE"
        assert payload["before_judge"] is False
        assert payload["encounter_class"] == encounter_class
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type=?",
            (SPIRIT_EFFECT_EVENT_TYPE,),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_noop_and_equipped_without_trigger_emit_no_lineage_event():
    conn, nonce, spirit_id, encounter_class = _database()
    try:
        result = _settle(
            conn,
            nonce,
            spirit_id,
            encounter_class,
            moves=[{"x": 0, "y": 0}],
        )
        assert result["result"] == "INCORRECT"
        assert _events(conn) == []
    finally:
        conn.close()


def test_lord_effect_is_suppressed_by_lineage_boundary():
    conn, nonce, spirit_id, _ = _database(encounter_class="LORD")
    try:
        result = _settle(
            conn,
            nonce,
            spirit_id,
            "LORD",
            moves=[{"x": 3, "y": 3}],
        )
        assert result["result"] == "CORRECT"
        assert _events(conn) == []
    finally:
        conn.close()


def test_rejected_settlement_cannot_emit_lineage_event():
    conn, nonce, spirit_id, encounter_class = _database()
    try:
        result = _settle(
            conn,
            nonce,
            spirit_id,
            encounter_class,
            moves=[{"x": 3, "y": 3}],
            judge=lambda *_args: JudgeOutcome(
                "INVALID", None, "map-battle-judge-v1", "d029_rejected_fixture"
            ),
        )
        assert result["submission_state"] == "REJECTED"
        assert _events(conn) == []
    finally:
        conn.close()


def test_same_committed_settlement_replay_does_not_create_new_event():
    conn, nonce, spirit_id, encounter_class = _database()
    try:
        first = _settle(
            conn,
            nonce,
            spirit_id,
            encounter_class,
            moves=[{"x": 3, "y": 3}],
        )
        conn.commit()
        first_event = _events(conn)[0]

        def must_not_re_evaluate(*_args):
            raise AssertionError("settlement replay must not re-evaluate Spirit")

        retry = _settle(
            conn,
            nonce,
            spirit_id,
            encounter_class,
            moves=[{"x": 3, "y": 3}],
            revision=first["battle_revision"],
            projection_resolver=must_not_re_evaluate,
        )
        assert retry["duplicate"] is True
        assert retry["submission_id"] == first["submission_id"]
        assert _events(conn)[0]["event_id"] == first_event["event_id"]
        assert len(_events(conn)) == 1
    finally:
        conn.close()


def test_same_lineage_identity_with_changed_payload_fails_closed():
    conn, nonce, spirit_id, encounter_class = _database()
    try:
        result = _settle(
            conn,
            nonce,
            spirit_id,
            encounter_class,
            moves=[{"x": 3, "y": 3}],
        )
        conn.commit()
        event = _events(conn)[0]
        payload = dict(event["payload"])
        payload["damage_after_spirit"] = int(payload["damage_after_spirit"]) + 1
        with pytest.raises(SpiritOperationConflict):
            append_spirit_effect_event(
                conn,
                user_id=USER_ID,
                spirit_id=payload["spirit_id"],
                source_settlement_id=payload["source_settlement_id"],
                effect_id=payload["effect_id"],
                effect_policy_version=payload["effect_policy_version"],
                evolution_stage=payload["evolution_stage"],
                encounter_class=payload["encounter_class"],
                encounter_context=payload["encounter_context"],
                damage_before_spirit=payload["damage_before_spirit"],
                damage_after_spirit=payload["damage_after_spirit"],
                modifier_delta=payload["modifier_delta"],
                player_hp_before=payload["player_hp_before"],
                monster_hp_before=payload["monster_hp_before"],
            )
        assert len(_events(conn)) == 1
    finally:
        conn.close()


def test_lineage_failure_rolls_back_combat_settlement(monkeypatch):
    conn, nonce, spirit_id, encounter_class = _database()
    try:
        def fail_lineage(*_args, **_kwargs):
            raise SpiritOperationConflict("changed lineage payload")

        monkeypatch.setattr(map_battle_runtime, "append_spirit_effect_event", fail_lineage)
        with pytest.raises(SpiritOperationConflict):
            _settle(
                conn,
                nonce,
                spirit_id,
                encounter_class,
                moves=[{"x": 3, "y": 3}],
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0
        assert tuple(conn.execute(
            "SELECT battle_revision, monster_hp FROM map_battles WHERE id='d029-battle'"
        ).fetchone()) == (0, 1000)
    finally:
        conn.close()


def test_rejected_client_claim_cannot_emit_lineage_event():
    conn, nonce, spirit_id, encounter_class = _database()
    try:
        payload = _payload(conn, nonce, moves=[{"x": 3, "y": 3}])
        payload["correct"] = True
        with pytest.raises(ForbiddenClientAuthority):
            _settle(
                conn,
                nonce,
                spirit_id,
                encounter_class,
                moves=payload["moves"],
                payload_override=payload,
            )
        assert _events(conn) == []
    finally:
        conn.close()
