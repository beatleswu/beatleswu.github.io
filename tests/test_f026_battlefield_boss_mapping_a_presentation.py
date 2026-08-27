"""F026 Mapping A presentation coverage and canonical asset binding tests."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "js" / "game" / "battlefield_boss_reward_presentation_v1.js"
DISPLAY = ROOT / "js" / "game" / "battlefield_boss_cosmetic_display_v1.js"
STYLE = ROOT / "css" / "e10" / "battlefield_boss_reward_presentation_v1.css"
INDEX = ROOT / "index.html"
FIXTURE = ROOT / "tests" / "e2e" / "fixtures" / "f026_battlefield_boss_mapping_a_presentation.html"


MAPPING_IDS = [
    "back_pack",
    "hat_cloth",
    "hat_bamboo",
    "robe_crane",
    "hat_onihorns",
    "robe_dragon",
    "acc_dragon_pendant",
    "back_cloak",
    "hat_dragon_horn",
    "hat_celestial_crown",
]


def _assignment_value(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if targets and any(isinstance(target, ast.Name) and target.id == name for target in targets):
            value = node.value
            if isinstance(value, ast.Call) and len(value.args) == 1:
                value = value.args[0]
            return ast.literal_eval(value)
    raise AssertionError(f"assignment not found: {name}")


def _canonical_definitions():
    rows = _assignment_value(ROOT / "app.py", "APPEARANCE_DEFS")
    return {row["id"]: row for row in rows}


def test_mapping_a_is_consumed_from_typed_id_without_ui_zone_mapping():
    script = SCRIPT.read_text(encoding="utf-8")
    display = DISPLAY.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    assert "mapped_cosmetic_id" in script
    assert "battlefield_boss_cosmetic_display_v1.js" in index
    assert "BattlefieldBossCosmeticDisplayV1" in script
    assert "MAPPING_A" not in script
    assert "zone_01" not in script
    assert "zone_10" not in script
    assert "APPEARANCE_DEFS.id + PURE_COSMETIC_PRESENTATION_REGISTRY" in display
    assert "fetch(" not in script.lower()
    assert "player_wardrobe" not in script.lower()
    assert "commit(" not in script.lower()
    assert "rollback(" not in script.lower()


def test_all_mapping_a_ids_have_canonical_metadata_and_assets():
    display = DISPLAY.read_text(encoding="utf-8")
    definitions = _canonical_definitions()
    mapping = _assignment_value(
        ROOT / "world_battlefield_boss_first_clear_entitlement.py", "MAPPING_A"
    )
    assert [mapping[f"zone_{index:02d}"] for index in range(1, 11)] == MAPPING_IDS
    assert set(MAPPING_IDS).issubset(definitions)
    for item_id in MAPPING_IDS:
        row = definitions[item_id]
        assert row.get("premium_only") is not True
        assert row["slot"] in {"outfit", "hat", "back", "accessory"}
        assert f"canonical_cosmetic_id: '{item_id}'" in display
        assert f"display_name: '{row['name']}'" in display
        assert f"display_category: '{row['slot']}'" in display
        svg = ROOT / "assets" / "hero" / "items" / f"{item_id}.svg"
        webp = ROOT / "assets" / "hero" / "items" / "fullbody" / f"{item_id}.webp"
        if webp.is_file():
            expected_asset = f"/assets/hero/items/fullbody/{item_id}.webp"
        else:
            expected_asset = f"/assets/hero/items/{item_id}.svg"
        assert Path(ROOT / expected_asset.lstrip("/")).is_file()
        assert expected_asset in display


def test_display_projection_contains_no_reward_or_power_authority():
    script = DISPLAY.read_text(encoding="utf-8").lower()
    for forbidden in (
        "mapping_a",
        "first_clear_entitlement",
        "player_wardrobe",
        "coins",
        "price",
        "rarity",
        "combat_power",
        "commit(",
        "rollback(",
    ):
        assert forbidden not in script


def test_f026_fixture_covers_exact_ten_ids_and_fail_closed_states():
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert len(re.findall(r"\['zone-\d{2}',", fixture)) == 10
    assert fixture.count("FIRST_CLEAR_NEW_COSMETIC") == 1
    assert fixture.count("FIRST_CLEAR_ALREADY_OWNED_NO_OP") == 1
    assert fixture.count("NOT_FIRST_CLEAR") == 1
    for item_id in MAPPING_IDS:
        assert item_id in fixture
    assert "synthetic server-authored F024 transport payloads" in fixture
    assert "F022; this fixture checks presentation coverage only" in fixture
