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
    CANONICAL_WORLD_NPC_REGISTRY_COUNT,
    WORLD_NPC_IDENTITY_REGISTRY_RELATIVE_PATH,
    WORLD_NPC_REGISTRY_VERSION,
    world_npc_registry_payload,
)


REGISTRY_PATH = ROOT / "docs/planning/rpg_wave2_lane_a_character_identity_registry_v1.json"
SPEC_PATH = ROOT / "docs/planning/GO_ODYSSEY_WORLD_NPC_CANONICAL_SPEC.md"
APP_PATH = ROOT / "app.py"
IMAGE_PACK_MANIFEST_PATH = ROOT / "deploy/canonical-image-pack-manifest.json"

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


def test_single_canonical_registry_authority_and_no_competing_npc_registries():
    candidates = []
    for path in (ROOT / "docs" / "planning").glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if "world_npc_presentation_registry" in payload or "world_npcs" in payload:
            candidates.append(path)

    assert candidates == [REGISTRY_PATH]
    authority = _registry()["world_npc_presentation_registry"]["authority_model"]
    assert CANONICAL_WORLD_NPC_REGISTRY_COUNT == 1
    assert authority["canonical_registry_count"] == 1
    assert authority["canonical_registry_file"] == WORLD_NPC_IDENTITY_REGISTRY_RELATIVE_PATH
    assert authority["is_existing_shared_registry"] is True
    assert authority["is_world_npc_canonical_authority"] is True
    assert authority["filename_is_historical"] is True
    assert authority["competing_npc_registries"] == []
    assert authority["projection_loaders_are_not_registries"] is True


def test_runtime_surface_table_is_complete_and_unambiguous():
    surfaces = _registry()["world_npc_presentation_registry"]["runtime_surfaces"]
    assert len(surfaces) == 8
    assert {surface["surface_id"] for surface in surfaces} == {
        "canonical_registry_api",
        "static_asset_serving",
        "story_cinematic",
        "zone_details",
        "npc_cards",
        "dialogue_surfaces",
        "world_map_zone_ui",
        "journal_lore",
    }
    statuses = {status: sum(surface["status"] == status for surface in surfaces) for status in {
        "INTEGRATED",
        "MISSING_REQUIRED",
        "LEGACY_NONBLOCKING",
        "NOT_REQUIRED",
        "DEFERRED",
    }}
    assert statuses == {
        "INTEGRATED": 2,
        "MISSING_REQUIRED": 0,
        "LEGACY_NONBLOCKING": 2,
        "NOT_REQUIRED": 2,
        "DEFERRED": 2,
    }
    assert all(surface["status"] != "MISSING_REQUIRED" for surface in surfaces)
    for surface in surfaces:
        assert surface["current_consumer"]
        assert surface["evidence"]
        assert surface["responsive_validation"]

    static_surface = next(item for item in surfaces if item["surface_id"] == "static_asset_serving")
    assert static_surface["wave2_required"] is True
    assert "desktop" in static_surface["responsive_validation"]
    assert "iPad landscape" in static_surface["responsive_validation"]
    assert "iPad portrait" in static_surface["responsive_validation"]
    assert "mobile" in static_surface["responsive_validation"]


def test_legacy_reference_table_is_explained_and_nonblocking():
    references = _registry()["world_npc_presentation_registry"]["legacy_references"]
    assert len(references) == 2
    assert {reference["classification"] for reference in references} == {"LEGACY_NONBLOCKING"}
    assert {reference["live_or_dead"] for reference in references} == {"LIVE"}
    assert all(reference["safe_to_remove"] is False for reference in references)
    assert all(reference["file"] and reference["reference"] and reference["resolution"] for reference in references)
    for reference in references:
        for file_name in reference["file"].split("; "):
            assert (ROOT / file_name).is_file(), file_name
    assert "Runner/messenger" in (ROOT / "docs/planning/e10_final_screenplay_v1.md").read_text(encoding="utf-8")
    voice_bible = (ROOT / "docs/planning/e10_voice_cast_bible_v1.md").read_text(encoding="utf-8")
    dialogue_assets = (ROOT / "assets/e10/audio/zone2/zone2-dialogue-assets.json").read_text(encoding="utf-8")
    assert "e10.messenger" in voice_bible
    assert "e10.zone2.herder" in voice_bible
    assert '"speaker": "herder"' in dialogue_assets


