"""RPG_WAVE1_PREREQUISITE_INTEGRATION_FIX_003 proof.

Standalone proof of the two approved Wave 1 integration fixes, extracted to
apply directly on top of current master with NO Lane A/B/C dependency:

  Fix 1 -- app._mitigate_authoritative_retaliation: naive
  round(monster_atk * (1 - dmg_reduce)) silently loses all armor mitigation
  at low integer attack values (round(2 * 0.92) == 2). On current master,
  monster_atk is still question-supplied (Lane B's roster authority has not
  landed) -- these tests exercise the real _update_monster_and_quests path
  with that question-supplied value directly, unlike the Lane-B-aware
  version of this test used in PR #384.

  Fix 2 -- an explicit two-key allowlist (APPROVED_PRESENTATION_EXTENSION_FIELDS
  = combat_stats, level_up_rewards) in the review_contracts.py /
  review_compatibility.py / legacy_review_serializer.py compatibility seam.
  Current master produces neither key yet -- that is expected; this seam is
  a prerequisite landed ahead of the lanes that will populate it.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "rpg-wave1-prerequisite-fix-003-test-secret")
import app as app_module  # noqa: E402
from app import _mitigate_authoritative_retaliation  # noqa: E402
from review_compatibility import (  # noqa: E402
    adapt_legacy_review_result,
    serialize_legacy_review_result,
)
from review_contracts import (  # noqa: E402
    APPROVED_PRESENTATION_EXTENSION_FIELDS,
    CORE_20_FIELDS,
    FULL_26_FIELDS,
    INTERNAL_DUPLICATE_4_FIELDS,
)

_ARMOR_EQUIP_ID = "cloth_robe"  # effects: {'player_dmg_reduce': 0.08}


# ---------------------------------------------------------------------------
# Fix 1: pure mitigation function
# ---------------------------------------------------------------------------

def test_mitigation_no_reduction_unchanged():
    assert _mitigate_authoritative_retaliation(2, 0.0) == 2
    assert _mitigate_authoritative_retaliation(20, 0.0) == 20
    assert _mitigate_authoritative_retaliation(8, 0.0) == 8


def test_mitigation_low_attack_required_example():
    assert _mitigate_authoritative_retaliation(2, 0.08) == 1


def test_mitigation_normal_attack_required_example():
    assert _mitigate_authoritative_retaliation(20, 0.08) == 18


def test_mitigation_floor_safety_never_negative_or_zero_from_positive_retaliation():
    for atk in range(2, 41):
        for reduce_pct in (0.01, 0.08, 0.25, 0.5, 0.9, 0.99):
            result = _mitigate_authoritative_retaliation(atk, reduce_pct)
            assert result >= 1
            assert result < atk  # any positive armor removes at least 1 point


def test_mitigation_retaliation_of_one_is_never_reduced_below_one():
    assert _mitigate_authoritative_retaliation(1, 0.08) == 1
    assert _mitigate_authoritative_retaliation(1, 0.99) == 1


# ---------------------------------------------------------------------------
# Fix 1: integration proof via the real _update_monster_and_quests path
# (current master -- no Lane B roster override, monster_atk is
# question-supplied, exactly as accepted pre-Wave1 behavior)
# ---------------------------------------------------------------------------

def _create_combat_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_stats (
                user_id INTEGER PRIMARY KEY,
                total_correct INTEGER NOT NULL DEFAULT 0,
                go_rank TEXT NOT NULL DEFAULT '30k',
                xp INTEGER NOT NULL DEFAULT 0,
                rank_level TEXT NOT NULL DEFAULT 'LV1',
                player_hp INTEGER NOT NULL DEFAULT 500,
                player_max_hp INTEGER NOT NULL DEFAULT 500
            );
            CREATE TABLE player_appearance (
                user_id INTEGER PRIMARY KEY,
                combat_weapon TEXT,
                combat_armor TEXT
            );
            CREATE TABLE player_inventory (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT,
                source TEXT,
                rarity TEXT
            );
            CREATE TABLE player_skills (
                user_id INTEGER NOT NULL,
                skill_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, skill_id)
            );
            CREATE TABLE battlefield_monster (
                user_id INTEGER NOT NULL,
                bf_date TEXT NOT NULL,
                monster_idx INTEGER NOT NULL DEFAULT 0,
                monster_type TEXT NOT NULL,
                monster_name TEXT NOT NULL,
                monster_avatar TEXT,
                max_hp INTEGER NOT NULL,
                current_hp INTEGER NOT NULL,
                defeated INTEGER NOT NULL DEFAULT 0,
                kill_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, bf_date)
            );
            """
        )
        conn.execute("INSERT INTO user_stats(user_id,total_correct,go_rank) VALUES(1,2000,'5k')")
        conn.execute(
            "INSERT INTO player_appearance(user_id,combat_weapon,combat_armor) VALUES(1,NULL,NULL)"
        )
        conn.execute(
            "INSERT INTO battlefield_monster(user_id,bf_date,monster_idx,monster_type,"
            "monster_name,monster_avatar,max_hp,current_hp,defeated,kill_count)"
            " VALUES(1,'2026-08-20',0,'goblin','LV1 goblin','g.webp',9999,9999,0,0)"
        )


