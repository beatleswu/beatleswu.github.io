"""Offline source admission (not execution permission) adversarial checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from tools.verify_owner_star_source_bundle_20261019 import (
    verify_archive, BundleRefused, MAINTENANCE_FILES,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "handoffs"
BUNDLE = OUTPUT / "GO_ODYSSEY_13_STAR_SOURCE_ADMISSION_R2_20261019.zip"
MANIFEST = OUTPUT / "GO_ODYSSEY_13_STAR_SOURCE_ADMISSION_MANIFEST_R2_20261019.json"
PIN = "4d9d3b3d655a4e1c631dccfb253eb910b3768a4f85a1e70efee335cb70a9dcc2"


def _pack(path, items):
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in items:
            z.writestr(name, data)


@pytest.fixture
def checked_contents():
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == PIN
    with zipfile.ZipFile(BUNDLE, "r") as z:
        return [(x.filename, z.read(x)) for x in z.infolist()]


def test_original_zip_verifies_only_as_source_not_execution(checked_contents):
    result = verify_archive(BUNDLE, MANIFEST, expected_manifest_sha256=PIN,
                            runtime_root=ROOT)
    assert result["file_count"] == 3
    assert result["runtime_dependencies_byte_identical"] is True
    assert result["independent_execution_permit_verified"] is False
    assert result["production_mutated"] is False
    assert {name for name, _ in checked_contents} == MAINTENANCE_FILES


def test_tampered_source_bytes_refused(tmp_path, checked_contents):
    rewritten = [(name, data + b"\n# changed content\n" if i == 0 else data)
                 for i, (name, data) in enumerate(checked_contents)]
    target = tmp_path / "modified.zip"
    _pack(target, rewritten)
    with pytest.raises(BundleRefused, match="source bytes"):
        verify_archive(target, MANIFEST, expected_manifest_sha256=PIN)


@pytest.mark.parametrize("addition", [
    ("unexpected.sh", b"exit 0"),
    ("../escape.py", b"print('escape')"),
])
def test_extra_or_parent_path_refused(tmp_path, checked_contents, addition):
    target = tmp_path / "extra.zip"
    _pack(target, [*checked_contents, addition])
    with pytest.raises(BundleRefused, match="missing, duplicate or additional"):
        verify_archive(target, MANIFEST, expected_manifest_sha256=PIN)


def test_missing_file_refused(tmp_path, checked_contents):
    target = tmp_path / "missing.zip"
    _pack(target, checked_contents[:-1])
    with pytest.raises(BundleRefused, match="missing"):
        verify_archive(target, MANIFEST, expected_manifest_sha256=PIN)


def test_wrong_pin_refused(checked_contents):
    with pytest.raises(BundleRefused, match="pinned"):
        verify_archive(BUNDLE, MANIFEST, expected_manifest_sha256="0" * 64)


def test_modified_manifest_even_with_modified_pin_cannot_change_scope(
        tmp_path, checked_contents):
    revised = json.loads(MANIFEST.read_text(encoding="utf-8"))
    revised["immutable_preflight"]["eligible_unawarded_users"] = 14
    alt = tmp_path / "scope_changed.json"
    alt.write_text(json.dumps(revised), encoding="utf-8")
    pin = hashlib.sha256(alt.read_bytes()).hexdigest()
    with pytest.raises(BundleRefused, match="13-player"):
        verify_archive(BUNDLE, alt, expected_manifest_sha256=pin)


def test_dependency_version_mismatch_refused(tmp_path, checked_contents):
    for relative in (
        "db.py", "adventure_progress_compatibility.py",
        "adventure_zone_progression_authority.py",
    ):
        dest = tmp_path / relative
        dest.write_bytes((ROOT / relative).read_bytes())
    (tmp_path / "db.py").write_bytes(b"not the reviewed DB version")
    with pytest.raises(BundleRefused, match="runtime dependency checksum"):
        verify_archive(BUNDLE, MANIFEST, expected_manifest_sha256=PIN,
                       runtime_root=tmp_path)


def test_bare_manifest_without_archive_cannot_authorize_execution(checked_contents):
    verdict = verify_archive(BUNDLE, MANIFEST, expected_manifest_sha256=PIN)
    assert verdict["independent_execution_permit_verified"] is False
    assert verdict["runtime_dependencies_byte_identical"] is False
