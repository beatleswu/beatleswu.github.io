"""Bounded aggregation tests for ``shadow_dashboard.aggregate_shadow_events``.

Every event and rotation in this module is synthetic and confined to pytest's
temporary directory. The tests exercise the storage-owned rotation filename
contract without reading application, corpus, database, or production data.
"""

from __future__ import annotations

import builtins
import datetime as dt
import json
import os
import tracemalloc
from pathlib import Path

import shadow_dashboard


NOW = dt.datetime(2026, 7, 17, 12, 0, tzinfo=dt.timezone.utc)
RATING_ROUTE = "/api/rating_test/answer"
DAILY_ROUTE = "/api/daily-challenge/submit"
FRIEND_ROUTE = "/api/challenges/friend/7/answer"


def _event(
    event_id,
    *,
    schema_version="shadow-v4",
    route=RATING_ROUTE,
    match=None,
    **extra,
):
    event = {
        "schema_version": schema_version,
        "created_at": "2026-07-17T11:00:00+00:00",
    }
    if event_id is not None:
        event["event_id"] = event_id
    if route is not None:
        event["route"] = route
    if match is not None:
        event["match"] = match
    event.update(extra)
    return event


def _encode_rows(rows) -> list[bytes]:
    return [
        json.dumps(row, separators=(",", ":"), sort_keys=True).encode("utf-8")
        + b"\n"
        for row in rows
    ]


def _write_jsonl(path: Path, rows) -> list[bytes]:
    encoded = _encode_rows(rows)
    path.write_bytes(b"".join(encoded))
    return encoded


def _owned_rotation(active_path: Path, timestamp: int, nonce_digit: str) -> Path:
    return active_path.with_name(
        f"{active_path.name}.rotated-{timestamp:020d}-1-"
        f"{nonce_digit * 32}.jsonl"
    )


def _rows_by_key(rows, key):
    return {row[key]: row["count"] for row in rows}


def _aggregate(path: Path, **overrides):
    kwargs = {
        "path": str(path),
        "now": NOW,
        "max_bytes": 1_000_000,
        "max_events": 1_000,
        "latency_budget_ms": 5_000,
        "monotonic": lambda: 0.0,
    }
    kwargs.update(overrides)
    return shadow_dashboard.aggregate_shadow_events(**kwargs)


def test_aggregates_active_and_all_owned_rotations(tmp_path):
    active = tmp_path / "shadow_events.jsonl"
    newer = _owned_rotation(active, 2, "b")
    older = _owned_rotation(active, 1, "a")

    _write_jsonl(active, [_event("active", match=True, latency_ms=5)])
    _write_jsonl(
        newer,
        [
            _event(
                "newer",
                schema_version="shadow-v3",
                route=DAILY_ROUTE,
                match=False,
                latency_ms=15,
            )
        ],
    )
    _write_jsonl(older, [_event("older", route=FRIEND_ROUTE, match=True)])

    result = _aggregate(active)

    assert result["files_considered"] == 3
    assert result["files_scanned"] == 3
    assert result["bytes_scanned"] == sum(
        path.stat().st_size for path in (active, newer, older)
    )
    assert result["events_scanned"] == 3
    assert result["summary"]["total_events"] == 3
    assert result["routes"][RATING_ROUTE]["total"] == 1
    assert result["routes"][DAILY_ROUTE]["total"] == 1
    assert (
        result["routes"]["/api/challenges/friend/<int:cid>/answer"]["total"]
        == 1
    )
    assert _rows_by_key(result["schema_versions"], "schema_version") == {
        "shadow-v4": 2,
        "shadow-v3": 1,
    }
    assert result["agreement_window"] == {
        "matches": 2,
        "mismatches": 1,
        "rate": 0.666667,
        "window_complete": True,
    }
    assert result["scan_truncated"] is False
    assert result["window_complete"] is True


