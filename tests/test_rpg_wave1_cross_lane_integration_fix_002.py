"""RPG_WAVE1_CROSS_LANE_INTEGRATION_FIX_002 proof.

Covers the two cross-lane integration blockers identified against the
converged A+B+C tree (0a8d768cdb5faea847199c53a0080c336b6d5168):

  Blocker 1 -- Lane B's authoritative roster attack composed with Lane A's
  armor reduction silently loses all mitigation at low integer attack
  values (``round(2 * 0.92) == 2``). Fixed by
  ``app._mitigate_authoritative_retaliation``.

  Blocker 2 -- Lane A's ``combat_stats`` and Lane B's ``level_up_rewards``
  presentation additions break ``review_compatibility.adapt_legacy_review_result``'s
  exact legacy-shape check, turning a committed domain write into an HTTP 500.
  Fixed by the approved-extension allowlist seam in ``review_contracts.py``/
  ``review_compatibility.py``/``legacy_review_serializer.py``.

Fix 1 is proven here against SQLite (matching the existing Lane A unit-test
harness style); the full HTTP/PostgreSQL proof for both fixes lives in
tests/test_rpg_wave1_cross_lane_integration_fix_002_postgres.py.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "rpg-wave1-integration-fix-002-test-secret")
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

# Roster indices (see app._BATTLEFIELD_ROSTER): index 0 is the first LV1
# encounter (attack=2), index 14 is the LV8 golem (attack=20) -- these are
# exactly the task's required low/normal attack proof values.
_LOW_ATTACK_MONSTER_IDX = 0
_LOW_ATTACK_BASELINE = 2
_NORMAL_ATTACK_MONSTER_IDX = 14
_NORMAL_ATTACK_BASELINE = 20
_ARMOR_EQUIP_ID = "cloth_robe"  # effects: {'player_dmg_reduce': 0.08}


def _create_combat_db(path, *, monster_idx):
    roster = app_module._BATTLEFIELD_ROSTER[monster_idx]
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
        conn.execute(
            "INSERT INTO user_stats(user_id,total_correct,go_rank) VALUES(1,?,?)",
            (2000, "5k"),
        )
        conn.execute(
            "INSERT INTO player_appearance(user_id,combat_weapon,combat_armor) VALUES(1,NULL,NULL)"
        )
        conn.execute(
            """
            INSERT INTO battlefield_monster(
                user_id,bf_date,monster_idx,monster_type,monster_name,
                monster_avatar,max_hp,current_hp,defeated,kill_count
            ) VALUES(1,'2026-08-20',?,?,?,'m.webp',9999,9999,0,0)
            """,
            (monster_idx, roster[0], roster[1]),
        )


def _run_wrong_answer(path, monkeypatch, *, monster_idx, equipped_armor=False):
    """Exercise the real, merged, fixed authoritative retaliation path."""
    _create_combat_db(path, monster_idx=monster_idx)
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
        # grade=0 (wrong answer) triggers the retaliation branch. The
        # question-supplied monster_atk below is intentionally wrong (999)
        # to prove Lane B's roster authority -- not this client value --
        # is what actually reaches the mitigation formula.
        return app_module._update_monster_and_quests(
            conn, 1, 9001, 0, {"monster_atk": 999}, 0, "2026-08-20",
        )


# ---------------------------------------------------------------------------
# Fix 1: armor mitigation of Lane B's authoritative retaliation
# ---------------------------------------------------------------------------

def test_mitigation_function_matches_required_examples():
    assert _mitigate_authoritative_retaliation(2, 0.08) == 1
    assert _mitigate_authoritative_retaliation(20, 0.08) == 18


def test_mitigation_function_no_armor_unchanged():
    assert _mitigate_authoritative_retaliation(2, 0.0) == 2
    assert _mitigate_authoritative_retaliation(20, 0.0) == 20


def test_mitigation_function_never_reaches_zero_from_positive_retaliation():
    for atk in range(2, 41):
        for reduce_pct in (0.01, 0.08, 0.5, 0.9, 0.99):
            assert _mitigate_authoritative_retaliation(atk, reduce_pct) >= 1


def test_armor_reduces_retaliation_at_low_authoritative_attack(tmp_path, monkeypatch):
    baseline = _run_wrong_answer(
        tmp_path / "baseline.sqlite", monkeypatch, monster_idx=_LOW_ATTACK_MONSTER_IDX
    )
    equipped = _run_wrong_answer(
        tmp_path / "equipped.sqlite", monkeypatch,
        monster_idx=_LOW_ATTACK_MONSTER_IDX, equipped_armor=True,
    )
    assert baseline["monster"]["player_dmg"] == _LOW_ATTACK_BASELINE
    assert equipped["monster"]["player_dmg"] == 1


def test_armor_reduces_retaliation_at_normal_authoritative_attack(tmp_path, monkeypatch):
    baseline = _run_wrong_answer(
        tmp_path / "baseline.sqlite", monkeypatch, monster_idx=_NORMAL_ATTACK_MONSTER_IDX
    )
    equipped = _run_wrong_answer(
        tmp_path / "equipped.sqlite", monkeypatch,
        monster_idx=_NORMAL_ATTACK_MONSTER_IDX, equipped_armor=True,
    )
    assert baseline["monster"]["player_dmg"] == _NORMAL_ATTACK_BASELINE
    assert equipped["monster"]["player_dmg"] == 18


def test_unequip_restores_authoritative_baseline(tmp_path, monkeypatch):
    equipped = _run_wrong_answer(
        tmp_path / "equipped.sqlite", monkeypatch,
        monster_idx=_LOW_ATTACK_MONSTER_IDX, equipped_armor=True,
    )
    unequipped = _run_wrong_answer(
        tmp_path / "unequipped.sqlite", monkeypatch,
        monster_idx=_LOW_ATTACK_MONSTER_IDX, equipped_armor=False,
    )
    assert equipped["monster"]["player_dmg"] == 1
    assert unequipped["monster"]["player_dmg"] == _LOW_ATTACK_BASELINE


def test_monster_attack_authority_ignores_client_supplied_value(tmp_path, monkeypatch):
    # _run_wrong_answer always passes a bogus monster_atk=999; both proof
    # tests above already show the roster value (2 or 20) wins, not 999.
    # This test names that guarantee explicitly.
    result = _run_wrong_answer(
        tmp_path / "authority.sqlite", monkeypatch, monster_idx=_LOW_ATTACK_MONSTER_IDX
    )
    assert result["monster"]["player_dmg"] != 999
    assert result["monster"]["player_dmg"] == _LOW_ATTACK_BASELINE


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


def test_combat_stats_and_level_up_rewards_survive_as_presentation_only():
    payload = _core_payload(
        combat_stats={"attack_bonus": 0.08, "damage_reduction": 0.08},
        level_up_rewards={"hp_gain": 12, "skill_unlocks": []},
    )
    serialized = serialize_legacy_review_result(payload)
    assert serialized["combat_stats"] == {"attack_bonus": 0.08, "damage_reduction": 0.08}
    assert serialized["level_up_rewards"] == {"hp_gain": 12, "skill_unlocks": []}
    assert set(serialized) == set(CORE_20_FIELDS) | {"combat_stats", "level_up_rewards"}


def test_full26_shape_with_only_combat_stats_still_classifies_correctly():
    payload = _full_payload(combat_stats={"attack_bonus": 0.0})
    outcome = adapt_legacy_review_result(payload)
    assert outcome.kind.value == "PUBLIC_FULL"
    assert "combat_stats" not in outcome.payload
    assert outcome.presentation_extensions == {"combat_stats": {"attack_bonus": 0.0}}


def test_unknown_extension_key_still_fails_closed():
    payload = _core_payload(this_is_not_an_approved_key="nope")
    with pytest.raises(ValueError):
        adapt_legacy_review_result(payload)


def test_unknown_extension_key_fails_closed_even_alongside_approved_ones():
    payload = _core_payload(
        combat_stats={"attack_bonus": 0.0},
        second_unapproved_key=123,
    )
    with pytest.raises(ValueError):
        adapt_legacy_review_result(payload)


def test_internal_duplicate_shape_still_requires_internal_flag():
    payload = {k: None for k in INTERNAL_DUPLICATE_4_FIELDS}
    with pytest.raises(ValueError):
        adapt_legacy_review_result(payload, internal=False)
    outcome = adapt_legacy_review_result(payload, internal=True)
    assert outcome.kind.value == "INTERNAL_DUPLICATE"


def test_no_extensions_present_leaves_legacy_shape_byte_identical():
    payload = _core_payload()
    serialized = serialize_legacy_review_result(payload)
    assert set(serialized) == set(CORE_20_FIELDS)
