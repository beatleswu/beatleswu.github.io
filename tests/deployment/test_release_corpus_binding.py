"""Static and local contract tests for corpus release binding."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools import content_remote_publish as remote


REPO_ROOT = Path(__file__).resolve().parents[2]
FIELDS = {
    "questions_corpus_sha256",
    "questions_corpus_record_count",
    "questions_corpus_bytes",
    "questions_corpus_snapshot_id",
    "questions_corpus_source_identity",
    "questions_corpus_source_sha256",
    "questions_corpus_source_record_count",
}


def test_release_schema_requires_all_corpus_identity_fields():
    schema = json.loads((REPO_ROOT / "deploy" / "release-manifest.schema.json").read_text(encoding="utf-8"))
    assert FIELDS.issubset(set(schema["required"]))
    assert FIELDS.issubset(set(schema["properties"]))


def test_release_example_and_build_manifest_carry_corpus_identity_contract():
    example = json.loads((REPO_ROOT / "deploy" / "release-manifest.example.json").read_text(encoding="utf-8"))
    assert FIELDS.issubset(set(example))
    build = json.loads((REPO_ROOT / "deploy" / "build-manifest.json").read_text(encoding="utf-8"))
    contract = build["build_inputs"]["questions_corpus_release_binding"]
    assert contract["required"] is True
    assert contract["no_implicit_discovery"] is True
    assert FIELDS == set(contract["identity_fields"])


def test_package_and_shared_manifest_tool_require_explicit_corpus_identity():
    package = (REPO_ROOT / "scripts" / "release" / "package-release-image.ps1").read_text(encoding="utf-8")
    module = (REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1").read_text(encoding="utf-8")
    for token in (
        "$QuestionsCorpusPath",
        "$QuestionsCorpusSha256",
        "$QuestionsCorpusRecordCount",
        "$QuestionsCorpusBytes",
        "RELEASE_ENFORCEMENT",
        "questions_corpus_validation.py",
        "-QuestionsCorpusIdentity",
    ):
        assert token in package
    for token in ("QuestionsCorpusIdentity is required", "questions_corpus_snapshot_id", "questions_corpus_source_identity"):
        assert token in module


def test_deployment_record_rebinds_all_manifest_corpus_identity_fields():
    deployment = (REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1").read_text(encoding="utf-8")
    start = deployment.index("function New-DeploymentRecord")
    end = deployment.index("function Save-DeploymentRecord", start)
    record_builder = deployment[start:end]

    assert "$questionsCorpusIdentity = [pscustomobject]@{" in record_builder
    assert "-QuestionsCorpusIdentity $questionsCorpusIdentity" in record_builder
    for field in FIELDS:
        assert re.search(
            rf"^\s+{field}\s*=\s*(?:\[int64\])?\$manifest\.{field}\s*$",
            record_builder,
            flags=re.MULTILINE,
        )
    assert "questions_corpus_sha256 = '" not in record_builder
    assert "questions_corpus_snapshot_id = '" not in record_builder


def _actual() -> remote.FileIdentity:
    return remote.FileIdentity(path="fixture", size_bytes=100, sha256="a" * 64, record_count=2)


def _binding() -> dict:
    return {
        "questions_corpus_sha256": "a" * 64,
        "questions_corpus_record_count": 2,
        "questions_corpus_bytes": 100,
        "questions_corpus_snapshot_id": "fixture-snapshot-001",
        "questions_corpus_source_identity": "b" * 64,
        "questions_corpus_source_sha256": "c" * 64,
        "questions_corpus_source_record_count": 2,
    }


def test_publish_validator_rejects_missing_and_wrong_identity_fields():
    binding = _binding()
    assert remote._validate_questions_corpus_binding(
        binding,
        actual=_actual(),
        expected_source_sha256="c" * 64,
        expected_source_record_count=2,
    )["questions_corpus_sha256"] == "a" * 64
    missing = dict(binding)
    del missing["questions_corpus_source_identity"]
    with pytest.raises(remote.ContentPublishError, match="questions_corpus_binding_missing"):
        remote._validate_questions_corpus_binding(
            missing,
            actual=_actual(),
            expected_source_sha256="c" * 64,
            expected_source_record_count=2,
        )
    wrong = dict(binding)
    wrong["questions_corpus_bytes"] = 101
    with pytest.raises(remote.ContentPublishError, match="questions_corpus_bytes_mismatch"):
        remote._validate_questions_corpus_binding(
            wrong,
            actual=_actual(),
            expected_source_sha256="c" * 64,
            expected_source_record_count=2,
        )


def test_image_boundary_remains_external():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY questions.json" not in dockerfile
    assert "questions_corpus" not in dockerfile
