"""Disposable PostgreSQL proof of exact-source historical Zone 1 second-star catch-up.

Tests an independent historical receipt, NOT a forged Map/Boss ledger event.
Production DB is never a fixture input; reuses the native, local pg test cluster.
"""
from __future__ import annotations

import pytest
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from adventure_progress_compatibility import BASELINE_VERSION
from migrations.adventure_zone_star_progression_v1 import upgrade as upgrade_stars
from migrations.adventure_historical_mastery_v1 import upgrade as upgrade_history
from migrations.adventure_zone_star_historical_catchup_v1 import (
    upgrade as upgrade_catchup_receipts, OWNER_GATE as SCHEMA_GATE,
    RECEIPT_TABLE,
)
from tools.incident_019b_historical_second_star_catchup import (
    APPROVAL_ID,CatchupRefused,build_readonly_plan,apply_owner_approved_plan,
)

ZONE="k26_30"
POOL=tuple(range(401,411))
STAMP="2026-10-19T13:00:00+09:00"


@pytest.fixture
def fake_cohort(native_runtime):
    app=native_runtime
    with app.get_db() as conn:
        assert upgrade_stars(conn)["valid"] is True
        assert upgrade_history(conn)["valid"] is True
        conn.execute(
            "INSERT INTO adventure_historical_mastery_baseline "
            "(baseline_version,cutoff_literal,captured_at,frozen_at,status,"
            "membership_count,source_rule_version,expected_membership_count,"
            "actual_membership_count,membership_fingerprint,ready_at,"
            "failure_reason,predicate_reference_sha,cutoff_operator,cutoff_domain,"
            "exact_membership_count,conservative_membership_count) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (BASELINE_VERSION,"2026-08-29T13:17:30",STAMP,STAMP,
             "BASELINE_READY",128,"prechange_display_predicate_v1",
             128,128,"a"*64,STAMP,None,
             "4f2547a6defd60a228f77a4457b96f24b916e22c",
             "<","LEGACY_NAIVE_REVIEWED_AT_STORAGE_DOMAIN",128,0),
        )
        for index,uid in enumerate(range(83001,83024)):
            conn.execute(
                "INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (uid,f"synthetic-star-{index}","Synthetic","unused",0,"free",STAMP),
            )
            conn.execute(
                "INSERT INTO adventure_boss_progress "
                "(user_id,zone_key,cleared,stars,attempts,best_score) "
                "VALUES(?,?,1,1,1,18)",
                (uid,ZONE),
            )
            if index < 3:
                # Exactly the kind of mixed 3-present + 20-legacy cohort
                # seen in the read-only real DB census.
                conn.execute(
                    "INSERT INTO adventure_zone_star_progress"
                    "(user_id,zone_key,earned_stars,updated_at) VALUES(?,?,1,?)",
                    (uid,ZONE,STAMP),
                )
            for qid in POOL[:(6 if index<13 else 5)]:
                conn.execute(
                    "INSERT INTO adventure_historical_mastery "
                    "(user_id,question_id,baseline_version,source_mask,"
                    "entitlement_source,captured_at,cutoff_literal,"
                    "reconstruction_class) VALUES(?,?,?,?,?,?,?,?)",
                    (uid,qid,BASELINE_VERSION,1,
                     "grandfathered_legacy_progress",
                     "2026-10-01T00:00:00","2026-10-01",
                     "EXACT_RECONSTRUCTABLE"),
                )
    return app


def _state(app):
    with app.get_db() as conn:
        row=conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_star_progress "
            "WHERE zone_key=? AND earned_stars=2",(ZONE,),
        ).fetchone()
        hist=conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_star_earnings WHERE zone_key=?",(ZONE,)
        ).fetchone()
        return row["n"],hist["n"]


def test_dry_run_census_23_players_13_exact_no_writes(fake_cohort):
    app=fake_cohort
    before=_state(app)
    with app.get_db() as conn:
        p=build_readonly_plan(conn,POOL)
        assert p.threshold==6
        assert p.pool_count==10
        assert p.cleared_users==23
        assert p.qualified_users==13
        assert len(p.candidates)==13
        assert p.conservative_needed==0
        assert p.possible_third_star==0
        assert p.summary()["production_mutated"] is False
        assert not conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name=?",(RECEIPT_TABLE,)
        ).fetchone()
    assert _state(app)==before


