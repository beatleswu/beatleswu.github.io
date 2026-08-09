"""E10-Z1-AUDIO-PRODUCTION-001 -- casting lock/pending state invariants.

Owner instruction: "Do NOT silently replace an Owner-approved voice later."
These checks keep casting_candidates.json and audition_set_b_recast_briefs.json
structurally consistent with that rule -- a locked slot must always carry a
real voice_id and never be a target of the recast briefs, and every recast
brief's exclude list must cover every voice_id already decided (locked or
explicitly rejected) so Set B can never re-offer or double-cast one.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = REPO_ROOT / "tools" / "e10_zone1_audio"
CASTING_PATH = TOOL_DIR / "casting_candidates.json"
BRIEFS_PATH = TOOL_DIR / "audition_set_b_recast_briefs.json"


def _load_casting():
    return json.loads(CASTING_PATH.read_text(encoding="utf-8"))


def _load_briefs():
    return json.loads(BRIEFS_PATH.read_text(encoding="utf-8"))


def test_locked_roles_list_matches_locked_slots():
    casting = _load_casting()
    declared_locked = {(r["role"], r["locale"]) for r in casting["locked_roles"]}
    declared_pending = {(r["role"], r["locale"]) for r in casting["pending_roles"]}
    assert declared_locked.isdisjoint(declared_pending)

    actual_locked = set()
    actual_pending = set()
    for role_key, role in casting["roles"].items():
        for locale, slot in role["voices"].items():
            if slot.get("locked"):
                actual_locked.add((role_key, locale))
            else:
                actual_pending.add((role_key, locale))

    assert declared_locked == actual_locked, (
        f"locked_roles list does not match slots actually marked locked=true: "
        f"declared={declared_locked} actual={actual_locked}"
    )
    assert declared_pending == actual_pending


def test_locked_slots_have_a_real_voice_id():
    casting = _load_casting()
    for role_key, role in casting["roles"].items():
        for locale, slot in role["voices"].items():
            if slot.get("locked"):
                assert slot.get("voice_id"), f"{role_key}/{locale} is locked but has no voice_id"


def test_pending_slots_have_no_voice_id_and_a_recast_candidates_field():
    casting = _load_casting()
    for role_key, role in casting["roles"].items():
        for locale, slot in role["voices"].items():
            if not slot.get("locked"):
                assert slot.get("voice_id") is None, (
                    f"{role_key}/{locale} is pending but has a voice_id set -- "
                    "a pending role must not appear to be decided"
                )
                assert "recast_candidates" in slot, (
                    f"{role_key}/{locale} is pending but missing recast_candidates "
                    "(the field --audition-set-b writes discovered options into)"
                )


def test_recast_briefs_never_target_a_locked_slot():
    casting = _load_casting()
    briefs = _load_briefs()
    for role_key, brief in briefs["roles"].items():
        role_config_key = brief["role_config_key"]
        locale = brief["locale"]
        slot = casting["roles"][role_config_key]["voices"][locale]
        assert not slot.get("locked"), (
            f"recast brief {role_key!r} targets {role_config_key}/{locale}, which is "
            "locked in casting_candidates.json -- Set B must never target an approved role"
        )


def test_recast_briefs_cover_exactly_the_pending_roles():
    casting = _load_casting()
    briefs = _load_briefs()
    pending = {(r["role"], r["locale"]) for r in casting["pending_roles"]}
    brief_targets = {
        (brief["role_config_key"], brief["locale"]) for brief in briefs["roles"].values()
    }
    assert brief_targets == pending, (
        f"audition_set_b_recast_briefs.json targets {brief_targets} but "
        f"casting_candidates.json pending_roles is {pending} -- they must match exactly"
    )


def test_exclude_list_covers_every_locked_and_rejected_voice_id():
    casting = _load_casting()
    briefs = _load_briefs()
    exclude_ids = set(briefs["exclude_voice_ids"])

    decided_ids = set()
    for role in casting["roles"].values():
        for slot in role["voices"].values():
            if slot.get("locked") and slot.get("voice_id"):
                decided_ids.add(slot["voice_id"])
            for candidate in slot.get("candidates", []):
                outcome = candidate.get("outcome", "")
                if outcome == "APPROVED" or outcome.startswith("REJECTED"):
                    decided_ids.add(candidate["voice_id"])

    missing = decided_ids - exclude_ids
    assert not missing, (
        f"audition_set_b_recast_briefs.json exclude_voice_ids is missing already-decided "
        f"voice_id(s) {missing} -- Set B could re-offer or double-cast an already-decided voice"
    )


def test_recast_briefs_declare_male_gender_filter_for_hero_roles():
    # Canon: the Hero is male. Any active hero recast brief must filter for
    # it so the Voice Library search can't resurface female candidates
    # again. Set B is currently COMPLETE (all 3 original targets locked,
    # "roles" is intentionally empty) -- this only exercises entries that
    # actually exist, so it stays meaningful if a hero role is ever
    # unlocked and a fresh recast brief added later.
    briefs = _load_briefs()
    hero_briefs = {
        key: brief for key, brief in briefs["roles"].items()
        if brief.get("role_config_key") == "hero"
    }
    for key, brief in hero_briefs.items():
        assert brief["search"].get("gender") == "male", f"{key} search filter must require gender=male"
        assert brief.get("fallback_search", {}).get("gender") == "male", (
            f"{key} fallback_search filter must also require gender=male"
        )
