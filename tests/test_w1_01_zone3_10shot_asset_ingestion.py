"""Bounded contract tests for the Owner-approved Zone 3 ten-shot package."""

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "assets/e10/art/zone3/cinematic"
MANIFEST_PATH = PACKAGE_ROOT / "zone3-cinematic-asset-package.json"
OWNER_PACKAGE_SHA256 = (
    "b3aa7e3e4d0d06c294d8f30eb3a05f5e9c5375721bbf4a4e16ccd6a1134ed1b8"
)

SHOT_IDS = [f"SHOT{i:02d}" for i in range(1, 11)]
SOURCE_NAMES = [
    "zone3_shot01_moving_refugees_owner_approved.jpeg",
    "zone3_shot02_household_belongings_owner_approved.jpeg",
    "zone3_shot03_meet_grik_owner_approved.jpeg",
    "zone3_shot04_shrinking_living_space_owner_approved.jpeg",
    "zone3_shot05_blocked_water_route_owner_approved.jpeg",
    "zone3_shot06_last_door_centurion_owner_approved.jpeg",
    "zone3_shot07_lord_trial_challenge_owner_approved.png",
    "zone3_shot08_fragile_truce_owner_approved.png",
    "zone3_shot09_stone_shard_handoff_owner_approved.jpeg",
    "zone3_shot10_mist_forest_hook_owner_approved.jpeg",
]
SOURCE_RECORDS = [
    (545655, "381d94c09d1d37d921c461e3f6c80b9a37ba92ed0d63581e9015ac53440e470f", (1536, 864)),
    (663920, "f2af78399c1603ba1df453f5efb9df22f344999d9fe6721ebeb418527155bbc0", (1536, 1024)),
    (621107, "e7c08c827f213b3adc9db24ce419282d747cbfd7ee2ca08fbf2c4cfd32dad1a2", (1536, 1024)),
    (591629, "bd4f1b818e49aa976a20cd82c5d48fef77c569c70ba23e4407942b50adb85a67", (1536, 1024)),
    (711516, "f7261e5f42545327bb5960aec2d38f049ffba0cb94c11d405e2f2ac81d2d4f4f", (1536, 864)),
    (619999, "9309ba5bd565007a30666a018c904321df43d64baeeee3ac0286016dd4a8ab15", (1536, 1024)),
    (2545852, "e861ef571c3b46ba7e8b93839da472a390ee8a9a25784cf860564a1c1627950f", (1672, 941)),
    (2527541, "ffecac99714b6f936df6e95aaccd4287f64bda73eeedf224bdcb7e93641edab2", (1536, 1024)),
    (557654, "573e29b1176182705847dfbf89dc1cceff686567187a6514f6e8fe213b861344", (1536, 1024)),
    (569654, "06b276012e83971631a8ac352ba07325938bb06f61be3a49f6050314084e6646", (1536, 1024)),
]
RUNTIME_SHA256 = [
    "f689f568dc501452b6c00212d5cec50d341ef2ba5b6059ddb23ebaeebe8eeb8c",
    "66dd93e017fa3f20e1e24f7deb1c7375da969384062d4987a7cad83f2d67cda6",
    "904d21f0f753eff5f3858d2f1a8c735c18ad35f96be61825977de1ad63180cc1",
    "0dc20e776ec12dfe79aed8a988dbe3c7597982354885175a098871e9fda7e431",
    "ae506cfa36b766ff94fe0e3cdf690e9da9d9d1231b1eeecaf0db46f90c1d20e9",
    "7722c6fe21d066ae6063072ba9e4c7c8e1df91f079711169d904506cc62af065",
    "c1bee63b305635ec4e65b52dc18424b92dddb3c895c38d3582275fccf4f2f780",
    "7209bca8197b18dd498936caeb7d774051fa2733ddce3d7ec45a6cefd43ff238",
    "b6d7456a485499f1ef25a32d23ca48ea70402aecb09912157f5d2994d09e739c",
    "159b843ac507b814dcec91eb020d9dd45d4513de4aa0100d693d4d981f8da7e4",
]


def _load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_owner_package_and_exact_ten_shot_contract():
    manifest = _load_manifest()
    assert manifest["owner_package"]["sha256"] == OWNER_PACKAGE_SHA256
    assert manifest["owner_package"]["sha256_match"] is True
    assert manifest["canonical_zone"] == {
        "zone_id": 3,
        "name_zh": "哥布林洞穴",
        "name_en": "Goblin Cave",
        "identity_authority": "current canonical runtime/API identity",
    }
    assert manifest["source_shot_count"] == 10
    assert manifest["runtime_derivative_count"] == 10
    assert manifest["rejected_asset_paths"] == []
    assert [shot["SHOT_ID"] for shot in manifest["shots"]] == SHOT_IDS
    assert [shot["SOURCE_MASTER"]["filename"] for shot in manifest["shots"]] == SOURCE_NAMES
    assert len({shot["SHOT_ID"] for shot in manifest["shots"]}) == 10
    assert all(shot["OWNER_APPROVED"] == "YES" for shot in manifest["shots"])


