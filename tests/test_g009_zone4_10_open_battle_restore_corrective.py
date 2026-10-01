"""G009 Zone4-10 OPEN Map Battle restore corrective.

Owner design (2026-10-01): one Map Battle fights ONE monster across MULTIPLE
questions.  The monster is selected when the battle is created and the
persisted monster stays authoritative for the whole battle; a later
question's new-battle selection must not invalidate or replace it.

Production admits the Zone4-10 provider through the shared Map Battle
boundary.  This candidate still registers Zone4-10 as a disabled admission
slot, so these tests use a test-only boundary that admits the real provider
exactly as Production does.  The provider under test is the real module.
"""

from __future__ import annotations

import hashlib
import sqlite3
from types import MappingProxyType

import pytest

import app as app_module
import map_battle_runtime
from adventure_monster_runtime_contract import (
    AdventureMonsterRuntimeContractError,
    AdventureQuestionBinding,
    MissingBindingError,
    ProfileBindingMismatchError,
    WrongZoneBindingError,
    persistence_metadata,
)
from adventure_zone1_2_monster_runtime_provider import (
    ZONE1_2_BINDING_SOURCE,
    ZONE1_2_MONSTER_RUNTIME_PROVIDER,
    ZONE1_2_PROVIDER_ID,
)
from adventure_zone4_10_monster_runtime_provider import (
    ZONE4_10_BINDING_SOURCE,
    ZONE4_10_MONSTER_RUNTIME_PROVIDER,
    ZONE4_10_PROVIDER_ID,
    select_zone4_10_monster_profile,
)
from map_battle_persistence import (
    create_map_battle,
    ensure_map_battle_tables,
    issue_map_battle_attempt,
)
from map_battle_runtime import (
    MAP_BATTLE_PROVIDER_BOUNDARY,
    MapBattleProviderBoundary,
    ensure_submission_lifecycle_schema,
    issue_submission_nonce_for_attempt,
    resolve_map_battle_provider_for_new,
    settle_answer,
)

APP_ZONE = "k6_10"
PROVIDER_ZONE = "Z5"
USER_ID = 101
MODE = {"E10_MAP_BATTLE_V1_MODE": "global"}


class _AdmittedZone4_10Boundary(MapBattleProviderBoundary):
    """Test-only boundary admitting the real Zone4-10 provider (as Production)."""

    _PROVIDER_ID_BY_PERSISTENCE_SOURCE = MappingProxyType(
        {
            ZONE1_2_BINDING_SOURCE: ZONE1_2_PROVIDER_ID,
            ZONE4_10_BINDING_SOURCE: ZONE4_10_PROVIDER_ID,
        }
    )

    def __init__(self) -> None:
        super(MapBattleProviderBoundary, self).__init__(
            (ZONE1_2_MONSTER_RUNTIME_PROVIDER, ZONE4_10_MONSTER_RUNTIME_PROVIDER)
        )


ADMITTED = _AdmittedZone4_10Boundary()


def _qid_selecting(monster_id: str, *, exclude=()) -> int:
    for question_id in range(48000, 60000):
        if question_id in exclude:
            continue
        if select_zone4_10_monster_profile(PROVIDER_ZONE, question_id).monster_id == monster_id:
            return question_id
    raise AssertionError(f"no question id selects {monster_id}")


def _question(question_id: int) -> dict:
    content = f"(;SZ[19];B[dd];W[ee]C[q{question_id}])"
    return {"id": question_id, "source": f"g009/z4_10/{question_id}.sgf", "content": content}


def _revision(question: dict) -> str:
    return hashlib.sha256(question["content"].encode("utf-8")).hexdigest()


def _binding(question_id: int) -> AdventureQuestionBinding:
    return AdventureQuestionBinding(question_id, _revision(_question(question_id)))


QID_A = _qid_selecting("M047")                       # creates the battle
QID_B = _qid_selecting("M050")                       # later question, other monster
QID_A2 = _qid_selecting("M047", exclude={QID_A})     # later question, same monster
QIDS_OTHER = [_qid_selecting(m) for m in ("M049", "M053", "M054", "M046")]


def _db_battle_row(binding) -> dict:
    """Shape of a real persisted map_battles row (no question columns)."""
    return {
        "id": "g009-z4-10-battle",
        "zone_key": APP_ZONE,
        "state": "OPEN",
        "player_hp": 20,
        "player_hp_max": 20,
        "monster_hp": binding.max_hp,
        "monster_hp_max": binding.max_hp,
        **persistence_metadata(binding),
    }


