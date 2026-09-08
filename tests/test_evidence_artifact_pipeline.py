"""Filesystem-only contract tests for the durable evidence authority pipeline."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root not found")


ROOT = _repo_root(Path(__file__).resolve())
sys.path.insert(0, str(ROOT))

from scripts.evidence import evidence_core as core  # noqa: E402


def _metadata(
    *,
    task: str = "TEST-EVIDENCE-VALID",
    artifact_class: str = "INDEPENDENT_REVIEW",
    filename: str = "review.md",
    owner_gate_ref: str | None = None,
    authority_state: str = "ORIGINAL",
    **extra,
) -> dict:
    metadata = {
        "program": "TEST-EVIDENCE",
        "task": task,
        "artifact_class": artifact_class,
        "filename": filename,
        "content_type": "text/markdown; charset=utf-8",
        "producer": "filesystem-test",
        "provenance": {
            "source_type": "test-fixture",
            "fixture": "evidence-pipeline",
        },
        "authority_state": authority_state,
        "created_at_utc": "2026-01-01T00:00:00Z",
    }
    if owner_gate_ref is not None:
        metadata["owner_gate_ref"] = owner_gate_ref
    metadata.update(extra)
    return metadata


def _source(tmp_path: Path, name: str = "source.md", data: bytes = b"evidence") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _finalize(
    tmp_path: Path,
    *,
    data: bytes = b"evidence",
    name: str = "source.md",
    metadata: dict | None = None,
):
    root = tmp_path / "evidence"
    source = _source(tmp_path, name, data)
    result = core.finalize(
        source,
        root=root,
        metadata=metadata
        or _metadata(filename="stored.md"),
    )
    return root, source, result


def _index(root: Path) -> dict:
    return json.loads((root / core.INDEX_FILENAME).read_text(encoding="utf-8"))


def test_register_finalize_and_verify_content_identity(tmp_path):
    root, source, result = _finalize(tmp_path)

    assert result["status"] == "PASS"
    assert result["verified"] == "YES"
    assert result["bytes"] == source.stat().st_size
    assert result["sha256"] == core.sha256_file(source)
    assert Path(result["durable_path"]).is_file()
    assert Path(result["manifest_path"]).is_file()
    assert core.verify(result["artifact_id"], root=root)["verified"] == "YES"

    proposed = core.register(
        source,
        root=tmp_path / "unregistered",
        metadata=_metadata(filename="proposed.md"),
    )
    assert proposed["status"] == "PROPOSED"
    assert not (tmp_path / "unregistered" / core.INDEX_FILENAME).exists()


def test_manifest_and_index_bind_artifact_and_sidecar_hash(tmp_path):
    root, _source_path, result = _finalize(tmp_path)
    artifact = Path(result["durable_path"])
    manifest = Path(result["manifest_path"])
    sidecar = json.loads(manifest.read_text(encoding="utf-8"))
    index_entry = _index(root)["entries"][0]

    assert sidecar["artifact_id"] == result["artifact_id"]
    assert sidecar["bytes"] == artifact.stat().st_size
    assert sidecar["sha256"] == core.sha256_file(artifact)
    assert index_entry["manifest_sha256"] == core.sha256_file(manifest)
    assert index_entry["stable_path"] == str(artifact)
    assert index_entry["manifest_path"] == str(manifest)


def test_mutated_artifact_is_detected(tmp_path):
    _root, _source_path, result = _finalize(tmp_path)
    artifact = Path(result["durable_path"])
    artifact.write_bytes(b"tampered")

    with pytest.raises(core.EvidenceError) as error:
        core.verify(result["artifact_id"], root=_root)
    assert error.value.code == "ARTIFACT_BYTE_COUNT_MISMATCH" or error.value.code == "ARTIFACT_HASH_MISMATCH"


def test_missing_source_is_rejected(tmp_path):
    with pytest.raises(core.EvidenceError) as error:
        core.register(
            tmp_path / "missing.md",
            root=tmp_path / "evidence",
            metadata=_metadata(filename="missing.md"),
        )
    assert error.value.code == "ARTIFACT_MISSING"


def test_duplicate_identity_is_idempotent_but_metadata_collision_fails(tmp_path):
    root, source, first = _finalize(tmp_path)
    second = core.finalize(
        source,
        root=root,
        metadata=_metadata(filename="stored.md"),
    )
    assert second["artifact_id"] == first["artifact_id"]
    assert second["idempotent"] is True
    assert len(_index(root)["entries"]) == 1

    with pytest.raises(core.EvidenceError) as error:
        core.finalize(
            source,
            root=root,
            metadata=_metadata(filename="stored.md", owner_gate_ref="different-gate"),
        )
    assert error.value.code == "DUPLICATE_ARTIFACT_ID"


def test_partial_destination_cannot_become_authoritative(tmp_path):
    root = tmp_path / "evidence"
    source = _source(tmp_path, data=b"partial")
    proposed = core.register(
        source,
        root=root,
        metadata=_metadata(filename="partial.md"),
    )
    artifact = Path(proposed["durable_path"])
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(source.read_bytes())

    with pytest.raises(core.EvidenceError) as error:
        core.finalize(
            source,
            root=root,
            metadata=_metadata(filename="partial.md"),
        )
    assert error.value.code == "PARTIAL_PUBLICATION"
    assert not (root / core.INDEX_FILENAME).exists()


def test_index_update_failure_retains_unindexed_pair_without_false_lock(tmp_path, monkeypatch):
    root = tmp_path / "evidence"
    source = _source(tmp_path, data=b"index failure")

    def fail_index(_root, _index):
        raise core.EvidenceError("sentinel")

    monkeypatch.setattr(core, "_write_index", fail_index)
    with pytest.raises(core.EvidenceError) as error:
        core.finalize(
            source,
            root=root,
            metadata=_metadata(filename="retained.md"),
        )
    assert error.value.code == "INDEX_UPDATE_FAILED"
    assert not (root / core.INDEX_FILENAME).exists()
    assert list(root.rglob("retained.md"))
    assert list(root.rglob(core.MANIFEST_FILENAME))


def test_invalid_manifest_and_missing_artifact_fail_closed(tmp_path):
    root, _source_path, result = _finalize(tmp_path)
    manifest = Path(result["manifest_path"])
    manifest.write_text("{not-json", encoding="utf-8")
    with pytest.raises(core.EvidenceError) as error:
        core.verify(result["artifact_id"], root=root)
    assert error.value.code == "INVALID_JSON"

    root2, _source_path2, result2 = _finalize(tmp_path / "second")
    Path(result2["durable_path"]).unlink()
    with pytest.raises(core.EvidenceError) as error2:
        core.verify(result2["artifact_id"], root=root2)
    assert error2.value.code == "ARTIFACT_MISSING"


def test_secret_content_and_protected_source_path_are_rejected(tmp_path):
    secret_source = _source(
        tmp_path,
        name="candidate.md",
        data=b"Authorization: Bearer " + (b"A" * 24),
    )
    with pytest.raises(core.EvidenceError) as error:
        core.register(
            secret_source,
            root=tmp_path / "evidence",
            metadata=_metadata(filename="candidate.md"),
        )
    assert error.value.code == "PROHIBITED_SECRET_CONTENT"
    assert "Bearer" not in str(error.value)
    assert "AAAA" not in str(error.value)

    protected = tmp_path / "secret_key.txt"
    protected.write_bytes(b"not inspected")
    with pytest.raises(core.EvidenceError) as path_error:
        core.register(
            protected,
            root=tmp_path / "protected-evidence",
            metadata=_metadata(filename="copy.md"),
        )
    assert path_error.value.code == "PROTECTED_SOURCE_PATH_REJECTED"
    with pytest.raises(core.EvidenceError) as metadata_error:
        core._load_metadata_json(protected)
    assert metadata_error.value.code == "PROTECTED_SOURCE_PATH_REJECTED"


def test_supersession_is_explicit_and_old_bytes_are_retained(tmp_path):
    root = tmp_path / "evidence"
    old = core.finalize(
        _source(tmp_path, "old-source.md", b"old"),
        root=root,
        metadata=_metadata(task="TEST-SUPERSEDE-OLD", filename="old.md"),
    )
    new = core.finalize(
        _source(tmp_path, "new-source.md", b"new"),
        root=root,
        metadata=_metadata(task="TEST-SUPERSEDE-NEW", filename="new.md"),
    )
    old_artifact = Path(old["durable_path"])
    result = core.supersede(old["artifact_id"], new["artifact_id"], root=root)
    assert result["verified"] == "YES"
    entries = {entry["artifact_id"]: entry for entry in _index(root)["entries"]}
    assert entries[old["artifact_id"]]["lifecycle_state"] == "SUPERSEDED"
    assert entries[old["artifact_id"]]["superseded_by"] == [new["artifact_id"]]
    assert entries[new["artifact_id"]]["supersedes"] == [old["artifact_id"]]
    assert old_artifact.is_file()
    assert Path(new["durable_path"]).is_file()


def test_recovered_original_preserves_content_bound_identity_and_reconstruction_is_new(tmp_path):
    root = tmp_path / "evidence"
    original_source = _source(tmp_path, "original.md", b"recovered original")
    recovered_metadata = _metadata(
        task="TEST-F33-RECOVERED-ORIGINAL",
        artifact_class="RECOVERY_MANIFEST",
        filename="original.md",
        authority_state="RECOVERED_ORIGINAL",
        recovered_from="D:\\go-odyssey-release-evidence\\w2-f33\\original.md",
    )
    first = core.recover(
        original_source,
        root=root,
        metadata=recovered_metadata,
    )
    second = core.recover(
        original_source,
        root=root,
        metadata=recovered_metadata,
    )
    assert first["artifact_id"] == second["artifact_id"]
    assert second["idempotent"] is True
    sidecar = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))
    assert sidecar["authority_state"] == "RECOVERED_ORIGINAL"
    assert sidecar["recovered_from"].endswith("original.md")

    reconstruction_source = _source(tmp_path, "reconstruction.md", b"reconstructed")
    reconstructed = core.recover(
        reconstruction_source,
        root=root,
        metadata=_metadata(
            task="TEST-F33-RECONSTRUCTION",
            artifact_class="RECOVERY_MANIFEST",
            filename="reconstruction.md",
            authority_state="RECONSTRUCTED",
            reconstruction_of=first["artifact_id"],
        ),
    )
    assert reconstructed["artifact_id"] != first["artifact_id"]
    reconstructed_sidecar = json.loads(
        Path(reconstructed["manifest_path"]).read_text(encoding="utf-8")
    )
    assert reconstructed_sidecar["authority_state"] == "RECONSTRUCTED"
    assert reconstructed_sidecar["reconstruction_of"] == first["artifact_id"]


def test_scratchpad_registration_is_not_durable_closeout(tmp_path):
    root = tmp_path / "evidence"
    source = _source(tmp_path, data=b"working")
    proposal = core.register(
        source,
        root=root,
        metadata=_metadata(filename="working.md"),
    )
    assert proposal["status"] == "PROPOSED"
    assert not (root / core.INDEX_FILENAME).exists()
    assert not list(root.rglob("working.md"))


def test_verify_lookup_and_audit_fail_closed_when_index_is_missing(tmp_path):
    root = tmp_path / "evidence"
    source = _source(tmp_path, data=b"unindexed")
    proposal = core.register(
        source,
        root=root,
        metadata=_metadata(filename="unindexed.md"),
    )
    for operation in (
        lambda: core.verify(proposal["artifact_id"], root=root),
        lambda: core.lookup(root=root),
        lambda: core.audit(root=root),
    ):
        with pytest.raises(core.EvidenceError) as error:
            operation()
        assert error.value.code == "INDEX_MISSING"


def test_f33_bootstrap_backfill_preserves_existing_legacy_artifact_id(tmp_path):
    root = tmp_path / "evidence"
    data = b"F33 recovered original fixture"
    sha256 = core._sha256_bytes(data)
    artifact_id = f"GOE1-W2-INFRA-EVIDENCE-001-MASTERPLAN-{sha256[:16]}"
    artifact = (
        root
        / "W2-INFRASTRUCTURE"
        / "W2-INFRA-EVIDENCE-001"
        / "MASTERPLAN"
        / artifact_id
        / "authority.md"
    )
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(data)
    manifest = artifact.parent / core.MANIFEST_FILENAME
    manifest_payload = {
        "artifact_id": artifact_id,
        "schema_version": core.BOOTSTRAP_SCHEMA_VERSION,
        "task": "W2-INFRA-EVIDENCE-001-AUTHORITY-ARTIFACT-PIPELINE-CENSUS-AND-CONTRACT-LOCK",
        "artifact_class": "MASTERPLAN",
        "filename": "authority.md",
        "stable_path": str(artifact),
        "content_type": "text/markdown; charset=utf-8",
        "bytes": len(data),
        "hash_algorithm": "SHA256",
        "sha256": sha256,
        "created_at_utc": "2026-01-01T00:00:00Z",
        "producer": "bootstrap-fixture",
        "provenance": {"source_type": "F33"},
        "authority_state": "ORIGINAL",
        "lifecycle_state": "CURRENT_ACTIONABLE",
        "retention_class": "ACTIVE_AUTHORITY",
        "immutable": True,
        "canonical_head": "a" * 40,
        "canonical_tree": "b" * 40,
        "BOOTSTRAP_CREATED_BEFORE_EVIDENCE_PIPELINE_V1": "YES",
        "CENTRAL_INDEX_ENTRY_PENDING": "YES",
    }
    manifest.write_bytes(core._json_bytes(manifest_payload))

    result = core.backfill_existing_artifact(artifact, root=root)
    assert result["artifact_id"] == artifact_id
    assert result["idempotent"] is False
    assert core.verify(artifact_id, root=root)["verified"] == "YES"
    assert _index(root)["entries"][0]["artifact_id"] == artifact_id


def test_lookup_by_task_class_sha_and_owner_gate(tmp_path):
    root, source, result = _finalize(
        tmp_path,
        metadata=_metadata(
            task="TEST-LOOKUP",
            filename="lookup.md",
            owner_gate_ref="GO_TEST_GATE",
            canonical_head="a" * 40,
            canonical_tree="b" * 40,
        ),
    )
    sha256 = core.sha256_file(source)
    assert core.lookup(root=root, task="TEST-LOOKUP")["entries"][0]["artifact_id"] == result["artifact_id"]
    assert core.lookup(root=root, artifact_class="INDEPENDENT_REVIEW")["entries"]
    assert core.lookup(root=root, sha256=sha256)["entries"]
    assert core.lookup(root=root, canonical_head="a" * 40)["entries"]
    assert core.lookup(root=root, canonical_tree="b" * 40)["entries"]
    assert core.lookup(root=root, owner_gate_ref="GO_TEST_GATE")["entries"]


def test_audit_detects_mutation_and_index_corruption(tmp_path):
    root, _source, result = _finalize(tmp_path)
    assert core.audit(root=root)["verified"] == "YES"
    Path(result["durable_path"]).write_bytes(b"mutated")
    with pytest.raises(core.EvidenceError) as error:
        core.audit(root=root)
    assert error.value.code in {"ARTIFACT_BYTE_COUNT_MISMATCH", "ARTIFACT_HASH_MISMATCH"}

    root2, _source2, result2 = _finalize(tmp_path / "corrupt")
    index_path = root2 / core.INDEX_FILENAME
    payload = _index(root2)
    payload["entries"].append(dict(payload["entries"][0]))
    index_path.write_bytes(core._json_bytes(payload))
    with pytest.raises(core.EvidenceError) as index_error:
        core.lookup(root=root2)
    assert index_error.value.code == "DUPLICATE_ARTIFACT_ID"
    assert result2["artifact_id"] in index_path.read_text(encoding="utf-8")


def test_bounded_audit_rebuilds_bootstrap_index_without_rewriting_sidecar(tmp_path):
    root = tmp_path / "evidence"
    source = _source(tmp_path, "bootstrap.md", b"bootstrap")
    sha256 = core.sha256_file(source)
    artifact_id = f"GOE1-W2-INFRA-EVIDENCE-001-MASTERPLAN-{sha256[:16]}"
    artifact = root / "W2-INFRASTRUCTURE" / "W2-INFRA-EVIDENCE-001" / "MASTERPLAN" / artifact_id / "bootstrap.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(source.read_bytes())
    manifest = artifact.parent / core.MANIFEST_FILENAME
    manifest.write_bytes(
        core._json_bytes(
            {
                "artifact_id": artifact_id,
                "schema_version": core.BOOTSTRAP_SCHEMA_VERSION,
                "task": "W2-INFRA-EVIDENCE-001-AUTHORITY-ARTIFACT-PIPELINE-CENSUS-AND-CONTRACT-LOCK",
                "artifact_class": "MASTERPLAN",
                "filename": "bootstrap.md",
                "stable_path": str(artifact),
                "bytes": len(b"bootstrap"),
                "hash_algorithm": "SHA256",
                "sha256": sha256,
                "authority_state": "ORIGINAL",
                "lifecycle_state": "CURRENT_ACTIONABLE",
                "retention_class": "ACTIVE_AUTHORITY",
                "immutable": True,
            }
        )
    )
    before = manifest.read_bytes()
    result = core.audit(root=root, rebuild_index=True, artifact_paths=[artifact])
    assert result["verified"] == "YES"
    assert manifest.read_bytes() == before
    assert _index(root)["entries"][0]["artifact_id"] == artifact_id


def test_cli_and_powershell_entrypoint_expose_core_commands(tmp_path):
    root = tmp_path / "evidence"
    source = _source(tmp_path, data=b"cli")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_bytes(core._json_bytes(_metadata(filename="cli.md")))
    core_path = ROOT / "scripts" / "evidence" / "evidence_core.py"
    result = subprocess.run(
        [
            sys.executable,
            str(core_path),
            "--root",
            str(root),
            "finalize",
            "--source",
            str(source),
            "--metadata-json",
            str(metadata_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verified"] == "YES"

    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell entrypoint unavailable")
    wrapper = ROOT / "scripts" / "evidence" / "evidence.ps1"
    verify = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "--root",
            str(root),
            "verify",
            "--artifact-id",
            payload["artifact_id"],
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert json.loads(verify.stdout)["verified"] == "YES"


def test_schema_declares_artifact_and_index_contract():
    schema = json.loads(
        (ROOT / "scripts" / "evidence" / "evidence_schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$id"] == "go-odyssey-evidence-contract-v1"
    assert "artifact_manifest" in schema["$defs"]
    assert "evidence_index" in schema["$defs"]
    assert "sha256" in schema["$defs"]["artifact_manifest"]["properties"]
    assert "manifest_sha256" in schema["$defs"]["index_entry"]["properties"]
