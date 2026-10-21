"""G026 Oracle daily is GCS, unlike independent weekly OCI boot snapshots."""
import pytest
from scripts.release.g026_gcs_daily_backup_readonly_preflight import (
    bucket_metadata_readonly,release_backup_gate,
)

GOOD="godokoro-daily-backup-test"
class GcsProbeError(Exception):
    def __init__(self, code):
        self.status_code=code
        super().__init__("REDACTED_SENSITIVE_BUCKET_AND_ACTOR")

_UNSPECIFIED = object()


class FakeGcsReadOnly:
    def __init__(self, code=None, response=_UNSPECIFIED):
        self.code=code
        self.response={"exists":True} if response is _UNSPECIFIED else response
        self.reads=[]
        self.writes=[]
        self.deletes=[]
    def get_bucket_metadata(self, *, bucket):
        self.reads.append(bucket)
        if self.code is not None:
            raise GcsProbeError(self.code)
        return self.response
    def upload_object(self, **kwargs):
        self.writes.append(kwargs)
        raise AssertionError("Read-only preflight attempted to write")
    def delete_object(self, **kwargs):
        self.deletes.append(kwargs)
        raise AssertionError("Read-only preflight attempted to delete")

@pytest.mark.parametrize("code,reason",[
    (401,"GCS_AUTHENTICATION_401"),
    (403,"GCS_PERMISSION_DENIED_403"),
    (404,"GCS_BUCKET_SCOPE_OR_VISIBILITY_404"),
    (429,"GCS_THROTTLED_429"),
    (500,"GCS_READONLY_API_UNKNOWN_ERROR"),
])
def test_403_and_other_cloud_auth_errors_fail_closed_without_writes(code,reason):
    provider=FakeGcsReadOnly(code=code)
    r=bucket_metadata_readonly(provider=provider,bucket=GOOD)
    assert r.verdict=="HOLD" and r.reason==reason
    assert r.request_count==1 and provider.reads==[GOOD]
    assert provider.writes==provider.deletes==[]
    assert not r.object_create_authorized and not r.production_release_authorized

@pytest.mark.parametrize("bucket",[
    "", "ab", "gs://godokoro-daily-backup-test",
    "../other-project", "goog-reserved-prefix", "has spaces",
    "INVALID_UPPERCASE", "a"*64, "x..hidden", "example/dir"
])
def test_reject_invalid_or_unsafe_bucket_scope_with_zero_provider_calls(bucket):
    provider=FakeGcsReadOnly()
    r=bucket_metadata_readonly(provider=provider,bucket=bucket)
    assert r.verdict=="HOLD" and r.reason=="INVALID_BUCKET_SCOPE"
    assert r.request_count==0
    assert not provider.reads and not provider.writes and not provider.deletes

def test_metadata_access_success_does_not_prove_upload_or_restore():
    provider=FakeGcsReadOnly()
    r=bucket_metadata_readonly(provider=provider,bucket=GOOD)
    assert r.verdict=="READONLY_GCS_METADATA_PASS"
    assert r.reason=="GCS_OBJECT_CREATE_AND_RESTORE_UNVERIFIED"
    assert r.read_authorized and not r.object_create_authorized
    assert not r.consistent_postgres_restore_proven and not r.production_release_authorized
    assert provider.reads==[GOOD] and not provider.writes and not provider.deletes

def test_missing_readonly_provider_fails_closed():
    r=bucket_metadata_readonly(provider=object(),bucket=GOOD)
    assert r.verdict=="HOLD" and r.reason=="READONLY_PROVIDER_UNAVAILABLE"
    assert r.request_count==0

@pytest.mark.parametrize("value",[
    None, {}, {"exists":False}, {"objects_count":123}, "yes",
])
def test_malformed_or_nonexistent_metadata_not_accepted(value):
    r=bucket_metadata_readonly(provider=FakeGcsReadOnly(response=value),bucket=GOOD)
    assert r.verdict=="HOLD"
    assert r.reason=="UNVERIFIED_BUCKET_METADATA"

FLAGS=dict(daily_gcs_upload_verified=True,uploaded_manifest_sha_matches=True,
           production_postgres_consistent_backup_verified=True,
           independent_postgres_restore_verified=True,
           boot_volume_recovery_verified=True,
           static_runtime_sha_pair_admitted=True,
           owner_go_merge=True,owner_go_deploy=True)

@pytest.mark.parametrize("flag",list(FLAGS))
def test_every_independent_backup_or_owner_release_gate_is_required(flag):
    values=FLAGS.copy()
    values[flag]=False
    assert release_backup_gate(**values) is False

def test_all_flags_have_to_be_explicitly_verified():
    assert release_backup_gate(**FLAGS) is True

def test_cloud_sdk_not_imported_and_cannot_write_from_readonly_preflight():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    code=(root/"scripts/release/g026_gcs_daily_backup_readonly_preflight.py").read_text(encoding="utf8")
    assert "import google.cloud" not in code
    assert "import oci" not in code
    assert "subprocess" not in code
    assert "urllib" not in code
    assert "upload_object(" not in code and "delete_object(" not in code
