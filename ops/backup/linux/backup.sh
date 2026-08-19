#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
ROOT="${GO_ODYSSEY_BACKUP_ROOT:-/opt/go-odyssey}"
CFG="$ROOT/ops/backup/backup-config.json"
STAMP="$(date -u +%F_%H%M%S)"
DATE_PATH="$(date -u +%F)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
CURRENT_MODE=""
CURRENT_SUMMARY=""

export CLOUDSDK_CONFIG="${CLOUDSDK_CONFIG:-/home/ubuntu/.config/gcloud}"
export HOME="${HOME:-/home/ubuntu}"

if [ ! -f "$CFG" ]; then
  echo "Missing config: $CFG" >&2
  exit 1
fi

GCS_BUCKET="$(python3 - <<'PY' "$CFG"
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(cfg["gcs_bucket"])
PY
)"

OCI_BOOT_VOLUME_ID="$(python3 - <<'PY' "$CFG"
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(cfg["oci_boot_volume_id"])
PY
)"

OCI_COMPARTMENT_ID="$(python3 - <<'PY' "$CFG"
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(cfg["oci_compartment_id"])
PY
)"

OCI_WEEKLY_RETENTION="$(python3 - <<'PY' "$CFG"
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(cfg["oci_weekly_retention"])
PY
)"

OCI_PREFIX="$(python3 - <<'PY' "$CFG"
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(cfg["oci_backup_prefix"])
PY
)"

notify_backup() {
  local subject="$1"
  local body="$2"
  python3 - <<'PY' "$subject" "$body"
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

subject = sys.argv[1]
body = sys.argv[2]
host = os.environ.get("BACKUP_SMTP_HOST", "").strip()
to_raw = os.environ.get("BACKUP_NOTIFY_TO", "").strip()
if not host or not to_raw:
    sys.exit(0)

port = int(os.environ.get("BACKUP_SMTP_PORT", "587"))
user = os.environ.get("BACKUP_SMTP_USER", "").strip()
password = os.environ.get("BACKUP_SMTP_PASS", "")
sender = os.environ.get("BACKUP_SMTP_FROM", "").strip() or user or "godokro-backup@localhost"
use_starttls = os.environ.get("BACKUP_SMTP_STARTTLS", "1").lower() not in ("0", "false", "no")
recipients = [addr.strip() for addr in to_raw.split(",") if addr.strip()]
if not recipients:
    sys.exit(0)

msg = EmailMessage()
msg["Subject"] = subject
msg["From"] = sender
msg["To"] = ", ".join(recipients)
msg.set_content(body)

context = ssl.create_default_context()
with smtplib.SMTP(host, port, timeout=30) as smtp:
    smtp.ehlo()
    if use_starttls:
        smtp.starttls(context=context)
        smtp.ehlo()
    if user:
        smtp.login(user, password)
    smtp.send_message(msg)
PY
}

notify_failure() {
  local exit_code="$1"
  local line_no="$2"
  local msg="Godokro backup failed

Mode: ${CURRENT_MODE:-unknown}
Exit code: $exit_code
Line: $line_no
Host: $(hostname)
Time (UTC): $(date -u +'%F %T')
"
  if [ -n "${CURRENT_SUMMARY:-}" ]; then
    msg="$msg
Last summary:
$CURRENT_SUMMARY"
  fi
  notify_backup "[Godokro] backup failed" "$msg" || true
}

trap 'notify_failure $? $LINENO' ERR

case "$MODE" in
  daily)
    CURRENT_MODE="daily"
    DB_DUMP="$WORKDIR/godokro-go_odyssey-$STAMP.dump"
    SITE_TAR="$WORKDIR/godokro-site-files-$STAMP.tar.gz"
    MANIFEST="$WORKDIR/manifest.json"

    bash "$ROOT/ops/backup/remote/make_db_dump.sh" "$DB_DUMP"
    bash "$ROOT/ops/backup/remote/make_site_archive.sh" "$SITE_TAR"

    python3 - <<'PY' "$MANIFEST" "$STAMP" "$DB_DUMP" "$SITE_TAR" "$OCI_BOOT_VOLUME_ID" "$ROOT"
