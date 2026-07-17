"""Bounded, multi-process-safe JSONL storage for Shadow Judging events.

The public writer is deliberately failure-isolated: ``append_event`` returns
``False`` for every storage-side failure and never lets one escape into an
answer route.  Rotation and retention operate only on filenames owned by this
module; the active file, lock file, and unrelated neighbouring artifacts are
never retention candidates.
"""
from __future__ import annotations

import errno
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_ROTATE_SIZE_BYTES = 64 * 1024 * 1024
DEFAULT_RETAINED_ROTATED_FILES = 8
DEFAULT_LOCK_TIMEOUT_SECONDS = 0.050
MAX_RECORD_BYTES = 64 * 1024

MIN_ROTATE_SIZE_BYTES = MAX_RECORD_BYTES
MAX_ROTATE_SIZE_BYTES = 1024 * 1024 * 1024
MIN_RETAINED_ROTATED_FILES = 1
MAX_RETAINED_ROTATED_FILES = 64
MIN_LOCK_TIMEOUT_SECONDS = 0.001
MAX_LOCK_TIMEOUT_SECONDS = 5.0

ROTATE_SIZE_ENV = "SHADOW_EVENTS_ROTATE_SIZE_BYTES"
RETAINED_FILES_ENV = "SHADOW_EVENTS_RETAINED_ROTATED_FILES"
LOCK_TIMEOUT_MS_ENV = "SHADOW_EVENTS_LOCK_TIMEOUT_MS"
EVENTS_PATH_ENV = "SHADOW_EVENTS_PATH"
DEFAULT_EVENTS_PATH = "shadow_events.jsonl"


def _safe_bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if minimum <= parsed <= maximum else default


def _safe_bounded_float(value, default: float, minimum: float, maximum: float) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if minimum <= parsed <= maximum else default


@dataclass(frozen=True)
class StorageConfig:
    """Validated storage limits.

    Direct construction is safe as well as ``load_config``: malformed or
    out-of-range values fall back to the same conservative defaults.
    """

    rotate_size_bytes: int = DEFAULT_ROTATE_SIZE_BYTES
    retained_rotated_files: int = DEFAULT_RETAINED_ROTATED_FILES
    lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rotate_size_bytes",
            _safe_bounded_int(
                self.rotate_size_bytes,
                DEFAULT_ROTATE_SIZE_BYTES,
                MIN_ROTATE_SIZE_BYTES,
                MAX_ROTATE_SIZE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "retained_rotated_files",
            _safe_bounded_int(
                self.retained_rotated_files,
                DEFAULT_RETAINED_ROTATED_FILES,
                MIN_RETAINED_ROTATED_FILES,
                MAX_RETAINED_ROTATED_FILES,
            ),
        )
        object.__setattr__(
            self,
            "lock_timeout_seconds",
            _safe_bounded_float(
                self.lock_timeout_seconds,
                DEFAULT_LOCK_TIMEOUT_SECONDS,
                MIN_LOCK_TIMEOUT_SECONDS,
                MAX_LOCK_TIMEOUT_SECONDS,
            ),
        )


def load_config(environ: Mapping[str, str] | None = None) -> StorageConfig:
    """Load bounded configuration from an environment-like mapping.

    Unknown, malformed, empty, negative, and out-of-range values fail closed
    to the defaults rather than disabling the bound.
    """

    source = os.environ if environ is None else environ
    timeout_ms = _safe_bounded_float(
        source.get(LOCK_TIMEOUT_MS_ENV),
        DEFAULT_LOCK_TIMEOUT_SECONDS * 1000.0,
        MIN_LOCK_TIMEOUT_SECONDS * 1000.0,
        MAX_LOCK_TIMEOUT_SECONDS * 1000.0,
    )
    return StorageConfig(
        rotate_size_bytes=_safe_bounded_int(
            source.get(ROTATE_SIZE_ENV),
            DEFAULT_ROTATE_SIZE_BYTES,
            MIN_ROTATE_SIZE_BYTES,
            MAX_ROTATE_SIZE_BYTES,
        ),
        retained_rotated_files=_safe_bounded_int(
            source.get(RETAINED_FILES_ENV),
            DEFAULT_RETAINED_ROTATED_FILES,
            MIN_RETAINED_ROTATED_FILES,
            MAX_RETAINED_ROTATED_FILES,
        ),
        lock_timeout_seconds=timeout_ms / 1000.0,
    )


_COUNTER_KEYS = (
    "events_appended",
    "events_dropped_oversize",
    "events_dropped_lock_timeout",
    "events_dropped_rotation_failure",
    "events_dropped_write_failure",
    "events_dropped_storage_failure",
    "rotations_completed",
    "rotated_files_deleted",
)
_COUNTERS = {key: 0 for key in _COUNTER_KEYS}
_COUNTERS_LOCK = threading.Lock()


