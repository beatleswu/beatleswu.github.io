# G026 | Daily GCS 403 corrected branch investigation / offline guard

Date: 2026-10-21 (Asia/Taipei). Scope: isolated local branch only.
Status: G026 diagnostic development and negative-test phase; **not** a repaired production backup or a release approval.

## Superseding finding (G025 remains preserved as historical evidence)
The *daily* `godokro-backup-daily.service` branch creates a database dump,
site tarball, and manifest, then uses `gcloud` to upload to **Google Cloud
Storage (GCS)**. The 2026-10-19/20/21 daily jobs returned HTTP 403 with
`gcloud` / `upload` markers and matching sanitized error-line fingerprint
`731c6e869207`. G025's attribution of this daily failure to the OCI
Boot Volume IAM path is superseded. Do not change OCI IAM to repair this
GCS error.

The *weekly* `godokro-backup-weekly.service` branch uses the OCI
BlockstorageClient. Read-only OCI list/get confirmed four AVAILABLE
weekly boot-volume snapshots (9/27, 10/4, 10/11, 10/18).
These do not prove a consistent Player PostgreSQL backup or an independent
database restore. Script SHA256:
`30490db056e3dde120df3684d6586c17a31a98039ce16646d9acec2a11256264`.

## Observed versus unresolved
- Read-only gcloud inspection found two configured identities, one active;
  its real identity remains confidential and has not been proven to be the
  effective upload principal in the failed systemd job.
- Read-only Google Cloud Logging filtered denial query returned zero matches.
  No exact GCS permission, denied principal, bucket scope, or audit method has
  been independently established. A zero-result query is not authorization
  evidence and does not imply the HTTP 403 was resolved.
- No credential, secret, original cloud object path, player row, or full
  production log is included with the sanitized evidence.
- Do not try upload/delete or grant broad permissions as a probe.
  A separately authorized operator must inspect the actual job identity,
  precise GCS error reason, destination scope, policy and audit configuration,
  then execute a narrow permission fix and a controlled end-to-end backup
  verification. Effective IAM is not guessed here.

## Code and repeatable negative evidence
- `scripts/release/g026_gcs_daily_backup_readonly_preflight.py`:
  dependency-injected OFFLINE fake-provider metadata gate; no SDK, CLI,
  authentication, network access or write method. A successful metadata read
  does **not** prove `storage.objects.create`, cloud upload, or restorability.
- `tests/test_g026_daily_gcs_backup_offline_preflight.py`:
  invalid bucket, 401/403/404/429/500, malformed metadata, read-only
  success and eight independent release-gate negative checks.
- Direct run: `python -m pytest -q
  tests/test_g026_daily_gcs_backup_offline_preflight.py`
  => **32 passed**.
- Combined G025 + G026 focused regression:
  `python -m pytest -q
  tests/test_g026_daily_gcs_backup_offline_preflight.py
  tests/test_g025_backup_audit_evidence_contract.py
  tests/test_g025_backup_iam_403_readonly_gate.py`
  => **57 passed**.
- All pass counts are this local execution, not a cloud remediation test.
- Original sanitized receipt directory:
  `D:\go-odyssey-g026-oci-audit-20261021`, especially
  `G026_BACKUP_DAILY_WEEKLY_BRANCH_MAP_20261021.json`,
  `G026_DAILY_GCS_AUTH_READONLY_20261021.json`,
  `G026_GCS_CLI_READONLY_STATUS_20261021.json`,
  `G026_GCS_CLOUD_AUDIT_READONLY_20261021.json`,
  `G026_BOOTBACKUP_READONLY_OPS_MATRIX_20261021.json`.

## Boundary, formal release and next engineering gate
G026 stages and checks are isolated; the current Product candidate and
G010 RC3 clean, official GitHub master, Oracle prod service, IAM, DB
and live players are out of scope. No `GO_MERGE`, no `GO_DEPLOY`.
Production release remains **NO-GO** until successful ongoing daily backup,
object manifest SHA readback, production consistent PG backup and
independent restore evidence, weekly backup recovery validation, the
approved Runtime/Static source pair, governed production migration,
Owner physical iPad Safari UAT, and separate Owner authorizations.
No claim of precise GCS root IAM cause or of restored backups is made.

V4 independent Goal Loop status is not changed by this G026 work.
Historical G021-G025 test and build evidence remains intact and must
not be regenerated merely for handoff.