def test_gate_blocks_apply_and_migration_without_approval(fake_cohort):
    app=fake_cohort
    with app.get_db() as conn:
        p=build_readonly_plan(conn,POOL)
        with pytest.raises(PermissionError):
            upgrade_catchup_receipts(conn,owner_gate="bad-gate",execute=True)
        with pytest.raises(CatchupRefused):
            apply_owner_approved_plan(conn,POOL,
                expected_candidate_digest=p.candidate_digest,
                expected_candidate_count=13,
                owner_gate="bad-gate",owner_batch_id="TEST_ONLY",
                timestamp=STAMP)
        assert upgrade_catchup_receipts(conn,owner_gate=SCHEMA_GATE,
                                       execute=False)["status"]=="DRY_RUN"
    assert _state(app)==(0,0)


def test_separate_historical_receipts_only_no_forged_map_ledger(fake_cohort):
    app=fake_cohort
    with app.get_db() as conn:
        p=build_readonly_plan(conn,POOL)
        migration=upgrade_catchup_receipts(conn,owner_gate=SCHEMA_GATE,execute=True)
        assert migration["present"] is True
        res=apply_owner_approved_plan(
            conn,POOL,expected_candidate_digest=p.candidate_digest,
            expected_candidate_count=13,
            owner_gate=APPROVAL_ID,owner_batch_id="DISPOSABLE_TEST_BATCH",
            timestamp=STAMP,
        )
        assert res["granted"]==13
    assert _state(app)==(13,0)
    with app.get_db() as conn:
        receipts=conn.execute(
            f"SELECT user_id,star_number,distinct_correct,required_correct "
            f"FROM {RECEIPT_TABLE} ORDER BY user_id",
        ).fetchall()
        assert len(receipts)==13
        assert all(int(r["star_number"])==2 and
                   int(r["distinct_correct"])==6 and
                   int(r["required_correct"])==6 for r in receipts)
        plan=build_readonly_plan(conn,POOL)
        assert len(plan.candidates)==0
        # Below-threshold players remain at inherited one star.
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_boss_progress "
            "WHERE zone_key=? AND cleared=1 AND stars=1",(ZONE,),
        ).fetchone()["n"]==23
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_star_progress "
            "WHERE zone_key=? AND earned_stars>=3",(ZONE,),
        ).fetchone()["n"]==0
    client=app.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"]=83001
        sess["username"]="synthetic-star-0"
    response=client.get("/api/adventure/bootstrap")
    assert response.status_code==200
    zone=next(z for z in response.get_json()["zones"] if z["key"]==ZONE)
    assert zone["zone_authority_stars"]==2
    assert zone["stars"]==2
    assert zone["cleared"] is True
    fresh=app.app.test_client()
    with fresh.session_transaction() as sess:
        sess["user_id"]=83001
        sess["username"]="synthetic-star-0"
    new_state=next(z for z in fresh.get("/api/adventure/bootstrap").get_json()["zones"]
                   if z["key"]==ZONE)
    assert new_state["stars"]==2


def test_stale_corpus_or_cohort_hash_fails_closed(fake_cohort):
    app=fake_cohort
    with app.get_db() as conn:
        plan=build_readonly_plan(conn,POOL)
        upgrade_catchup_receipts(conn,owner_gate=SCHEMA_GATE,execute=True)
        with pytest.raises(CatchupRefused,match="drift"):
            apply_owner_approved_plan(
                conn,POOL[:-1],expected_candidate_digest=plan.candidate_digest,
                expected_candidate_count=13,
                owner_gate=APPROVAL_ID,owner_batch_id="DISPOSABLE_TEST_BATCH",
                timestamp=STAMP)
    assert _state(app)==(0,0)


