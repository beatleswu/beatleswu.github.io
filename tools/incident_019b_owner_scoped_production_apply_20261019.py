"""One-shot OWNER-APPROVED Zone 1 second-star historical data correction.

This is a *maintenance process*, not a product deployment or cron.
The caller must independently verify the full PG backup on the host, stage
SHA-verified reviewed sources, and invoke with explicit immutable arguments.
No credentials are copied out of the running app container. Any mismatch
before COMMIT rolls back the entire PostgreSQL transaction.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

import psycopg2
from psycopg2.extras import DictCursor
from db import PostgresConnectionWrapper

from tools.incident_019b_historical_second_star_catchup import (
    ZONE, APPROVAL_ID, build_readonly_plan, apply_owner_approved_plan,
    _canonical_pool_from_local_files, RECEIPT_TABLE, CatchupRefused,
)
from migrations.adventure_zone_star_historical_catchup_v1 import (
    upgrade as migrate_historical_receipt, OWNER_GATE as MIGRATE_GATE,
    validate as validate_receipt_schema,
)

CANONICAL_POOL_COUNT = 1939
CANONICAL_SECOND_THRESHOLD = 1164
APPROVED_CLEARED = 23
APPROVED_CANDIDATES = 13
APPROVED_SHA = "279efb96aba3fc515250c32134f391d4d989b7409fd6bce2f739b0bfc982eb12"
APPROVED_POOL_SHA = "5dd5ccf622873128fd7d9a66877acb60b58b84d00e333f222751b452c1d37248"
APPROVED_OWNER_SCOPE = "20261019-owner-approved-first-zone-exact-13-second-star-only"
TABLES_UNCHANGED = (
    "adventure_boss_progress",
    "adventure_zone_unlocks",
    "adventure_zone_star_earnings",
    "user_stats",
    "shop_inventory",
    "player_inventory",
    "player_wardrobe",
    "pet_inventory",
    "badges_earned",
    "currency_log",
    "review_log",
)


def fail(message):
    raise CatchupRefused(message)


def norm(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), default=str)


def fingerprint(value):
    return hashlib.sha256(norm(value).encode("utf-8")).hexdigest()


def select(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def secure_plan(conn, pool, *, expected_digest):
    p = build_readonly_plan(conn, pool)
    if (
        p.zone != ZONE or p.pool_count != CANONICAL_POOL_COUNT
        or p.threshold != CANONICAL_SECOND_THRESHOLD
        or p.cleared_users != APPROVED_CLEARED
        or p.qualified_users != APPROVED_CANDIDATES
        or len(p.candidates) != APPROVED_CANDIDATES
        or p.conservative_needed != 0
        or p.possible_third_star != 0
        or p.pool_sha256 != APPROVED_POOL_SHA
        or p.candidate_digest != expected_digest
    ):
        fail("FROZEN_SCOPE_DRIFT — do not perform production corrections")
    if any(c.legacy_stars != 1 or c.authority_stars > 1 for c in p.candidates):
        fail("UNEXPECTED_LEGACY_STAR_OR_AUTHORITY")
    return p


def capture_unchanged(conn, user_ids, candidates):
    """Hashes only; no player data is returned in stdout or the receipt."""
    marks = ",".join("?" for _ in user_ids)
    tables = {row["table_name"] for row in conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public'",
    ).fetchall()}
    snapshots = {}
    for t in TABLES_UNCHANGED:
        if t not in tables:
            # Optional domain tables are legitimately absent in some
            # Product database revisions; no attempt is made to create them.
            snapshots[t] = "TABLE_ABSENT"
            continue
        data = select(conn, f"SELECT * FROM {t} WHERE user_id IN ({marks})", user_ids)
        snapshots[t] = fingerprint(sorted((norm(row) for row in data)))
    # One controlled table is allowed to change, but NOT rows for other
    # accounts/zones. Compare full SQL read-view excluding approved targets.
    approved = tuple(c.user_id for c in candidates)
    approved_marks = ",".join("?" for _ in approved)
    other = select(conn,
        "SELECT * FROM adventure_zone_star_progress "
        f"WHERE NOT (zone_key=? AND user_id IN ({approved_marks}))",
        (ZONE,*approved),
    )
    snapshots["star_authority_unapproved_rows"]=fingerprint(
        sorted(norm(row) for row in other))
    return snapshots


def zone_authority(conn, user_ids):
    marks = ",".join("?" for _ in user_ids)
    rows = conn.execute(
        "SELECT user_id,earned_stars FROM adventure_zone_star_progress "
        f"WHERE zone_key=? AND user_id IN ({marks})",
        (ZONE,*user_ids),
    ).fetchall()
    return {int(r["user_id"]):int(r["earned_stars"]) for r in rows}


def audit_receipts(conn, plan, batch_id, before_authority):
    rows=conn.execute(
        f"SELECT * FROM {RECEIPT_TABLE} WHERE owner_batch_id=? "
        "AND candidate_digest=?",
        (batch_id,plan.candidate_digest),
    ).fetchall()
    if len(rows)!=APPROVED_CANDIDATES:
        fail("WRONG_COMMITTED_RECEIPT_COUNT")
    candidate_map={c.user_id:c for c in plan.candidates}
    for row in rows:
        uid=int(row["user_id"])
        if uid not in candidate_map or row["star_number"]!=2:
            fail("UNAPPROVED_RECEIPT")
        if row["pool_sha256"]!=plan.pool_sha256 or             int(row["pool_count"])!=CANONICAL_POOL_COUNT or             int(row["required_correct"])!=CANONICAL_SECOND_THRESHOLD or             int(row["distinct_correct"])!=candidate_map[uid].distinct_correct:
            fail("RECIPIENT_CREDIT_OR_POOL_DRIFT")
        prev=before_authority.get(uid)
        if bool(row["prior_row_existed"]) != (prev is not None):
            fail("PREVIOUS_ROW_EXISTENCE_NOT_AUDITED")
        if prev is not None and int(row["prior_earned_stars"])!=prev:
            fail("PREVIOUS_STAR_LEVEL_NOT_AUDITED")
        if prev is None and row["prior_earned_stars"] is not None:
            fail("FABRICATED_PREVIOUS_STAR")
    return len(rows)


def run(args):
    if args.owner_scope != APPROVED_OWNER_SCOPE:
        fail("NO_OWNER_SCOPED_AUTHORIZATION")
    if args.expected_candidate_digest != APPROVED_SHA:
        fail("NO_REVIEWED_CANDIDATE_DIGEST")
    if args.backup_sha256 != (
        "77237595ff4aea9f946a13e2ffc44e436c825a74f6c7bc7f2e88acc28216effe"
    ):
        fail("NO_VERIFIED_PREWRITE_BACKUP")
    if not args.batch_id.startswith("HISTORICAL_ZONE1_13_20261019_"):
        fail("UNREVIEWED_BATCH_ID")
    if os.environ.get("GO_ADVENTURE_RETROACTIVE_MILESTONE_POLICY","hold").lower() != "hold":
        fail("PRODUCTION_RETROACTIVE_POLICY_CHANGED")
    pool = _canonical_pool_from_local_files(args.canonical_root)
    database_url=os.environ.get("DATABASE_URL")
    if not database_url:
        fail("DATABASE_URL_UNAVAILABLE")
    raw=psycopg2.connect(database_url,cursor_factory=DictCursor,connect_timeout=8)
    committed=False
    out={}
    try:
        raw.set_session(isolation_level="SERIALIZABLE",
                        readonly=False,autocommit=False)
        conn=PostgresConnectionWrapper(raw)
        # Safe production transaction: fail rather than wait indefinitely.
        conn.execute("SET LOCAL lock_timeout = '6s'")
        conn.execute("SET LOCAL statement_timeout = '90s'")
        plan=secure_plan(conn,pool,expected_digest=args.expected_candidate_digest)
        all_users=tuple(int(row["user_id"]) for row in conn.execute(
            "SELECT user_id FROM adventure_boss_progress "
            "WHERE zone_key=? AND cleared=1 ORDER BY user_id",
            (ZONE,),
        ).fetchall())
        if len(all_users)!=APPROVED_CLEARED:
            fail("LORD_CLEARED_COHORT_CHANGED")
        candidate_ids={c.user_id for c in plan.candidates}
        initial=zone_authority(conn,all_users)
        untouched_before={u:initial.get(u) for u in all_users
                          if u not in candidate_ids}
        before_hashes=capture_unchanged(conn,all_users,plan.candidates)

        migrate=migrate_historical_receipt(conn,owner_gate=MIGRATE_GATE,execute=True)
        if migrate.get("status")!="APPLIED" or not validate_receipt_schema(conn)["present"]:
            fail("AUDIT_MIGRATION_NOT_APPLIED")
        when=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        applied=apply_owner_approved_plan(
            conn,pool,expected_candidate_digest=plan.candidate_digest,
            expected_candidate_count=APPROVED_CANDIDATES,
            owner_gate=APPROVAL_ID,owner_batch_id=args.batch_id,
            timestamp=when,
        )
        if applied.get("granted")!=APPROVED_CANDIDATES:
            fail("MISMATCHED_GRANT_COUNT")
        after=zone_authority(conn,all_users)
        if any(after.get(u)!=2 for u in candidate_ids):
            fail("CANDIDATE_DID_NOT_RECEIVE_EXACTLY_STAR_TWO")
        if {u:after.get(u) for u in untouched_before} != untouched_before:
            fail("NON_CANDIDATE_STAR_WAS_MODIFIED")
        if any(stars>=3 for stars in after.values()):
            fail("THIRD_STAR_WAS_ISSUED")
        if before_hashes!=capture_unchanged(conn,all_users,plan.candidates):
            fail("UNAPPROVED_GAME_DOMAIN_STATE_CHANGED")
        receipt_count=audit_receipts(conn,plan,args.batch_id,initial)
        fresh=build_readonly_plan(conn,pool)
        if fresh.candidates or fresh.qualified_users!=APPROVED_CANDIDATES:
            fail("POST_MUTATION_ELIGIBILITY_INVARIANT_FAILED")
        out={
            "operation":"HISTORICAL_FIRST_ZONE_SECOND_STAR",
            "owner_scope":APPROVED_OWNER_SCOPE,
            "batch_id":args.batch_id,
            "candidate_digest":APPROVED_SHA,
            "pool_sha256":APPROVED_POOL_SHA,
            "pool_count":CANONICAL_POOL_COUNT,
            "threshold":CANONICAL_SECOND_THRESHOLD,
            "first_zone_cleared":APPROVED_CLEARED,
            "star_two_granted":APPROVED_CANDIDATES,
            "nonrecipients_unchanged":len(untouched_before),
            "third_stars_granted":0,
            "historical_audit_receipts":receipt_count,
            "protected_domain_sha256":fingerprint(before_hashes),
            "prewrite_backup_sha256":args.backup_sha256,
            "commit_utc":when,
            "other_rewards_xp_coins_unchanged":True,
            "recovery_prior_star_levels_recorded":True,
        }
        if not args.apply:
            raw.rollback()
            out["result"]="VALIDATED_BUT_ROLLED_BACK_DRYRUN"
            return out
        raw.commit()
        committed=True
    except Exception:
        if not committed:
            raw.rollback()
        raise
    finally:
        raw.close()
    if not committed:
        fail("POST_COMMIT_NOT_REACHED")
    # Independent post-commit read in a NEW PostgreSQL session.
    ro=psycopg2.connect(database_url,cursor_factory=DictCursor,connect_timeout=8)
    try:
        ro.set_session(readonly=True)
        conn=PostgresConnectionWrapper(ro)
        result=conn.execute(
            "SELECT COUNT(*) AS n FROM adventure_zone_star_progress "
            "WHERE zone_key=? AND earned_stars=2 AND user_id IN "
            "(SELECT user_id FROM adventure_boss_progress "
            " WHERE zone_key=? AND cleared=1)",
            (ZONE,ZONE),
        ).fetchone()
        receipts=conn.execute(
            f"SELECT COUNT(*) AS n FROM {RECEIPT_TABLE} "
            "WHERE owner_batch_id=? AND candidate_digest=? AND star_number=2",
            (args.batch_id,APPROVED_SHA),
        ).fetchone()
        if int(result["n"])!=APPROVED_CANDIDATES or int(receipts["n"])!=APPROVED_CANDIDATES:
            fail("POST_COMMIT_READONLY_RECHECK_FAILED")
    finally:
        ro.rollback()
        ro.close()
    out["result"]="COMMITTED_AND_VERIFIED_ON_NEW_READONLY_CONNECTION"
    return out


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true",required=True)
    parser.add_argument("--owner-scope",required=True)
    parser.add_argument("--expected-candidate-digest",required=True)
    parser.add_argument("--backup-sha256",required=True)
    parser.add_argument("--batch-id",required=True)
    parser.add_argument("--canonical-root",default="/app")
    args=parser.parse_args()
    try:
        print(json.dumps(run(args),sort_keys=True,ensure_ascii=True))
    except Exception as e:
        # No identifying user data should leave the maintenance process.
        print("PRODUCTION_OWNER_STAR_CORRECTION_REFUSED",
              type(e).__name__,str(e),file=sys.stderr)
        sys.exit(1)
