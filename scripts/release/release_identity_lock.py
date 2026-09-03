"""Cross-artifact release identity lock.

The invalid Production pattern this exists to make impossible:

    new backend image (959c3842) + stale static generation (4bfaf834)

Every existing check was individually correct and still let that through, because
each script validates only its OWN artifact against its OWN ``-ExpectedGitSha``:

* ``deploy-release-image.ps1`` asserts the image manifest matches its expected SHA;
* ``deploy-static-release.ps1`` asserts the static manifest matches its expected SHA;
* ``verify-production-release.ps1`` compares the deployed image revision against the
  image release manifest.

Nothing compared the image identity to the static identity. If the two scripts are
run with different SHAs -- or the static step is skipped entirely -- every gate stays
green while Production serves mismatched halves.

This module supplies the missing cross-artifact assertion as a pure function so it
can be called from tooling and tested directly. It reads no secrets, performs no
I/O, and reaches no network: callers pass in the identities they already hold.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHORT_SHA_PATTERN = re.compile(r"^[0-9a-f]{8}$")
# <YYYYMMDD>-<HHMMSS>-<short-sha>-<sw-version-label>
GENERATION_PATTERN = re.compile(r"^(\d{8})-(\d{6})-([0-9a-f]{8})-(.+)$")


class ReleaseIdentityError(ValueError):
    """A release candidate whose artifacts do not share one identity."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def parse_static_generation(generation: Any) -> dict[str, str]:
    """Split a static generation directory name into its identity parts."""

    if not isinstance(generation, str) or not generation.strip():
        raise ReleaseIdentityError(
            "invalid_static_generation", "static generation must be a non-empty string"
        )
    value = generation.strip()
    if value == "current":
        raise ReleaseIdentityError(
            "invalid_static_generation",
            "'current' is a symlink alias, not a resolved generation identity",
        )
    match = GENERATION_PATTERN.fullmatch(value)
    if not match:
        raise ReleaseIdentityError(
            "invalid_static_generation", f"unrecognised generation name: {value}"
        )
    return {
        "date": match.group(1),
        "time": match.group(2),
        "short_sha": match.group(3),
        "sw_version": match.group(4),
    }


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value.strip().lower()):
        raise ReleaseIdentityError(
            "invalid_source_sha", f"{label} must be a full 40-hex commit sha"
        )
    return value.strip().lower()


def verify_release_identity(
    *,
    backend_source_sha: Any,
    image_source_sha: Any,
    image_revision_label: Any,
    static_source_sha: Any,
    static_generation: Any,
    static_sw_version: Any,
    runtime_sw_version: Any,
    documented_exceptions: Sequence[str] = (),
) -> dict[str, Any]:
    """Fail closed unless every release artifact resolves to one source identity.

    Returns a report on success. Raises :class:`ReleaseIdentityError` otherwise.

    ``documented_exceptions`` is the only escape hatch and must name explicit
    artifact keys; an undocumented divergence is always a hard failure.
    """

    backend = _require_sha(backend_source_sha, "backend_source_sha")
    image = _require_sha(image_source_sha, "image_source_sha")
    static = _require_sha(static_source_sha, "static_source_sha")
    revision = _require_sha(image_revision_label, "image_revision_label")

    exceptions = {str(e).strip() for e in documented_exceptions if str(e).strip()}
    mismatches: list[str] = []

    if image != backend:
        mismatches.append("image_source_sha")
    if revision != backend:
        mismatches.append("image_revision_label")
    if static != backend:
        mismatches.append("static_source_sha")

    undocumented = [m for m in mismatches if m not in exceptions]
    if undocumented:
        raise ReleaseIdentityError(
            "release_identity_mismatch",
            "artifacts disagree with backend_source_sha "
            f"{backend}: {', '.join(sorted(undocumented))}",
        )

    parts = parse_static_generation(static_generation)
    if parts["short_sha"] != static[:8]:
        raise ReleaseIdentityError(
            "static_generation_sha_mismatch",
            f"generation names {parts['short_sha']} but its manifest records {static[:8]}",
        )

    if not isinstance(static_sw_version, str) or not static_sw_version.strip():
        raise ReleaseIdentityError(
            "invalid_sw_version", "static_sw_version must be a non-empty string"
        )
    if parts["sw_version"] != static_sw_version.strip():
        raise ReleaseIdentityError(
            "static_generation_sw_mismatch",
            f"generation names sw '{parts['sw_version']}' but the manifest records "
            f"'{static_sw_version.strip()}'",
        )
    if str(runtime_sw_version).strip() != static_sw_version.strip():
        raise ReleaseIdentityError(
            "runtime_sw_version_mismatch",
            f"served service worker '{runtime_sw_version}' does not match the packaged "
            f"static '{static_sw_version}'",
        )

    return {
        "ok": True,
        "release_source_sha": backend,
        "short_sha": backend[:8],
        "static_generation": static_generation.strip(),
        "sw_version": static_sw_version.strip(),
        "documented_exceptions": sorted(exceptions),
    }


def verify_from_manifests(
    *,
    image_manifest: Mapping[str, Any],
    static_manifest: Mapping[str, Any],
    runtime_sw_version: Any,
    backend_source_sha: Any = None,
    documented_exceptions: Sequence[str] = (),
) -> dict[str, Any]:
    """Convenience wrapper over the two governed manifests the pipeline produces."""

    backend = backend_source_sha or image_manifest.get("release_git_sha")
    return verify_release_identity(
        backend_source_sha=backend,
        image_source_sha=image_manifest.get("release_git_sha"),
        image_revision_label=image_manifest.get("oci_revision")
        or image_manifest.get("release_git_sha"),
        static_source_sha=static_manifest.get("release_git_sha"),
        static_generation=static_manifest.get("static_generation_id"),
        static_sw_version=static_manifest.get("service_worker_version"),
        runtime_sw_version=runtime_sw_version,
        documented_exceptions=documented_exceptions,
    )
