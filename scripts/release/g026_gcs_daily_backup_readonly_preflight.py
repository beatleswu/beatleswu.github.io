"""G026 corrected Daily backup gate (Google Cloud Storage, NOT OCI).

Pure offline, fail-closed dependency-injected provider. Has NO gcloud CLI,
Google SDK, OCI SDK, SSH, network, upload, delete, or live credential access.
Cloud read-only checks never prove storage.objects.create or restorability.
"""
from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ReadOnlyGcsCheck:
    verdict: str
    reason: str
    request_count: int
    read_authorized: bool = False
    object_create_authorized: bool = False
    consistent_postgres_restore_proven: bool = False
    production_release_authorized: bool = False


def _safe_bucket(value: str) -> bool:
    return (isinstance(value, str)
            and 3 <= len(value) <= 63
            and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]*[a-z0-9]", value))
            and ".." not in value
            and not value.startswith("goog")
            and not value.startswith("gs://"))


def bucket_metadata_readonly(*, provider: Any, bucket: str) -> ReadOnlyGcsCheck:
    """Strict READ ONLY get_bucket_metadata; don't infer upload rights."""
    if not _safe_bucket(bucket):
        return ReadOnlyGcsCheck("HOLD", "INVALID_BUCKET_SCOPE", 0)
    read = getattr(provider, "get_bucket_metadata", None)
    if not callable(read):
        return ReadOnlyGcsCheck("HOLD", "READONLY_PROVIDER_UNAVAILABLE", 0)
    try:
        data = read(bucket=bucket)
        if not isinstance(data, dict) or data.get("exists") is not True:
            return ReadOnlyGcsCheck("HOLD", "UNVERIFIED_BUCKET_METADATA", 1)
        return ReadOnlyGcsCheck("READONLY_GCS_METADATA_PASS",
                                "GCS_OBJECT_CREATE_AND_RESTORE_UNVERIFIED",
                                1, read_authorized=True)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(exc, "status", None)
        reason = {
            401: "GCS_AUTHENTICATION_401",
            403: "GCS_PERMISSION_DENIED_403",
            404: "GCS_BUCKET_SCOPE_OR_VISIBILITY_404",
            429: "GCS_THROTTLED_429",
        }.get(status, "GCS_READONLY_API_UNKNOWN_ERROR")
        return ReadOnlyGcsCheck("HOLD", reason, 1)


def release_backup_gate(*, daily_gcs_upload_verified: bool,
                        uploaded_manifest_sha_matches: bool,
                        production_postgres_consistent_backup_verified: bool,
                        independent_postgres_restore_verified: bool,
                        boot_volume_recovery_verified: bool,
                        static_runtime_sha_pair_admitted: bool,
                        owner_go_merge: bool,
                        owner_go_deploy: bool) -> bool:
    """All independent criteria required. Querying an existing bucket isn't one."""
    return all((
        daily_gcs_upload_verified, uploaded_manifest_sha_matches,
        production_postgres_consistent_backup_verified,
        independent_postgres_restore_verified, boot_volume_recovery_verified,
        static_runtime_sha_pair_admitted, owner_go_merge, owner_go_deploy))
