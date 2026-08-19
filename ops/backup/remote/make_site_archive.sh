#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: make_site_archive.sh OUTPUT_FILE" >&2
  exit 1
fi

out="$1"
root="${GO_ODYSSEY_BACKUP_ROOT:-/opt/go-odyssey}"

cd "$root"
tar -czf "$out" \
  --exclude=.git \
  --exclude=.venv \
  --exclude=venv \
  --exclude=__pycache__ \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.log' \
  --exclude='*.tmp' \
  --exclude='*.bak*' \
  --exclude='*.tar.gz' \
  --exclude='katago_cache.db' \
  --exclude='katago_review_exports' \
  --exclude='analysis_logs' \
  --exclude='test_solve' \
  --exclude='outputs' \
  --exclude='_backup_*' \
  --exclude='SGF題庫_backup_before_katago_sync_*' \
  --exclude='./.e9-rollout-backups/***' \
  --exclude='./.shadow-judging-backups/***' \
  .
