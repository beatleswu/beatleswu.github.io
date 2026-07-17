#!/usr/bin/env python3
"""Governed, single-key Shadow Judging configuration helper.

The helper edits only ``SHADOW_JUDGING_ENABLED``.  Production orchestration
is performed by ``set-shadow-judging.ps1`` over bounded SSH, while tests use
only synthetic temporary configuration files.  Output and audit records are
sanitized: no unrelated environment key or value is ever returned.
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


ALLOWED_KEY = "SHADOW_JUDGING_ENABLED"
OWNER_GATES = {
    "enable": "GO_ENABLE_SHADOW",
    "disable": "GO_DISABLE_SHADOW",
    "rollback": "GO_SHADOW_ROLLBACK",
}
TARGET_MARKER = "shadow-judging-governed-backup-v1"
MAX_ENV_BYTES = 1024 * 1024
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})
ASSIGNMENT = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<sep>[ \t]*=[ \t]*)(?P<value>.*?)(?P<newline>\r?\n?)$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHADOW_PREFIX_RE = re.compile(r"^(?:export[ \t]+)?SHADOW_JUDGING_[A-Za-z0-9_]*\b")


class ConfigError(RuntimeError):
    """Expected fail-closed configuration error with a sanitized reason."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_lines(raw: bytes):
    if len(raw) > MAX_ENV_BYTES:
        raise ConfigError("env_exceeds_bounded_size")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("env_not_valid_utf8") from exc
    if "\x00" in text:
        raise ConfigError("env_contains_nul")

    lines = text.splitlines(keepends=True)
    target = None
    for index, line in enumerate(lines):
        match = ASSIGNMENT.match(line)
        if not match:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and SHADOW_PREFIX_RE.match(stripped):
                raise ConfigError("malformed_shadow_judging_assignment")
            continue
        key = match.group("key")
        if key == ALLOWED_KEY:
            if target is not None:
                raise ConfigError("duplicate_shadow_judging_assignment")
            target = (index, match)
        elif key.startswith("SHADOW_JUDGING_"):
            raise ConfigError("unknown_shadow_judging_key")
    return text, lines, target


def effective(value):
    if value is None:
        return {
            "configured": False,
            "state": "unset_default_disabled",
            "enabled": False,
            "canonical_value": "false",
        }
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return {
            "configured": True,
            "state": "enabled",
            "enabled": True,
            "canonical_value": "true",
            "canonical_assignment": value == "true",
        }
    if normalized in FALSE_VALUES:
        return {
            "configured": True,
            "state": "disabled",
            "enabled": False,
            "canonical_value": "false",
            "canonical_assignment": value == "false",
        }
    return {
        "configured": True,
        "state": "invalid_fail_closed",
        "enabled": False,
        "canonical_value": "false",
        "canonical_assignment": False,
    }


def read_state(env_path: Path):
    if not env_path.is_file() or env_path.is_symlink():
        raise ConfigError("env_path_missing_or_not_regular_file")
    info = env_path.stat()
    if info.st_size > MAX_ENV_BYTES:
        raise ConfigError("env_exceeds_bounded_size")
    raw = env_path.read_bytes()
    text, lines, target = parse_lines(raw)
    value = target[1].group("value") if target is not None else None
    return raw, text, lines, target, value, effective(value)


def safe_snapshot(env_path: Path):
    info = env_path.stat()
    return {
        "uid": int(getattr(info, "st_uid", 0)),
        "gid": int(getattr(info, "st_gid", 0)),
        "mode": stat.S_IMODE(info.st_mode),
        "sha256": sha256_file(env_path),
    }


def _value_state(value, state):
    if value is None:
        return "UNSET_DEFAULT_FALSE"
    if state["state"] == "invalid_fail_closed":
        return "EXPLICIT_INVALID_FAIL_CLOSED"
    if state.get("canonical_assignment"):
        return "EXPLICIT_TRUE" if state["enabled"] else "EXPLICIT_FALSE"
    return "EXPLICIT_NONCANONICAL_TRUE" if state["enabled"] else "EXPLICIT_NONCANONICAL_FALSE"