def test_active_tail_then_newer_rotation_wins_duplicate_event_ids(tmp_path):
    active = tmp_path / "shadow_events.jsonl"
    newer = _owned_rotation(active, 20, "b")
    older = _owned_rotation(active, 10, "a")

    # The final active line is newest within the active file.
    _write_jsonl(
        active,
        [
            _event("within-active", route=DAILY_ROUTE, match=False),
            _event("active-over-rotation", route=RATING_ROUTE, match=True),
            _event("within-active", route=RATING_ROUTE, match=True),
        ],
    )
    _write_jsonl(
        newer,
        [
            _event("active-over-rotation", route=DAILY_ROUTE, match=False),
            _event("newer-over-older", route=FRIEND_ROUTE, match=True),
        ],
    )
    _write_jsonl(
        older,
        [
            _event("newer-over-older", route=DAILY_ROUTE, match=False),
            _event("unique-older", route=DAILY_ROUTE, match=True),
        ],
    )

    result = _aggregate(active)

    assert result["events_scanned"] == 7
    assert result["summary"]["total_events"] == 4
    assert result["duplicate_events_skipped"] == 3
    assert result["routes"][RATING_ROUTE]["total"] == 2
    assert result["routes"][RATING_ROUTE]["matches"] == 2
    assert result["routes"][DAILY_ROUTE]["total"] == 1
    assert result["routes"][DAILY_ROUTE]["matches"] == 1
    friend = result["routes"]["/api/challenges/friend/<int:cid>/answer"]
    assert friend["total"] == 1
    assert friend["matches"] == 1
    assert result["agreement_window"]["matches"] == 4
    assert result["agreement_window"]["mismatches"] == 0
    assert result["agreement_window"]["rate"] == 1.0


def test_mixed_v3_v4_and_missing_fields_remain_aggregate_safe(tmp_path):
    active = tmp_path / "shadow_events.jsonl"
    _write_jsonl(
        active,
        [
            # Historical v3 has neither event_id nor any V4 diagnostics.
            _event(
                None,
                schema_version="shadow-v3",
                route=RATING_ROUTE,
                match=True,
            ),
            _event(
                "v4-class-b",
                route=DAILY_ROUTE,
                classification="legacy_rejects_transform_candidate",
                source_judgement="reject",
                shadow_judgement="off_tree",
                candidate_only_detected=True,
                candidate_source="accepted_moves",
                canonical_puzzle_id=None,
                invalid_identity=True,
            ),
            # Missing optional V4 fields normalize to unknown, not false.
            _event("v4-minimal", route=FRIEND_ROUTE),
            # Missing route is counted as a partial event without raising.
            _event("v4-missing-route", route=None),
        ],
    )

    result = _aggregate(active)

    assert result["scan_errors"] == 0
    assert result["summary"]["total_events"] == 4
    assert result["summary"]["partial_events"] == 1
    assert _rows_by_key(result["schema_versions"], "schema_version") == {
        "shadow-v4": 3,
        "shadow-v3": 1,
    }
    assert result["candidate_diagnostics"]["candidate_only_detected"] == 1
    assert result["candidate_diagnostics"]["known_legacy_bug"] == 1
    assert _rows_by_key(
        result["candidate_diagnostics"]["by_source"], "candidate_source"
    ) == {"accepted_moves": 1}
    assert _rows_by_key(
        result["candidate_diagnostics"]["classes"], "classification"
    ) == {"legacy_rejects_transform_candidate": 1}
    assert result["agreement_window"] == {
        "matches": 1,
        "mismatches": 1,
        "rate": 0.5,
        "window_complete": True,
    }
    assert result["window_complete"] is True


def test_byte_cap_reports_truncated_partial_window_and_exact_budget(tmp_path):
    active = tmp_path / "shadow_events.jsonl"
    rows = [
        _event(
            f"byte-{index}",
            match=index % 2 == 0,
            padding="x" * 120,
        )
        for index in range(5)
    ]
    encoded = _write_jsonl(active, rows)
    byte_cap = len(encoded[-1]) + len(encoded[-2]) + 17

    result = _aggregate(active, max_bytes=byte_cap)

    assert result["read_budget"]["max_bytes"] == byte_cap
    assert result["bytes_scanned"] == byte_cap
    assert result["events_scanned"] == 2
    assert result["summary"]["total_events"] == 2
    assert result["scan_truncated"] is True
    assert result["window_complete"] is False
    assert result["agreement_window"]["window_complete"] is False
    assert result["agreement_window"]["rate"] is None


