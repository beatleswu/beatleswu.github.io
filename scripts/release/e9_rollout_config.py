#!/usr/bin/env python3
"""Fail-closed, four-key-only E9 rollout configuration helper.

This helper is intentionally usable with a temporary local fixture in tests,
but production execution is driven by set-e9-rollout.ps1 over SSH stdin.  It
never prints or returns any non-E9 .env value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from pathlib import Path

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows test host
    fcntl = None
    import msvcrt


ALLOWED_KEYS = (
    "E9_ROLLOUT_GLOBAL_ENABLED",
    "E9_ROLLOUT_ADMIN_ENABLED",
    "E9_ROLLOUT_SCOPE",
    "E9_ROLLOUT_FLAGS",
)
FLAGS = "e9Shell,e9TopHud,e9LeftNav,e9RightCards,e9BottomDock,e9WorldStage"
TARGET_MARKER = "e9-rollout-governed-backup-v1"
ASSIGNMENT = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<sep>[ \t]*=[ \t]*)(?P<value>.*?)(?P<newline>\r?\n?)$")


class ConfigError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_lines(raw: bytes):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("env is not valid UTF-8") from exc
    if "\x00" in text:
        raise ConfigError("env contains NUL")
    lines = text.splitlines(keepends=True)
    entries = {}
    for index, line in enumerate(lines):
        match = ASSIGNMENT.match(line)
        if not match:
            continue
        key = match.group("key")
        if key in entries:
            raise ConfigError(f"duplicate assignment: {key}")
        entries[key] = (index, match)
    unknown = [key for key in entries if key.startswith("E9_ROLLOUT_") and key not in (*ALLOWED_KEYS, "E9_ROLLOUT_ALLOWLIST")]
    if unknown:
        raise ConfigError("unknown_e9_key")
    return text, lines, entries


def e9_values(entries):
    return {key: entries[key][1].group("value") if key in entries else None for key in ALLOWED_KEYS}


def effective(values, allowlist):
    scope = values["E9_ROLLOUT_SCOPE"] or "admin_only"
    global_enabled = (values["E9_ROLLOUT_GLOBAL_ENABLED"] or "").strip().lower() == "true"
    admin_enabled = (values["E9_ROLLOUT_ADMIN_ENABLED"] or "").strip().lower() == "true"
    flags = values["E9_ROLLOUT_FLAGS"] or FLAGS
    valid = (
        scope in {"admin_only", "named_allowlist"}
        and not (scope == "admin_only" and allowlist.strip())
        and flags == FLAGS
        and (values["E9_ROLLOUT_GLOBAL_ENABLED"] in {None, "true", "false"})
        and (values["E9_ROLLOUT_ADMIN_ENABLED"] in {None, "true", "false"})
    )
    if not valid:
        return {"state": "invalid_fail_closed", "global": False, "admin": False, "scope": "admin_only", "flags": FLAGS}
    state = "admin_only" if global_enabled and admin_enabled and scope == "admin_only" else "disabled"
    return {"state": state, "global": global_enabled, "admin": admin_enabled, "scope": scope, "flags": flags}


def read_state(env_path: Path):
    if not env_path.is_file() or env_path.is_symlink():
        raise ConfigError("env_path_missing_or_not_regular_file")
    raw = env_path.read_bytes()
    text, lines, entries = parse_lines(raw)
    values = e9_values(entries)
    allowlist = entries.get("E9_ROLLOUT_ALLOWLIST")
    allowlist_value = allowlist[1].group("value") if allowlist else ""
    return raw, text, lines, entries, values, effective(values, allowlist_value)


def safe_snapshot(env_path: Path):
    info = env_path.stat()
    return {"uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode), "sha256": sha256_file(env_path)}


def safe_output(values, eff, *, operation, desired=None, backup=None, changed=None):
    def value_state(value):
        return "UNSET — APPLICATION DEFAULT APPLIES" if value is None else f"EXPLICIT VALUE: {value}"

    result = {
        "operation": operation,
        "values": {key: value_state(values[key]) for key in ALLOWED_KEYS},
        "effective": eff,
    }
    if desired is not None:
        result["desired"] = desired
        result["keys_to_add"] = [key for key in ALLOWED_KEYS if values[key] is None and desired[key] is not None]
        result["keys_to_update"] = [key for key in ALLOWED_KEYS if values[key] is not None and values[key] != desired[key]]
        result["keys_unchanged"] = [key for key in ALLOWED_KEYS if values[key] == desired[key]]
    if backup:
        result["backup"] = backup
    if changed is not None:
        result["changed_keys"] = changed
    return result


def desired_for(operation):
    if operation == "enable-admin-only":
        return {key: value for key, value in zip(ALLOWED_KEYS, ("true", "true", "admin_only", FLAGS))}
    if operation == "disable":
        return {key: value for key, value in zip(ALLOWED_KEYS, ("false", "false", "admin_only", FLAGS))}
    return None


def render(lines, entries, desired):
    output = list(lines)
    changed = []
    for key in ALLOWED_KEYS:
        if key in entries:
            index, match = entries[key]
            newline = match.group("newline") or ("\n" if output[index].endswith("\n") else "")
            output[index] = f"{match.group('indent')}{key}{match.group('sep')}{desired[key]}{newline}"
            if match.group("value") != desired[key]:
                changed.append(key)
        else:
            if output and not output[-1].endswith(("\n", "\r")):
                output[-1] += "\n"
            output.append(f"{key}={desired[key]}\n")
            changed.append(key)
    return "".join(output).encode("utf-8"), changed


def verify_only_e9_changed(before: bytes, after: bytes, env_path: Path, desired):
    _before_text, before_lines, before_entries = parse_lines(before)
    _after_text, after_lines, after_entries = parse_lines(after)
    for line_before, line_after in zip(before_lines, after_lines):
        mb = ASSIGNMENT.match(line_before)
        ma = ASSIGNMENT.match(line_after)
        kb = mb.group("key") if mb else None
        ka = ma.group("key") if ma else None
        if kb != ka and kb not in ALLOWED_KEYS:
            raise ConfigError("non-E9 line identity changed")
        if kb not in ALLOWED_KEYS and line_before != line_after:
            # Adding the first new assignment must terminate a legacy final
            # line that lacked a newline; the non-newline bytes remain exact.
            if not (line_before.rstrip("\r\n") == line_after.rstrip("\r\n") and not line_before.endswith(("\n", "\r"))):
                raise ConfigError("non-E9 line content changed")
    for key, value in desired.items():
        if key not in after_entries or after_entries[key][1].group("value") != value:
            raise ConfigError(f"written value failed validation: {key}")


def backup(env_path: Path, backup_dir: Path, snapshot):
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    base = backup_dir / f"{stamp}-{snapshot['sha256'][:12]}"
    path = base.with_suffix(".env")
    meta_path = base.with_suffix(".json")
    counter = 0
    while path.exists() or meta_path.exists():
        counter += 1
        path = backup_dir / f"{stamp}-{snapshot['sha256'][:12]}-{counter}.env"
        meta_path = path.with_suffix(".json")
    try:
        shutil.copyfile(env_path, path)
        if hasattr(os, "chown"):
            os.chown(path, snapshot["uid"], snapshot["gid"])
        os.chmod(path, snapshot["mode"])
        metadata = {"marker": TARGET_MARKER, "env_path": str(env_path), "backup_path": str(path), "backup_sha256": sha256_file(path), "original": snapshot}
        meta_path.write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")
        if hasattr(os, "chown"):
            os.chown(meta_path, snapshot["uid"], snapshot["gid"])
        os.chmod(meta_path, 0o600)
    except Exception:
        path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        raise
    return {"id": path.stem, "path": str(path), "sha256": metadata["backup_sha256"]}


def atomic_replace(env_path: Path, data: bytes, snapshot):
    fd, temp_name = tempfile.mkstemp(prefix=".e9-rollout-", dir=str(env_path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if hasattr(os, "chown"):
            os.chown(temp_path, snapshot["uid"], snapshot["gid"])
        os.chmod(temp_path, snapshot["mode"])
        os.replace(temp_path, env_path)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(env_path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temp_path.unlink(missing_ok=True)


def audit(audit_path: Path, record):
    audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(audit_path, 0o600)


def latest_backup(backup_dir: Path, env_path: Path):
    candidates = []
    for meta_path in backup_dir.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("marker") == TARGET_MARKER and meta.get("env_path") == str(env_path):
                backup_path = Path(meta["backup_path"])
                if backup_path.is_file() and sha256_file(backup_path) == meta.get("backup_sha256"):
                    candidates.append((meta_path.stat().st_mtime, meta, backup_path))
        except (OSError, ValueError, KeyError):
            continue
    if not candidates:
        raise ConfigError("no_valid_governed_backup")
    return max(candidates, key=lambda item: item[0])[1], max(candidates, key=lambda item: item[0])[2]


def acquire_lock(handle):
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConfigError("lock_unavailable") from exc
        return
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        raise ConfigError("lock_unavailable") from exc


def run(args):
    env_path = Path(args.env_path)
    backup_dir = Path(args.backup_dir)
    audit_path = Path(args.audit_path)
    lock_path = Path(args.lock_path)
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_handle:
        if lock_path.stat().st_size == 0:
            lock_handle.write("0")
            lock_handle.flush()
        lock_handle.seek(0)
        acquire_lock(lock_handle)
        raw, _text, lines, entries, values, eff = read_state(env_path)
        if args.operation in {"status", "dry-run"}:
            desired = desired_for(args.desired) if args.operation == "dry-run" else None
            result = safe_output(values, eff, operation=args.operation, desired=desired)
            if args.operation == "dry-run":
                result.update({"restart_plan": ["app", "scheduler", "nginx"], "backup_plan": "timestamped governed backup before atomic write"})
            print(json.dumps(result, sort_keys=True))
            return
        if args.operation == "rollback":
            meta, source = latest_backup(backup_dir, env_path)
            snapshot = safe_snapshot(env_path)
            data = source.read_bytes()
            atomic_replace(env_path, data, meta["original"])
            audit(audit_path, {"marker": TARGET_MARKER, "operation": "rollback", "backup_id": source.stem, "restored_sha256": sha256_file(env_path), "timestamp": int(time.time())})
            print(json.dumps({"operation": "rollback", "backup_id": source.stem, "restored_sha256": sha256_file(env_path), "previous_sha256": snapshot["sha256"]}, sort_keys=True))
            return
        desired = desired_for(args.operation)
        if desired is None:
            raise ConfigError("unsupported_operation")
        if eff["state"] == "invalid_fail_closed" and args.operation == "enable-admin-only":
            raise ConfigError("current_e9_configuration_invalid")
        snapshot = safe_snapshot(env_path)
        backup_info = backup(env_path, backup_dir, snapshot)
        after, changed = render(lines, entries, desired)
        verify_only_e9_changed(raw, after, env_path, desired)
        atomic_replace(env_path, after, snapshot)
        audit(audit_path, {"marker": TARGET_MARKER, "operation": args.operation, "backup_id": backup_info["id"], "changed_keys": changed, "before_sha256": snapshot["sha256"], "after_sha256": sha256_file(env_path), "timestamp": int(time.time())})
        print(json.dumps({"operation": args.operation, "backup": backup_info, "changed_keys": changed, "after_sha256": sha256_file(env_path), "service_recreate_required": True}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--operation", choices=("status", "dry-run", "enable-admin-only", "disable", "rollback"), required=True)
    parser.add_argument("--desired", choices=("enable-admin-only", "disable"))
    parser.add_argument("--env-path", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--audit-path", required=True)
    parser.add_argument("--lock-path", required=True)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        print(json.dumps({"status": "fail_closed", "reason": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