def test_repeating_complete_batch_is_idempotent(fake_cohort):
    app=fake_cohort
    with app.get_db() as conn:
        initial=build_readonly_plan(conn,POOL)
        upgrade_catchup_receipts(conn,owner_gate=SCHEMA_GATE,execute=True)
        out=apply_owner_approved_plan(
            conn,POOL,expected_candidate_digest=initial.candidate_digest,
            expected_candidate_count=13,owner_gate=APPROVAL_ID,
            owner_batch_id="DISPOSABLE_REPEAT_BATCH",timestamp=STAMP)
        assert out["granted"]==13
    with app.get_db() as conn:
        repeated=apply_owner_approved_plan(
            conn,POOL,expected_candidate_digest=initial.candidate_digest,
            expected_candidate_count=13,owner_gate=APPROVAL_ID,
            owner_batch_id="DISPOSABLE_REPEAT_BATCH",timestamp=STAMP)
        assert repeated["operation"]=="ALREADY_APPLIED"
        assert repeated["granted"]==0
        assert repeated["existing_receipts"]==13
    assert _state(app)==(13,0)


def test_disallowed_partial_or_rebound_batch_cannot_regrant(fake_cohort):
    app=fake_cohort
    with app.get_db() as conn:
        plan=build_readonly_plan(conn,POOL)
        upgrade_catchup_receipts(conn,owner_gate=SCHEMA_GATE,execute=True)
        apply_owner_approved_plan(
            conn,POOL,expected_candidate_digest=plan.candidate_digest,
            expected_candidate_count=13,owner_gate=APPROVAL_ID,
            owner_batch_id="DISPOSABLE_AUDIT_BATCH",timestamp=STAMP)
    with app.get_db() as conn:
        with pytest.raises(CatchupRefused,match="drift"):
            apply_owner_approved_plan(
                conn,POOL,expected_candidate_digest=plan.candidate_digest,
                expected_candidate_count=13,owner_gate=APPROVAL_ID,
                owner_batch_id="DIFFERENT_BATCH_SHOULD_FAIL",timestamp=STAMP)
        with pytest.raises(CatchupRefused,match="drift"):
            apply_owner_approved_plan(
                conn,POOL,expected_candidate_digest=plan.candidate_digest,
                expected_candidate_count=12,owner_gate=APPROVAL_ID,
                owner_batch_id="DISPOSABLE_AUDIT_BATCH",timestamp=STAMP)
    assert _state(app)==(13,0)


def test_outer_transaction_rollback_is_all_or_nothing(fake_cohort):
    app=fake_cohort
    with app.get_db() as conn:
        plan=build_readonly_plan(conn,POOL)
    with pytest.raises(RuntimeError,match="simulate outer transaction rollback"):
        with app.get_db() as conn:
            upgrade_catchup_receipts(conn,owner_gate=SCHEMA_GATE,execute=True)
            outcome=apply_owner_approved_plan(
                conn,POOL,expected_candidate_digest=plan.candidate_digest,
                expected_candidate_count=13,owner_gate=APPROVAL_ID,
                owner_batch_id="DISPOSABLE_ROLLBACK_BATCH",timestamp=STAMP)
            assert outcome["granted"]==13
            raise RuntimeError("simulate outer transaction rollback")
    assert _state(app)==(0,0)
    with app.get_db() as conn:
        assert not conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name=?",
            (RECEIPT_TABLE,),
        ).fetchone()


def test_conservative_membership_cannot_expand_batch(fake_cohort):
    app=fake_cohort
    with app.get_db() as conn:
        # 14th player has five EXACT memberships; make the sixth only
        # CONSERVATIVE. That player may have a visible continuity credit,
        # but must not receive a historical star in this exact-source batch.
        conn.execute(
            "INSERT INTO adventure_historical_mastery "
            "(user_id,question_id,baseline_version,source_mask,"
            "entitlement_source,captured_at,cutoff_literal,"
            "reconstruction_class) VALUES(?,?,?,?,?,?,?,?)",
            (83014,POOL[5],BASELINE_VERSION,4,
             "grandfathered_legacy_progress",STAMP,"2026-08-29T13:17:30",
             "CONSERVATIVE_GRANDFATHERED"),
        )
        plan=build_readonly_plan(conn,POOL)
        assert len(plan.candidates)==13
        assert plan.conservative_needed==1
        upgrade_catchup_receipts(conn,owner_gate=SCHEMA_GATE,execute=True)
        with pytest.raises(CatchupRefused,match="conservative"):
            apply_owner_approved_plan(
                conn,POOL,expected_candidate_digest=plan.candidate_digest,
                expected_candidate_count=13,owner_gate=APPROVAL_ID,
                owner_batch_id="DISPOSABLE_BLOCK_CONSERVATIVE",timestamp=STAMP)
    assert _state(app)==(0,0)