def safe_output(value, state, *, operation, desired=None):
    result = {
        "operation": operation,
        "key": ALLOWED_KEY,
        "value_state": _value_state(value, state),
        "effective": state,
        "mutation_performed": False,
    }
    if desired is not None:
        desired_value = desired_for(desired)
        if value is None:
            change = "add"
        elif value == desired_value:
            change = "unchanged"
        else:
            change = "update"
        result.update(
            {
                "desired": desired,
                "desired_value": desired_value,
                "change": change,
                "execution_allowed": not (
                    desired == "enable" and state["state"] == "invalid_fail_closed"
                ),
                "service_recreate_required": change != "unchanged",
                "backup_plan": "governed backup before atomic replacement",
            }
        )
    return result


def desired_for(operation: str) -> str:
    if operation == "enable":
        return "true"
    if operation == "disable":
        return "false"
    raise ConfigError("unsupported_operation")


def render(lines, target, desired_value: str):
    output = list(lines)
    changed = True
    if target is not None:
        index, match = target
        newline = match.group("newline")
        output[index] = (
            f"{match.group('indent')}{ALLOWED_KEY}{match.group('sep')}"
            f"{desired_value}{newline}"
        )
        changed = match.group("value") != desired_value
    else:
        newline = "\r\n" if any(line.endswith("\r\n") for line in output) else "\n"
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += newline
        output.append(f"{ALLOWED_KEY}={desired_value}{newline}")
    return "".join(output).encode("utf-8"), changed


def _without_target(lines):
    output = []
    for line in lines:
        match = ASSIGNMENT.match(line)
        if match is None or match.group("key") != ALLOWED_KEY:
            output.append(line)
    return "".join(output)


def verify_only_target_changed(before: bytes, after: bytes, desired_value: str):
    _before_text, before_lines, before_target = parse_lines(before)
    _after_text, after_lines, after_target = parse_lines(after)
    if after_target is None or after_target[1].group("value") != desired_value:
        raise ConfigError("written_value_failed_validation")

    before_other = _without_target(before_lines)
    after_other = _without_target(after_lines)
    if before_target is None and before_other and not before_other.endswith(("\n", "\r")):
        newline = "\r\n" if any(line.endswith("\r\n") for line in after_lines) else "\n"
        before_other += newline
    if before_other != after_other:
        raise ConfigError("non_shadow_judging_content_changed")


def _ensure_secure_directory(path: Path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir() or path.is_symlink():
        raise ConfigError("governed_directory_invalid")
    os.chmod(path, 0o700)


def _apply_owner(path: Path, snapshot):
    if hasattr(os, "chown"):
        os.chown(path, snapshot["uid"], snapshot["gid"])


def _write_metadata(meta_path: Path, metadata, snapshot):
    fd, temp_name = tempfile.mkstemp(prefix=".shadow-meta-", dir=str(meta_path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _apply_owner(temp_path, snapshot)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, meta_path)
    finally:
        temp_path.unlink(missing_ok=True)


def backup(env_path: Path, backup_dir: Path, snapshot):
    _ensure_secure_directory(backup_dir)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    base_id = f"{stamp}-{snapshot['sha256'][:12]}"
    backup_id = base_id
    counter = 0
    while (backup_dir / f"{backup_id}.env").exists() or (backup_dir / f"{backup_id}.json").exists():
        counter += 1
        backup_id = f"{base_id}-{counter}"

    backup_path = backup_dir / f"{backup_id}.env"
    meta_path = backup_dir / f"{backup_id}.json"
    try:
        with env_path.open("rb") as source, backup_path.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        _apply_owner(backup_path, snapshot)
        os.chmod(backup_path, snapshot["mode"])
        backup_sha = sha256_file(backup_path)
        metadata = {
            "marker": TARGET_MARKER,
            "backup_id": backup_id,
            "created_at_ns": time.time_ns(),
            "env_path": str(env_path),
            "backup_path": str(backup_path),
            "backup_sha256": backup_sha,
            "original": snapshot,
        }
        _write_metadata(meta_path, metadata, snapshot)
    except Exception:
        backup_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        raise
    return {"id": backup_id, "sha256": backup_sha}


def _valid_snapshot(value) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("uid"), int)
        and value["uid"] >= 0
        and isinstance(value.get("gid"), int)
        and value["gid"] >= 0
        and isinstance(value.get("mode"), int)
        and 0 <= value["mode"] <= 0o7777
        and isinstance(value.get("sha256"), str)
        and bool(SHA256_RE.fullmatch(value["sha256"]))
    )


