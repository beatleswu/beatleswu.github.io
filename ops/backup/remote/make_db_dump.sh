#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: make_db_dump.sh OUTPUT_FILE" >&2
  exit 1
fi

out="$1"
mkdir -p "$(dirname "$out")"

docker exec go-odyssey-postgres pg_dump -U go -d go_odyssey -Fc > "$out"
