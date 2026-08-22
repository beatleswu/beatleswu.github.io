"""D5E Premium claim idempotency, provenance, and lineage tests."""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import urlsplit

import pytest

from migrations.domain_event_outbox_v1 import (
    downgrade_for_isolated_test as downgrade_outbox,
    upgrade as upgrade_outbox,
)
from migrations.premium_claim_lineage_v1 import (
    downgrade_for_isolated_test as downgrade_premium,
    upgrade as upgrade_premium,
    validate_schema,
)
from premium_provenance import grant_premium_with_provenance
from premium_reward_claim_runtime import PremiumRewardClaimService


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _stamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=UTC)


class FakeCatalog:
    def __init__(self, reward_id: str = "cosmetic.monthly.2026-08", *, functional: bool = False):
        self.reward_id = reward_id
        self.functional = functional

    def resolve_period_reward(self, *, period_key, reward_catalog_key, requested_reward_id=None):
        del period_key, reward_catalog_key
        if requested_reward_id and requested_reward_id != self.reward_id:
            return None
        return {
            "reward_id": self.reward_id,
            "reward_type": "TITLE",
            "ownership_authority": "player_wardrobe",
            "pure_presentation": True,
            "functional_effect_count": 1 if self.functional else 0,
            "combat_authority": "NO",
            "effect_flags": {"xp": 1 if self.functional else 0},
        }


def _create_base(conn):
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "CREATE TABLE users ("
        "id INTEGER PRIMARY KEY, plan TEXT NOT NULL, premium_until TEXT, "
        "is_admin INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE player_wardrobe ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "item_id TEXT NOT NULL, obtained_at TEXT NOT NULL, "
        "source TEXT NOT NULL DEFAULT 'drop', UNIQUE(user_id,item_id))"
    )


def _open_sqlite():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    _create_base(conn)
    upgrade_outbox(conn)
    upgrade_premium(conn)
    conn.commit()
    return conn


def _add_user(conn, user_id: int, *, plan: str = "premium", premium_until: str | None = "2026-12-31T23:59:59+00:00"):
    conn.execute("INSERT INTO users(id,plan,premium_until) VALUES(?,?,?)", (user_id, plan, premium_until))


def _add_verified_grant(conn, user_id: int, *, plan_term: str = "MONTHLY", valid_until: str | None = "2026-12-31T23:59:59+00:00"):
    return grant_premium_with_provenance(
        conn,
        user_id=user_id,
        source_class="VERIFIED_PAID",
        source_reference=f"payment:{user_id}",
        granted_by_or_system_source="payment_settlement",
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until=valid_until,
        commercial_reward_eligibility="ALLOWED",
        provider="test-provider",
        currency="TWD",
        amount="299",
        plan_key="premium.monthly.test",
        plan_term=plan_term,
        payment_order_id=1000 + user_id,
    )


