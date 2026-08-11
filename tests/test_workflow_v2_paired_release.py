from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workflow_v2_paired_release import (  # noqa: E402
    PairedReleaseError,
    bind_paired_release,
    calculate_compatibility_id,
    finalize_new_pair,
    plan_failure_convergence,
    validate_independent_release,
    validate_paired_release,
    verify_pair_state,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


MERGED_SOURCE = digest("merged-source")[:40]


def app_identity(prefix: str, source_sha: str = MERGED_SOURCE) -> dict[str, str]:
    return {
        "release_manifest_sha256": digest(f"{prefix}-release-manifest"),
        "archive_sha256": digest(f"{prefix}-archive"),
        "image_id": f"sha256:{digest(f'{prefix}-image')}"[:71],
        "image_tag": f"go-odyssey:{prefix}",
        "oci_revision": source_sha,
    }


def static_identity(prefix: str, source_sha: str = MERGED_SOURCE) -> dict[str, str]:
    return {
        "manifest_sha256": digest(f"{prefix}-static-manifest"),
        "archive_sha256": digest(f"{prefix}-static-archive"),
        "static_generation_id": f"static-{prefix}",
        "release_git_sha": source_sha,
        "service_worker_identity": f"sw-{prefix}",
    }


def make_envelope() -> dict[str, object]:
    app = app_identity("new")
    static = static_identity("new")
    previous_app = app_identity("old", digest("old-source")[:40])
    previous_static = static_identity("old", digest("old-source")[:40])
    previous_compatibility_id = calculate_compatibility_id(
        previous_app["oci_revision"], previous_app, previous_static
    )
    compatibility_id = calculate_compatibility_id(MERGED_SOURCE, app, static)
    return bind_paired_release(
        merged_source_sha=MERGED_SOURCE,
        release_id="release-2026-08-12-paired",
        app_artifact=app,
        static_artifact=static,
        compatibility_declaration={
            "declared": True,
            "declared_by": "owner-preflight",
            "compatibility_id": compatibility_id,
            "merged_source_sha": MERGED_SOURCE,
            "app_artifact_identity": app["image_id"],
            "app_archive_sha256": app["archive_sha256"],
            "static_generation_identity": static["static_generation_id"],
            "static_archive_sha256": static["archive_sha256"],
            "service_worker_identity": static["service_worker_identity"],
        },
        previous_app_identity=previous_app,
        previous_static_identity=previous_static,
        predeploy_capture={
            "observation_id": "preflight-observation-1",
            "captured_at": "2026-08-12T12:00:00Z",
            "evidence_sha256": digest("preflight-evidence"),
            "source_tool": "preflight-production.ps1",
            "capture_scope": ["app", "static"],
            "coherence_verified": True,
            "previous_compatibility_id": previous_compatibility_id,
        },
    )


def pair_state(envelope: dict[str, object], pair_name: str) -> dict[str, object]:
    pair = envelope[pair_name]
    assert isinstance(pair, dict)
    return copy.deepcopy(pair)


def test_paired_identity_binding_is_deterministic_and_exact() -> None:
    envelope = make_envelope()

    assert validate_paired_release(envelope)["merged_source_sha"] == MERGED_SOURCE
    assert envelope["new_pair"]["app"]["oci_revision"] == MERGED_SOURCE
    assert envelope["new_pair"]["static"]["release_git_sha"] == MERGED_SOURCE
    assert envelope["new_pair"]["compatibility_id"].startswith("pair-")
    assert envelope["compatibility"]["compatibility_id"] == envelope["new_pair"]["compatibility_id"]


def test_incompatible_pair_is_rejected() -> None:
    app = app_identity("new")
    static = static_identity("new", digest("different-source")[:40])
    with pytest.raises(PairedReleaseError, match="release_git_sha"):
        calculate_compatibility_id(MERGED_SOURCE, app, static)

    envelope = make_envelope()
    broken = copy.deepcopy(envelope)
    broken["compatibility"]["static_generation_identity"] = "static-not-approved"
    with pytest.raises(PairedReleaseError, match="does not bind"):
        validate_paired_release(broken)


def test_immediate_predeploy_capture_contains_both_identities() -> None:
    envelope = make_envelope()

    assert envelope["predeploy"]["source_tool"] == "preflight-production.ps1"
    assert envelope["predeploy"]["capture_scope"] == ["app", "static"]
    assert envelope["predeploy"]["coherence_verified"] is True
    assert envelope["old_pair"]["app"]["image_id"].startswith("sha256:")
    assert envelope["old_pair"]["static"]["static_generation_id"] == "static-old"

    broken = copy.deepcopy(envelope)
    broken["predeploy"]["capture_scope"] = ["app"]
    with pytest.raises(PairedReleaseError, match="exactly app and static"):
        validate_paired_release(broken)

    broken = copy.deepcopy(envelope)
    broken["predeploy"]["previous_compatibility_id"] = "pair-" + digest("wrong-old-pair")
    with pytest.raises(PairedReleaseError, match="previous_compatibility_id"):
        validate_paired_release(broken)


def test_failure_after_app_switch_converges_to_old_coherent_pair() -> None:
    result = plan_failure_convergence(
        make_envelope(),
        phase="APP_SWITCHED",
        failure_kind="app_health_failure",
    )

    assert result["final_state"] == "OLD_COHERENT_PAIR"
    assert result["auto_rollback"] is True
    assert any(action["operation"] == "rollback_app_to_previous" for action in result["actions"])
    assert result["actions"][-1]["operation"] == "verify_old_coherent_pair"


def test_failure_after_static_switch_converges_to_old_coherent_pair() -> None:
    result = plan_failure_convergence(
        make_envelope(),
        phase="STATIC_SWITCHED",
        failure_kind="static_integrity_failure",
    )

    assert result["final_state"] == "OLD_COHERENT_PAIR"
    assert result["auto_rollback"] is True
    assert any(
        action["operation"] == "rollback_static_to_previous"
        for action in result["actions"]
    )
    assert result["actions"][-1]["operation"] == "verify_old_coherent_pair"


def test_failure_after_both_switches_rolls_back_both_under_guard() -> None:
    result = plan_failure_convergence(
        make_envelope(),
        phase="BOTH_SWITCHED",
        failure_kind="critical_affected_path_smoke_failure",
    )

    operations = [action["operation"] for action in result["actions"]]
    assert result["final_state"] == "OLD_COHERENT_PAIR"
    assert result["transition_guard_required"] is True
    assert "rollback_static_to_previous" in operations
    assert "rollback_app_to_previous" in operations
    assert "verify_old_coherent_pair" in operations


def test_successful_new_coherent_pair_requires_exact_artifacts() -> None:
    envelope = make_envelope()
    result = finalize_new_pair(envelope, pair_state(envelope, "new_pair"))

    assert result == {
        "final_state": "NEW_COHERENT_PAIR",
        "coherent": True,
        "compatibility_id": envelope["new_pair"]["compatibility_id"],
    }

    mismatched = pair_state(envelope, "new_pair")
    mismatched["static"]["static_generation_id"] = "static-old"
    with pytest.raises(PairedReleaseError, match="exact pair"):
        finalize_new_pair(envelope, mismatched)


def test_rollback_to_old_coherent_pair_is_exact_and_immediate_predeploy() -> None:
    envelope = make_envelope()
    result = verify_pair_state(
        envelope,
        pair_state(envelope, "old_pair"),
        expected_final_state="OLD_COHERENT_PAIR",
    )

    assert result["final_state"] == "OLD_COHERENT_PAIR"
    assert result["coherent"] is True
    assert result["compatibility_id"] == envelope["old_pair"]["compatibility_id"]


def test_subjective_owner_rejection_does_not_auto_rollback() -> None:
    result = plan_failure_convergence(
        make_envelope(),
        phase="BOTH_SWITCHED",
        subjective_owner_rejection=True,
    )

    assert result["auto_rollback"] is False
    assert result["final_state"] == "UNRESOLVED_UNTIL_OWNER_DECISION"
    assert all("rollback" not in action["operation"] for action in result["actions"])


def test_app_only_and_static_only_remain_independent() -> None:
    app_result = validate_independent_release(
        "APP_ONLY",
        app_artifact=app_identity("app-only"),
    )
    static_result = validate_independent_release(
        "STATIC_ONLY",
        static_artifact=static_identity("static-only"),
    )

    assert app_result["paired"] is False
    assert app_result["release_type"] == "APP_ONLY"
    assert static_result["paired"] is False
    assert static_result["release_type"] == "STATIC_ONLY"