def _increment_counter(key: str, amount: int = 1) -> None:
    with _COUNTERS_LOCK:
        _COUNTERS[key] += amount


def get_counters_snapshot() -> dict[str, int]:
    """Return a process-local, mutation-safe snapshot of storage counters."""

    with _COUNTERS_LOCK:
        result = dict(_COUNTERS)
    result["events_dropped_total"] = sum(
        value for key, value in result.items() if key.startswith("events_dropped_")
    )
    return result


def counters_snapshot() -> dict[str, int]:
    """Short alias for operator/dashboard integrations."""

    return get_counters_snapshot()


class _LockTimeout(RuntimeError):
    pass


class _RotationFailure(RuntimeError):
    pass


class _WriteFailure(RuntimeError):
    pass


_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def _local_lock_for(path: Path) -> threading.Lock:
    key = os.path.abspath(os.fspath(path))
    with _LOCAL_LOCKS_GUARD:
        lock = _LOCAL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCAL_LOCKS[key] = lock
        return lock


def _lock_is_busy(exc: OSError) -> bool:
    return (
        isinstance(exc, BlockingIOError)
        or exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        or getattr(exc, "winerror", None) in {33, 36}
    )


class _AdvisoryFileLock:
    """A bounded advisory lock shared by threads and operating-system processes."""

    def __init__(self, path: Path, timeout_seconds: float):
        self.path = path
        self.timeout_seconds = timeout_seconds
        self._handle = None
        self._local_lock = _local_lock_for(path)
        self._local_acquired = False
        self._os_acquired = False

    def __enter__(self):
        deadline = time.monotonic() + self.timeout_seconds
        if not self._local_lock.acquire(timeout=self.timeout_seconds):
            raise _LockTimeout("local lock timeout")
        self._local_acquired = True
        try:
            self._handle = open(self.path, "a+b", buffering=0)
            if os.name == "nt":
                self._handle.seek(0, os.SEEK_END)
                if self._handle.tell() == 0:
                    self._handle.write(b"\0")
                self._handle.seek(0)

            while True:
                try:
                    self._try_os_lock()
                    self._os_acquired = True
                    return self
                except OSError as exc:
                    if not _lock_is_busy(exc):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise _LockTimeout("advisory lock timeout") from exc
                    time.sleep(min(0.005, remaining))
        except Exception:
            self._cleanup()
            raise

    def _try_os_lock(self) -> None:
        if os.name == "nt":
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_os(self) -> None:
        if not self._os_acquired or self._handle is None:
            return
        if os.name == "nt":
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)

    def _cleanup(self) -> None:
        try:
            self._unlock_os()
        except Exception:
            pass
        self._os_acquired = False
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None
        if self._local_acquired:
            self._local_lock.release()
            self._local_acquired = False

    def __exit__(self, exc_type, exc, traceback):
        self._cleanup()
        return False


def _lock_path(active_path: Path) -> Path:
    return active_path.with_name(active_path.name + ".lock")


def _rotation_pattern(active_path: Path) -> re.Pattern[str]:
    return re.compile(
        rf"^{re.escape(active_path.name)}\.rotated-"
        r"(?P<timestamp>[0-9]{20})-(?P<pid>[0-9]+)-"
        r"(?P<nonce>[0-9a-f]{32})\.jsonl$"
    )


def _owned_rotations(active_path: Path) -> list[tuple[int, str, Path]]:
    pattern = _rotation_pattern(active_path)
    owned: list[tuple[int, str, Path]] = []
    try:
        entries = list(active_path.parent.iterdir())
    except OSError:
        return owned
    for entry in entries:
        match = pattern.fullmatch(entry.name)
        if match is None:
            continue
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        owned.append((int(match.group("timestamp")), entry.name, entry))
    owned.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return owned


def discover_event_files(
    path: str | os.PathLike[str], retained_limit: int | None = None
) -> list[Path]:
    """Return active file first, then owned rotations newest-first.

    ``retained_limit`` applies only to rotated files. Discovery is read-only,
    ignores unrelated neighbours, and tolerates files disappearing during a
    concurrent dashboard scan.
    """

    try:
        active_path = Path(os.fspath(path))
    except (TypeError, ValueError):
        return []
    result: list[Path] = []
    try:
        if active_path.is_file():
            result.append(active_path)
    except OSError:
        pass

    rotations = [item[2] for item in _owned_rotations(active_path)]
    if retained_limit is not None:
        try:
            limit = max(0, int(retained_limit))
        except (TypeError, ValueError):
            limit = 0
        rotations = rotations[:limit]
    result.extend(rotations)
    return result


def _new_rotation_path(active_path: Path) -> Path:
    for _ in range(16):
        candidate = active_path.with_name(
            f"{active_path.name}.rotated-{time.time_ns():020d}-"
            f"{os.getpid()}-{uuid.uuid4().hex}.jsonl"
        )
        if not candidate.exists():
            return candidate
    raise OSError("could not allocate a collision-free rotation name")


