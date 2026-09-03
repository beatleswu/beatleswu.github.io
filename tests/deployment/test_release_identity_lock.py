"""The backend / image / static / SW identity lock, with its negative controls.

Production served a new backend alongside a stale ``4bfaf834`` static generation
and every gate stayed green, because each release script validates only its own
artifact against its own ``-ExpectedGitSha``. Nothing compared the image identity
to the static identity.

These tests pin the cross-artifact contract and, critically, prove the negative
cases FAIL. A guard that has never been shown to reject the bad input is not a
guard.
"""

from __future__ import annotations

import pathlib
import sys

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RELEASE_DIR = REPO_ROOT / "scripts" / "release"
for candidate in (str(REPO_ROOT), str(RELEASE_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from release_identity_lock import (  # noqa: E402
    ReleaseIdentityError,
    parse_static_generation,
    verify_from_manifests,
    verify_release_identity,
)


GOOD_SHA = "959c38423bff201bfd2968c34ba755b2d2f25b86"
STALE_SHA = "4bfaf8349167f5de844b45888a152205fde40244"
SW = "v240-a028-hero-player-presentation-readonly"
GOOD_GENERATION = f"20260902-231917-{GOOD_SHA[:8]}-{SW}"
STALE_GENERATION = f"20260901-103529-{STALE_SHA[:8]}-{SW}"


def _identity(**overrides):
    base = {
        "backend_source_sha": GOOD_SHA,
        "image_source_sha": GOOD_SHA,
        "image_revision_label": GOOD_SHA,
        "static_source_sha": GOOD_SHA,
        "static_generation": GOOD_GENERATION,
        "static_sw_version": SW,
        "runtime_sw_version": SW,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Positive contract
# ---------------------------------------------------------------------------
def test_a_coherent_release_passes():
    report = verify_release_identity(**_identity())
    assert report["ok"] is True
    assert report["release_source_sha"] == GOOD_SHA
    assert report["static_generation"] == GOOD_GENERATION
    assert report["sw_version"] == SW


def test_generation_name_is_parsed_into_identity_parts():
    parts = parse_static_generation(GOOD_GENERATION)
    assert parts["short_sha"] == GOOD_SHA[:8]
    assert parts["sw_version"] == SW


# ---------------------------------------------------------------------------
# NEGATIVE CONTROL A -- mismatched backend/static source identity
# ---------------------------------------------------------------------------
def test_stale_static_against_new_backend_is_rejected():
    """The exact invalid Production pattern must be a hard failure."""

    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_release_identity(
            **_identity(
                static_source_sha=STALE_SHA,
                static_generation=STALE_GENERATION,
            )
        )
    assert excinfo.value.code == "release_identity_mismatch"
    assert "static_source_sha" in excinfo.value.detail


def test_stale_image_against_new_backend_is_rejected():
    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_release_identity(**_identity(image_source_sha=STALE_SHA))
    assert excinfo.value.code == "release_identity_mismatch"
    assert "image_source_sha" in excinfo.value.detail


def test_image_label_disagreeing_with_its_manifest_is_rejected():
    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_release_identity(**_identity(image_revision_label=STALE_SHA))
    assert excinfo.value.code == "release_identity_mismatch"
    assert "image_revision_label" in excinfo.value.detail


def test_generation_name_disagreeing_with_its_own_manifest_is_rejected():
    """A generation directory renamed to look current must not pass."""

    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_release_identity(**_identity(static_generation=STALE_GENERATION))
    assert excinfo.value.code == "static_generation_sha_mismatch"


# ---------------------------------------------------------------------------
# NEGATIVE CONTROL B -- stale SW / static identity
# ---------------------------------------------------------------------------
def test_runtime_sw_not_matching_packaged_static_is_rejected():
    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_release_identity(**_identity(runtime_sw_version="v239-something-older"))
    assert excinfo.value.code == "runtime_sw_version_mismatch"


def test_generation_sw_label_not_matching_manifest_is_rejected():
    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_release_identity(
            **_identity(static_generation=f"20260902-231917-{GOOD_SHA[:8]}-v239-old")
        )
    assert excinfo.value.code == "static_generation_sw_mismatch"


def test_current_symlink_alias_is_not_an_identity():
    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_release_identity(**_identity(static_generation="current"))
    assert excinfo.value.code == "invalid_static_generation"


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "not-a-generation", "20260902-231917-ZZZZZZZZ-v240", None, 12345],
)
def test_malformed_generation_names_fail_closed(bad):
    with pytest.raises(ReleaseIdentityError):
        verify_release_identity(**_identity(static_generation=bad))


@pytest.mark.parametrize("field", ["backend_source_sha", "image_source_sha", "static_source_sha"])
def test_malformed_source_shas_fail_closed(field):
    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_release_identity(**_identity(**{field: "not-a-sha"}))
    assert excinfo.value.code == "invalid_source_sha"


# ---------------------------------------------------------------------------
# Documented exception escape hatch
# ---------------------------------------------------------------------------
def test_divergence_passes_only_when_explicitly_documented():
    """An immutable exception must be named, never inferred."""

    with pytest.raises(ReleaseIdentityError):
        verify_release_identity(**_identity(static_source_sha=STALE_SHA,
                                            static_generation=STALE_GENERATION))

    report = verify_release_identity(
        **_identity(static_source_sha=STALE_SHA, static_generation=STALE_GENERATION),
        documented_exceptions=["static_source_sha"],
    )
    assert report["ok"] is True
    assert report["documented_exceptions"] == ["static_source_sha"]


# ---------------------------------------------------------------------------
# Manifest-shaped entry point (what the pipeline actually holds)
# ---------------------------------------------------------------------------
def test_manifest_wrapper_accepts_a_coherent_pair():
    report = verify_from_manifests(
        image_manifest={"release_git_sha": GOOD_SHA, "oci_revision": GOOD_SHA},
        static_manifest={
            "release_git_sha": GOOD_SHA,
            "static_generation_id": GOOD_GENERATION,
            "service_worker_version": SW,
        },
        runtime_sw_version=SW,
    )
    assert report["ok"] is True


def test_manifest_wrapper_rejects_the_production_incident_shape():
    """image=959c3842 + static=4bfaf834 -- the shape that shipped."""

    with pytest.raises(ReleaseIdentityError) as excinfo:
        verify_from_manifests(
            image_manifest={"release_git_sha": GOOD_SHA, "oci_revision": GOOD_SHA},
            static_manifest={
                "release_git_sha": STALE_SHA,
                "static_generation_id": STALE_GENERATION,
                "service_worker_version": SW,
            },
            runtime_sw_version=SW,
        )
    assert excinfo.value.code == "release_identity_mismatch"


# ---------------------------------------------------------------------------
# The gap this module closes is real
# ---------------------------------------------------------------------------
def test_existing_verifier_does_not_compare_image_to_static():
    """Documents why this lock is necessary rather than duplicative.

    ``verify-production-release.ps1`` compares the deployed image revision to the
    IMAGE release manifest only. If it ever grows a genuine cross-check against
    the live static generation's ``release_git_sha``, this test should be updated
    to point at that instead.
    """

    verifier = (REPO_ROOT / "scripts" / "release" / "verify-production-release.ps1")
    text = verifier.read_text(encoding="utf-8", errors="replace")
    assert "release_git_sha" in text, "sanity: the verifier does handle image identity"
    assert "static_generation_id" not in text, (
        "verify-production-release.ps1 now reads the static generation identity; "
        "fold this cross-artifact lock into it and update this test"
    )