def _new_binding():
    return ADMITTED.new_battle_binding(
        app_zone_key=APP_ZONE, question_binding=_binding(QID_A), user_id=USER_ID
    )


def test_fixture_question_ids_select_the_intended_monsters():
    assert select_zone4_10_monster_profile(PROVIDER_ZONE, QID_A).monster_id == "M047"
    assert select_zone4_10_monster_profile(PROVIDER_ZONE, QID_A2).monster_id == "M047"
    assert select_zone4_10_monster_profile(PROVIDER_ZONE, QID_B).monster_id == "M050"
    others = {select_zone4_10_monster_profile(PROVIDER_ZONE, q).monster_id for q in QIDS_OTHER}
    assert "M047" not in others and len(others) == len(QIDS_OTHER)
    # The five Production incident questions select monsters other than M047.
    incident = {select_zone4_10_monster_profile(PROVIDER_ZONE, q).monster_id
                for q in (48500, 48513, 48520, 48522, 48526)}
    assert "M047" not in incident


def test_e_new_battle_keeps_deterministic_selection():
    binding = _new_binding()
    assert binding.monster_id == "M047"
    assert binding.zone_key == PROVIDER_ZONE
    assert binding.persistence_version.split(":")[2] == "M047"
    again = ADMITTED.new_battle_binding(
        app_zone_key=APP_ZONE, question_binding=_binding(QID_A), user_id=USER_ID
    )
    assert again.monster_id == binding.monster_id
    assert ADMITTED.new_battle_binding(
        app_zone_key=APP_ZONE, question_binding=_binding(QID_B), user_id=USER_ID
    ).monster_id == "M050"


def test_a_open_battle_restores_when_next_question_selects_same_monster():
    battle = _db_battle_row(_new_binding())
    restored = ADMITTED.restore_binding(
        battle=battle, question_binding=_binding(QID_A2), user_id=USER_ID
    )
    assert restored.monster_id == "M047"


def test_b_open_battle_restores_with_persisted_monster_when_question_selects_another():
    battle = _db_battle_row(_new_binding())
    restored = ADMITTED.restore_binding(
        battle=battle, question_binding=_binding(QID_B), user_id=USER_ID
    )
    assert restored.monster_id == "M047"
    assert restored.question_binding == _binding(QID_B)
    assert restored.persistence_version == battle["migration_version"]


def test_b_app_restore_seam_no_longer_maps_mismatch_to_503(monkeypatch):
    battle = _db_battle_row(_new_binding())
    monkeypatch.setattr(
        app_module,
        "resolve_map_battle_provider_for_restore",
        lambda **kwargs: ADMITTED.restore_resolution(**kwargs),
    )
    question = _question(QID_B)
    metadata = {}
    monkeypatch.setattr(
        app_module, "_map_battle_question_binding", lambda q, m: _binding(q["id"])
    )
    resolution = app_module._map_battle_provider_for_restore(
        battle, question, metadata, user_id=USER_ID
    )
    assert resolution.binding.monster_id == "M047"


def test_c_multiple_questions_keep_the_same_persisted_monster():
    battle = _db_battle_row(_new_binding())
    for question_id in [QID_B, *QIDS_OTHER, QID_A2]:
        restored = ADMITTED.settlement_binding(
            battle=battle, question_binding=_binding(question_id), user_id=USER_ID
        )
        assert restored.monster_id == "M047"
        assert restored.max_hp == battle["monster_hp_max"]


def test_d_invalid_persisted_provider_state_still_fails_closed():
    binding = _new_binding()
    unknown_monster = _db_battle_row(binding)
    unknown_monster["migration_version"] = "w2.z4_10.binding.v1:Z5:M001:missing:v1"
    other_zone = _db_battle_row(binding)
    other_zone["migration_version"] = other_zone["migration_version"].replace(":Z5:", ":Z4:")
    bad_profile = _db_battle_row(binding)
    parts = bad_profile["migration_version"].split(":")
    parts[3] = "adventure_z5_normal_M999"
    bad_profile["migration_version"] = ":".join(parts)
    bad_hp = _db_battle_row(binding)
    bad_hp["monster_hp_max"] = binding.max_hp + 1
    bad_source = _db_battle_row(binding)
    bad_source["migration_source"] = "future-provider-v99"
    for battle, error in (
        (unknown_monster, MissingBindingError),
        (other_zone, WrongZoneBindingError),
        (bad_profile, ProfileBindingMismatchError),
        (bad_hp, ProfileBindingMismatchError),
        (bad_source, AdventureMonsterRuntimeContractError),
    ):
        with pytest.raises(error):
            ADMITTED.restore_binding(
                battle=battle, question_binding=_binding(QID_B), user_id=USER_ID
            )


