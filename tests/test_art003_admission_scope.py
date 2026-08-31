from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.art003_admission_scope import (
    ART003_B09_SCOPE_TIP,
    ART003_B10_SCOPE_TIP,
    ART003_B11_SCOPE_TIP,
    CANONICAL_MASTER_SNAPSHOT,
    admission_base,
    changed_paths,
    is_canonical_line,
)


ROOT = Path(__file__).resolve().parents[1]


B09_BASE = "c1a55daebc411df46ca4bbfef6c0b814c813ec73"
B10_BASE = "7d5c9c389561b877896f2b28e4b7db5f67fb97e8"
B11_BASE = "16548803a62c9fc76a459cb247a026187e644c5c"

B09_SCOPE = {
    "art/monsters/M089_steelfang_hyena.png",
    "art/monsters/M090_battlement_lizard.png",
    "art/monsters/M091_smokescreen_weasel.png",
    "art/monsters/M092_ironwheel_rhino.png",
    "art/monsters/M093_beacon_scorpion.png",
    "art/monsters/M094_shieldshell_crab.png",
    "art/monsters/M095_obsidian_automaton.png",
    "art/monsters/M096_wallbreak_bear.png",
    "art/monsters/M097_scout_hawkbeast.png",
    "art/monsters/M099_aurora_serpent.png",
    "docs/planning/art_003_batch_009_manifest.json",
    "docs/planning/art_003_batch_009_owner_visual_review_pack.md",
    "tests/test_art003_b02_owner_pass_freeze_publication.py",
    "tests/test_art003_b03_production.py",
    "tests/test_art003_b04_production.py",
    "tests/test_art003_b05_production.py",
    "tests/test_art003_b05_r1_publication.py",
    "tests/test_art003_b06_production.py",
    "tests/test_art003_b06_r1_publication.py",
    "tests/test_art003_b07_production.py",
    "tests/test_art003_b08_production.py",
    "tests/test_art003_b09_r1_publication.py",
}
B10_SCOPE = {
    *{
        f"art/monsters/{name}.png"
        for name in (
            "M100_thundercrown_stag",
            "M101_skyvault_whale",
            "M102_star_ring_ape",
            "M103_riftbow_eagle",
            "M104_moon_eclipse_mantis",
            "M105_skydrum_tortoise",
            "M106_starsand_wolf",
            "M107_monolith_beetle",
            "M108_thundercrystal_mantis",
            "M109_firmament_jelly",
        )
    },
    "docs/planning/art_003_batch_010_manifest.json",
    "docs/planning/art_003_batch_010_owner_visual_review_pack.md",
    "tests/test_art003_b10_production.py",
    "tests/test_art003_b10_publication.py",
}
B11_SCOPE = {
    *{
        f"art/monsters/{name}.png"
        for name in (
            "M110_dawnwing_serpent",
            "M111_starshard_rhino",
            "M113_timeworn_stone_turtle",
            "M114_endgate_beast",
            "M115_ancient_bell_crawler",
            "M116_ivorylight_beetle",
            "M117_blacksand_hound",
            "M118_relic_shellbeast",
            "M119_silent_tabletling",
            "M120_evergreen_rootbeast",
        )
    },
    "docs/planning/art_003_batch_011_manifest.json",
    "docs/planning/art_003_batch_011_owner_visual_review_pack.md",
    "tests/test_art003_b11_production.py",
    "tests/test_art003_b11_r1_publication.py",
}


def test_canonical_admissions_use_nonempty_commit_windows():
    assert changed_paths(
        canonical_tip=ART003_B09_SCOPE_TIP,
        candidate_base=B09_BASE,
        head_ref="origin/master",
        include_worktree=False,
    ) == B09_SCOPE
    assert changed_paths(
        canonical_tip=ART003_B10_SCOPE_TIP,
        candidate_base=B10_BASE,
        head_ref="origin/master",
        include_worktree=False,
    ) == B10_SCOPE
    assert changed_paths(
        canonical_tip=ART003_B11_SCOPE_TIP,
        candidate_base=B11_BASE,
        head_ref="origin/master",
        include_worktree=False,
    ) == B11_SCOPE


def test_candidate_line_uses_candidate_base_and_preserves_exact_scope():
    assert not is_canonical_line(
        canonical_tip=ART003_B10_SCOPE_TIP,
        canonical_master=ART003_B11_SCOPE_TIP,
        head_ref="codex/art003-b10-r1-owner-pass-canonical-publication",
    )
    assert admission_base(
        canonical_tip=ART003_B10_SCOPE_TIP,
        candidate_base=B10_BASE,
        canonical_master=ART003_B11_SCOPE_TIP,
        head_ref="codex/art003-b10-r1-owner-pass-canonical-publication",
    ) == B10_BASE
    assert changed_paths(
        canonical_tip=ART003_B10_SCOPE_TIP,
        candidate_base=B10_BASE,
        canonical_master=ART003_B11_SCOPE_TIP,
        head_ref="codex/art003-b10-r1-owner-pass-canonical-publication",
        include_worktree=False,
    ) == B10_SCOPE


def test_canonical_master_equal_head_uses_historical_parent():
    assert is_canonical_line(
        canonical_tip=ART003_B11_SCOPE_TIP,
        canonical_master=ART003_B11_SCOPE_TIP,
        head_ref=ART003_B11_SCOPE_TIP,
    )
    assert admission_base(
        canonical_tip=ART003_B11_SCOPE_TIP,
        candidate_base=B11_BASE,
        canonical_master=ART003_B11_SCOPE_TIP,
        head_ref=ART003_B11_SCOPE_TIP,
    ) == ART003_B10_SCOPE_TIP


def test_fresh_reanchored_candidate_uses_current_master_line():
    # The repair branch is a direct child of the fetched master snapshot.  Its
    # candidate base is intentionally not used for the historical ART003
    # contract; the canonical window remains the recorded B11 admission.
    assert is_canonical_line(
        canonical_tip=ART003_B11_SCOPE_TIP,
        canonical_master="HEAD^1",
        head_ref="HEAD",
    )
    assert admission_base(
        canonical_tip=ART003_B11_SCOPE_TIP,
        candidate_base="HEAD^1",
        canonical_master="HEAD^1",
        head_ref="HEAD",
    ) == ART003_B10_SCOPE_TIP
    assert CANONICAL_MASTER_SNAPSHOT


def test_equal_candidate_base_is_rejected_instead_of_passing_empty_diff():
    with pytest.raises(AssertionError, match="equals HEAD"):
        admission_base(
            canonical_tip=ART003_B10_SCOPE_TIP,
            candidate_base="HEAD",
            canonical_master=B10_BASE,
        )


def test_negative_control_missing_expected_path_is_rejected():
    missing = B10_SCOPE - {"tests/test_art003_b10_publication.py"}
    with pytest.raises(AssertionError):
        assert missing == B10_SCOPE


def test_negative_control_unexpected_path_is_rejected():
    extra = B10_SCOPE | {"tests/unexpected_art003_scope.py"}
    with pytest.raises(AssertionError):
        assert extra == B10_SCOPE


def test_negative_control_asset_hash_change_is_rejected():
    asset = ROOT / "art/monsters/M100_thundercrown_stag.png"
    expected = hashlib.sha256(asset.read_bytes()).hexdigest().upper()
    wrong = ("0" if expected[0] != "0" else "1") + expected[1:]
    with pytest.raises(AssertionError):
        assert wrong == expected
