# Production backup pipeline

The tracked files in this directory are the reviewed source for the
Production backup runtime:

- `linux/backup.sh` performs the existing daily PostgreSQL/site archive and
  weekly OCI flows.
- `remote/make_db_dump.sh` creates the existing PostgreSQL custom-format dump.
- `remote/make_site_archive.sh` creates the site archive. Protected rollback
  directories `.e9-rollout-backups` and `.shadow-judging-backups` are excluded
  recursively.
- `systemd/` contains the unit and timer contract currently used on the host.

`backup-config.json` and `/etc/godokro-backup.env` remain host-provisioned.
They contain environment-specific identifiers or credentials and are never
committed. `backup-config.example.json` documents the required non-secret
shape.

The production host must receive these files through
`install-production-backup-scripts.ps1`. That tool requires an explicit source
commit SHA and `GO_BACKUP_PROPAGATION` owner gate, stages files remotely,
verifies hashes and shell syntax, preserves the previous runtime copy, and
activates only after all checks pass. It never changes application/static
deployments, the database, or backup data.

This change does not alter backup retention, compression, upload, or OCI
semantics. A service rerun remains a separate operational approval.