def _run_wrong_answer(path, monkeypatch, *, monster_atk, equipped_armor=False):
    _create_combat_db(path)
    if equipped_armor:
        with sqlite3.connect(path) as conn:
            conn.execute(
                "INSERT INTO player_inventory(id,user_id,equip_id,equipped,obtained_at,source,rarity)"
                " VALUES(1,1,?,1,'2026-08-20','drop','common')",
                (_ARMOR_EQUIP_ID,),
            )
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *a, **k: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda conn, uid, amount: amount)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return app_module._update_monster_and_quests(
            conn, 1, 9001, 0, {"monster_atk": monster_atk}, 0, "2026-08-20",
        )


def test_armor_reduces_retaliation_at_low_attack_via_real_path(tmp_path, monkeypatch):
    baseline = _run_wrong_answer(tmp_path / "baseline.sqlite", monkeypatch, monster_atk=2)
    equipped = _run_wrong_answer(
        tmp_path / "equipped.sqlite", monkeypatch, monster_atk=2, equipped_armor=True
    )
    assert baseline["monster"]["player_dmg"] == 2
    assert equipped["monster"]["player_dmg"] == 1


def test_armor_reduces_retaliation_at_normal_attack_via_real_path(tmp_path, monkeypatch):
    baseline = _run_wrong_answer(tmp_path / "baseline.sqlite", monkeypatch, monster_atk=20)
    equipped = _run_wrong_answer(
        tmp_path / "equipped.sqlite", monkeypatch, monster_atk=20, equipped_armor=True
    )
    assert baseline["monster"]["player_dmg"] == 20
    assert equipped["monster"]["player_dmg"] == 18


def test_unequip_restores_baseline_via_real_path(tmp_path, monkeypatch):
    equipped = _run_wrong_answer(
        tmp_path / "equipped.sqlite", monkeypatch, monster_atk=2, equipped_armor=True
    )
    unequipped = _run_wrong_answer(
        tmp_path / "unequipped.sqlite", monkeypatch, monster_atk=2, equipped_armor=False
    )
    assert equipped["monster"]["player_dmg"] == 1
    assert unequipped["monster"]["player_dmg"] == 2


# ---------------------------------------------------------------------------
# Fix 2: approved presentation-extension seam
# ---------------------------------------------------------------------------

def _core_payload(**overrides):
    payload = {k: None for k in CORE_20_FIELDS}
    payload.update(overrides)
    return payload


def _full_payload(**overrides):
    payload = {k: None for k in FULL_26_FIELDS}
    payload.update(overrides)
    return payload


def test_approved_extensions_are_exactly_combat_stats_and_level_up_rewards():
    assert set(APPROVED_PRESENTATION_EXTENSION_FIELDS) == {"combat_stats", "level_up_rewards"}


def test_normal_legacy_result_unchanged_with_no_extensions_present():
    payload = _core_payload()
    serialized = serialize_legacy_review_result(payload)
    assert set(serialized) == set(CORE_20_FIELDS)
    payload_full = _full_payload()
    serialized_full = serialize_legacy_review_result(payload_full)
    assert set(serialized_full) == set(FULL_26_FIELDS)


def test_combat_stats_alone_is_approved():
    payload = _core_payload(combat_stats={"attack_bonus": 0.08})
    serialized = serialize_legacy_review_result(payload)
    assert serialized["combat_stats"] == {"attack_bonus": 0.08}
    assert set(serialized) == set(CORE_20_FIELDS) | {"combat_stats"}


def test_level_up_rewards_alone_is_approved():
    payload = _core_payload(level_up_rewards={"hp_gain": 12})
    serialized = serialize_legacy_review_result(payload)
    assert serialized["level_up_rewards"] == {"hp_gain": 12}
    assert set(serialized) == set(CORE_20_FIELDS) | {"level_up_rewards"}


def test_both_extensions_approved_simultaneously():
    payload = _core_payload(
        combat_stats={"attack_bonus": 0.08},
        level_up_rewards={"hp_gain": 12},
    )
    serialized = serialize_legacy_review_result(payload)
    assert serialized["combat_stats"] == {"attack_bonus": 0.08}
    assert serialized["level_up_rewards"] == {"hp_gain": 12}
    assert set(serialized) == set(CORE_20_FIELDS) | {"combat_stats", "level_up_rewards"}


def test_unknown_key_still_rejected():
    payload = _core_payload(not_an_approved_extension="nope")
    with pytest.raises(ValueError):
        adapt_legacy_review_result(payload)


def test_unknown_key_still_rejected_alongside_approved_ones():
    payload = _core_payload(
        combat_stats={"attack_bonus": 0.0},
        level_up_rewards={"hp_gain": 0},
        not_an_approved_extension="nope",
    )
    with pytest.raises(ValueError):
        adapt_legacy_review_result(payload)


def test_internal_duplicate_shape_still_requires_internal_flag():
    payload = {k: None for k in INTERNAL_DUPLICATE_4_FIELDS}
    with pytest.raises(ValueError):
        adapt_legacy_review_result(payload, internal=False)
    outcome = adapt_legacy_review_result(payload, internal=True)
    assert outcome.kind.value == "INTERNAL_DUPLICATE"


def test_extension_can_be_separated_and_reattached_without_mutating_core_shape():
    payload = _full_payload(combat_stats={"attack_bonus": 0.0})
    outcome = adapt_legacy_review_result(payload)
    assert "combat_stats" not in outcome.payload
    assert set(outcome.payload) == set(FULL_26_FIELDS)
    assert outcome.presentation_extensions == {"combat_stats": {"attack_bonus": 0.0}}