def latest_backup(backup_dir: Path, env_path: Path):
    if not backup_dir.is_dir() or backup_dir.is_symlink():
        raise ConfigError("no_valid_governed_backup")
    candidates = []
    for meta_path in backup_dir.glob("*.json"):
        if meta_path.is_symlink() or not meta_path.is_file():
            continue
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            backup_id = metadata.get("backup_id")
            if not isinstance(backup_id, str) or not backup_id:
                continue
            expected_backup = backup_dir / f"{backup_id}.env"
            if meta_path != backup_dir / f"{backup_id}.json":
                continue
            if metadata.get("marker") != TARGET_MARKER:
                continue
            if metadata.get("env_path") != str(env_path):
                continue
            if metadata.get("backup_path") != str(expected_backup):
                continue
            if not _valid_snapshot(metadata.get("original")):
                continue
            if not isinstance(metadata.get("created_at_ns"), int):
                continue
            if not expected_backup.is_file() or expected_backup.is_symlink():
                continue
            expected_resolved = expected_backup.resolve(strict=True)
            if expected_resolved.parent != backup_dir.resolve(strict=True):
                continue
            digest = sha256_file(expected_backup)
            if digest != metadata.get("backup_sha256"):
                continue
            if digest != metadata["original"]["sha256"]:
                continue
            candidates.append((metadata["created_at_ns"], backup_id, metadata, expected_backup))
        except (OSError, ValueError, TypeError):
            continue
    if not candidates:
        raise ConfigError("no_valid_governed_backup")
    _created, _backup_id, metadata, backup_path = max(candidates, key=lambda item: (item[0], item[1]))
    return metadata, backup_path