def _retention_deletions(active_path: Path, config: StorageConfig) -> list[Path]:
    byte_budget = config.rotate_size_bytes * config.retained_rotated_files
    kept_count = 0
    kept_bytes = 0
    deletions: list[Path] = []
    for _timestamp, _name, candidate in _owned_rotations(active_path):
        try:
            size = candidate.stat().st_size
        except FileNotFoundError:
            continue
        if (
            kept_count < config.retained_rotated_files
            and kept_bytes + size <= byte_budget
        ):
            kept_count += 1
            kept_bytes += size
        else:
            deletions.append(candidate)
    return deletions


def _enforce_retention(
    active_path: Path,
    config: StorageConfig,
    *,
    newly_rotated: Path | None = None,
) -> None:
    deletions = _retention_deletions(active_path, config)
    # Delete oldest files first. If an oversized newly-rotated legacy file is
    # itself outside the byte budget, delete it last so earlier failures can
    # still restore it as the active file.
    deletions.reverse()
    if newly_rotated in deletions:
        deletions.remove(newly_rotated)
        deletions.append(newly_rotated)
    for candidate in deletions:
        try:
            candidate.unlink()
        except FileNotFoundError:
            continue
        _increment_counter("rotated_files_deleted")


def _restore_rotation(active_path: Path, rotated_path: Path | None) -> None:
    if rotated_path is None:
        return
    try:
        if rotated_path.exists() and not active_path.exists():
            os.replace(rotated_path, active_path)
    except OSError:
        pass


def _append_bytes(active_path: Path, record: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(active_path, flags, 0o600)
    original_size = os.fstat(descriptor).st_size
    try:
        view = memoryview(record)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short JSONL write")
            view = view[written:]
    except Exception:
        # A rare short/failed regular-file write must not poison the next
        # JSONL record. The cross-process lock is still held here, so rolling
        # back to the exact pre-append size is safe.
        try:
            os.ftruncate(descriptor, original_size)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def _append_locked(active_path: Path, record: bytes, config: StorageConfig) -> None:
    rotated_path: Path | None = None
    try:
        try:
            current_size = active_path.stat().st_size
        except FileNotFoundError:
            current_size = 0
        if current_size > 0 and current_size + len(record) > config.rotate_size_bytes:
            rotated_path = _new_rotation_path(active_path)
            os.replace(active_path, rotated_path)
        _enforce_retention(active_path, config, newly_rotated=rotated_path)
    except Exception as exc:
        _restore_rotation(active_path, rotated_path)
        raise _RotationFailure("rotation or retention failed") from exc

    if rotated_path is not None:
        _increment_counter("rotations_completed")

    try:
        _append_bytes(active_path, record)
    except Exception as exc:
        try:
            if active_path.exists() and active_path.stat().st_size == 0:
                active_path.unlink()
        except OSError:
            pass
        _restore_rotation(active_path, rotated_path)
        raise _WriteFailure("event append failed") from exc


def append_event(
    event: Mapping,
    path: str | os.PathLike[str] | None = None,
    config: StorageConfig | None = None,
) -> bool:
    """Append one event, returning ``True`` on success and ``False`` on drop.

    The function intentionally never raises an ``Exception`` for serialization,
    path, lock, rotation, retention, or write failures.
    """

    try:
        if not isinstance(event, Mapping):
            raise TypeError("event must be a mapping")
        record = (
            json.dumps(
                dict(event),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except Exception:
        _increment_counter("events_dropped_storage_failure")
        return False

    if len(record) > MAX_RECORD_BYTES:
        _increment_counter("events_dropped_oversize")
        return False

    try:
        effective_config = load_config() if config is None else config
        if not isinstance(effective_config, StorageConfig):
            raise TypeError("config must be StorageConfig")
        raw_path = path
        if raw_path is None:
            raw_path = os.environ.get(EVENTS_PATH_ENV) or DEFAULT_EVENTS_PATH
        active_path = Path(os.fspath(raw_path))
        if not active_path.name:
            raise ValueError("event path must name a file")

        with _AdvisoryFileLock(
            _lock_path(active_path), effective_config.lock_timeout_seconds
        ):
            _append_locked(active_path, record, effective_config)
    except _LockTimeout:
        _increment_counter("events_dropped_lock_timeout")
        return False
    except _RotationFailure:
        _increment_counter("events_dropped_rotation_failure")
        return False
    except _WriteFailure:
        _increment_counter("events_dropped_write_failure")
        return False
    except Exception:
        _increment_counter("events_dropped_storage_failure")
        return False

    _increment_counter("events_appended")
    return True


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_RETAINED_ROTATED_FILES",
    "DEFAULT_ROTATE_SIZE_BYTES",
    "MAX_RECORD_BYTES",
    "StorageConfig",
    "append_event",
    "counters_snapshot",
    "discover_event_files",
    "get_counters_snapshot",
    "load_config",
]
