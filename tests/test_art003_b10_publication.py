"""Publication and byte-freeze checks for the Owner-approved ART003 B10 set."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HEAD = "16548803a62c9fc76a459cb247a026187e644c5c"
SOURCE_BRANCH = "codex/art003-b10-m100-m109-canonical-monster-art-production"
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
EXPECTED_HASHES = {
    "M100": "20C8E3CF6BF9E360111B2A80B358D9D3E5334B6DF808C12D40C7620F830B6ED5",
    "M101": "0D0EBC962AA976FBB68475A1C79A9B14086CDAAE9A1DF8C23A78A1B08D0CEAF2",
    "M102": "B13CF95BBE49DE6EA5436A1A62340F277311506D1EED6623577B0CE82071C779",
    "M103": "7ADCAC9321B63ACCF1CF5E239FFDBE1F600FE35811CC54C416AC7BB4C81A80F8",
    "M104": "6EBB69384E8B6B9CCB59E98908199A2BB0C45E252964FABD7847200DA8227EF3",
    "M105": "088131B2A947259D7199255B023161BE1F854D26855BA7079AAD6966E5ED6732",
    "M106": "356DF03C08FFF522FF707D8CAF0F17278BF8BA80CFB8479B746C0BE06834F963",
    "M107": "BF342DD63A3E7B01601385CCDB8DA760B62DB7E8AEF9AFEA625927634C9FBA10",
    "M108": "6B8D34B5039DF82B28FC57BEB4BDED7C47438B2263CD5EF30363EDFF89485DB0",
    "M109": "4DF9C8972C15BBB35E894A7AEF62DE6BA3400EA654F81257D09AA351113459E2",
}
MANIFEST = ROOT / "docs/planning/art_003_batch_010_manifest.json"
PACK = ROOT / "docs/planning/art_003_batch_010_owner_visual_review_pack.md"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_owner_pass_and_exact_publication_set() -> None:
    data = _manifest()
    assert data["status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
    assert data["owner_visual_review_status"] == "PASS"
    assert data["owner_pass_count"] == "10/10"
    assert data["owner_rejected_ids"] == "NONE"
    assert data["redraw_required"] == "NONE"
    assert data["expected_ids"] == EXPECTED_IDS
    assert data["expected_id_count"] == 10
    assert data["canonical_art_published_count"] == 10
    assert data["canonical_art_id_set_exact"] == "YES"
    ids = [entry["monster_id"] for entry in data["assets"]]
    assert ids == EXPECTED_IDS
    assert len(ids) == len(set(ids)) == 10
    assert "M084" not in ids


def test_owner_approved_hash_lock_and_source_byte_identity() -> None:
    data = _manifest()
    assert data["owner_approved_hash_match_count"] == 10
    assert data["owner_approved_bytes_match"] == "YES"
    assert data["owner_approved_byte_drift_count"] == 0
    assert data["authoritative_lineage"]["source_head"] == SOURCE_HEAD
    assert _git("rev-parse", f"origin/{SOURCE_BRANCH}") == SOURCE_HEAD
    _git("cat-file", "-e", f"{SOURCE_HEAD}^{{commit}}")

    published_hashes = []
    for entry in data["assets"]:
        monster_id = entry["monster_id"]
        expected_hash = EXPECTED_HASHES[monster_id]
        assert entry["sha256"] == expected_hash
        assert entry["owner_approved_sha256"] == expected_hash
        assert entry["published_sha256"] == expected_hash
        assert entry["byte_drift"] == 0
        assert entry["owner_visual_review_status"] == "PASS"
        assert entry["freeze_status"] == "FROZEN"
        assert entry["canonical_art_status"] == "OWNER_PASS_FROZEN_AND_PUBLISHED"
        assert entry["source_head"] == SOURCE_HEAD
        path = ROOT / entry["asset_path"]
        actual = path.read_bytes()
        source_bytes = subprocess.check_output(
            ["git", "show", f"{SOURCE_HEAD}:{entry['asset_path']}"], cwd=ROOT
        )
        assert actual == source_bytes
        digest = hashlib.sha256(actual).hexdigest().upper()
        assert digest == expected_hash
        published_hashes.append(digest)
    assert len(published_hashes) == len(set(published_hashes)) == 10


def test_review_pack_records_owner_pass_and_no_excluded_candidate() -> None:
    pack = PACK.read_text(encoding="utf-8")
    assert "Status: `OWNER_VISUAL_REVIEW_STATUS=PASS`" in pack
    assert "Owner pass count: `10/10`" in pack
    assert "Owner revision required: `NO`" in pack
    assert "Canonical art status: `OWNER_PASS_FROZEN_AND_PUBLISHED`" in pack
    assert "PENDING" not in pack
    assert "| M084 |" not in pack
    assert "art/monsters/M084_" not in pack
    for index, monster_id in enumerate(EXPECTED_IDS, start=1):
        assert f"### {index}. " in pack
        assert monster_id in pack
    assert pack.count("Owner review: `PASS`") == 10


def test_governance_firewalls_and_publication_scope() -> None:
    data = _manifest()
    planning = data["planning_semantics"]
    assert planning["f035_zone_assignment_mutated"] == "NO"
    assert planning["f035_zone_used_for_gameplay"] == "NO"
    assert planning["f036_batch_plan_mutated"] == "NO"
    runtime = data["runtime_firewall"]
    assert runtime["app_py_changed"] == "NO"
    assert runtime["runtime_source_changed"] == "NO"
    assert runtime["gameplay_source_changed"] == "NO"
    assert runtime["strict_m_id_binding_implemented"] == "NO"
    assert runtime["monster_catalog_gameplay_authority_changed"] == "NO"
    assert data["firewall_summary"]["master_merge"] == "NO"
    assert data["firewall_summary"]["production_query"] == "NO"
    assert data["firewall_summary"]["production_mutation"] == "NO"
    assert data["firewall_summary"]["deploy"] == "NO"
    assert data["owner_gate"]["ready_for_owner_visual_review"] == "NO"
    assert data["owner_gate"]["self_approval"] == "NO"


def test_prior_art_and_runtime_scope_unchanged() -> None:
    changed = set(_git("diff", "--name-only", f"{SOURCE_HEAD}...HEAD").splitlines())
    expected = {
        "docs/planning/art_003_batch_010_manifest.json",
        "docs/planning/art_003_batch_010_owner_visual_review_pack.md",
        "tests/test_art003_b10_publication.py",
    }
    assert changed == expected
    assert not any(path == "app.py" or path.endswith(".js") or path.endswith(".html") for path in changed)
    prior_assets = set(_git("ls-tree", "-r", "--name-only", SOURCE_HEAD, "--", "art/monsters").splitlines())
    assert not (changed & prior_assets)
    assert _git("status", "--short", "--untracked-files=no") == ""