def atomic_replace(env_path: Path, data: bytes, snapshot):
    fd, temp_name = tempfile.mkstemp(prefix=".shadow-judging-", dir=str(env_path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _apply_owner(temp_path, snapshot)
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
    _ensure_secure_directory(audit_path.parent)
    if audit_path.exists() and (audit_path.is_symlink() or not audit_path.is_file()):
        raise ConfigError("audit_path_invalid")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(audit_path, flags, 0o600)
    except OSError as exc:
        raise ConfigError("audit_path_invalid") from exc
    with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ConfigError("audit_path_invalid")
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(audit_path, 0o600)


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


def open_lock(lock_path: Path):
    parent = lock_path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ConfigError("lock_directory_invalid")
    if lock_path.exists() and (lock_path.is_symlink() or not lock_path.is_file()):
        raise ConfigError("lock_path_invalid")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ConfigError("lock_path_invalid") from exc
    handle = os.fdopen(descriptor, "r+")
    try:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ConfigError("lock_path_invalid")
        os.chmod(lock_path, 0o600)
        return handle
    except Exception:
        handle.close()
        raise


def validate_mutation_gate(args):
    if not args.execute:
        raise ConfigError("mutation_requires_execute")
    expected = OWNER_GATES.get(args.operation)
    if expected is None or args.owner_gate != expected:
        raise ConfigError("owner_gate_mismatch")


def _restore_or_raise(env_path: Path, backup_path: Path, snapshot, reason: str):
    try:
        atomic_replace(env_path, backup_path.read_bytes(), snapshot)
    except Exception as restore_error:
        raise ConfigError(f"{reason}_restore_failed") from restore_error
    raise ConfigError(f"{reason}_restored")


def run(args):
    if args.operation in {"enable", "disable", "rollback"}:
        validate_mutation_gate(args)

    env_path = Path(args.env_path)
    backup_dir = Path(args.backup_dir)
    audit_path = Path(args.audit_path)
    lock_path = Path(args.lock_path)
    if env_path.is_symlink() or not env_path.is_file():
        raise ConfigError("env_path_missing_or_not_regular_file")
    if backup_dir.is_symlink():
        raise ConfigError("governed_directory_invalid")
    if audit_path.is_symlink():
        raise ConfigError("audit_path_invalid")

    with open_lock(lock_path) as lock_handle:
        if lock_path.stat().st_size == 0:
            lock_handle.write("0")
            lock_handle.flush()
        lock_handle.seek(0)
        acquire_lock(lock_handle)

        env_path = env_path.resolve(strict=True)
        backup_dir = backup_dir.resolve(strict=False)
        audit_path = audit_path.resolve(strict=False)
        raw, _text, lines, target, value, state = read_state(env_path)

        if args.operation == "status":
            return safe_output(value, state, operation="status")
        if args.operation == "dry-run":
            return safe_output(value, state, operation="dry-run", desired=args.desired)

        if args.operation == "rollback":
            metadata, source = latest_backup(backup_dir, env_path)
            snapshot = safe_snapshot(env_path)
            rollback_backup = backup(env_path, backup_dir, snapshot)
            try:
                restored_data = source.read_bytes()
                parse_lines(restored_data)
                atomic_replace(env_path, restored_data, metadata["original"])
                _raw, _text, _lines, _target, restored_value, restored_state = read_state(env_path)
                audit(
                    audit_path,
                    {
                        "marker": TARGET_MARKER,
                        "operation": "rollback",
                        "backup_id": metadata["backup_id"],
                        "rollback_backup_id": rollback_backup["id"],
                        "previous_sha256": snapshot["sha256"],
                        "restored_sha256": sha256_file(env_path),
                        "effective_state": restored_state["state"],
                        "timestamp": int(time.time()),
                    },
                )
            except Exception:
                _restore_or_raise(env_path, backup_dir / f"{rollback_backup['id']}.env", snapshot, "rollback_failed")
            return {
                "operation": "rollback",
                "key": ALLOWED_KEY,
                "backup_id": metadata["backup_id"],
                "rollback_backup_id": rollback_backup["id"],
                "previous_sha256": snapshot["sha256"],
                "restored_sha256": sha256_file(env_path),
                "value_state": _value_state(restored_value, restored_state),
                "effective": restored_state,
                "mutation_performed": True,
                "service_recreate_required": True,
            }

        desired_value = desired_for(args.operation)
        if state["state"] == "invalid_fail_closed" and args.operation == "enable":
            raise ConfigError("current_shadow_judging_configuration_invalid")

        snapshot = safe_snapshot(env_path)
        backup_info = backup(env_path, backup_dir, snapshot)
        backup_path = backup_dir / f"{backup_info['id']}.env"
        after, changed = render(lines, target, desired_value)
        verify_only_target_changed(raw, after, desired_value)
        try:
            atomic_replace(env_path, after, snapshot)
            _raw, _text, _lines, written_target, written_value, written_state = read_state(env_path)
            if written_target is None or written_value != desired_value:
                raise ConfigError("post_write_validation_failed")
            audit(
                audit_path,
                {
                    "marker": TARGET_MARKER,
                    "operation": args.operation,
                    "backup_id": backup_info["id"],
                    "changed": changed,
                    "before_sha256": snapshot["sha256"],
                    "after_sha256": sha256_file(env_path),
                    "effective_state": written_state["state"],
                    "timestamp": int(time.time()),
                },
            )
        except Exception:
            _restore_or_raise(env_path, backup_path, snapshot, "mutation_failed")

        return {
            "operation": args.operation,
            "key": ALLOWED_KEY,
            "backup": backup_info,
            "changed": changed,
            "after_sha256": sha256_file(env_path),
            "value_state": _value_state(written_value, written_state),
            "effective": written_state,
            "mutation_performed": True,
            "service_recreate_required": True,
        }


def build_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--operation",
        choices=("status", "dry-run", "enable", "disable", "rollback"),
        required=True,
    )
    parser.add_argument("--desired", choices=("enable", "disable"), default="enable")
    parser.add_argument("--env-path", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--audit-path", required=True)
    parser.add_argument("--lock-path", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--owner-gate")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except ConfigError as exc:
        print(json.dumps({"status": "fail_closed", "reason": str(exc)}, sort_keys=True))
        return 1
    except Exception as exc:  # unexpected errors must not leak paths or config values
        print(
            json.dumps(
                {
                    "status": "fail_closed",
                    "reason": f"internal_error_{exc.__class__.__name__}",
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
