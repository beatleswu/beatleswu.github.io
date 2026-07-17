import json
import multiprocessing
import os
import re
import time
from pathlib import Path

import shadow_event_storage as storage


def _event(event_id, payload_size=0):
    return {
        "event_id": str(event_id),
        "schema_version": "shadow-v4",
        "payload": "x" * payload_size,
    }


def _read_events(path):
    events = []
    for event_file in storage.discover_event_files(path):
        for line in event_file.read_text(encoding="utf-8").splitlines():
            events.append(json.loads(line))
    return events


def _multiprocess_writer(path, first_id, count, start_event, result_queue):
    config = storage.StorageConfig(
        rotate_size_bytes=4 * 1024 * 1024,
        retained_rotated_files=8,
        lock_timeout_seconds=5.0,
    )
    start_event.wait(10)
    written = 0
    for offset in range(count):
        if storage.append_event(
            _event(first_id + offset, payload_size=32),
            path=path,
            config=config,
        ):
            written += 1
    result_queue.put(written)


def _hold_advisory_lock(lock_path, ready_event, release_event):
    with storage._AdvisoryFileLock(Path(lock_path), 2.0):
        ready_event.set()
        release_event.wait(10)


def test_load_config_malformed_and_out_of_range_values_use_safe_defaults():
    config = storage.load_config(
        {
            storage.ROTATE_SIZE_ENV: "not-an-integer",
            storage.RETAINED_FILES_ENV: "0",
            storage.LOCK_TIMEOUT_MS_ENV: "999999999",
        }
    )

    assert config.rotate_size_bytes == 64 * 1024 * 1024
    assert config.retained_rotated_files == 8
    assert config.lock_timeout_seconds == 0.050

    directly_constructed = storage.StorageConfig(
        rotate_size_bytes=-1,
        retained_rotated_files=10_000,
        lock_timeout_seconds=0,
    )
    assert directly_constructed == storage.StorageConfig()


def test_load_config_accepts_values_inside_documented_bounds():
    config = storage.load_config(
        {
            storage.ROTATE_SIZE_ENV: str(storage.MIN_ROTATE_SIZE_BYTES),
            storage.RETAINED_FILES_ENV: "3",
            storage.LOCK_TIMEOUT_MS_ENV: "125",
        }
    )

    assert config.rotate_size_bytes == storage.MIN_ROTATE_SIZE_BYTES
    assert config.retained_rotated_files == 3
    assert config.lock_timeout_seconds == 0.125


def test_preappend_rotation_uses_atomic_owned_collision_free_name(tmp_path, monkeypatch):
    path = tmp_path / "shadow_events.jsonl"
    config = storage.StorageConfig(
        rotate_size_bytes=storage.MIN_ROTATE_SIZE_BYTES,
        retained_rotated_files=8,
        lock_timeout_seconds=1.0,
    )
    assert storage.append_event(_event("first", 35_000), path=path, config=config)

    real_replace = storage.os.replace
    replace_calls = []

    def tracking_replace(source, destination):
        replace_calls.append((Path(source), Path(destination)))
        return real_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", tracking_replace)
    assert storage.append_event(_event("second", 35_000), path=path, config=config)

    files = storage.discover_event_files(path)
    assert files[0] == path
    assert len(files) == 2
    rotated = files[1]
    assert replace_calls == [(path, rotated)]
    assert re.fullmatch(
        re.escape(path.name)
        + r"\.rotated-[0-9]{20}-[0-9]+-[0-9a-f]{32}\.jsonl",
        rotated.name,
    )
    assert json.loads(path.read_text(encoding="utf-8"))["event_id"] == "second"
    assert json.loads(rotated.read_text(encoding="utf-8"))["event_id"] == "first"
    assert not list(tmp_path.glob("*.tmp"))


def test_retention_enforces_count_byte_bound_and_current_file_safety(tmp_path):
    path = tmp_path / "shadow_events.jsonl"
    config = storage.StorageConfig(
        rotate_size_bytes=storage.MIN_ROTATE_SIZE_BYTES,
        retained_rotated_files=2,
        lock_timeout_seconds=1.0,
    )

    for index in range(14):
        assert storage.append_event(
            _event(index, payload_size=24_000), path=path, config=config
        )

    files = storage.discover_event_files(path)
    rotations = files[1:]
    assert files[0] == path
    assert path.is_file()
    assert len(rotations) <= config.retained_rotated_files
    assert sum(item.stat().st_size for item in rotations) <= (
        config.rotate_size_bytes * config.retained_rotated_files
    )
    assert sum(item.stat().st_size for item in files) <= (
        config.rotate_size_bytes * (config.retained_rotated_files + 1)
    )
    assert path.stat().st_size <= config.rotate_size_bytes
    assert any(event["event_id"] == "13" for event in _read_events(path))

    timestamps = [int(item.name.split(".rotated-", 1)[1].split("-", 1)[0]) for item in rotations]
    assert timestamps == sorted(timestamps, reverse=True)


