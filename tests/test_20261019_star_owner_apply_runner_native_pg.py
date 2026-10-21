"""Production-maintenance runner rehearsal on loopback-only disposable PG.

This imports the exact maintenance runner but monkeypatches the canonical
pool to TEN synthetic SGF IDs and adjusts scoped constants to the synthetic
23/13/6 scenario. All database connections stay on the pytest-owned
127.0.0.1:ephemeral_port cluster, never production.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from test_20261019_owner_exact_historical_star_catchup_pg import (
    fake_cohort, local_postgres, native_runtime, POOL, ZONE, RECEIPT_TABLE,
    _state,
)
from tools.incident_019b_historical_second_star_catchup import (
    build_readonly_plan, CatchupRefused, _canonical_pool_from_local_files,
)
import tools.incident_019b_owner_scoped_production_apply_20261019 as runner


@pytest.fixture
def local_owner_runner(fake_cohort, local_postgres, monkeypatch):
    url = os.environ.get("DATABASE_URL", "")
    parsed = urlparse(url)
    assert parsed.hostname == "127.0.0.1" and parsed.port
    assert parsed.path == "/postgres"
    assert url == local_postgres, "must use the disposable local database only"
    app = fake_cohort
    with app.get_db() as conn:
        plan = build_readonly_plan(conn, POOL)
        assert len(plan.candidates) == 13

    monkeypatch.setattr(runner, "_canonical_pool_from_local_files", lambda _: POOL)
    monkeypatch.setattr(runner, "CANONICAL_POOL_COUNT", 10)
    monkeypatch.setattr(runner, "CANONICAL_SECOND_THRESHOLD", 6)
    monkeypatch.setattr(runner, "APPROVED_CLEARED", 23)
    monkeypatch.setattr(runner, "APPROVED_CANDIDATES", 13)
    monkeypatch.setattr(runner, "APPROVED_SHA", plan.candidate_digest)
    monkeypatch.setattr(runner, "APPROVED_POOL_SHA", plan.pool_sha256)
    monkeypatch.setenv("GO_ADVENTURE_RETROACTIVE_MILESTONE_POLICY", "hold")
    args = SimpleNamespace(
        owner_scope=runner.APPROVED_OWNER_SCOPE,
        expected_candidate_digest=plan.candidate_digest,
        backup_sha256=("77237595ff4aea9f946a13e2ffc44e436c825a74f6c7bc7f2e88acc28216effe"),
        batch_id="HISTORICAL_ZONE1_13_20261019_DISPOSABLE_PG",
        canonical_root="DISPOSABLE_FIXTURE_NO_PRODUCTION_FILES",
        apply=False,
    )
    return app, args, plan


def test_full_runner_transaction_dryrun_rolls_back_migration_and_stars(local_owner_runner):
    app, args, plan = local_owner_runner
    before = _state(app)
    result = runner.run(args)
    assert result["result"] == "VALIDATED_BUT_ROLLED_BACK_DRYRUN"
    assert result["star_two_granted"] == 13
    assert result["historical_audit_receipts"] == 13
    assert result["other_rewards_xp_coins_unchanged"] is True
    assert _state(app) == before
    with app.get_db() as conn:
        assert not conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name=?",
            (RECEIPT_TABLE,),
        ).fetchone()


def test_full_runner_commits_to_disposable_pg_then_independent_new_connection_verifies(local_owner_runner):
    app, args, plan = local_owner_runner
    args.apply = True
    result = runner.run(args)
    assert result["result"] == "COMMITTED_AND_VERIFIED_ON_NEW_READONLY_CONNECTION"
    assert result["star_two_granted"] == 13
    assert result["nonrecipients_unchanged"] == 10
    assert result["third_stars_granted"] == 0
    assert result["historical_audit_receipts"] == 13
    assert result["recovery_prior_star_levels_recorded"] is True
    assert _state(app) == (13,0)  # do not forge Map/Boss event authority

    with app.get_db() as conn:
        rows = conn.execute(
            f"SELECT prior_row_existed,prior_earned_stars FROM {RECEIPT_TABLE} "
            "ORDER BY user_id",
        ).fetchall()
        assert len(rows) == 13
        assert sum(bool(r["prior_row_existed"]) for r in rows) == 3
        assert sum(r["prior_earned_stars"] == 1 for r in rows) == 3
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_star_progress "
            "WHERE zone_key=? AND earned_stars=3",(ZONE,),
        ).fetchone()["n"] == 0
    fresh_client = app.app.test_client()
    with fresh_client.session_transaction() as sess:
        sess["user_id"] = 83001
        sess["username"] = "synthetic-star-0"
    zone = next(z for z in fresh_client.get("/api/adventure/bootstrap").get_json()["zones"]
                if z["key"]==ZONE)
    assert zone["stars"] == 2

    with pytest.raises(CatchupRefused, match="DRIFT"):
        runner.run(args)
    assert _state(app) == (13,0)


def test_full_runner_rejects_wrong_scope_before_database_mutation(local_owner_runner):
    app, args, _ = local_owner_runner
    args.owner_scope = "ANOTHER_SCOPE"
    with pytest.raises(CatchupRefused,match="SCOPE"):
        runner.run(args)
    assert _state(app) == (0,0)
