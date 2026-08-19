#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: make_site_archive.sh OUTPUT_FILE" >&2
  exit 1
fi

out="$1"
root="${GO_ODYSSEY_BACKUP_ROOT:-/opt/go-odyssey}"

# Canonical archive exclusions.
#
# This single list drives both the unreadable-path preflight and tar itself so
# the two can never drift apart. Entries below the weight-reduction block are
# the protected-runtime contract: root-owned operational artifacts the backup
# user deliberately cannot read. They are operational/audit evidence, not
# restorable application state -- the authoritative reward and rollout state
# lives in PostgreSQL and is captured by the database dump.
#
# reward-operations is excluded per-artifact rather than as a whole tree: the
# period-keyed directories (e.g. 2026-W28) also hold backup-user-readable
# snapshot/preview evidence that must stay in the archive. Only the artifacts
# written by the owner-gated root grant path are dropped.
#
# These entries are deliberately literal. Operation directory names come from a
# per-wrapper ValidateSet literal, so there is no convention a pattern could
# safely predict, and a speculative wildcard would silently drop reward content
# nobody has inspected. A protected artifact that appears under a new name is
# caught by the preflight below in seconds and added here on review.
EXCLUDES=(
  '.git'
  '.venv'
  'venv'
  '__pycache__'
  '*.pyc'
  '*.pyo'
  '*.log'
  '*.tmp'
  '*.bak*'
  '*.tar.gz'
  'katago_cache.db'
  'katago_review_exports'
  'analysis_logs'
  'test_solve'
  'outputs'
  '_backup_*'
  'SGF題庫_backup_before_katago_sync_*'
  './.e9-rollout-backups'
  './.shadow-judging-backups'
  './releases/.shadow-judging-audit'
  './releases/e9-rollout-audit.jsonl'
  './reward-operations/2026-W28/grant-result.json'
  './reward-operations/w29-c866f611-20260720T055453Z-c001bcd0'
)

cd "$root"

# Return 0 when PATH is already covered by the canonical exclusions above.
# Mirrors tar's unanchored matching: an entry matches an exact path, anything
# beneath it, or any single path component.
_is_excluded() {
  local path="$1"
  local pattern
  for pattern in "${EXCLUDES[@]}"; do
    case "$path" in
      "$pattern" | "$pattern"/*) return 0 ;;
    esac
    # shellcheck disable=SC2254
    case "$path" in
      $pattern | $pattern/*) return 0 ;;
    esac
    # shellcheck disable=SC2254
    case "${path##*/}" in
      $pattern) return 0 ;;
    esac
  done
  return 1
}

# Fail-closed preflight.
#
# tar stays fail-closed on its own; this only moves the failure to the front of
# the run and names the offending paths, so a newly introduced root-owned
# artifact costs seconds instead of the minutes it takes to build a multi-GB
# archive that is then thrown away. It never suppresses an unreadable path --
# anything not already covered by EXCLUDES aborts the archive.
if find . -maxdepth 0 -readable >/dev/null 2>&1; then
  uncovered=()
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    if ! _is_excluded "$candidate"; then
      uncovered+=("$candidate")
    fi
  done < <(find . ! -readable -print 2>/dev/null | LC_ALL=C sort)

  if [ "${#uncovered[@]}" -ne 0 ]; then
    echo "make_site_archive.sh: unreadable paths are not covered by the canonical exclusions:" >&2
    printf '  %s\n' "${uncovered[@]}" >&2
    echo "Refusing to build an archive that would silently omit them." >&2
    echo "Extend the EXCLUDES contract deliberately, or restore read access." >&2
    exit 1
  fi
else
  echo "make_site_archive.sh: find(1) lacks -readable; skipping preflight (tar remains fail-closed)." >&2
fi

tar_args=()
for pattern in "${EXCLUDES[@]}"; do
  tar_args+=("--exclude=$pattern")
done

tar -czf "$out" "${tar_args[@]}" .