def test_retention_never_deletes_unowned_neighbours(tmp_path):
    path = tmp_path / "shadow_events.jsonl"
    unknown = tmp_path / "shadow_events.jsonl.rotated-manual-backup"
    unknown.write_text("operator-owned", encoding="utf-8")
    config = storage.StorageConfig(
        rotate_size_bytes=storage.MIN_ROTATE_SIZE_BYTES,
        retained_rotated_files=1,
        lock_timeout_seconds=1.0,
    )

    for index in range(8):
        assert storage.append_event(
            _event(index, payload_size=35_000), path=path, config=config
        )

    assert unknown.read_text(encoding="utf-8") == "operator-owned"
    assert unknown not in storage.discover_event_files(path)


def test_retention_enforces_byte_budget_even_below_file_count_limit(tmp_path):
    path = tmp_path / "shadow_events.jsonl"
    config = storage.StorageConfig(
        rotate_size_bytes=storage.MIN_ROTATE_SIZE_BYTES,
        retained_rotated_files=2,
        lock_timeout_seconds=1.0,
    )
    newest = tmp_path / (
        path.name + ".rotated-00000000000000000002-1-"
        + "a" * 32 + ".jsonl"
    )
    older = tmp_path / (
        path.name + ".rotated-00000000000000000001-1-"
        + "b" * 32 + ".jsonl"
    )
    newest.write_bytes(b"n" * 100_000)
    older.write_bytes(b"o" * 100_000)

    assert storage.append_event(_event("current"), path=path, config=config)

    rotations = storage.discover_event_files(path)[1:]
    assert rotations == [newest]
    assert newest.exists()
    assert not older.exists()
    assert sum(item.stat().st_size for item in rotations) <= (
        config.rotate_size_bytes * config.retained_rotated_files
    )


def test_oversize_record_is_dropped_without_creating_active_file(tmp_path):
    path = tmp_path / "shadow_events.jsonl"
    before = storage.get_counters_snapshot()

    assert not storage.append_event(
        _event("oversize", payload_size=storage.MAX_RECORD_BYTES), path=path
    )

    after = storage.get_counters_snapshot()
    assert not path.exists()
    assert after["events_dropped_oversize"] == before["events_dropped_oversize"] + 1
    assert after["events_dropped_total"] == before["events_dropped_total"] + 1


def test_real_multiprocessing_writers_produce_complete_unique_json_lines(tmp_path):
    path = tmp_path / "shadow_events.jsonl"
    process_count = 4
    events_per_process = 80
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_multiprocess_writer,
            args=(
                str(path),
                process_index * events_per_process,
                events_per_process,
                start_event,
                result_queue,
            ),
        )
        for process_index in range(process_count)
    ]

    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(30)
        assert process.exitcode == 0

    written_counts = [result_queue.get(timeout=5) for _ in processes]
    result_queue.close()
    assert written_counts == [events_per_process] * process_count

    events = _read_events(path)
    event_ids = {event["event_id"] for event in events}
    assert len(events) == process_count * events_per_process
    assert len(event_ids) == process_count * events_per_process


def test_lock_timeout_drops_event_quickly_and_increments_counter(tmp_path):
    path = tmp_path / "shadow_events.jsonl"
    lock_path = path.with_name(path.name + ".lock")
    context = multiprocessing.get_context("spawn")
    ready_event = context.Event()
    release_event = context.Event()
    holder = context.Process(
        target=_hold_advisory_lock,
        args=(str(lock_path), ready_event, release_event),
    )
    holder.start()
    try:
        assert ready_event.wait(10)
        before = storage.get_counters_snapshot()
        config = storage.StorageConfig(lock_timeout_seconds=0.020)
        started = time.monotonic()

        assert not storage.append_event(_event("blocked"), path=path, config=config)

        elapsed = time.monotonic() - started
        after = storage.get_counters_snapshot()
        assert elapsed < 1.0
        assert after["events_dropped_lock_timeout"] == (
            before["events_dropped_lock_timeout"] + 1
        )
        assert not path.exists()
    finally:
        release_event.set()
        holder.join(10)
    assert holder.exitcode == 0


def test_rotation_failure_is_isolated_and_preserves_current_file(tmp_path, monkeypatch):
    path = tmp_path / "shadow_events.jsonl"
    config = storage.StorageConfig(
        rotate_size_bytes=storage.MIN_ROTATE_SIZE_BYTES,
        retained_rotated_files=2,
        lock_timeout_seconds=1.0,
    )
    assert storage.append_event(_event("first", 35_000), path=path, config=config)
    original_bytes = path.read_bytes()
    before = storage.get_counters_snapshot()

    def fail_replace(_source, _destination):
        raise OSError("simulated atomic rename failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    assert not storage.append_event(_event("second", 35_000), path=path, config=config)

    after = storage.get_counters_snapshot()
    assert path.read_bytes() == original_bytes
    assert storage.discover_event_files(path) == [path]
    assert after["events_dropped_rotation_failure"] == (
        before["events_dropped_rotation_failure"] + 1
    )


def test_invalid_path_and_unserializable_event_never_raise(tmp_path):
    before = storage.get_counters_snapshot()

    assert not storage.append_event({"bad": object()}, path=tmp_path / "events.jsonl")
    assert not storage.append_event(_event("missing-parent"), path=tmp_path / "missing" / "events.jsonl")

    after = storage.get_counters_snapshot()
    assert after["events_dropped_storage_failure"] >= (
        before["events_dropped_storage_failure"] + 2
    )