def test_lifecycle_mapping_is_exact_and_not_inferred_from_file_order():
    manifest = _load_manifest()
    assert manifest["lifecycle"] == {
        "FIRST_ENTRY": SHOT_IDS[:5],
        "BOSS_READY": SHOT_IDS[5:7],
        "POST_CLEAR": SHOT_IDS[7:],
    }
    assert [shot["PHASE"] for shot in manifest["shots"]] == [
        "FIRST_ENTRY",
        "FIRST_ENTRY",
        "FIRST_ENTRY",
        "FIRST_ENTRY",
        "FIRST_ENTRY",
        "BOSS_READY",
        "BOSS_READY",
        "POST_CLEAR",
        "POST_CLEAR",
        "POST_CLEAR",
    ]


def test_source_masters_and_runtime_derivatives_resolve_to_recorded_hashes():
    manifest = _load_manifest()
    source_files = sorted((PACKAGE_ROOT / "source").iterdir())
    runtime_files = sorted(PACKAGE_ROOT.glob("zone3_shot*.webp"))
    assert [path.name for path in source_files] == sorted(SOURCE_NAMES)
    assert [path.name for path in runtime_files] == [
        f"zone3_shot{i:02d}.webp" for i in range(1, 11)
    ]

    for index, shot in enumerate(manifest["shots"]):
        source = ROOT / shot["SOURCE_PATH"]
        runtime = ROOT / shot["RUNTIME_PATH"]
        expected_bytes, expected_source_sha, expected_dimensions = SOURCE_RECORDS[index]
        assert source.is_file()
        assert runtime.is_file()
        assert source.stat().st_size == expected_bytes
        assert _sha256(source) == expected_source_sha
        assert shot["SOURCE_SHA256"] == expected_source_sha
        assert shot["SOURCE_MASTER"]["bytes"] == expected_bytes
        assert tuple(shot["SOURCE_MASTER"]["dimensions"].split("x")) == tuple(
            str(value) for value in expected_dimensions
        )
        assert _sha256(runtime) == RUNTIME_SHA256[index]
        assert shot["RUNTIME_SHA256"] == RUNTIME_SHA256[index]
        assert shot["SOURCE_MASTER"]["asset_class"] == "SOURCE_MASTER"
        assert shot["RUNTIME_DERIVATIVE"]["asset_class"] == "RUNTIME_DERIVATIVE"


def test_runtime_webp_decodes_and_uses_common_16_9_delivery_dimensions():
    manifest = _load_manifest()
    assert manifest["runtime_delivery"]["runtime_format"] == "image/webp"
    assert manifest["runtime_delivery"]["runtime_dimensions"] == "1536x864"
    for shot in manifest["shots"]:
        runtime = ROOT / shot["RUNTIME_PATH"]
        with Image.open(runtime) as image:
            assert image.format == "WEBP"
            image.verify()
        with Image.open(runtime) as image:
            image.load()
            assert image.size == (1536, 864)
        assert shot["RUNTIME_DIMENSIONS"] == "1536x864"


def test_responsive_review_is_explicit_and_physical_acceptance_remains_open():
    manifest = _load_manifest()
    review_keys = (
        "DESKTOP_16_9",
        "IPAD_LANDSCAPE",
        "IPAD_PORTRAIT",
        "MOBILE_PORTRAIT",
    )
    safe_counts = {key: 0 for key in review_keys}
    for shot in manifest["shots"]:
        notes = shot["RESPONSIVE_NOTES"]
        assert set(review_keys) <= notes.keys()
        assert notes["PHYSICAL_DEVICE_ACCEPTANCE"] == "REQUIRED_LATER"
        for key in review_keys:
            assert notes[key]["SAFE"] in {"YES", "NO"}
            if notes[key]["SAFE"] == "YES":
                safe_counts[key] += 1
    assert safe_counts == {
        "DESKTOP_16_9": 10,
        "IPAD_LANDSCAPE": 10,
        "IPAD_PORTRAIT": 2,
        "MOBILE_PORTRAIT": 2,
    }


def test_content_guards_replay_safety_and_lord_boundary_are_presentation_only():
    manifest = _load_manifest()
    guards = manifest["content_guards"]
    assert all(
        guards[key]
        for key in (
            "TEXT_NOT_BAKED_INTO_BASE_IMAGE",
            "ZONE_STATE_NOT_BAKED_INTO_BASE_IMAGE",
            "BOSS_STATE_NOT_BAKED_INTO_BASE_IMAGE",
            "ROUTE_NOT_BAKED_INTO_BASE_IMAGE",
            "REWARD_NOT_BAKED_INTO_BASE_IMAGE",
        )
    )
    assert guards["GAMEPLAY_AUTHORITY_CHANGED"] is False
    assert manifest["runtime_delivery"]["source_master_untouched"] is True
    assert manifest["runtime_delivery"]["stretching_used"] is False
    assert manifest["runtime_delivery"]["text_inserted"] is False
    assert manifest["replay_contract"] == {
        "presentation_only": True,
        "replay_reuses_same_runtime_paths": True,
        "replay_changes_zone_state": False,
        "replay_issues_rewards": False,
        "replay_consumes_items": False,
    }
    assert manifest["stone_shard_contract"] == {
        "shot": "SHOT09",
        "ordinary": True,
        "glowing": False,
        "irregular": True,
        "natural_marks_only": True,
        "magic_map": False,
        "rune_artifact": False,
        "gameplay_authority_object": False,
    }
    dependencies = manifest["world_hero_dependency_contract"]
    assert dependencies["character_art_generation_in_scope"] is False
    assert dependencies["separate_character_overlay_required"] is False
    assert dependencies["battlefield_boss_vs_lord_preserved"] is True
    assert manifest["validation_contract"]["physical_device_acceptance"] == "REQUIRED_LATER"
