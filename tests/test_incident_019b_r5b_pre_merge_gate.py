"""Incident019B R5B migration-gate and star-authority contracts."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tools.incident_019b_progression_continuity import (
    MIGRATION_OWNER_GATE,
    _parser,
    _validate_execution_gate,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_incident019b_migration_is_not_reachable_from_app_init_db():
    source = (REPOSITORY_ROOT / "app.py").read_text(encoding="utf-8")

    assert "upgrade_adventure_historical_mastery_schema" not in source
    assert "from migrations.adventure_historical_mastery_v1" not in source


def test_capture_requires_explicit_production_db_migration_gate():
    args = _parser().parse_args(
        ["--capture-baseline", "--confirm-baseline-version", "wrong"]
    )
    with pytest.raises(SystemExit, match="requires --execute"):
        _validate_execution_gate(args)

    args = _parser().parse_args(
        [
            "--capture-baseline",
            "--confirm-baseline-version",
            "wrong",
            "--execute",
            "--owner-gate",
            "GO_DEPLOY",
        ]
    )
    with pytest.raises(SystemExit, match="GO_PRODUCTION_DB_MIGRATION"):
        _validate_execution_gate(args)


def test_ordinary_deploy_gate_cannot_be_reused_for_baseline_capture():
    args = argparse.Namespace(
        capture_baseline=False,
        execute=True,
        owner_gate="GO_DEPLOY",
    )
    with pytest.raises(SystemExit, match="only valid with --capture-baseline"):
        _validate_execution_gate(args)

    args = argparse.Namespace(
        capture_baseline=True,
        execute=True,
        owner_gate=MIGRATION_OWNER_GATE,
    )
    _validate_execution_gate(args)


def test_r3_star_code_reads_only_server_owned_boss_state():
    source = (REPOSITORY_ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def _adventure_state(uid):")
    end = source.index("\n\n_ADVENTURE_STATE_CACHE", start)
    state_function = source[start:end]

    assert "stars = max(0, int(row.get('stars') or 0))" in state_function
    assert "if pct >= 60" not in state_function
    assert "if total and defeated >= total" not in state_function
    assert "stars = 0" not in state_function
