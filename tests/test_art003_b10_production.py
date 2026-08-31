"""Focused structural and governance checks for ART003 B10 candidates."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

from tests.art003_admission_scope import (
    ART003_B10_SCOPE_TIP,
    admission_base,
    changed_paths as admission_changed_paths,
    is_canonical_line,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = "7d5c9c389561b877896f2b28e4b7db5f67fb97e8"
EXPECTED_IDS = [
    "M100",
    "M101",
    "M102",
    "M103",
    "M104",
    "M105",
    "M106",
    "M107",
    "M108",
    "M109",
]
EXPECTED = {
    "M100": ("Thundercrown Stag", "Z1", "art/monsters/M100_thundercrown_stag.png", "20C8E3CF6BF9E360111B2A80B358D9D3E5334B6DF808C12D40C7620F830B6ED5", (1230, 1278)),
    "M101": ("Skyvault Whale", "Z9", "art/monsters/M101_skyvault_whale.png", "0D0EBC962AA976FBB68475A1C79A9B14086CDAAE9A1DF8C23A78A1B08D0CEAF2", (1536, 1024)),
    "M102": ("Star-ring Ape", "Z9", "art/monsters/M102_star_ring_ape.png", "B13CF95BBE49DE6EA5436A1A62340F277311506D1EED6623577B0CE82071C779", (1230, 1278)),
    "M103": ("Riftbow Eagle", "Z9", "art/monsters/M103_riftbow_eagle.png", "7ADCAC9321B63ACCF1CF5E239FFDBE1F600FE35811CC54C416AC7BB4C81A80F8", (1536, 1024)),
    "M104": ("Moon-eclipse Mantis", "Z9", "art/monsters/M104_moon_eclipse_mantis.png", "6EBB69384E8B6B9CCB59E98908199A2BB0C45E252964FABD7847200DA8227EF3", (1214, 1295)),
    "M105": ("Skydrum Tortoise", "Z1", "art/monsters/M105_skydrum_tortoise.png", "088131B2A947259D7199255B023161BE1F854D26855BA7079AAD6966E5ED6732", (1536, 1024)),
    "M106": ("Starsand Wolf", "Z9", "art/monsters/M106_starsand_wolf.png", "356DF03C08FFF522FF707D8CAF0F17278BF8BA80CFB8479B746C0BE06834F963", (1536, 1024)),
    "M107": ("Monolith Beetle", "Z1", "art/monsters/M107_monolith_beetle.png", "BF342DD63A3E7B01601385CCDB8DA760B62DB7E8AEF9AFEA625927634C9FBA10", (1312, 1199)),
    "M108": ("Thundercrystal Mantis", "Z9", "art/monsters/M108_thundercrystal_mantis.png", "6B8D34B5039DF82B28FC57BEB4BDED7C47438B2263CD5EF30363EDFF89485DB0", (1536, 1024)),
    "M109": ("Firmament Jelly", "Z9", "art/monsters/M109_firmament_jelly.png", "4DF9C8972C15BBB35E894A7AEF62DE6BA3400EA654F81257D09AA351113459E2", (1024, 1536)),
}
MANIFEST = ROOT / "docs/planning/art_003_batch_010_manifest.json"
PACK = ROOT / "docs/planning/art_003_batch_010_owner_visual_review_pack.md"
B10_ADMISSION_PATHS = frozenset(
    {value[2] for value in EXPECTED.values()}
    | {
        "docs/planning/art_003_batch_010_manifest.json",
        "docs/planning/art_003_batch_010_owner_visual_review_pack.md",
        "tests/test_art003_b10_production.py",
        "tests/test_art003_b10_publication.py",
    }
)


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, capture_output=True)
    return result.stdout.strip()


def _scoped_changed_paths() -> set[str]:
    return admission_changed_paths(canonical_tip=ART003_B10_SCOPE_TIP, candidate_base=BASE)


def _assert_prior_art_unchanged() -> None:
    scope_base = admission_base(canonical_tip=ART003_B10_SCOPE_TIP, candidate_base=BASE)
    prior = set(_git("ls-tree", "-r", "--name-only", scope_base, "--", "art/monsters").splitlines())
    candidate = set(_git("ls-tree", "-r", "--name-only", "HEAD", "--", "art/monsters").splitlines())
    assert not (B10_ADMISSION_PATHS & prior)
    for path in sorted(prior & candidate):
        assert _git("rev-parse", f"{scope_base}:{path}") == _git("rev-parse", f"HEAD:{path}")
    if is_canonical_line(canonical_tip=ART003_B10_SCOPE_TIP):
        assert prior <= candidate


def _assert_no_unexpected_worktree_changes() -> None:
    status_paths = {
        line[2:].lstrip()
        for line in _git("status", "--short", "--untracked-files=no").splitlines()
        if len(line) >= 3
    }
    assert status_paths <= {
        "tests/test_art003_b10_production.py",
        "tests/test_art003_b10_publication.py",
    }


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_b10_exact_id_set_and_manifest_completeness() -> None:
    data = _manifest()
    assert data["batch"] == "ART003_B10"
    assert data["expected_id_count"] == 10
    assert data["expected_ids"] == EXPECTED_IDS
    assert data["id_set_exact"] == "YES"
    entries = data["assets"]
    assert [entry["monster_id"] for entry in entries] == EXPECTED_IDS
    assert len(entries) == 10
    assert "M084" not in {entry["monster_id"] for entry in entries}
    assert data["owner_visual_review_status"] == "PASS"
    assert data["owner_pass_count"] == "10/10"


def test_b10_asset_bytes_and_png_contract() -> None:
    data = _manifest()
    entries = {entry["monster_id"]: entry for entry in data["assets"]}
    hashes = []
    for monster_id in EXPECTED_IDS:
        name, zone, relative_path, expected_hash, expected_size = EXPECTED[monster_id]
        entry = entries[monster_id]
        assert entry["canonical_name"] == name
        assert entry["planning_zone"] == zone
        assert entry["asset_path"] == relative_path
        assert entry["sha256"] == expected_hash
        path = ROOT / relative_path
        assert path.is_file()
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert image.size == expected_size
            alpha = image.getchannel("A")
            assert alpha.getextrema()[1] > 0
            assert alpha.getbbox() is not None
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert digest == expected_hash
        assert entry["width"] == expected_size[0]
        assert entry["height"] == expected_size[1]
        assert entry["mode"] == "RGBA"
        hashes.append(digest)
    assert len(hashes) == len(set(hashes)) == 10


def test_b10_source_head_contains_exact_candidate_bytes() -> None:
    data = _manifest()
    source_head = data["authoritative_lineage"]["source_head"]
    _git("cat-file", "-e", f"{source_head}^{{commit}}")
    for entry in data["assets"]:
        committed = subprocess.check_output(
            ["git", "show", f"{source_head}:{entry['asset_path']}"], cwd=ROOT
        )
        assert committed == (ROOT / entry["asset_path"]).read_bytes()


def test_b10_zone_and_firewall_metadata() -> None:
    data = _manifest()
    assert data["planning_semantics"]["zone_distribution"] == {"Z1": 3, "Z9": 7}
    assert data["planning_semantics"]["f035_zone_assignment_mutated"] == "NO"
    assert data["planning_semantics"]["f035_zone_used_for_gameplay"] == "NO"
    assert data["planning_semantics"]["f036_batch_plan_mutated"] == "NO"
    assert data["runtime_firewall"]["app_py_changed"] == "NO"
    assert data["runtime_firewall"]["runtime_source_changed"] == "NO"
    assert data["runtime_firewall"]["gameplay_source_changed"] == "NO"
    assert data["runtime_firewall"]["monster_catalog_gameplay_authority_changed"] == "NO"


def test_b10_review_pack_exact_order_and_owner_pass_gate() -> None:
    pack = PACK.read_text(encoding="utf-8")
    assert "OWNER_VISUAL_REVIEW_STATUS=PASS" in pack
    assert "Owner pass count: `10/10`" in pack
    positions = [pack.index(f"### {index}. ") for index in range(1, 11)]
    assert positions == sorted(positions)
    for index, monster_id in enumerate(EXPECTED_IDS, start=1):
        assert f"### {index}. " in pack
        assert monster_id in pack
    assert "| M084 |" not in pack
    assert "art/monsters/M084_" not in pack


def test_b10_change_scope_and_prior_art_protection() -> None:
    changed = _scoped_changed_paths()
    assert changed == B10_ADMISSION_PATHS
    assert {entry["asset_path"] for entry in _manifest()["assets"]} == {
        value[2] for value in EXPECTED.values()
    }
    assert not any(
        path == "app.py"
        or path.startswith(("runtime/", "gameplay/"))
        or path.endswith((".js", ".html"))
        or "b11" in path.lower()
        or "M084" in path
        for path in changed
    )
    _assert_prior_art_unchanged()
    _assert_no_unexpected_worktree_changes()