def test_event_cap_reports_truncated_partial_window(tmp_path):
    active = tmp_path / "shadow_events.jsonl"
    _write_jsonl(
        active,
        [_event(f"event-{index}", match=True) for index in range(5)],
    )

    result = _aggregate(
        active,
        max_bytes=active.stat().st_size,
        max_events=2,
    )

    assert result["read_budget"]["max_events"] == 2
    assert result["events_scanned"] == 2
    assert result["summary"]["total_events"] == 2
    assert result["scan_truncated"] is True
    assert result["window_complete"] is False
    assert result["agreement_window"]["matches"] == 2
    assert result["agreement_window"]["rate"] is None


class _DeterministicBudgetClock:
    """Let one event through, then cross a ten-millisecond deadline."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return 0.0 if self.calls <= 3 else 0.020


def test_injected_monotonic_makes_latency_budget_truncation_deterministic(tmp_path):
    active = tmp_path / "shadow_events.jsonl"
    _write_jsonl(
        active,
        [_event(f"clock-{index}", match=True) for index in range(4)],
    )
    clock = _DeterministicBudgetClock()

    result = _aggregate(
        active,
        max_bytes=active.stat().st_size,
        latency_budget_ms=10,
        monotonic=clock,
    )

    assert clock.calls >= 4
    assert result["read_budget"]["latency_budget_ms"] == 10
    assert result["events_scanned"] == 1
    assert result["summary"]["total_events"] == 1
    assert result["scan_truncated"] is True
    assert result["window_complete"] is False
    assert result["agreement_window"]["rate"] is None


class _TrackingBinaryReader:
    def __init__(self, handle, read_sizes):
        self._handle = handle
        self._read_sizes = read_sizes

    def read(self, size=-1):
        self._read_sizes.append(size)
        return self._handle.read(size)

    def __getattr__(self, name):
        return getattr(self._handle, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._handle.__exit__(exc_type, exc, traceback)


def test_large_window_streams_in_chunks_with_bounded_tracemalloc_peak(
    tmp_path, monkeypatch
):
    active = tmp_path / "shadow_events.jsonl"
    event_count = 9_000
    padding = "x" * 512
    with active.open("wb") as handle:
        for index in range(event_count):
            row = _event(
                f"stream-{index:05d}",
                match=True,
                padding=padding,
            )
            handle.write(
                json.dumps(row, separators=(",", ":"), sort_keys=True).encode(
                    "utf-8"
                )
                + b"\n"
            )

    file_size = active.stat().st_size
    assert file_size > shadow_dashboard._AGGREGATE_READ_CHUNK_BYTES * 10

    real_open = builtins.open
    target = os.path.abspath(os.fspath(active))
    read_sizes = []

    def _tracking_open(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if os.path.abspath(os.fspath(file)) == target and mode == "rb":
            return _TrackingBinaryReader(handle, read_sizes)
        return handle

    monkeypatch.setattr(builtins, "open", _tracking_open)

    tracemalloc.start()
    try:
        result = _aggregate(
            active,
            max_bytes=file_size,
            max_events=event_count + 1,
            monotonic=lambda: 0.0,
        )
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result["summary"]["total_events"] == event_count
    assert result["events_scanned"] == event_count
    assert result["bytes_scanned"] == file_size
    assert result["scan_truncated"] is False
    assert result["window_complete"] is True
    assert read_sizes
    assert all(0 < size <= shadow_dashboard._AGGREGATE_READ_CHUNK_BYTES for size in read_sizes)
    assert max(read_sizes) == shadow_dashboard._AGGREGATE_READ_CHUNK_BYTES
    assert len(read_sizes) > 10

    # The implementation advertises 64 MiB. This tighter test ceiling leaves
    # room for dedupe IDs and decoder objects while rejecting whole-file
    # buffering plus a second decoded copy of this multi-megabyte fixture.
    test_memory_ceiling = shadow_dashboard._AGGREGATE_MEMORY_BUDGET_BYTES // 4
    assert peak < test_memory_ceiling
