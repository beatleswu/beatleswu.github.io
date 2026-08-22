"""C013 Revenue V1 deterministic Premium benefit contract tests."""

from __future__ import annotations

import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from migrations.premium_reward_bundle_v1 import upgrade as upgrade_bundle
from migrations.question_capacity_lineage_v1 import upgrade as upgrade_capacity
from premium_provenance import grant_premium_with_provenance
from premium_reward_bundle_runtime import PremiumRewardBundleClaimService
from premium_v1_revenue import (
    C013_CLAIM_GRACE_DAYS,
    C013_HIDDEN_IDS,
    C013_LAUNCH_COSMETIC_IDS,
    C013_REWARD_CATALOG_KEY,
    build_c013_annual_vesting_periods,
    build_c013_catalog_resolver,
    build_c013_offer_projection,
    ensure_c013_reward_periods,
    c013_claim_route_enabled,
    c013_result_payload,
    read_c013_claim_evidence,
    select_server_claim_period,
)

from test_d5e_premium_claim_lineage import (
    NOW,
    _add_period,
    _add_user,
    _add_verified_grant,
    _open_sqlite,
)


def _resolver(*, owned_ids=()):
    definitions = [
        {"id": item_id, "name": item_id, "name_en": item_id, "slot": "outfit", "rarity": "common"}
        for item_id in C013_LAUNCH_COSMETIC_IDS
    ]
    presentation = {
        item_id: {
            "asset": f"/assets/hero/items/fullbody/{item_id}.webp",
            "asset_id": item_id,
            "asset_format": "WEBP",
            "mode": "FULL_BODY_COSMETIC_REFERENCE",
            "pure_presentation": True,
            "functional_effect_count": 0,
            "combat_authority": "NO",
        }
        for item_id in C013_LAUNCH_COSMETIC_IDS
    }
    return build_c013_catalog_resolver(
        appearance_defs=definitions,
        presentation_registry=presentation,
        hidden_ids=C013_HIDDEN_IDS,
        appearance_effects={},
        owned_ids=owned_ids,
    )


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
               created_at TEXT NOT NULL,
               operation_id TEXT,
               source_item_key TEXT)"""
    )
    upgrade_capacity(conn)
    upgrade_bundle(conn)
    _add_user(conn, 1)
    _add_verified_grant(conn, 1)
    _add_period(conn)
    conn.execute(
        "UPDATE premium_reward_periods SET reward_catalog_key=? WHERE period_key=?",
        (C013_REWARD_CATALOG_KEY, "2026-08"),
    )
    conn.commit()
    yield conn
    conn.close()


def _service(conn, *, user_id=1):
    owned_ids = [
        row[0]
        for row in conn.execute(
            "SELECT item_id FROM player_wardrobe WHERE user_id=?", (user_id,)
        ).fetchall()
    ]
    return PremiumRewardBundleClaimService(
        conn,
        catalog_resolver=_resolver(owned_ids=owned_ids),
    )


def _claim(conn, *, user_id=1, operation_id="c013-claim-1", cosmetic_id="robe_plain"):
    result = _service(conn, user_id=user_id).claim_period_bundle(
        user_id,
        "2026-08",
        operation_id=operation_id,
        include_cosmetic=True,
        requested_cosmetic_id=cosmetic_id,
        now=NOW,
    )
    conn.commit()
    return result


def test_locked_pool_is_exact_and_visual_projection_is_pure():
    resolver = _resolver()
    projection = build_c013_offer_projection(
        enabled=True,
        premium_entitled=True,
        catalog_resolver=resolver,
    )
    assert [item["item_id"] for item in projection["cosmetic_pool"]] == list(C013_LAUNCH_COSMETIC_IDS)
    assert set(projection["hidden_excluded_ids"]) == set(C013_HIDDEN_IDS)
    assert len(projection["cosmetic_pool"]) == 5
    assert all(item["pure_presentation"] is True for item in projection["cosmetic_pool"])
    assert all(item["combat_authority"] == "NO" for item in projection["cosmetic_pool"])
    assert projection["annual_policy"]["vesting"] == "MONTHLY"
    assert projection["annual_policy"]["grace_days_for_earned_credits"] == C013_CLAIM_GRACE_DAYS


def test_verified_paid_bundle_uses_d5b_d5f_d5a_and_replays_safely(db):
    first = _claim(db, operation_id="c013-retry", cosmetic_id="back_pack")
    retry = _claim(db, operation_id="c013-retry", cosmetic_id="back_pack")
    different_request = _claim(db, operation_id="c013-retry-2", cosmetic_id="back_pack")

    assert first.status == retry.status == different_request.status == "GRANTED"
    assert first.created is True
    assert retry.created is False
    assert different_request.created is False
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM premium_reward_credits").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM player_wardrobe WHERE item_id='back_pack'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM active_effects WHERE effect_key='extra_questions' AND value=5").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='QUESTION_CAPACITY'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='PREMIUM_CLAIM'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'").fetchone()[0] == 1


def test_response_loss_reselects_original_period_and_changed_selection_conflicts(db):
    first = _claim(db, operation_id="c013-response-loss", cosmetic_id="robe_plain")
    assert first.status == "GRANTED"
    service = _service(db)
    assert select_server_claim_period(
        service,
        user_id=1,
        operation_id="c013-response-loss",
        now=NOW + dt.timedelta(days=40),
    ) == "2026-08"
    conflict = service.claim_period_bundle(
        1,
        "2026-08",
        operation_id="c013-response-loss",
        include_cosmetic=True,
        requested_cosmetic_id="robe_fox",
        now=NOW,
    )
    db.commit()
    assert conflict.status == "CONFLICT"
    assert conflict.reason == "CLAIM_IDEMPOTENCY_CONFLICT"
    assert db.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 1


def test_all_five_owned_does_not_consume_credit_or_convert(db):
    for item_id in C013_LAUNCH_COSMETIC_IDS:
        db.execute(
            "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)",
            (1, item_id, "2026-08-10T00:00:00+00:00", "test"),
        )
    db.commit()
    result = _claim(db, operation_id="c013-all-owned", cosmetic_id="robe_plain")
    payload = c013_result_payload(result)
    assert result.status == "DENIED"
    assert payload["reason"] == "NO_AVAILABLE_REWARD"
    assert payload["credit_consumed"] is False
    assert db.execute("SELECT COUNT(*) FROM premium_reward_credits").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM active_effects").fetchone()[0] == 0


@pytest.mark.parametrize("source_class", [
    "ADMIN_GRANTED",
    "PERMANENT_COMP",
    "TRIAL",
    "LEGACY",
    "UNKNOWN",
])
def test_non_verified_sources_preserve_access_but_cannot_claim(source_class, db):
    user_id = {
        "ADMIN_GRANTED": 2,
        "PERMANENT_COMP": 3,
        "TRIAL": 4,
        "LEGACY": 5,
        "UNKNOWN": 6,
    }[source_class]
    _add_user(db, user_id)
    source_kwargs = {}
    if source_class == "TRIAL":
        source_kwargs["trial_redemption_id"] = 400 + user_id
    elif source_class in {"ADMIN_GRANTED", "PERMANENT_COMP"}:
        source_kwargs["grant_policy_profile"] = f"{source_class.lower()}_fixture"
    else:
        source_kwargs["classification_reason"] = f"{source_class.lower()}_fixture"
    grant_premium_with_provenance(
        db,
        user_id=user_id,
        source_class=source_class,
        source_reference=f"c013:{source_class}:{user_id}",
        granted_by_or_system_source="test_policy_fixture",
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until="2026-12-31T23:59:59+00:00",
        commercial_reward_eligibility="BLOCKED",
        plan_term="MONTHLY",
        **source_kwargs,
    )
    db.commit()
    result = _claim(db, user_id=user_id, operation_id=f"c013-{source_class}")
    assert result.status == "DENIED"
    assert result.reason == "RECURRING_REWARD_NOT_ELIGIBLE"
    assert db.execute("SELECT plan FROM users WHERE id=?", (user_id,)).fetchone()[0] == "premium"
    assert db.execute("SELECT COUNT(*) FROM premium_reward_claims WHERE user_id=?", (user_id,)).fetchone()[0] == 0


def test_support_evidence_is_read_only_projection(db):
    result = _claim(db, operation_id="c013-support", cosmetic_id="acc_dragon_pendant")
    evidence = read_c013_claim_evidence(db, user_id=1, operation_id="c013-support")
    assert result.status == "GRANTED"
    assert evidence["status"] == "OK"
    assert evidence["claim"]["id"] == result.claim_id
    assert evidence["credit"]["source_class_snapshot"] == "VERIFIED_PAID"
    assert {row["component_type"] for row in evidence["components"]} == {"QUESTION_CAPACITY", "PURE_COSMETIC"}
    assert {row["event_type"] for row in evidence["outbox_events"]} == {
        "PREMIUM_CLAIM",
        "QUESTION_CAPACITY",
        "ITEM_ACQUISITION",
    }


def test_default_off_and_no_runtime_migration_contract():
    assert c013_claim_route_enabled({}) is False
    assert c013_claim_route_enabled({"GO_REVENUE_V1_PREMIUM_CLAIM_ENABLED": "0"}) is False
    assert c013_claim_route_enabled({"GO_REVENUE_V1_PREMIUM_CLAIM_ENABLED": "1"}) is True
    assert not Path("migrations/c013_premium_v1.py").exists()


def test_annual_vesting_creates_period_definitions_not_upfront_credits(db):
    periods = build_c013_annual_vesting_periods(dt.date(2027, 1, 15), created_at=NOW)
    assert len(periods) == 12
    assert len({period["period_key"] for period in periods}) == 12
    assert all(period["annual_grace_days"] == 90 for period in periods)
    assert all(period["reward_type"] == "MONTHLY_COLLECTION_CREDIT" for period in periods)
    assert ensure_c013_reward_periods(db, periods[:2]) == 2
    assert ensure_c013_reward_periods(db, periods[:2]) == 0
    db.commit()
    assert db.execute(
        "SELECT COUNT(*) FROM premium_reward_periods WHERE period_key LIKE '2027-%'"
    ).fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM premium_reward_credits").fetchone()[0] == 0


def test_all_locked_art_assets_exist_and_are_canonical_webp():
    root = Path(__file__).resolve().parents[1]
    for item_id in C013_LAUNCH_COSMETIC_IDS:
        asset = root / "assets" / "hero" / "items" / "fullbody" / f"{item_id}.webp"
        assert asset.is_file(), item_id
        assert asset.stat().st_size > 0


def _postgres_url():
    url = os.environ.get("C013_PREMIUM_POSTGRES_URL")
    if not url or os.environ.get("C013_PREMIUM_POSTGRES_DISPOSABLE") != "1":
        return None
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "c013" not in database:
        pytest.skip("refusing PostgreSQL URL without an explicitly disposable test/c013 database")
    return url


def _pg_open(url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def test_postgres_concurrent_c013_claim_is_exactly_once():
    url = _postgres_url()
    if not url:
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    from test_d5f_premium_reward_bundle import _pg_base

    setup = _pg_open(url)
    try:
        _pg_base(setup)
        _add_user(setup, 1)
        _add_verified_grant(setup, 1)
        _add_period(setup)
        setup.execute(
            "UPDATE premium_reward_periods SET reward_catalog_key=? WHERE period_key=?",
            (C013_REWARD_CATALOG_KEY, "2026-08"),
        )
        setup.commit()
    finally:
        setup.close()

    barrier = Barrier(2)

    def worker():
        conn = _pg_open(url)
        try:
            barrier.wait(timeout=10)
            result = _service(conn).claim_period_bundle(
                1,
                "2026-08",
                operation_id="c013-pg-same",
                include_cosmetic=True,
                requested_cosmetic_id="robe_plain",
                now=NOW,
            )
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
        assert check.execute("SELECT COUNT(*) FROM premium_reward_bundle_components").fetchone()[0] == 2
        assert check.execute("SELECT COUNT(*) FROM player_wardrobe WHERE item_id='robe_plain'").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='QUESTION_CAPACITY'").fetchone()[0] == 1
    finally:
        check.close()
