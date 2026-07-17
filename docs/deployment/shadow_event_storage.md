# Shadow Event Storage and Dashboard Read Contract

Status: implementation contract for SGF Engine V1 closure (2026-07-17)

Shadow storage is diagnostic-only. Any lock, serialization, rotation,
retention, disk, or read failure must leave the Legacy answer response and all
player-facing side effects unchanged.

## Write-side bounds

`shadow_event_storage.py` owns the active JSONL file and rotated files.
Configuration is bounded and malformed values fail closed to safe defaults:

| Setting | Default | Allowed bound |
|---|---:|---:|
| `SHADOW_EVENTS_ROTATE_SIZE_BYTES` | 64 MiB | 64 KiB to 1 GiB |
| `SHADOW_EVENTS_RETAINED_ROTATED_FILES` | 8 | 1 to 64 |
| `SHADOW_EVENTS_LOCK_TIMEOUT_MS` | 50 ms | 1 ms to 5 s |
| encoded event record | at most 64 KiB | fixed |

Before an append would cross the rotation threshold, the non-empty active
file is moved with `os.replace` to a collision-free owned name. The writer
then creates/appends the new active file. Threads and processes share a
bounded advisory lock; a timeout drops only the Shadow event and increments a
process-local diagnostic counter.

Retention deletes oldest owned rotations only. It never deletes the active
file, lock file, or an unrelated neighbor. Retained data is bounded by both
count and bytes. With `R` as rotate size, `N` as retained count, and `E` as the
64 KiB maximum encoded record, the normal maximum is:

```text
active current-file overshoot (at most E) + (R * N)
```

The active file normally remains at or below `R`; the `E` term documents the
single-record boundary and conservative disk reservation. Rotation or
retention failure restores the previous active file when possible and never
propagates into an answer route. A partial append is truncated back to its
pre-write size while the cross-process lock remains held.

## Aggregate dashboard window

`GET /api/admin/shadow/dashboard` reads, in order:

1. active file, newest records first;
2. owned rotations, newest file first and newest records first.

The first occurrence of a non-empty `event_id` wins, so a copied boundary
record is counted once. Both `shadow-v3` and `shadow-v4` are accepted; missing
v4 fields remain unknown (`null`), never fabricated `false` evidence.
`/api/admin/shadow/dashboard/recent` intentionally remains current-file-only.

Default aggregate limits are 8 MiB, 50,000 valid events, 250 ms, a 64 KiB
streaming read chunk, and a documented 64 MiB working-memory budget. Maximum
configurable limits are 64 MiB, 250,000 events, and 5 seconds. Malformed read
settings fall back to the defaults.

Every aggregate response publishes:

```text
window_complete
files_considered
files_scanned
events_scanned
bytes_scanned
scan_truncated
duplicate_events_skipped
scan_errors
read_budget
```

If any cap, file error, or partial file window prevents a complete scan,
`window_complete=false` and `scan_truncated=true`. In that state the dashboard
reports `agreement_window.rate=null`; it must not present a partial-window rate
as a complete observation window.

## Governed operator pull boundary

The canonical release layout records the in-container event path as
`shadow_event_log_path`. This repository currently has no approved
download/pull operator for Shadow event files: the shared release tooling
supports bounded SSH commands and uploads, but not a governed download.

Therefore an operator must not improvise `ssh`, `scp`, `docker exec`, direct
container copies, or protected environment edits. A Production pull requires
an owner-approved DEPLOY-GOV-1 change that adds an allowlist-only bounded
download command with a declared byte cap, exact layout path, destination,
checksum, audit record, and retention/privacy handling. No Production pull or
remote inspection was performed by this task.
