"""D5F Premium deterministic bundle correctness and lineage tests."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import urlsplit

import pytest

from migrations.premium_reward_bundle_v1 import (
    downgrade_for_isolated_test as downgrade_bundle,
    upgrade as upgrade_bundle,
    validate_schema as validate_bundle_schema,
)
from premium_reward_bundle_runtime import (
    BUNDLE_VERSION,
    PremiumRewardBundleClaimService,
)

from test_d5e_premium_claim_lineage import (
    NOW,
    FakeCatalog,
    _add_period,
    _add_user,
    _add_verified_grant,
    _open_sqlite,
)


def _service(conn, *, catalog=None):
    return PremiumRewardBundleClaimService(conn, catalog_resolver=catalog or FakeCatalog())


@pytest.fixture()
def db():
    conn = _open_sqlite()
    conn.execute(
        """CREATE TABLE active_effects(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL,
               effect_key TEXT NOT NULL,
               value REAL NOT NULL DEFAULT 1,
               expires_at TEXT,
               effect_date TEXT,
               created_at TEXT NOT NULL)"""
    )
    from migrations.question_capacity_lineage_v1 import upgrade as upgrade_capacity

    upgrade_capacity(conn)
    upgrade_bundle(conn)
    _add_user(conn, 1)
    _add_verified_grant(conn, 1)
    _add_period(conn)
    conn.commit()
    yield conn
    downgrade_bundle(conn)
    conn.close()


def _claim(conn, *, operation_id="bundle-001", include_cosmetic=False, catalog=None, **kwargs):
    result = _service(conn, catalog=catalog).claim_period_bundle(
        1,
        "2026-08",
        operation_id=operation_id,
        include_cosmetic=include_cosmetic,
        now=NOW,
        **kwargs,
    )
    conn.commit()
    return result


def test_bundle_schema_and_question_capacity_component_are_single_period_claim(db):
    assert validate_bundle_schema(db)["valid"] is True
    result = _claim(db)

    assert result.status == "GRANTED"
    assert result.created is True
    assert len(result.components) == 1
    assert result.components[0]["component_type"] == "QUESTION_CAPACITY"
    assert result.components[0]["capacity_delta"] == 5
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 1
    assert db.execute("SELECT ownership_authority FROM premium_reward_claims").fetchone()[0] == "premium_bundle"
    assert db.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM active_effects WHERE effect_key='extra_questions'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='QUESTION_CAPACITY'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='PREMIUM_CLAIM'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'").fetchone()[0] == 0


def test_same_operation_and_different_operation_retry_replay_without_component_duplication(db):
    first = _claim(db, operation_id="bundle-retry")
    retry = _claim(db, operation_id="bundle-retry")
    other_operation = _claim(db, operation_id="bundle-retry-2")

    assert retry.status == other_operation.status == "GRANTED"
    assert retry.created is False
    assert other_operation.created is False
    assert retry.claim_id == other_operation.claim_id == first.claim_id
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM active_effects WHERE effect_key='extra_questions'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='QUESTION_CAPACITY'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='PREMIUM_CLAIM'").fetchone()[0] == 1


def test_same_operation_with_different_bundle_contract_fails_closed(db):
    first = _claim(db, operation_id="bundle-conflict")
    conflict = _service(db, catalog=FakeCatalog()).claim_period_bundle(
        1,
        "2026-08",
        operation_id="bundle-conflict",
        include_cosmetic=True,
        requested_cosmetic_id="cosmetic.monthly.2026-08",
        now=NOW,
    )
    db.commit()
    assert first.status == "GRANTED"
    assert conflict.status == "CONFLICT"
    assert conflict.reason == "CLAIM_IDEMPOTENCY_CONFLICT"
    assert db.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 1


def test_optional_pure_cosmetic_uses_wardrobe_and_d5c_acquisition_shape(db):
    result = _claim(
        db,
        operation_id="bundle-cosmetic",
        include_cosmetic=True,
        catalog=FakeCatalog(reward_id="cosmetic.bundle.fixture"),
    )
    assert result.status == "GRANTED"
    assert len(result.components) == 2
    cosmetic = next(item for item in result.components if item["component_type"] == "PURE_COSMETIC")
    assert cosmetic["item_id"] == "cosmetic.bundle.fixture"
    assert cosmetic["ownership_created"] is True
    assert db.execute("SELECT COUNT(*) FROM player_wardrobe WHERE item_id='cosmetic.bundle.fixture'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'").fetchone()[0] == 1
    item_event = db.execute("SELECT source_event_id FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'").fetchone()[0]
    assert item_event == result.premium_event_id


def test_bundle_fault_rolls_back_claim_capacity_components_and_events(db):
    def fail(stage):
        if stage == "after_premium_event":
            raise RuntimeError("forced bundle rollback")

    with pytest.raises(RuntimeError, match="forced bundle rollback"):
        _service(db).claim_period_bundle(1, "2026-08", operation_id="bundle-rollback", now=NOW, fault_hook=fail)
    db.rollback()
    assert db.execute("SELECT COUNT(*) FROM premium_claim_operations").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM active_effects").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0


def test_cosmetic_failure_rolls_back_both_bundle_components(db):
    def fail(stage):
        if stage == "after_cosmetic_write":
            raise RuntimeError("forced cosmetic rollback")

    with pytest.raises(RuntimeError, match="forced cosmetic rollback"):
        _service(db, catalog=FakeCatalog(reward_id="cosmetic.rollback.fixture")).claim_period_bundle(
            1,
            "2026-08",
            operation_id="bundle-cosmetic-rollback",
            include_cosmetic=True,
            now=NOW,
            fault_hook=fail,
        )
    db.rollback()
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM active_effects").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0


def test_capacity_authority_failure_rolls_back_claim(monkeypatch, db):
    import premium_reward_bundle_runtime as runtime

    def fail_capacity(*args, **kwargs):
        raise RuntimeError("forced capacity failure")

    monkeypatch.setattr(runtime, "apply_question_capacity_in_transaction", fail_capacity)
    with pytest.raises(RuntimeError, match="forced capacity failure"):
        _service(db).claim_period_bundle(1, "2026-08", operation_id="bundle-capacity-failure", now=NOW)
    db.rollback()
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM premium_claim_operations").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0


def test_premium_event_failure_rolls_back_capacity_and_claim(monkeypatch, db):
    import premium_reward_bundle_runtime as runtime

    def fail_event(*args, **kwargs):
        raise RuntimeError("forced Premium event failure")

    monkeypatch.setattr(runtime, "append_event", fail_event)
    with pytest.raises(RuntimeError, match="forced Premium event failure"):
        _service(db).claim_period_bundle(1, "2026-08", operation_id="bundle-event-failure", now=NOW)
    db.rollback()
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM active_effects").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox").fetchone()[0] == 0


def test_same_operation_id_isolated_by_user(db):
    _add_user(db, 2)
    _add_verified_grant(db, 2)
    db.commit()
    first = _claim(db, operation_id="cross-user-bundle")
    second = _service(db).claim_period_bundle(2, "2026-08", operation_id="cross-user-bundle", now=NOW)
    db.commit()
    assert first.status == second.status == "GRANTED"
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 2


def _postgres_url():
    url = os.environ.get("D5F_PREMIUM_BUNDLE_POSTGRES_URL")
    if not url or os.environ.get("D5F_PREMIUM_BUNDLE_POSTGRES_DISPOSABLE") != "1":
        return None
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d5f" not in database:
        pytest.skip("refusing PostgreSQL URL without an explicitly disposable test/d5f database")
    return url


def _pg_open(url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _pg_base(conn):
    conn.execute("DROP TABLE IF EXISTS premium_reward_bundle_components CASCADE")
    conn.execute("DROP TABLE IF EXISTS domain_event_outbox CASCADE")
    for table in ("premium_claim_operations", "premium_reward_claims", "premium_reward_credits", "premium_reward_periods", "premium_entitlement_events", "premium_entitlement_grants", "player_wardrobe", "users"):
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, plan TEXT NOT NULL, premium_until TEXT, is_admin INTEGER NOT NULL DEFAULT 0)")
    conn.execute("CREATE TABLE player_wardrobe (id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL, item_id TEXT NOT NULL, obtained_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'drop', UNIQUE(user_id,item_id))")
    conn.execute(
        """CREATE TABLE active_effects(
               id BIGSERIAL PRIMARY KEY,
               user_id INTEGER NOT NULL,
               effect_key TEXT NOT NULL,
               value REAL NOT NULL DEFAULT 1,
               expires_at TEXT,
               effect_date TEXT,
               created_at TEXT NOT NULL)"""
    )
    from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
    from migrations.premium_claim_lineage_v1 import upgrade as upgrade_premium
    from migrations.question_capacity_lineage_v1 import upgrade as upgrade_capacity

    upgrade_outbox(conn)
    upgrade_premium(conn)
    upgrade_capacity(conn)
    upgrade_bundle(conn)


def test_postgres_bundle_concurrent_claim_is_exactly_once():
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
            result = _service(conn).claim_period_bundle(1, "2026-08", operation_id="pg-bundle-same", now=NOW)
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
        assert check.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM active_effects").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='QUESTION_CAPACITY'").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='PREMIUM_CLAIM'").fetchone()[0] == 1
    finally:
        check.close()

    other = _pg_open(url)
    try:
        _add_user(other, 2)
        _add_verified_grant(other, 2)
        other.commit()
        result = _service(other).claim_period_bundle(2, "2026-08", operation_id="pg-cross-user", now=NOW)
        other.commit()
        assert result.status == "GRANTED"
        assert other.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 2
    finally:
        other.close()
