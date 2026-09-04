"""Focused contract checks for the W2-03 equipment visual vertical slice.

These checks intentionally read the server definition source instead of
importing ``app``.  The visual slice is a projection consumer; it must not
create a second equipment authority or execute application startup as a test
side effect.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "js" / "w2_03_equipment_loadout_visual_slice.js"
STYLES = ROOT / "css" / "w2_03_equipment_loadout_visual_slice.css"
HERO = ROOT / "hero.html"

CANONICAL_EQUIPMENT_IDS = (
    "wooden_sword",
    "iron_sword",
    "fox_fang",
    "dragon_claw",
    "celestial_blade",
    "cloth_robe",
    "leather_armor",
    "fox_pelt",
    "dragon_scale",
    "void_mantle",
    "lucky_stone",
    "xp_amulet",
    "fox_mask",
    "dragon_eye",
    "go_stone_black",
)


def _canonical_equipment_ids() -> tuple[str, ...]:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "EQUIPMENT_DEFS" for target in node.targets)
    )
    definitions = ast.literal_eval(assignment.value)
    return tuple(str(definition["id"]) for definition in definitions)


def _git_show(path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"origin/master:{path}"],
        cwd=ROOT,
    )


def test_current_server_equipment_registry_has_exact_functional_count():
    ids = _canonical_equipment_ids()
    assert ids == CANONICAL_EQUIPMENT_IDS
    assert len(ids) == 15
    assert len(set(ids)) == 15
    assert "hat_scholar" not in ids


def test_surface_consumes_server_projection_and_canonical_mutation_boundary():
    source = MODULE.read_text(encoding="utf-8")

    assert "canonical_equippable === true" in source
    assert "canonicalSlot" in source
    assert "equipment_loadout_enabled === true" in source
    assert "'/api/player/inventory/equip'" in source
    assert "credentials: 'include'" in source
    assert "body: JSON.stringify({ inv_id: item.invId, action })" in source
    assert "await load(item.invId)" in source
    assert "Selection never auto-equips." in source
    assert "localStorage" not in source

    # A client-side functional ID list would be a second authority.  The
    # module must render whatever canonical rows the server projects.
    for equipment_id in CANONICAL_EQUIPMENT_IDS:
        assert equipment_id not in source


def test_paper_doll_is_composable_and_presentation_only():
    source = MODULE.read_text(encoding="utf-8")

    assert "PAPER_DOLL_LAYER_COUNT = PAPER_DOLL_LAYER_ORDER.length" in source
    assert source.count("'BACK_WEAPON'") == 1
    assert source.count("'BACK_BODY'") == 1
    assert source.count("'CHARACTER_BASE'") == 1
    assert source.count("'TORSO_ARMOR'") == 1
    assert source.count("'FRONT_BODY'") == 1
    assert source.count("'FRONT_ACCESSORY'") == 1
    assert source.count("'HEAD_FACE'") == 1
    assert source.count("'HAIR_FRONT_MASK'") == 1
    assert "GoOdysseyWearableRenderer" in source
    assert "renderSafe" in source
    assert "data-gameplay-authority=\"none\"" in source
    assert "hat_scholar" not in source


def test_loadout_visual_slice_has_responsive_and_reduced_motion_contract():
    styles = STYLES.read_text(encoding="utf-8")
    hero = HERO.read_text(encoding="utf-8")

    assert "@media (max-width: 1040px)" in styles
    assert "@media (max-width: 860px)" in styles
    assert "@media (max-width: 540px)" in styles
    assert "@media (max-width: 350px)" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert "w2_03_equipment_loadout_visual_slice.css" in hero
    assert "w2_03_equipment_loadout_visual_slice.js" in hero
    assert 'data-w2-03-equipment-slice' in hero


def test_protected_runtime_and_authority_files_are_unchanged():
    for path in (
        "app.py",
        "index.html",
        "i18n.js",
        "js/game/cinematic_replay.js",
        "sw.js",
        "inventory.html",
    ):
        assert (ROOT / path).read_bytes() == _git_show(path), path