import hashlib
import json
import sys
from pathlib import Path

manifest_path, stamp, db_dump, site_tar, boot_volume_id, root = sys.argv[1:7]
files = []
for path in [db_dump, site_tar]:
    p = Path(path)
    files.append({
        "name": p.name,
        "size_bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    })
Path(manifest_path).write_text(json.dumps({
    "created_at": stamp,
    "root": root,
    "oci_boot_volume_id": boot_volume_id,
    "files": files,
}, ensure_ascii=False, indent=2), encoding="utf-8")
PY

    gsutil_cmd="$(command -v gcloud)"
    "$gsutil_cmd" storage cp "$MANIFEST" "$DB_DUMP" "$SITE_TAR" "gs://$GCS_BUCKET/daily/$DATE_PATH/$STAMP/"
    CURRENT_SUMMARY="Uploaded to gs://$GCS_BUCKET/daily/$DATE_PATH/$STAMP/
Manifest: $(basename "$MANIFEST")
Database dump: $(basename "$DB_DUMP")
Site archive: $(basename "$SITE_TAR")"
    notify_backup "[Godokro] daily backup success" "Godokro daily backup completed successfully.

${CURRENT_SUMMARY}
Host: $(hostname)
Time (UTC): $(date -u +'%F %T')
" || true
    ;;
  weekly)
    CURRENT_MODE="weekly"
    weekly_result="$(python3 - <<'PY' "$OCI_BOOT_VOLUME_ID" "$OCI_COMPARTMENT_ID" "$OCI_WEEKLY_RETENTION" "$OCI_PREFIX" "$STAMP"
import json
import sys
import time
from datetime import datetime, timezone

import oci

boot_volume_id = sys.argv[1]
compartment_id = sys.argv[2]
retention = int(sys.argv[3])
prefix = sys.argv[4]
stamp = sys.argv[5]

config = oci.config.from_file()
block = oci.core.BlockstorageClient(config)

backups = oci.pagination.list_call_get_all_results(
    block.list_boot_volume_backups,
    compartment_id=compartment_id,
    boot_volume_id=boot_volume_id,
).data

backup_type = "FULL" if len(backups) == 0 else "INCREMENTAL"
display_name = f"{prefix}-{stamp}"

details = oci.core.models.CreateBootVolumeBackupDetails(
    boot_volume_id=boot_volume_id,
    display_name=display_name,
    type=backup_type,
)
created = block.create_boot_volume_backup(details).data
print(json.dumps({
    "created_backup_id": created.id,
    "display_name": created.display_name,
    "state": created.lifecycle_state,
    "type": backup_type,
}, ensure_ascii=False))

for _ in range(120):
    current = block.get_boot_volume_backup(created.id).data
    if current.lifecycle_state in ("AVAILABLE", "FAILED", "TERMINATED"):
        print(json.dumps({
            "final_state": current.lifecycle_state,
            "backup_id": current.id,
        }, ensure_ascii=False))
        break
    time.sleep(30)
else:
    raise SystemExit("Timed out waiting for boot volume backup")

backups = sorted(
    oci.pagination.list_call_get_all_results(
        block.list_boot_volume_backups,
        compartment_id=compartment_id,
        boot_volume_id=boot_volume_id,
    ).data,
    key=lambda b: b.time_created,
    reverse=True,
)

for old in backups[retention:]:
    if old.lifecycle_state in ("AVAILABLE", "FAILED"):
        block.delete_boot_volume_backup(old.id)
        print(json.dumps({
            "deleted_backup_id": old.id,
            "display_name": old.display_name,
        }, ensure_ascii=False))
PY
    )"
    CURRENT_SUMMARY="$weekly_result"
    notify_backup "[Godokro] weekly snapshot success" "Godokro weekly OCI boot volume backup completed successfully.

$weekly_result
Host: $(hostname)
Time (UTC): $(date -u +'%F %T')
" || true
    ;;
  *)
    echo "usage: $0 daily|weekly" >&2
    exit 1
    ;;
esac
