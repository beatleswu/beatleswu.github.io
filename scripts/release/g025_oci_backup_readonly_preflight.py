"""G025 fail-closed Oracle Boot Volume Backup IAM diagnostic.

This is an OFFLINE, dependency-injected, READ-ONLY preflight contract, not an
Oracle permission change, not an OCI backup and not a deployment authorization.
A caller must supply a separately approved read-only provider. The preflight
never starts, deletes or modifies any OCI backup or reads production user data.
"""
from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class Preflight:
    verdict: str
    reason: str
    request_count: int
    oracle_create_permission_proven: bool = False
    player_pg_restore_proven: bool = False
    permits_go_deploy: bool = False


def _valid_ocid(value: str, kind: str) -> bool:
    return (isinstance(value, str)
            and 18 <= len(value) <= 240
            and bool(re.fullmatch(r"ocid1[.]" + re.escape(kind) +
                                  r"[.]oc[0-9]+[.][A-Za-z0-9._-]+", value)))


def diagnose_readonly_list(*, provider: Any, compartment_id: str,
                           boot_volume_id: str) -> Preflight:
    """Only read/list; error categories avoid exporting OCIDs or credentials.

    List permission is NOT sufficient to create or restore a boot-volume backup.
    """
    if not _valid_ocid(compartment_id, "compartment"):
        return Preflight("HOLD", "INVALID_COMPARTMENT_SCOPE", 0)
    if not _valid_ocid(boot_volume_id, "bootvolume"):
        return Preflight("HOLD", "INVALID_BOOT_VOLUME_SCOPE", 0)
    method = getattr(provider, "list_boot_volume_backups", None)
    if not callable(method):
        return Preflight("HOLD", "READONLY_PROVIDER_UNAVAILABLE", 0)
    try:
        rows = method(compartment_id=compartment_id,
                      boot_volume_id=boot_volume_id)
        if rows is None or not isinstance(rows, (tuple, list)):
            return Preflight("HOLD", "INVALID_LIST_RESPONSE", 1)
        return Preflight("READONLY_LIST_PASS", "CREATE_AND_RESTORE_UNVERIFIED", 1)
    except Exception as err:
        code = getattr(err, "status", None)
        if code == 403:
            reason = "OCI_IAM_LIST_FORBIDDEN_403"
        elif code == 401:
            reason = "OCI_AUTHENTICATION_401"
        elif code == 404:
            reason = "OCI_SCOPE_OR_VISIBILITY_404"
        elif code == 429:
            reason = "OCI_THROTTLED_429"
        else:
            reason = "OCI_BACKUP_READONLY_API_UNVERIFIED"
        return Preflight("HOLD", reason, 1)


def permit_production_backup_gate(*, daily_backup_healthy: bool,
                                   consistent_pg_backup_verified: bool,
                                   independent_pg_restore_verified: bool,
                                   boot_volume_backup_verified: bool,
                                   runtime_static_pair_admitted: bool,
                                   owner_deploy_approval: bool) -> bool:
    """Separate release gate; diagnostic success cannot grant authorization."""
    return all((daily_backup_healthy, consistent_pg_backup_verified,
                independent_pg_restore_verified, boot_volume_backup_verified,
                runtime_static_pair_admitted, owner_deploy_approval))
