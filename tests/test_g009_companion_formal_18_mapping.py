import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "assets/3d_shop/p048/companion/formal_18/mapping_manifest.json"
PET_KEYS = (
    "ink_drop_kelpie",
    "whispering_void_kit",
    "star_shell_hatchling",
    "starpath_antlerling",
    "fatty",
    "obsidian_bastion",
)
STAGES = ("I", "II", "III")
EXPECTED_AUTHORITY = {
    "task_id": "A_G009_COMPANION_FORMAL_18_MAPPING_CLOSURE_001",
    "owner_approval_sha256": "7F763F86718A5CD15193053B0C12A1D790F78801362DABCCB0ED283A78CF5AA7",
    "mapping_markdown_sha256": "11A013FF35481119E2724A36BBEDB60AB5C885F44BBD81F13ABEC60A6120CC7A",
    "mapping_json_sha256": "ABF2DCEB43139B022A0156F4EE8A5B15D61409E4A5949B56480BB66E86D5A24D",
    "handoff_sha256": "F99769E48D4910B43B9D307A91D0FB16EFE74BC9DB0B85A94D61AA8E9812ACA0",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def test_formal_18_manifest_preserves_exact_owner_authority_and_tuples():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for key, expected in EXPECTED_AUTHORITY.items():
        assert manifest[key] == expected
    assert manifest["owner_approved_18_18"] is True
    assert manifest["canonical_pet_keys"] == list(PET_KEYS)
    assert manifest["mapping_count"] == 18
    assert len(manifest["mappings"]) == 18
    assert manifest["stage_authority"]["source"] == "Persistent server pet level only."

    tuples = [(row["pet_key"], row["stage"]) for row in manifest["mappings"]]
    assert len(set(tuples)) == 18
    assert set(tuples) == {(pet_key, stage) for pet_key in PET_KEYS for stage in STAGES}
    assert all("legacy_fallback" not in row for row in manifest["mappings"])
    assert all("Bunny" not in row["runtime_glb"] and "Corgi" not in row["runtime_glb"] for row in manifest["mappings"])


def test_all_approved_runtime_derivatives_are_copied_byte_exact_and_valid_glb():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    total_bytes = 0
    for row in manifest["mappings"]:
        relative = row["runtime_glb"]
        assert relative.startswith("assets/3d_shop/p048/companion/formal_18/")
        path = ROOT / relative
        assert path.is_file()
        assert path.stat().st_size == row["asset_bytes"]
        assert _sha256(path) == row["asset_sha256"]
        total_bytes += path.stat().st_size

        with path.open("rb") as stream:
            header = stream.read(20)
            assert header[:4] == b"glTF"
            version, declared_length = struct.unpack_from("<II", header, 4)
            json_length, json_chunk_type = struct.unpack_from("<II", header, 12)
            assert version == 2
            assert declared_length == path.stat().st_size
            assert json_chunk_type == 0x4E4F534A
            gltf = json.loads(stream.read(json_length).decode("utf-8").rstrip(" \t\r\n\0"))
        assert gltf["asset"]["version"] == "2.0"
        assert gltf.get("meshes")
        assert gltf.get("nodes")
    assert total_bytes == 253_705_012


def test_shared_host_child_behavior_replaces_obsolete_adapter_structure():
    import subprocess
    result = subprocess.run(
        ["node", "tests/e2e/run_g009_companion_shared_host_candidate.mjs"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "HERO_COMPANION_SHARED_SCENE=PASS_CONTROLLED" in result.stdout
    assert "STATUS_AND_MODEL_RACES=PASS" in result.stdout
    assert "MAX_RENDERERS=1" in result.stdout


def test_server_stage_contract_without_importing_application_or_database():
    import ast
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_pet_stage")
    module = ast.Module(body=[fn], type_ignores=[])
    namespace = {}
    exec(compile(module, "server_stage_contract", "exec"), namespace)
    for level, expected in [(9, 1), (10, 2), (24, 2), (25, 3)]:
        assert namespace["_pet_stage"](level) == expected
