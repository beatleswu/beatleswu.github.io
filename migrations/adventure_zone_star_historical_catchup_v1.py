"""Independent Owner-approved historical Zone-2nd-star audit receipt schema.

NEVER called by app.init_db(); granting historical entitlements cannot
be disguised as a new map answer. Does not commit: an approved runner owns
the isolated transaction, migration checksum and rollback verification.
"""
from __future__ import annotations

SCHEMA_ID="incident019b_historical_star_catchup_v1"
RECEIPT_TABLE="adventure_zone_star_historical_catchup_receipts"
OWNER_GATE="OWNER_APPROVED_019B_HISTORY_60PCT"


def validate(conn):
    rows=conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=?",
        (RECEIPT_TABLE,),
    ).fetchall()
    found={str(row[0]) for row in rows}
    required={
        "user_id","zone_key","star_number","baseline_version","pool_sha256",
        "pool_count","required_correct","distinct_correct","receipt_sha256",
        "candidate_digest","prior_row_existed","prior_earned_stars",
        "prior_updated_at",
        "owner_batch_id","granted_at",
    }
    if not found:
        return {"present":False,"missing":[RECEIPT_TABLE]}
    if found!=required:
        raise ValueError("historical catch-up receipt schema does not match reviewed contract")
    constraints=conn.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid=?::regclass",
        (f"public.{RECEIPT_TABLE}",),
    ).fetchall()
    names={str(row[0]) for row in constraints}
    if f"{RECEIPT_TABLE}_pkey" not in names:
        raise ValueError("missing historical receipt primary key")
    return {"present":True,"missing":[]}


def upgrade(conn, *, owner_gate, execute=False):
    if owner_gate != OWNER_GATE:
        raise PermissionError("independent Owner gate required for historical receipt migration")
    if not execute:
        return {"status":"DRY_RUN","schema_id":SCHEMA_ID,
                "already_present":validate(conn)["present"]}
    # This additive operation is to be applied only in an approved maintenance
    # window. The receipt source remains disjoint from normal Map event ledger.
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS public.{RECEIPT_TABLE} (
           user_id INTEGER NOT NULL,
           zone_key TEXT NOT NULL,
           star_number INTEGER NOT NULL CHECK(star_number=2),
           baseline_version TEXT NOT NULL,
           pool_sha256 TEXT NOT NULL CHECK(length(pool_sha256)=64),
           pool_count INTEGER NOT NULL CHECK(pool_count>0),
           required_correct INTEGER NOT NULL CHECK(required_correct>0),
           distinct_correct INTEGER NOT NULL CHECK(distinct_correct>=required_correct),
           receipt_sha256 TEXT NOT NULL UNIQUE CHECK(length(receipt_sha256)=64),
           candidate_digest TEXT NOT NULL CHECK(length(candidate_digest)=64),
           prior_row_existed BOOLEAN NOT NULL,
           prior_earned_stars INTEGER CHECK(prior_earned_stars BETWEEN 0 AND 1),
           prior_updated_at TEXT,
           CONSTRAINT prior_row_evidence_consistent CHECK(
             (prior_row_existed AND prior_earned_stars IS NOT NULL
              AND prior_updated_at IS NOT NULL)
              OR (NOT prior_row_existed AND prior_earned_stars IS NULL
                  AND prior_updated_at IS NULL)
           ),
           owner_batch_id TEXT NOT NULL,
           granted_at TEXT NOT NULL,
           PRIMARY KEY(user_id,zone_key,star_number)
        )"""
    )
    observed=validate(conn)
    if not observed["present"]:
        raise RuntimeError("historical receipt schema not available after migration")
    return {"status":"APPLIED","schema_id":SCHEMA_ID,
            "present":True,"transaction_committed_by_caller":False}