def test_world_npc_api_projects_canonical_registry_read_only_and_serves_exact_assets():
    import app

    client = app.app.test_client()
    response = client.get("/api/world-npcs")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["canonical_count"] == 7
    assert tuple(payload["canonical_ids"]) == CANONICAL_WORLD_NPC_IDS
    assert payload["registry_authority"]["canonical_registry_count"] == 1
    assert payload["mutation_boundary"]["database_mutation"] == 0
    assert payload["mutation_boundary"]["ownership_mutation"] == 0

    for record in payload["world_npcs"]:
        asset_response = client.get("/" + record["runtime_asset"])
        assert asset_response.status_code == 200, record["canonical_id"]
        assert asset_response.mimetype == "image/webp"
        assert asset_response.data == (ROOT / record["runtime_asset"]).read_bytes()


def test_packaging_closure_is_exact_and_superseded_eastern_guardian_shield_is_not_canonical():
    registry = _registry()["world_npc_presentation_registry"]
    records = _records()
    manifest = json.loads(IMAGE_PACK_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_by_path = {entry["path"]: entry for entry in manifest["files"]}
    runtime_paths = {record["runtime_asset"] for record in records}
    master_paths = {record["art_master"] for record in records}
    mobile_paths = {record["mobile_asset"] for record in records}

    assert len(master_paths) == len(runtime_paths) == len(mobile_paths) == 7
    assert runtime_paths <= set(manifest_by_path)
    assert mobile_paths == runtime_paths
    assert not (master_paths & set(manifest_by_path)), "PNG masters are source-only, not release payload"
    assert all("shield" not in path.lower() for path in runtime_paths | master_paths | mobile_paths)
    assert not any(
        "eastern" in path.lower() and "shield" in path.lower()
        for path in manifest_by_path
    )
    assert registry["packaging"]["superseded_eastern_guardian_shield_asset_canonical"] is False
    assert registry["packaging"]["master_png_release_policy"] == "SOURCE_ONLY_NOT_DEPLOYED"
    assert registry["packaging"]["release_inventory_delta_from_previous_freeze"] == {
        "files_added": 7,
        "bytes_added": 5236664,
        "owner_approved_project_created_entries_added": 7,
    }
    # The canonical image pack now includes the separately closed Wave2
    # runtime assets.  The World NPC delta above remains scoped to this
    # registry; these totals assert the current combined release inventory.
    # The current combined image pack also contains the nine A021A/D038
    # runtime Spirit presentation assets. Their release registration is
    # intentionally separate from this World NPC delta.
    assert manifest["total_files"] == 1448
    assert manifest["total_bytes"] == 789091914
    for path in runtime_paths:
        entry = manifest_by_path[path]
        raw = (ROOT / path).read_bytes()
        assert entry["size"] == len(raw)
        assert entry["sha256"] == hashlib.sha256(raw).hexdigest()


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
        "INTEGRATED", "MISSING_REQUIRED", "LEGACY_NONBLOCKING", "NOT_REQUIRED", "DEFERRED"
    }}
    assert counts == {
        "INTEGRATED": 2,
        "MISSING_REQUIRED": 0,
        "LEGACY_NONBLOCKING": 2,
        "NOT_REQUIRED": 2,
        "DEFERRED": 2,
    }
    assert "UNCLASSIFIED_MISSING_SURFACE_COUNT=0" in spec
    assert "UNEXPLAINED_LEGACY_REFERENCE_COUNT=0" in spec