def test_d_candidate_boundary_still_fails_closed_for_unadmitted_zone4_10():
    battle = _db_battle_row(_new_binding())
    with pytest.raises(AdventureMonsterRuntimeContractError):
        MAP_BATTLE_PROVIDER_BOUNDARY.restore_binding(
            battle=battle, question_binding=_binding(QID_B), user_id=USER_ID
        )


def test_f_zone1_2_restore_unchanged():
    question = AdventureQuestionBinding(8101, "rev-8101")
    later = AdventureQuestionBinding(8102, "rev-8102")
    for app_zone in ("k26_30", "k21_25"):
        binding = resolve_map_battle_provider_for_new(
            zone_key=app_zone, question_binding=question, user_id=USER_ID
        )
        battle = {**_db_battle_row(binding), "zone_key": app_zone}
        restored = MAP_BATTLE_PROVIDER_BOUNDARY.restore_binding(
            battle=battle, question_binding=later, user_id=USER_ID
        )
        assert restored.monster_id == binding.monster_id


def _lifecycle_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES (?)", (USER_ID,))
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    return conn


def _settle_one(conn, battle_id, question_id, step, revision):
    question = _question(question_id)
    attempt_id = issue_map_battle_attempt(
        conn,
        user_id=USER_ID,
        battle_id=battle_id,
        question_id=question_id,
        question_revision=_revision(question),
        initial_position_identity=f"pos-{question_id}",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        battle_revision_at_issue=revision,
        attempt_id=f"attempt-{step}",
        issued_at=f"2026-10-01T00:{step:02d}:00+00:00",
        expires_at="2026-10-02T00:00:00+00:00",
    )
    nonce = issue_submission_nonce_for_attempt(
        conn, user_id=USER_ID, attempt_id=attempt_id,
        now=f"2026-10-01T00:{step:02d}:10+00:00", mode_environ=MODE,
    )["submission_nonce"]
    return settle_answer(
        conn,
        user_id=USER_ID,
        payload={
            "battle_id": battle_id, "attempt_id": attempt_id, "submission_nonce": nonce,
            "battle_revision": revision, "question_revision": _revision(question),
            "player_color": "black", "transform_id": "identity",
            "transform_version": "transform-v1", "moves": [{"x": 3, "y": 3}],
        },
        question_loader=lambda qid: _question(qid),
        mode_environ=MODE,
        now=f"2026-10-01T00:{step:02d}:20+00:00",
        runtime_provider=ADMITTED,
        monster_profile_resolver=lambda *args: pytest.fail("fell back to legacy profile"),
    )


def test_g_lifecycle_hp_persists_across_questions_and_battle_completes():
    conn = _lifecycle_db()
    binding = _new_binding()
    battle_id = create_map_battle(
        conn, battle_id="g009-z4-10-lifecycle", user_id=USER_ID, zone_key=APP_ZONE,
        player_hp=20, player_hp_max=20, monster_hp=binding.max_hp,
        monster_hp_max=binding.max_hp, **persistence_metadata(binding),
        now="2026-10-01T00:00:00+00:00",
    )
    sequence = [QID_A, QID_B, *QIDS_OTHER, QID_A2] * 8
    previous_hp = binding.max_hp
    completed = False
    for step, question_id in enumerate(sequence, start=1):
        row = conn.execute(
            "SELECT state, monster_hp, battle_revision, migration_version FROM map_battles WHERE id=?",
            (battle_id,),
        ).fetchone()
        assert row["migration_version"] == binding.persistence_version  # monster immutable
        if row["state"] != "OPEN":
            completed = True
            break
        result = _settle_one(conn, battle_id, question_id, step, int(row["battle_revision"]))
        assert result["result"] == "CORRECT"
        after = conn.execute(
            "SELECT monster_hp FROM map_battles WHERE id=?", (battle_id,)
        ).fetchone()["monster_hp"]
        assert after < previous_hp            # same monster's HP keeps falling
        previous_hp = after
    final = conn.execute(
        "SELECT state, monster_hp, migration_version FROM map_battles WHERE id=?", (battle_id,)
    ).fetchone()
    assert completed or final["state"] == "COMPLETED"
    assert final["monster_hp"] == 0
    assert final["migration_version"] == binding.persistence_version
    conn.close()
