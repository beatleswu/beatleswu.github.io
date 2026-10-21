"""G025: production backup HTTP403 FAIL CLOSED; offline fake OCI provider only."""
import pytest
from scripts.release.g025_oci_backup_readonly_preflight import (
    diagnose_readonly_list, permit_production_backup_gate,
)

COMP="ocid1.compartment.oc1..syntheticcompartment1"
VOLUME="ocid1.bootvolume.oc1.phx.syntheticvolume1"

class SimulatedCloudApiError(Exception):
    def __init__(self, status):
        self.status=status
        super().__init__("redacted")

class FakeReadOnlyOci:
    def __init__(self, status=None, result=None):
        self.status=status
        self.result=[] if result is None else result
        self.requests=[]
        self.create_attempts=0
        self.delete_attempts=0
    def list_boot_volume_backups(self, *, compartment_id, boot_volume_id):
        self.requests.append((compartment_id,boot_volume_id))
        if self.status is not None:
            raise SimulatedCloudApiError(self.status)
        return self.result
    def create_boot_volume_backup(self, **kwargs):
        self.create_attempts+=1
        raise AssertionError("preflight must never create backup")
    def delete_boot_volume_backup(self, **kwargs):
        self.delete_attempts+=1
        raise AssertionError("preflight must never delete backup")

@pytest.mark.parametrize("status,reason",[
    (403,"OCI_IAM_LIST_FORBIDDEN_403"),
    (401,"OCI_AUTHENTICATION_401"),
    (404,"OCI_SCOPE_OR_VISIBILITY_404"),
    (429,"OCI_THROTTLED_429"),
    (500,"OCI_BACKUP_READONLY_API_UNVERIFIED"),
])
def test_oci_failure_never_mutates_cloud(status,reason):
    provider=FakeReadOnlyOci(status=status)
    result=diagnose_readonly_list(provider=provider,
        compartment_id=COMP,boot_volume_id=VOLUME)
    assert result.verdict=="HOLD" and result.reason==reason
    assert result.request_count==len(provider.requests)==1
    assert provider.create_attempts==provider.delete_attempts==0
    assert not result.oracle_create_permission_proven
    assert not result.player_pg_restore_proven and not result.permits_go_deploy

def test_readonly_list_success_never_implies_oci_create_or_pg_backup():
    provider=FakeReadOnlyOci(result=[{"fake":"synthetic"}])
    r=diagnose_readonly_list(provider=provider,compartment_id=COMP,boot_volume_id=VOLUME)
    assert r.verdict=="READONLY_LIST_PASS"
    assert r.reason=="CREATE_AND_RESTORE_UNVERIFIED"
    assert r.request_count==1 and len(provider.requests)==1
    assert not r.oracle_create_permission_proven and not r.player_pg_restore_proven
    assert not r.permits_go_deploy
    assert provider.create_attempts==provider.delete_attempts==0

@pytest.mark.parametrize("comp,volume,reason",[
    ("",VOLUME,"INVALID_COMPARTMENT_SCOPE"),
    ("ocid1.user.oc1..syntheticuser123456",VOLUME,"INVALID_COMPARTMENT_SCOPE"),
    (COMP,"","INVALID_BOOT_VOLUME_SCOPE"),
    (COMP,"ocid1.compartment.oc1..syntheticnotavolume1","INVALID_BOOT_VOLUME_SCOPE"),
])
def test_untrusted_scopes_do_not_make_any_cloud_calls(comp,volume,reason):
    p=FakeReadOnlyOci()
    r=diagnose_readonly_list(provider=p,compartment_id=comp,boot_volume_id=volume)
    assert r.verdict=="HOLD" and r.reason==reason and r.request_count==0
    assert p.requests==[] and p.create_attempts==p.delete_attempts==0

def test_unavailable_provider_closed_without_exposure():
    r=diagnose_readonly_list(provider=object(),compartment_id=COMP,boot_volume_id=VOLUME)
    assert r.verdict=="HOLD" and r.reason=="READONLY_PROVIDER_UNAVAILABLE"
    assert r.request_count==0

def test_malformed_backend_response_is_hold_and_has_no_write():
    p=FakeReadOnlyOci(result={"malformed":"not a list"})
    r=diagnose_readonly_list(provider=p,compartment_id=COMP,boot_volume_id=VOLUME)
    assert r.verdict=="HOLD" and r.reason=="INVALID_LIST_RESPONSE"
    assert p.create_attempts==p.delete_attempts==0

def test_current_oracle_daily_failed_means_release_denied():
    assert not permit_production_backup_gate(daily_backup_healthy=False,
        consistent_pg_backup_verified=True,independent_pg_restore_verified=True,
        boot_volume_backup_verified=True,runtime_static_pair_admitted=True,
        owner_deploy_approval=True)

@pytest.mark.parametrize("missing",[
 "daily_backup_healthy","consistent_pg_backup_verified",
 "independent_pg_restore_verified","boot_volume_backup_verified",
 "runtime_static_pair_admitted","owner_deploy_approval",
])
def test_each_independent_release_gate_required(missing):
    values=dict(daily_backup_healthy=True,consistent_pg_backup_verified=True,
        independent_pg_restore_verified=True,boot_volume_backup_verified=True,
        runtime_static_pair_admitted=True,owner_deploy_approval=True)
    values[missing]=False
    assert not permit_production_backup_gate(**values)

def test_only_all_explicitly_verified_boolean_gates_would_allow():
    assert permit_production_backup_gate(daily_backup_healthy=True,
        consistent_pg_backup_verified=True,independent_pg_restore_verified=True,
        boot_volume_backup_verified=True,runtime_static_pair_admitted=True,
        owner_deploy_approval=True)
