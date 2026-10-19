"""Owner-gated, provenance-safe historical second-star catch-up.

DRY RUN by default. The normal Map/Boss Zone-star event ledger is never
forged. Historical entitlements have their OWN receipt table. An apply must
happen only in a separately approved transactional maintenance window.

The first Zone has an Owner-locked 60% denominator over ALL canonical
enabled questions in that Zone, not answered questions or Lord question count.
The historical baseline must be FROZEN, READY and EXACT_RECONSTRUCTABLE.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from adventure_progress_compatibility import BASELINE_VERSION
from adventure_zone_progression_authority import second_star_requirement

ZONE = "k26_30"
LEGACY_SOURCE = "grandfathered_legacy_progress"
EXACT = "EXACT_RECONSTRUCTABLE"
RECEIPT_TABLE = "adventure_zone_star_historical_catchup_receipts"
LOCK_KEY = 773310060
SOURCE = "exact_reconstructed_historical_60pct"
APPROVAL_ID = "OWNER_APPROVED_019B_HISTORY_60PCT"

class CatchupRefused(RuntimeError):
    pass

@dataclass(frozen=True)
class Candidate:
    user_id: int
    distinct_correct: int
    exact_historical_correct: int
    trusted_map_correct: int
    legacy_stars: int
    authority_stars: int

@dataclass(frozen=True)
class Plan:
    zone: str
    baseline_version: str
    pool_count: int
    threshold: int
    pool_sha256: str
    candidate_digest: str
    candidates: tuple[Candidate, ...]
    cleared_users: int
    qualified_users: int
    conservative_needed: int
    possible_third_star: int

    def summary(self) -> dict[str, Any]:
        return {
            "verdict": "DRY_RUN_ONLY_NOT_A_GRANT",
            "zone_key": self.zone,
            "baseline_version": self.baseline_version,
            "pool_count": self.pool_count,
            "second_star_required": self.threshold,
            "cleared_users": self.cleared_users,
            "qualified_users": self.qualified_users,
            "candidates_missing_second_star": len(self.candidates),
            "conservative_records_needed_for_candidate": self.conservative_needed,
            "potential_100pct_review_only": self.possible_third_star,
            "pool_sha256": self.pool_sha256,
            "candidate_digest": self.candidate_digest,
            "production_mutated": False,
        }


def _fingerprint(blob: Any) -> str:
    return hashlib.sha256(json.dumps(
        blob, ensure_ascii=True, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _value(row: Any, name: str, index: int) -> Any:
    try:
        return row[name]
    except (TypeError, KeyError, IndexError):
        return row[index]


def build_readonly_plan(conn: Any, canonical_question_ids: Iterable[int], *, zone: str = ZONE) -> Plan:
    """Return an exact, privacy-safe cohort; execute only SELECT statements."""
    if zone != ZONE:
        raise CatchupRefused("only explicit Owner-reviewed Zone 1 is in scope")
    pool = tuple(sorted({int(q) for q in canonical_question_ids}))
    if not pool or any(q <= 0 for q in pool):
        raise CatchupRefused("canonical question set unavailable")
    threshold = second_star_requirement(len(pool))
    pool_hash = _fingerprint(pool)
    baseline = conn.execute(
        "SELECT status, membership_count, exact_membership_count, "
        "conservative_membership_count "
        "FROM adventure_historical_mastery_baseline "
        "WHERE baseline_version=?",
        (BASELINE_VERSION,),
    ).fetchone()
    if not baseline or _value(baseline, "status", 0) != "BASELINE_READY":
        raise CatchupRefused("frozen historical baseline is not ready")

    cleared = conn.execute(
        "SELECT b.user_id,b.stars,COALESCE(s.earned_stars,0) AS authority_stars "
        "FROM adventure_boss_progress b "
        "LEFT JOIN adventure_zone_star_progress s "
        "ON s.user_id=b.user_id AND s.zone_key=b.zone_key "
        "WHERE b.zone_key=? AND b.cleared=1 ORDER BY b.user_id",
        (zone,),
    ).fetchall()
    if not cleared:
        raise CatchupRefused("no first-star / Lord-clear cohort present")
    owned: dict[int,tuple[int,int]] = {
        int(_value(r,"user_id",0)):
            (int(_value(r,"stars",1) or 0),
             int(_value(r,"authority_stars",2) or 0))
        for r in cleared
    }
    for u,(legacy,authority) in owned.items():
        if max(legacy, authority) < 1:
            raise CatchupRefused("cleared Boss without first-star entitlement")

    # All read sources are scoped to exact canonical Zone question ids and
    # to Lord-cleared accounts. No name/email/secret fields are read.
    users = tuple(sorted(owned))
    historical: dict[int,set[int]] = {u:set() for u in users}
    all_hist: dict[int,set[int]] = {u:set() for u in users}
    trusted: dict[int,set[int]] = {u:set() for u in users}
    marks = ",".join("?" for _ in pool)
    user_marks = ",".join("?" for _ in users)
    histories = conn.execute(
        "SELECT user_id,question_id,reconstruction_class "
        "FROM adventure_historical_mastery "
        f"WHERE user_id IN ({user_marks}) AND question_id IN ({marks}) "
        "AND baseline_version=? AND source_mask>0 AND entitlement_source=?",
        (*users,*pool,BASELINE_VERSION,LEGACY_SOURCE),
    ).fetchall()
    for r in histories:
        u=int(_value(r,"user_id",0))
        q=int(_value(r,"question_id",1))
        klass=str(_value(r,"reconstruction_class",2))
        all_hist[u].add(q)
        if klass == EXACT:historical[u].add(q)
    reviews = conn.execute(
        "SELECT DISTINCT user_id,question_id FROM review_log "
        f"WHERE user_id IN ({user_marks}) AND question_id IN ({marks}) "
        "AND grade>=3 AND source_context LIKE ?",
        (*users,*pool,"mbv1:%"),
    ).fetchall()
    for r in reviews:
        trusted[int(_value(r,"user_id",0))].add(int(_value(r,"question_id",1)))

    candidates=[]
    qualified=0
    conservative_needed=0
    possible_third=0
    for uid in users:
        # ONLY exact frozen pre-cutoff history plus newly server-settled Map.
        exact=historical[uid] | trusted[uid]
        all_legacy=all_hist[uid] | trusted[uid]
        current=max(owned[uid])
        if len(exact)>=len(pool):possible_third+=1
        if len(exact)>=threshold:
            qualified+=1
            if current<2:
                candidates.append(Candidate(
                    uid,len(exact),len(historical[uid]),len(trusted[uid]),
                    owned[uid][0],owned[uid][1]))
        elif len(all_legacy)>=threshold and current<2:
            conservative_needed+=1
    candidates=tuple(sorted(candidates,key=lambda c:c.user_id))
    cohort_digest=_fingerprint({
        "zone":zone,"baseline":BASELINE_VERSION,
        "pool_hash":pool_hash,"threshold":threshold,
        "members":[(c.user_id,c.distinct_correct,c.exact_historical_correct,
                    c.trusted_map_correct,c.legacy_stars,c.authority_stars)
                   for c in candidates],
    })
    return Plan(
        zone,BASELINE_VERSION,len(pool),threshold,pool_hash,
        cohort_digest,candidates,len(users),qualified,
        conservative_needed,possible_third)


def _verify_receipt_schema(conn: Any) -> None:
    # Do NOT silently create a production migration from a report.
    from migrations.adventure_zone_star_historical_catchup_v1 import validate
    if not validate(conn)["present"]:
        raise CatchupRefused("separate Owner-approved historical receipt migration is missing")


def apply_owner_approved_plan(
    conn: Any, canonical_question_ids: Iterable[int], *,
    expected_candidate_digest: str,
    expected_candidate_count: int,
    owner_gate: str,
    owner_batch_id: str,
    timestamp: str,
) -> dict[str, Any]:
    """Atomic mutation core. NEVER called by app/init_db or report CLI.

    Caller must explicitly start/commit one transaction after separately
    obtaining Owner authorization; failed assertions must rollback it.
    """
    if owner_gate != APPROVAL_ID or not owner_batch_id.strip():
        raise CatchupRefused("no explicit Owner release gate")
    if not expected_candidate_digest or len(expected_candidate_digest)!=64:
        raise CatchupRefused("immutable dry-run digest required")
    if expected_candidate_count <= 0:
        raise CatchupRefused("positive reviewed cohort count required")
    # PostgreSQL transaction advisory lock for concurrent / repeated runs.
    conn.execute("SELECT pg_advisory_xact_lock(?)",(LOCK_KEY,))
    plan=build_readonly_plan(conn,canonical_question_ids)
    if plan.candidate_digest!=expected_candidate_digest:
        # An exact repeat of the already-committed batch is a clean NO-OP.
        # A different/partial/mixed batch, however, must fail closed.
        _verify_receipt_schema(conn)
        if plan.candidates:
            raise CatchupRefused("live candidate set has drifted since approval")
        rows=conn.execute(
            f"SELECT user_id,zone_key,star_number,pool_sha256 "
            f"FROM {RECEIPT_TABLE} WHERE owner_batch_id=? AND candidate_digest=?",
            (owner_batch_id,expected_candidate_digest),
        ).fetchall()
        if len(rows)!=expected_candidate_count:
            raise CatchupRefused("no matching complete prior batch; cohort drift")
        for row in rows:
            uid=int(_value(row,"user_id",0))
            if str(_value(row,"zone_key",1))!=plan.zone or int(_value(row,"star_number",2))!=2:
                raise CatchupRefused("invalid historical receipt in previously applied batch")
            if str(_value(row,"pool_sha256",3))!=plan.pool_sha256:
                raise CatchupRefused("pool changed; refuse replay")
            current=conn.execute(
                "SELECT earned_stars FROM adventure_zone_star_progress "
                "WHERE user_id=? AND zone_key=?",
                (uid,plan.zone),
            ).fetchone()
            if not current or int(_value(current,"earned_stars",0))<2:
                raise CatchupRefused("prior receipt is inconsistent with star authority")
        return {"operation":"ALREADY_APPLIED","granted":0,
                "existing_receipts":len(rows),"digest":expected_candidate_digest,
                "owner_batch_id":owner_batch_id,
                "transaction_committed_by_caller":False}
    if len(plan.candidates)!=expected_candidate_count:
        raise CatchupRefused("approved cohort size has drifted")
    if plan.conservative_needed:
        raise CatchupRefused("conservative reconstruction needs separate Owner decision")
    if plan.possible_third_star:
        # This operation does not claim the 100% milestone automatically.
        raise CatchupRefused("100% cases need an independent three-star catch-up review")
    _verify_receipt_schema(conn)
    granted=0
    for c in plan.candidates:
        # Lock existing first-star evidence, no resurrected/forged Boss clears.
        boss=conn.execute(
            "SELECT cleared,stars FROM adventure_boss_progress "
            "WHERE user_id=? AND zone_key=? FOR UPDATE",
            (c.user_id,plan.zone),
        ).fetchone()
        if not boss or int(_value(boss,"cleared",0))!=1 or int(_value(boss,"stars",1))<1:
            raise CatchupRefused("first-star state changed during catch-up")
        # Existing award ledger must not already contain star2. Its event
        # source is reserved for real Map/Boss operations.
        existing=conn.execute(
            "SELECT 1 FROM adventure_zone_star_earnings "
            "WHERE user_id=? AND zone_key=? AND star_number=2",
            (c.user_id,plan.zone),
        ).fetchone()
        if existing:
            raise CatchupRefused("star2 already has an actual award event")
        previous=conn.execute(
            "SELECT earned_stars,updated_at FROM adventure_zone_star_progress "
            "WHERE user_id=? AND zone_key=? FOR UPDATE",
            (c.user_id,plan.zone),
        ).fetchone()
        previous_exists=previous is not None
        previous_stars=(int(_value(previous,"earned_stars",0))
                        if previous_exists else None)
        previous_updated=(str(_value(previous,"updated_at",1))
                          if previous_exists else None)
        if previous_exists and previous_stars not in (0,1):
            raise CatchupRefused("already-awarded or invalid previous star state")
        receipt_id=_fingerprint({
            "domain":"historical_zone_second_star",
            "zone":plan.zone,"uid":c.user_id,
            "baseline":plan.baseline_version,"pool":plan.pool_sha256,
            "batch":owner_batch_id,
        })
        receipt=conn.execute(
            f"INSERT INTO {RECEIPT_TABLE} "
            "(user_id,zone_key,star_number,baseline_version,pool_sha256,"
            "pool_count,required_correct,distinct_correct,receipt_sha256,"
            "candidate_digest,prior_row_existed,prior_earned_stars,"
            "prior_updated_at,owner_batch_id,granted_at) "
            "VALUES(?,?,2,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (c.user_id,plan.zone,plan.baseline_version,plan.pool_sha256,
             plan.pool_count,plan.threshold,c.distinct_correct,
             receipt_id,plan.candidate_digest,previous_exists,
             previous_stars,previous_updated,owner_batch_id,timestamp),
        )
        if receipt.rowcount!=1:
            raise CatchupRefused("historical backfill receipt already exists")
        updated=conn.execute(
            "INSERT INTO adventure_zone_star_progress"
            "(user_id,zone_key,earned_stars,updated_at) "
            "VALUES(?,?,2,?) ON CONFLICT(user_id,zone_key) DO UPDATE SET "
            "earned_stars=2,updated_at=excluded.updated_at "
            "WHERE adventure_zone_star_progress.earned_stars<2",
            (c.user_id,plan.zone,timestamp),
        )
        if updated.rowcount != 1:
            # Concurrent true Map award won the row; caller must rollback
            # the historical receipt instead of manufacturing two sources.
            raise CatchupRefused("concurrent star award or authority drift")
        granted+=1
    return {
        "operation":"DRYRUN_PREAPPROVED_MUTATION_CORE",
        "granted":granted,"digest":plan.candidate_digest,
        "owner_batch_id":owner_batch_id,
        "transaction_committed_by_caller":False,
    }


def _canonical_pool_from_local_files(root: str) -> tuple[int, ...]:
    """Read the deployed canonical pool without importing the Flask app."""
    from pathlib import Path
    import ast
    source=ast.parse((Path(root)/"app.py").read_text(encoding="utf-8"))
    zones=next(ast.literal_eval(n.value) for n in source.body
        if isinstance(n,ast.Assign) and any(
            isinstance(t,ast.Name) and t.id=="ADVENTURE_ZONES" for t in n.targets))
    books=next(z["books"] for z in zones if z["key"]==ZONE)
    entries=json.loads((Path(root)/"data"/"questions.json").read_text(encoding="utf-8"))
    ids=[int(q["id"]) for q in entries
         if q.get("enabled",True) and q.get("topic") in books]
    if len(ids)!=len(set(ids)):
        raise CatchupRefused("canonical question IDs are not unique")
    return tuple(ids)


def _main_dry_run_only() -> None:
    import argparse
    import os
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper
    parser=argparse.ArgumentParser(
        description="READ-ONLY anonymous cohort audit; never grants stars")
    parser.add_argument("--dry-run",action="store_true",required=True)
    parser.add_argument("--root",default="/app")
    args=parser.parse_args()
    url=os.environ.get("DATABASE_URL")
    if not url:
        raise CatchupRefused("DATABASE_URL unavailable")
    raw=psycopg2.connect(url,cursor_factory=DictCursor,connect_timeout=8)
    try:
        # The server refuses INSERT/DDL regardless of the script. This
        # dry-run entrypoint has no --apply switch or user-list output.
        raw.set_session(readonly=True)
        conn=PostgresConnectionWrapper(raw)
        plan=build_readonly_plan(conn,_canonical_pool_from_local_files(args.root))
        print(json.dumps(plan.summary(),sort_keys=True))
        raw.rollback()
    finally:
        raw.close()


if __name__=="__main__":
    _main_dry_run_only()
