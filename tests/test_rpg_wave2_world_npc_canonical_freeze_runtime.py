"""Deterministic checks for the frozen seven-NPC presentation registry."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rpg_world_npc_registry import (
    CANONICAL_WORLD_NPC_IDS,
    WORLD_NPC_REGISTRY_VERSION,
    world_npc_registry_payload,
)


REGISTRY_PATH = ROOT / "docs/planning/rpg_wave2_lane_a_character_identity_registry_v1.json"
SPEC_PATH = ROOT / "docs/planning/GO_ODYSSEY_WORLD_NPC_CANONICAL_SPEC.md"
APP_PATH = ROOT / "app.py"

EXPECTED_MASTER_SHA256 = {
    "world.village_elder": "b68ce8dfe2088fef035a168d5f1caa528483659918ffcc271e72656e55528b9c",
    "world.messenger": "c602d7a7de3524c9cbfb05f1115c175e42e27fded5ac80e243fb990a7e8d8abe",
    "world.smith_elder": "a45551157f22ed7f2e071996523e4de37fc3f28d4bdbbebbced7fc053f8ade6d",
    "world.archmage": "b18d2b62a9d438be799b3be86713414831bf5f614c30bb33a57f56ae462e5986",
    "world.serel": "982903c73173af02504a74ecfc601cab247a7e595962534126cb6fb676edf6b3",
    "world.herder": "af6423b795fe7fcec8890169c1f18361c5d6cdd4c604f36092fc6d091b4b7ef6",
    "world.eastern_guardian": "ea176533d183bae32bd5d0b936587d3cef7858d3284f6a88ed630f70534b2790",
}


def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _records() -> list[dict]:
    return _registry()["world_npcs"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_canonical_npc_count_and_unique_ids():
    registry = _registry()
    presentation = registry["world_npc_presentation_registry"]
    records = _records()
    assert presentation["registry_version"] == WORLD_NPC_REGISTRY_VERSION
    assert presentation["canonical_count"] == 7
    assert tuple(presentation["canonical_ids"]) == CANONICAL_WORLD_NPC_IDS
    assert tuple(record["canonical_id"] for record in records) == CANONICAL_WORLD_NPC_IDS
    assert len({record["canonical_id"] for record in records}) == 7


def test_zone_mapping_and_required_presentation_fields_are_canonical():
    expected_zones = {
        "world.village_elder": (1, "Zone 1 Newbie Village"),
        "world.messenger": (1, "Zone 1 Newbie Village / Shot 10 transition"),
        "world.smith_elder": (5, "Zone 5 Orc Tribe"),
        "world.archmage": (7, "Zone 7 Sage Tower"),
        "world.serel": (8, "Zone 8 Demon Castle Front"),
        "world.herder": (2, "Zone 2 Slime Plains"),
        "world.eastern_guardian": (10, "Zone 10 Ancient Doom Temple"),
    }
    required = {
        "canonical_id",
        "display_name",
        "zone_id",
        "zone",
        "role",
        "asset_key",
        "art_master",
        "runtime_asset",
        "mobile_asset",
        "story_references",
        "player_selectable",
        "combat_authority",
        "equipment_authority",
    }
    for record in _records():
        assert required <= set(record), record["canonical_id"]
        assert (record["zone_id"], record["zone"]) == expected_zones[record["canonical_id"]]
        assert record["player_selectable"] is False
        assert record["combat_authority"] == "none"
        assert record["equipment_authority"] == "none"


def test_approved_master_and_runtime_asset_closure_is_exactly_seven():
    records = _records()
    masters = [ROOT / record["art_master"] for record in records]
    runtimes = [ROOT / record["runtime_asset"] for record in records]
    mobiles = [ROOT / record["mobile_asset"] for record in records]

    assert len(masters) == len(runtimes) == len(mobiles) == 7
    assert len({path.as_posix() for path in masters}) == 7
    assert len({path.as_posix() for path in runtimes}) == 7
    assert len({path.as_posix() for path in mobiles}) == 7
    assert all(path.is_file() for path in masters + runtimes + mobiles)
    assert all(record["mobile_asset"] == record["runtime_asset"] for record in records)

    master_hashes = {}
    for record, master, runtime in zip(records, masters, runtimes):
        assert _sha256(master) == EXPECTED_MASTER_SHA256[record["canonical_id"]]
        assert _sha256(master) not in master_hashes.values(), record["canonical_id"]
        master_hashes[record["canonical_id"]] = _sha256(master)

        with Image.open(master) as image:
            rgba = image.convert("RGBA")
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert rgba.size == (1056, 1408)
            assert rgba.getchannel("A").getextrema() == (0, 255)
            assert rgba.getbbox() is not None
            for red, green, blue, alpha in rgba.get_flattened_data():
                if alpha == 0:
                    assert (red, green, blue) == (0, 0, 0)

        with Image.open(runtime) as image:
            rgba = image.convert("RGBA")
            assert image.format == "WEBP"
            assert image.mode == "RGBA"
            assert rgba.size == (1056, 1408)
            assert rgba.getchannel("A").getextrema() == (0, 255)
            assert rgba.getbbox() is not None


def test_story_reference_integrity_has_no_broken_sources():
    broken = []
    for record in _records():
        for reference in record["story_references"]:
            source = ROOT / reference["source"]
            if not source.is_file():
                broken.append(f"{record['canonical_id']}:missing:{reference['source']}")
                continue
            if reference["required_text"] not in source.read_text(encoding="utf-8"):
                broken.append(
                    f"{record['canonical_id']}:missing-text:{reference['required_text']}"
                )
    assert not broken


def test_registry_loader_fails_closed_shape_and_exposes_zero_mutation_projection():
    payload = world_npc_registry_payload()
    assert payload["canonical_count"] == 7
    assert tuple(payload["canonical_ids"]) == CANONICAL_WORLD_NPC_IDS
    assert len(payload["world_npcs"]) == 7
    assert payload["mutation_boundary"] == {
        "ownership_mutation": 0,
        "player_inventory_mutation": 0,
        "combat_mutation": 0,
        "database_mutation": 0,
    }
    assert not any(
        record["player_selectable"]
        or record["combat_authority"] != "none"
        or record["equipment_authority"] != "none"
        for record in payload["world_npcs"]
    )


def test_runtime_api_is_single_read_only_presentation_route():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    route_functions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "route"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and decorator.args[0].value == "/api/world-npcs"
            ):
                route_functions.append(node)
    assert len(route_functions) == 1
    route_source = ast.get_source_segment(source, route_functions[0])
    assert route_source is not None
    assert "world_npc_registry_payload()" in route_source
    assert "get_db(" not in route_source
    assert ".commit(" not in route_source
    assert "INSERT" not in route_source.upper()
    assert "UPDATE" not in route_source.upper()
    assert "DELETE" not in route_source.upper()


def test_spec_and_surface_audit_are_present_and_consistent():
    spec = SPEC_PATH.read_text(encoding="utf-8")
    assert "Exactly seven PNG masters and seven WebP runtime assets" in spec
    assert "PLAYER_SELECTABLE=NO" in spec
    assert "GET /api/world-npcs" in spec
    assert "Zone 5 Orc Tribe" in spec
    assert "Zone 7 Sage Tower" in spec
    assert "Zone 10 Ancient Doom Temple" in spec
    statuses = _registry()["world_npc_presentation_registry"]["runtime_surfaces"]
    counts = {status: sum(item["status"] == status for item in statuses) for status in {
        "INTEGRATED", "MISSING", "LEGACY", "NOT_REQUIRED"
    }}
    assert counts == {"INTEGRATED": 2, "MISSING": 2, "LEGACY": 2, "NOT_REQUIRED": 2}
