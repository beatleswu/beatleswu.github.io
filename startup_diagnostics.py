"""Bounded, value-free diagnostics for application startup.

The emitted JSON is intentionally restricted to boot correlation, timing,
phase names, exception types, and stack frame locations.  It never serializes
environment variables, local variables, arguments, or exception messages.
"""

from __future__ import annotations

import contextlib
import datetime as _datetime
import functools
import json
import os
import sys
import threading
import time
import traceback
import uuid
from typing import Iterator, TextIO


_PREFIX = "[startup-diagnostic] "
_DEFAULT_INITIAL_DELAY_SECONDS = 45.0
_DEFAULT_SNAPSHOT_INTERVAL_SECONDS = 45.0
_DEFAULT_MAX_SNAPSHOTS = 3
_MAX_THREADS = 16
_MAX_FRAMES_PER_THREAD = 48


def _safe_boot_id(value: object) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return str(uuid.uuid4())


class StartupDiagnostics:
    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        boot_id: str | None = None,
        initial_delay_seconds: float = _DEFAULT_INITIAL_DELAY_SECONDS,
        snapshot_interval_seconds: float = _DEFAULT_SNAPSHOT_INTERVAL_SECONDS,
        max_snapshots: int = _DEFAULT_MAX_SNAPSHOTS,
    ) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self.boot_id = _safe_boot_id(boot_id or os.environ.get("GO_STARTUP_BOOT_ID"))
        self._started = time.monotonic()
        self._initial_delay = max(0.0, float(initial_delay_seconds))
        self._snapshot_interval = max(0.001, float(snapshot_interval_seconds))
        self._max_snapshots = max(0, min(int(max_snapshots), _DEFAULT_MAX_SNAPSHOTS))
        self._ready = threading.Event()
        self._watchdog_started = False
        self._write_lock = threading.Lock()
        self._ready_lock = threading.Lock()
        role = str(os.environ.get("GO_STARTUP_PROCESS_ROLE") or "unknown").strip().lower()
        self.process_role = role if role in {"app", "scheduler"} else "unknown"

    def _base_event(self, phase: str, status: str) -> dict[str, object]:
        return {
            "schema": "startup-diagnostic-v1",
            "boot_id": self.boot_id,
            "timestamp_utc": _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - self._started, 6),
            "pid": os.getpid(),
            "phase": str(phase),
            "status": str(status),
        }

    def _emit(self, payload: dict[str, object]) -> None:
        line = _PREFIX + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._write_lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def mark(self, phase: str, status: str = "point") -> None:
        self._emit(self._base_event(phase, status))

    @contextlib.contextmanager
    def phase(self, name: str) -> Iterator[None]:
        phase_started = time.monotonic()
        self.mark(name, "start")
        try:
            yield
        except BaseException as exc:
            payload = self._base_event(name, "failure")
            payload["phase_elapsed_seconds"] = round(time.monotonic() - phase_started, 6)
            payload["exception_type"] = type(exc).__name__
            self._emit(payload)
            raise
        else:
            payload = self._base_event(name, "success")
            payload["phase_elapsed_seconds"] = round(time.monotonic() - phase_started, 6)
            self._emit(payload)

    def _stack_snapshot(self, sequence: int) -> None:
        payload = self._base_event("delayed_start_stack", "snapshot")
        payload["snapshot_sequence"] = sequence
        threads: list[dict[str, object]] = []
        for thread_id, frame in list(sys._current_frames().items())[:_MAX_THREADS]:
            frames = traceback.extract_stack(frame, limit=_MAX_FRAMES_PER_THREAD)
            threads.append(
                {
                    "thread_id": int(thread_id),
                    "frames": [
                        {
                            "file": os.path.basename(item.filename),
                            "function": item.name,
                            "line": int(item.lineno),
                        }
                        for item in frames
                    ],
                }
            )
        payload["threads"] = threads
        self._emit(payload)

    def start_delayed_snapshots(self) -> None:
        if self._watchdog_started or self._max_snapshots == 0:
            return
        self._watchdog_started = True

        def worker() -> None:
            delay = self._initial_delay
            for sequence in range(1, self._max_snapshots + 1):
                if self._ready.wait(delay):
                    return
                self._stack_snapshot(sequence)
                delay = self._snapshot_interval

        threading.Thread(
            target=worker,
            name="startup-diagnostics-watchdog",
            daemon=True,
        ).start()

    def mark_ready(self, phase: str = "readiness") -> None:
        with self._ready_lock:
            if self._ready.is_set():
                return
            self.mark(phase, "ready")
            self._ready.set()

    def install_exception_hook(self) -> None:
        previous = sys.excepthook

        def hook(exc_type, exc_value, exc_traceback) -> None:  # type: ignore[no-untyped-def]
            payload = self._base_event("uncaught_startup_exception", "failure")
            payload["exception_type"] = getattr(exc_type, "__name__", "Exception")
            self._emit(payload)
            previous(exc_type, exc_value, exc_traceback)

        sys.excepthook = hook

    def instrument(self, phase_name: str, *, ready_for_role: str | None = None):
        """Decorate a real startup function without changing its semantics."""

        def decorator(function):
            @functools.wraps(function)
            def wrapped(*args, **kwargs):
                with self.phase(phase_name):
                    result = function(*args, **kwargs)
                if ready_for_role and self.process_role == ready_for_role:
                    self.mark_ready(f"{ready_for_role}_ready")
                return result

            return wrapped

        return decorator


diagnostics = StartupDiagnostics()
