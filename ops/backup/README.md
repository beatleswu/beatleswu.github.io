# Production backup pipeline

The tracked files in this directory are the reviewed source for the
Production backup runtime:

- `linux/backup.sh` performs the existing daily PostgreSQL/site archive and
  weekly OCI flows.
- `remote/make_db_dump.sh` creates the existing PostgreSQL custom-format dump.
- `remote/make_site_archive.sh` creates the site archive. See
  "Protected-runtime exclusion contract" below.
- `systemd/` contains the unit and timer contract currently used on the host.

`backup-config.json` and `/etc/godokro-backup.env` remain host-provisioned.
They contain environment-specific identifiers or credentials and are never
committed. `backup-config.example.json` documents only the non-secret keys
consumed by the current runtime. Daily GCS retention is not implemented by
this source; there is no `gcs_retention_days` setting here.

The production host must receive these files through
`install-production-backup-scripts.ps1`. That tool requires an explicit source
commit SHA and `GO_BACKUP_PROPAGATION` owner gate, stages files remotely,
verifies hashes and shell syntax, preserves the previous runtime copy, and
activates only after all checks pass. It never changes application/static
deployments, the database, or backup data.

This change does not alter backup retention, compression, upload, or OCI
semantics. A service rerun remains a separate operational approval.

## Protected-runtime exclusion contract

The backup runs as the unprivileged `ubuntu` user. Several operational tools
write root-owned artifacts under `/opt/go-odyssey` that this user cannot read,
and GNU tar exits non-zero when it cannot open a member. These excluded paths
are explicitly classified as operational/audit artifacts and are not part of
the canonical site-archive restore payload, so `make_site_archive.sh` excludes
them explicitly:

| Path | Written by |
| --- | --- |
| `./.e9-rollout-backups` | E9 rollout rollback snapshots |
| `./.shadow-judging-backups` | Shadow-judging rollback snapshots |
| `./releases/.shadow-judging-audit` | `scripts/release/set-shadow-judging.ps1` |
| `./releases/e9-rollout-audit.jsonl` | `scripts/release/set-e9-rollout.ps1` |
| `./reward-operations/2026-W28/grant-result.json` | root-run grant path |
| `./reward-operations/w29-c866f611-20260720T055453Z-c001bcd0` | owner-gated grant wrapper operation dir |

`reward-operations` is deliberately **not** excluded as a whole tree. Its
period-keyed directories (e.g. `2026-W28`) also hold backup-user-readable
snapshot and preview evidence that must stay in the archive; only the
artifacts produced by the owner-gated root grant path are dropped.

The reward entries are deliberately **literal, not patterned**. Operation
directory names come from a per-wrapper `ValidateSet` literal, so there is no
convention a wildcard could safely predict, and a speculative pattern would
silently drop reward content nobody has inspected. When a future grant writes a
new protected artifact, the preflight below names it within seconds and it is
added to this contract on review -- an extra reviewed line is a smaller cost
than an archive that quietly loses evidence.

The pipeline stays fail-closed. `tar --ignore-failed-read` is not used, tar is
not run as root, and protected artifact permissions are never changed -- a
backup that silently omits unreadable files must not be reported as success.

Because the exclusion list is a contract rather than a permission heuristic, a
newly introduced root-owned artifact would otherwise surface only after tar had
spent minutes building a multi-GB archive. `make_site_archive.sh` therefore runs
a preflight, as the same unprivileged user, that enumerates unreadable paths not
covered by the list and aborts before tar, printing the exact paths. Extending
the contract is a deliberate, owner-reviewed step; the preflight makes the need
for it obvious in seconds instead of minutes.