def _add_period(conn, *, key: str = "2026-08", window_end: str = "2026-10-31T23:59:59+00:00", grace: int = 90):
    conn.execute(
        """INSERT INTO premium_reward_periods(
               period_key,reward_type,reward_catalog_key,period_starts_at,
               period_ends_at,claim_window_starts_at,claim_window_ends_at,
               annual_grace_days,eligibility_policy_version,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            key,
            "MONTHLY_COLLECTION_CREDIT",
            f"catalog:{key}",
            "2026-08-01T00:00:00+00:00",
            "2026-08-31T23:59:59+00:00",
            "2026-08-01T00:00:00+00:00",
            window_end,
            grace,
            "premium_v2_verified_paid_v1",
            "2026-08-01T00:00:00+00:00",
        ),
    )


def _service(conn, *, catalog=None):
    return PremiumRewardClaimService(conn, catalog_resolver=catalog or FakeCatalog())


@pytest.fixture
def db():
    conn = _open_sqlite()
    _add_user(conn, 1)
    _add_verified_grant(conn, 1)
    _add_period(conn)
    conn.commit()
    yield conn
    conn.close()


def _claim(conn, **kwargs):
    catalog = kwargs.pop("catalog", None)
    result = _service(conn, catalog=catalog).claim_period_reward(
        1,
        "2026-08",
        now=NOW,
        **kwargs,
    )
    conn.commit()
    return result


def test_schema_and_lineage_contract_is_additive(db):
    schema = validate_schema(db)
    assert schema["valid"] is True
    assert schema["missing_tables"] == []
    assert schema["missing_columns"] == {}
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0


def test_first_claim_is_atomic_and_emits_two_distinct_lineage_events(db):
    result = _claim(db, operation_id="claim-001")

    assert result.status == "GRANTED"
    assert result.created is True
    assert result.ownership_created is True
    assert result.premium_event_id
    assert result.item_acquisition_event_id
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM premium_claim_operations WHERE operation_status='SUCCESS'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='PREMIUM_CLAIM'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE published_at IS NULL").fetchone()[0] == 2
    event = db.execute(
        "SELECT payload,source_event_id FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'"
    ).fetchone()
    assert "premium_source" in event[0]
    assert event[1] == result.premium_event_id


def test_same_operation_replays_original_result_without_mutation_or_event_duplication(db):
    first = _claim(db, operation_id="claim-retry")
    retry = _claim(db, operation_id="claim-retry")

    assert retry.status == "GRANTED"
    assert retry.created is False
    assert retry.claim_id == first.claim_id
    assert retry.premium_event_id == first.premium_event_id
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 2


def test_different_operation_same_period_does_not_duplicate_business_claim(db):
    first = _claim(db, operation_id="claim-a")
    second = _claim(db, operation_id="claim-b")

    assert second.status == "GRANTED"
    assert second.created is False
    assert second.claim_id == first.claim_id
    assert db.execute("SELECT COUNT(*) FROM premium_claim_operations").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='PREMIUM_CLAIM'").fetchone()[0] == 1


def test_same_operation_id_different_claim_is_conflict(db):
    first = _claim(db, operation_id="same-id")
    assert first.status == "GRANTED"
    with db:
        result = _service(db).claim_period_reward(
            1,
            "2026-09",
            operation_id="same-id",
            now=NOW,
        )
    assert result.status == "CONFLICT"
    assert result.reason == "CLAIM_IDEMPOTENCY_CONFLICT"
    assert db.execute("SELECT COUNT(*) FROM premium_claim_operations").fetchone()[0] == 1


def test_cross_user_operation_identity_isolated(db):
    _add_user(db, 2)
    _add_verified_grant(db, 2)
    db.commit()
    first = _claim(db, operation_id="shared-id")
    with db:
        second = _service(db).claim_period_reward(2, "2026-08", operation_id="shared-id", now=NOW)
    db.commit()
    assert first.status == second.status == "GRANTED"
    assert db.execute("SELECT COUNT(*) FROM premium_claim_operations WHERE operation_id='shared-id'").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 2


def test_unknown_access_is_preserved_but_recurring_claim_is_denied():
    conn = _open_sqlite()
    _add_user(conn, 17)
    grant_premium_with_provenance(
        conn,
        user_id=17,
        source_class="UNKNOWN",
        source_reference="legacy:unknown:17",
        granted_by_or_system_source="legacy_projection",
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until="2026-12-31T23:59:59+00:00",
        commercial_reward_eligibility="BLOCKED",
        classification_reason="source not preserved",
    )
    _add_period(conn)
    conn.commit()
    assert _service(conn).current_access(17, now=NOW) is True
    result = _service(conn).claim_period_reward(17, "2026-08", operation_id="unknown-claim", now=NOW)
    conn.commit()
    assert result.status == "DENIED"
    assert result.reason == "RECURRING_REWARD_NOT_ELIGIBLE"
    assert conn.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize("source_class", ["ADMIN_GRANTED", "PERMANENT_COMP", "TRIAL", "LEGACY"])
def test_non_verified_provenance_preserves_access_but_denies_recurring_reward(source_class):
    conn = _open_sqlite()
    _add_user(conn, 50)
    kwargs = {
        "user_id": 50,
        "source_class": source_class,
        "source_reference": f"{source_class.lower()}:50",
        "granted_by_or_system_source": "test",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_until": "2026-12-31T23:59:59+00:00",
        "commercial_reward_eligibility": "OWNER_POLICY_REQUIRED" if source_class in {"ADMIN_GRANTED", "PERMANENT_COMP"} else "BLOCKED",
    }
    if source_class == "TRIAL":
        kwargs["trial_redemption_id"] = 50
    elif source_class == "LEGACY":
        kwargs["classification_reason"] = "legacy policy"
    else:
        kwargs["grant_policy_profile"] = "access_only"
    grant_premium_with_provenance(conn, **kwargs)
    _add_period(conn)
    conn.commit()
    assert _service(conn).current_access(50, now=NOW) is True
    result = _service(conn).claim_period_reward(50, "2026-08", operation_id=f"{source_class}-claim", now=NOW)
    conn.commit()
    assert result.status == "DENIED"
    assert result.reason == "RECURRING_REWARD_NOT_ELIGIBLE"
    conn.close()


def test_functional_reward_is_fail_closed_without_mutation(db):
    result = _service(db, catalog=FakeCatalog(functional=True)).claim_period_reward(
        1, "2026-08", operation_id="functional", now=NOW
    )
    db.commit()
    assert result.status == "DENIED"
    assert result.reason == "CATALOG_REWARD_INVALID"
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0


def test_fault_rolls_back_claim_operation_reward_ownership_and_events(db):
    def fail(stage):
        if stage == "after_wardrobe_write":
            raise RuntimeError("forced D5E rollback")

    with pytest.raises(RuntimeError, match="forced D5E rollback"):
        _service(db).claim_period_reward(1, "2026-08", operation_id="rollback", now=NOW, fault_hook=fail)
    db.rollback()
    assert db.execute("SELECT COUNT(*) FROM premium_claim_operations").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0


def test_annual_grace_requires_pre_earned_credit_and_is_limited_to_90_days():
    conn = _open_sqlite()
    _add_user(conn, 3, premium_until="2026-08-31T23:59:59+00:00")
    _add_verified_grant(conn, 3, plan_term="ANNUAL", valid_until="2026-08-31T23:59:59+00:00")
    _add_period(conn, window_end="2026-08-31T23:59:59+00:00", grace=90)
    conn.commit()
    period_id = conn.execute("SELECT id FROM premium_reward_periods WHERE period_key='2026-08'").fetchone()[0]
    grant_id = conn.execute("SELECT id FROM premium_entitlement_grants WHERE user_id=3").fetchone()[0]
    conn.execute(
        "INSERT INTO premium_reward_credits(user_id,reward_period_id,entitlement_grant_id,source_class_snapshot,plan_term_snapshot,earned_at,claim_window_starts_at,claim_window_ends_at,credit_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (3, period_id, grant_id, "VERIFIED_PAID", "ANNUAL", "2026-08-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00", "2026-08-31T23:59:59+00:00", "EARNED", "2026-08-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00"),
    )
    conn.commit()
    within = _service(conn).claim_period_reward(3, "2026-08", operation_id="annual-grace", now=_stamp("2026-10-15T12:00:00+00:00"))
    conn.commit()
    assert within.status == "GRANTED"

    conn2 = _open_sqlite()
    _add_user(conn2, 4, premium_until="2026-08-31T23:59:59+00:00")
    _add_verified_grant(conn2, 4, plan_term="ANNUAL", valid_until="2026-08-31T23:59:59+00:00")
    _add_period(conn2, window_end="2026-08-31T23:59:59+00:00", grace=90)
    conn2.commit()
    expired = _service(conn2).claim_period_reward(4, "2026-08", operation_id="annual-expired", now=_stamp("2026-12-01T12:00:00+00:00"))
    conn2.commit()
    assert expired.status == "DENIED"
    assert expired.reason in {"PREMIUM_ACCESS_INACTIVE", "RECURRING_REWARD_NOT_ELIGIBLE", "CLAIM_WINDOW_EXPIRED"}
    conn.close()
    conn2.close()


def _postgres_url():
    url = os.environ.get("D5E_PREMIUM_POSTGRES_URL")
    if not url or os.environ.get("D5E_PREMIUM_POSTGRES_DISPOSABLE") != "1":
        return None
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d5e" not in database:
        pytest.skip("refusing PostgreSQL URL without an explicitly disposable test/d5e database")
    return url


def _pg_open(url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _pg_base(conn):
    conn.execute("DROP TABLE IF EXISTS domain_event_outbox CASCADE")
    for table in ("premium_claim_operations", "premium_reward_claims", "premium_reward_credits", "premium_reward_periods", "premium_entitlement_events", "premium_entitlement_grants", "player_wardrobe", "users"):
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, plan TEXT NOT NULL, premium_until TEXT, is_admin INTEGER NOT NULL DEFAULT 0)")
    conn.execute("CREATE TABLE player_wardrobe (id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL, item_id TEXT NOT NULL, obtained_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'drop', UNIQUE(user_id,item_id))")
    upgrade_outbox(conn)
    upgrade_premium(conn)


def test_postgres_migration_and_concurrent_claim_are_exactly_once():
    url = _postgres_url()
    if not url:
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    setup = _pg_open(url)
    try:
        _pg_base(setup)
        _add_user(setup, 1)
        _add_verified_grant(setup, 1)
        _add_period(setup)
        setup.commit()
    finally:
        setup.close()

    barrier = Barrier(2)

    def worker():
        conn = _pg_open(url)
        try:
            barrier.wait(timeout=10)
            result = _service(conn).claim_period_reward(1, "2026-08", operation_id="pg-same", now=NOW)
            conn.commit()
            return result
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _unused: worker(), range(2)))
    assert [result.status for result in results] == ["GRANTED", "GRANTED"]
    check = _pg_open(url)
    try:
        assert check.execute("SELECT COUNT(*) FROM premium_claim_operations").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='PREMIUM_CLAIM'").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'").fetchone()[0] == 1
    finally:
        check.close()


def test_postgres_conflict_cross_user_and_rollback_atomicity():
    url = _postgres_url()
    if not url:
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    conn = _pg_open(url)
    try:
        _pg_base(conn)
        _add_user(conn, 1)
        _add_user(conn, 2)
        _add_verified_grant(conn, 1)
        _add_verified_grant(conn, 2)
        _add_period(conn)
        _add_period(conn, key="2026-09")
        conn.commit()

        first = _service(conn).claim_period_reward(1, "2026-08", operation_id="pg-conflict", now=NOW)
        conn.commit()
        conflict = _service(conn).claim_period_reward(1, "2026-09", operation_id="pg-conflict", now=NOW)
        conn.commit()
        other = _service(conn).claim_period_reward(2, "2026-08", operation_id="pg-conflict", now=NOW)
        conn.commit()
        assert first.status == "GRANTED"
        assert conflict.status == "CONFLICT"
        assert other.status == "GRANTED"

        def fail(stage):
            if stage == "after_wardrobe_write":
                raise RuntimeError("pg forced rollback")

        with pytest.raises(RuntimeError, match="pg forced rollback"):
            _service(conn).claim_period_reward(1, "2026-09", operation_id="pg-rollback", now=NOW, fault_hook=fail)
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM premium_claim_operations WHERE operation_id='pg-rollback'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM premium_reward_claims WHERE user_id=1 AND reward_period_id=(SELECT id FROM premium_reward_periods WHERE period_key='2026-09')").fetchone()[0] == 0
    finally:
        conn.close()
