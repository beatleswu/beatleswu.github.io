"""SHOP-E independent acceptance harness for the 16-SKU Coin Shop launch.

This file is intentionally an acceptance consumer, not a Shop implementation.
It resolves the server-owned offer facts exposed by the integrated application
seam and exercises the existing C019 purchase operation against a disposable
PostgreSQL database.

Run the harness explicitly with SHOP_E_RUN_INTEGRATION=1.  The explicit
candidate-completeness test is expected to fail on a pre-SHOP-F baseline when
the launch facts are not present.  Dependent tests then report a blocked
precondition; that is evidence, not a release PASS.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import importlib
import os
from typing import Any

import pytest

from migrations.coin_purchase_operations_v1 import (
    TABLE_NAME as PURCHASE_OPERATIONS_TABLE,
    upgrade as upgrade_purchase_operations,
    validate_schema as validate_purchase_schema,
)
from migrations.domain_event_outbox_v1 import (
    upgrade as upgrade_event_outbox,
)
from coin_purchase_authority import (
    bind_bundle_acquisition_facts,
    canonical_bundle_acquisition_facts,
)
from shop_offer_identity_projection import (
    ServerShopOfferFacts,
    normalize_shop_offer,
)


CONSUMABLE_SKUS = (
    "hint_ticket",
    "ai_explain_ticket",
    "small_xp_potion",
    "streak_shield",
    "pet_snack",
    "extra_questions_small",
    "extra_questions",
    "xp_potion",
    "premium_hint_bundle",
    "double_streak_shield",
)
COSMETIC_SKUS = (
    "robe_bamboo",
    "back_pack",
    "robe_student",
    "acc_fan",
    "acc_jade_ring",
    "hat_dragon_horn",
)
LAUNCH_SKUS = CONSUMABLE_SKUS + COSMETIC_SKUS
EFFECT_SKUS = frozenset(
    {
        "small_xp_potion",
        "streak_shield",
        "extra_questions_small",
        "extra_questions",
        "xp_potion",
        "double_streak_shield",
    }
)
BUNDLE_SKUS = frozenset({"premium_hint_bundle", "pet_snack"})


@dataclass(frozen=True)
class SkuSpec:
    sku: str
    kind: str


SKU_MATRIX = tuple(
    SkuSpec(sku, "consumable") for sku in CONSUMABLE_SKUS
) + tuple(SkuSpec(sku, "cosmetic") for sku in COSMETIC_SKUS)


@dataclass(frozen=True)
class CandidateOffer:
    spec: SkuSpec
    facts: ServerShopOfferFacts
    offer: Any
    route: str
    selector_field: str
    selector_value: str


class CandidateIncomplete(RuntimeError):
    """The integrated candidate does not expose a complete launch matrix."""


class _PostgresDbContext:
    """App get_db context backed by one disposable PostgreSQL URL."""

    def __init__(self, database_url: str):
        import psycopg2
        from psycopg2.extras import DictCursor
        from db import PostgresConnectionWrapper

        raw = psycopg2.connect(
            database_url,
            connect_timeout=5,
            cursor_factory=DictCursor,
        )
        self.conn = PostgresConnectionWrapper(raw, pooled=False)

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()


def _integration_enabled() -> bool:
    return os.environ.get("SHOP_E_RUN_INTEGRATION", "").strip() == "1"


@pytest.fixture(scope="module")
def shop_e_postgres():
    if not _integration_enabled():
        pytest.skip(
            "SHOP-E acceptance is explicit; set SHOP_E_RUN_INTEGRATION=1 "
            "to run disposable PostgreSQL"
        )
    from postgres_test_harness import disposable_postgres

    with disposable_postgres(name_prefix="shop-e-16-sku") as record:
        yield record


def _connect(database_url: str):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(
        database_url,
        connect_timeout=5,
        cursor_factory=DictCursor,
    )
    return PostgresConnectionWrapper(raw, pooled=False)


def _reset_disposable_schema(database_url: str) -> None:
    conn = _connect(database_url)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute(
            """CREATE TABLE public.users (
                id INTEGER PRIMARY KEY,
                plan TEXT NOT NULL DEFAULT 'free',
                premium_until TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            """CREATE TABLE public.user_stats (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE public.currency_log (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE public.shop_inventory (
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_key)
            )"""
        )
        conn.execute(
            """CREATE TABLE public.pet_inventory (
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_key)
            )"""
        )
        conn.execute(
            """CREATE TABLE public.player_wardrobe (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                obtained_at TEXT NOT NULL,
                source TEXT NOT NULL,
                UNIQUE (user_id, item_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE public.player_appearance (
                user_id INTEGER PRIMARY KEY,
                outfit_id TEXT,
                updated_at TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE public.active_effects (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                effect_key TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 1,
                expires_at TEXT,
                effect_date TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE public.daily_shop (
                shop_date TEXT PRIMARY KEY,
                slots TEXT NOT NULL
            )"""
        )
        upgrade_purchase_operations(conn)
        upgrade_event_outbox(conn)
        conn.execute(
            "INSERT INTO users(id,plan) VALUES(1,'free'),(2,'free')"
        )
        conn.execute(
            "INSERT INTO user_stats(user_id,coins) VALUES(1,1000000),(2,1000000)"
        )
        # This sentinel makes an accidental purchase-time appearance write
        # observable without invoking the separate equip authority.
        conn.execute(
            "INSERT INTO player_appearance(user_id,outfit_id,updated_at) "
            "VALUES(1,'qa-baseline-outfit','qa-baseline-time')"
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def fresh_disposable_database(shop_e_postgres):
    _reset_disposable_schema(shop_e_postgres["database_url"])
    yield


def _app_module():
    try:
        return importlib.import_module("app")
    except ModuleNotFoundError as exc:
        raise CandidateIncomplete(
            "integrated application module is unavailable to the acceptance run"
        ) from exc


def _server_facts(conn) -> tuple[ServerShopOfferFacts, ...]:
    app_module = _app_module()
    resolver = getattr(app_module, "_canonical_shop_offer_facts", None)
    if not callable(resolver):
        raise CandidateIncomplete(
            "app._canonical_shop_offer_facts is not exposed by the integrated candidate"
        )
    raw_facts = resolver(conn)
    if raw_facts is None:
        raise CandidateIncomplete(
            "the integrated candidate returned no server Shop facts"
        )
    facts: list[ServerShopOfferFacts] = []
    for raw in raw_facts:
        facts.append(
            raw
            if isinstance(raw, ServerShopOfferFacts)
            else ServerShopOfferFacts.from_mapping(raw)
        )
    return tuple(facts)


def _fact_identifiers(fact: ServerShopOfferFacts) -> set[str]:
    return {
        str(value).strip()
        for value in (fact.item_key, fact.item_id, fact.product_id)
        if value is not None and str(value).strip()
    }


def _candidate_offers(database_url: str) -> dict[str, CandidateOffer]:
    conn = _connect(database_url)
    try:
        facts = _server_facts(conn)
    finally:
        conn.rollback()
        conn.close()

    missing: list[str] = []
    ambiguous: list[str] = []
    invalid: list[str] = []
    offers: dict[str, CandidateOffer] = {}
    for spec in SKU_MATRIX:
        matches = [fact for fact in facts if spec.sku in _fact_identifiers(fact)]
        if not matches:
            missing.append(spec.sku)
            continue
        if len(matches) != 1:
            ambiguous.append(spec.sku)
            continue
        fact = matches[0]
        try:
            offer = normalize_shop_offer(fact)
        except Exception as exc:
            invalid.append(f"{spec.sku}:{type(exc).__name__}")
            continue

        if spec.kind == "consumable":
            if offer.destination not in {"shop_inventory", "pet_inventory"}:
                invalid.append(f"{spec.sku}:destination={offer.destination}")
                continue
            if offer.duplicate_policy != "STACK":
                invalid.append(f"{spec.sku}:duplicate_policy={offer.duplicate_policy}")
                continue
            if spec.sku in BUNDLE_SKUS:
                expected_profile = canonical_bundle_acquisition_facts(spec.sku).as_metadata()
                if (
                    offer.quantity != 1
                    or fact.metadata.get("bundle_offer_type") != "BUNDLE"
                    or fact.metadata.get("bundle_grant_profile") != expected_profile
                ):
                    invalid.append(f"{spec.sku}:typed_bundle_contract")
                    continue
        else:
            if (
                offer.destination != "player_wardrobe"
                or offer.acquisition_class != "COSMETIC"
                or offer.duplicate_policy != "REJECT_IF_OWNED"
                or offer.quantity != 1
                or not fact.product_id
            ):
                invalid.append(f"{spec.sku}:cosmetic_contract")
                continue

        if spec.kind == "cosmetic":
            route = "/api/cosmetic-commerce/purchase"
            selector_field = "product_id"
            selector_value = str(fact.product_id)
        else:
            route = "/api/shop/buy"
            selector_field = "item_key"
            selector_value = str(fact.item_key or spec.sku)
        offers[spec.sku] = CandidateOffer(
            spec=spec,
            facts=fact,
            offer=offer,
            route=route,
            selector_field=selector_field,
            selector_value=selector_value,
        )

    if missing or ambiguous or invalid:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if ambiguous:
            details.append(f"ambiguous={','.join(ambiguous)}")
        if invalid:
            details.append(f"invalid={','.join(invalid)}")
        raise CandidateIncomplete(
            "SHOP-F launch offer matrix is incomplete: " + "; ".join(details)
        )
    return offers


def _available_offer(database_url: str, sku: str) -> CandidateOffer:
    conn = _connect(database_url)
    try:
        facts = _server_facts(conn)
    finally:
        conn.rollback()
        conn.close()
    matches = [fact for fact in facts if sku in _fact_identifiers(fact)]
    if len(matches) != 1:
        pytest.skip(f"baseline canonical probe unavailable for {sku}")
    fact = matches[0]
    try:
        offer = normalize_shop_offer(fact)
    except Exception as exc:
        pytest.skip(f"baseline canonical probe is not ready for {sku}: {exc}")
    kind = "cosmetic" if offer.destination == "player_wardrobe" else "consumable"
    if kind == "cosmetic":
        route = "/api/cosmetic-commerce/purchase"
        selector_field = "product_id"
        selector_value = str(fact.product_id)
    else:
        route = "/api/shop/buy"
        selector_field = "item_key"
        selector_value = str(fact.item_key or sku)
    return CandidateOffer(
        spec=SkuSpec(sku, kind),
        facts=fact,
        offer=offer,
        route=route,
        selector_field=selector_field,
        selector_value=selector_value,
    )


def _session_client(database_url: str, monkeypatch, *, user_id: int = 1):
    app_module = _app_module()
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _PostgresDbContext(database_url),
    )
    app_module.app.config.update(
        TESTING=True,
        PROPAGATE_EXCEPTIONS=False,
        SESSION_COOKIE_SECURE=False,
    )
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["username"] = f"shop-e-{user_id}"
    return client


def _purchase(client, candidate: CandidateOffer, operation_id: str):
    return client.post(
        candidate.route,
        json={
            candidate.selector_field: candidate.selector_value,
            "purchase_operation_id": operation_id,
            # All client-authored price/quantity values are deliberately
            # hostile.  The acceptance observes only server-resolved facts.
            "price": 1,
            "client_price": 999999999,
            "qty": 999,
            "requested_quantity": 999,
        },
    )


def _snapshot(database_url: str, *, user_id: int = 1) -> dict[str, Any]:
    conn = _connect(database_url)
    try:
        balance = conn.execute(
            "SELECT coins FROM user_stats WHERE user_id=?", (user_id,)
        ).fetchone()
        currency_logs = conn.execute(
            "SELECT delta,balance_after,reason FROM currency_log "
            "WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
        operations = conn.execute(
            f"SELECT purchase_operation_id,offer_id,operation_status,"
            f"resolved_price,reward_id,reward_quantity,destination,"
            f"acquisition_class,lineage_event_id "
            f"FROM {PURCHASE_OPERATIONS_TABLE} WHERE user_id=? "
            "ORDER BY purchase_operation_id",
            (user_id,),
        ).fetchall()
        shop_rows = conn.execute(
            "SELECT item_key,qty FROM shop_inventory WHERE user_id=?",
            (user_id,),
        ).fetchall()
        pet_rows = conn.execute(
            "SELECT item_key,qty FROM pet_inventory WHERE user_id=?",
            (user_id,),
        ).fetchall()
        wardrobe_rows = conn.execute(
            "SELECT item_id,source FROM player_wardrobe WHERE user_id=? "
            "ORDER BY item_id",
            (user_id,),
        ).fetchall()
        appearance = conn.execute(
            "SELECT outfit_id,updated_at FROM player_appearance WHERE user_id=?",
            (user_id,),
        ).fetchone()
        effect_rows = conn.execute(
            "SELECT effect_key,value,expires_at,effect_date FROM active_effects "
            "WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
        return {
            "coins": int(balance["coins"]),
            "currency_logs": tuple(
                (int(row["delta"]), int(row["balance_after"]), str(row["reason"]))
                for row in currency_logs
            ),
            "operations": tuple(
                (
                    str(row["purchase_operation_id"]),
                    str(row["offer_id"]),
                    str(row["operation_status"]),
                    int(row["resolved_price"]),
                    str(row["reward_id"]),
                    int(row["reward_quantity"]),
                    str(row["destination"]),
                    str(row["acquisition_class"]),
                    str(row["lineage_event_id"] or ""),
                )
                for row in operations
            ),
            "shop": {
                str(row["item_key"]): int(row["qty"]) for row in shop_rows
            },
            "pet": {
                str(row["item_key"]): int(row["qty"]) for row in pet_rows
            },
            "wardrobe": tuple(
                (str(row["item_id"]), str(row["source"])) for row in wardrobe_rows
            ),
            "appearance": (
                (str(appearance["outfit_id"]), str(appearance["updated_at"]))
                if appearance
                else None
            ),
            "effects": tuple(
                (
                    str(row["effect_key"]),
                    float(row["value"]),
                    row["expires_at"],
                    row["effect_date"],
                )
                for row in effect_rows
            ),
        }
    finally:
        conn.rollback()
        conn.close()


def _set_coins(database_url: str, amount: int, *, user_id: int = 1) -> None:
    conn = _connect(database_url)
    try:
        conn.execute(
            "UPDATE user_stats SET coins=? WHERE user_id=?",
            (amount, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def _operation(database_url: str, operation_id: str, *, user_id: int = 1):
    conn = _connect(database_url)
    try:
        return conn.execute(
            f"SELECT * FROM {PURCHASE_OPERATIONS_TABLE} "
            "WHERE user_id=? AND purchase_operation_id=?",
            (user_id, operation_id),
        ).fetchone()
    finally:
        conn.rollback()
        conn.close()


def _assert_committed_purchase(
    database_url: str,
    candidate: CandidateOffer,
    operation_id: str,
    response,
) -> dict[str, Any]:
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["ok"] is True
    assert body["offer_id"] == candidate.offer.offer_id
    assert body["coins_spent"] == candidate.offer.server_price
    assert body["quantity"] == candidate.offer.quantity
    assert isinstance(body.get("canonical_acquisition_result"), dict)

    row = _operation(database_url, operation_id)
    assert row is not None
    assert row["operation_status"] == "COMMITTED"
    assert int(row["resolved_price"]) == candidate.offer.server_price
    assert row["reward_id"] == candidate.offer.item_id
    assert int(row["reward_quantity"]) == candidate.offer.quantity
    assert row["destination"] == candidate.offer.destination
    assert row["acquisition_class"] == candidate.offer.acquisition_class
    assert row["currency_type"] == "COINS"
    assert str(row["lineage_event_id"] or "")

    snapshot = _snapshot(database_url)
    assert snapshot["currency_logs"] == (
        (
            -candidate.offer.server_price,
            snapshot["coins"],
            f"coin_purchase:{candidate.offer.offer_id}:{operation_id}",
        ),
    )
    return body


def _assert_single_grant_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    candidate: CandidateOffer,
) -> None:
    offer = candidate.offer
    if candidate.spec.sku in BUNDLE_SKUS:
        grants = canonical_bundle_acquisition_facts(candidate.spec.sku).grants
        assert len(grants) == 1
        grant = grants[0]
        if grant.destination == "shop_inventory":
            before_map, after_map = before["shop"], after["shop"]
        elif grant.destination == "pet_inventory":
            before_map, after_map = before["pet"], after["pet"]
        else:
            raise AssertionError(f"unsupported bundle destination: {grant.destination}")
        keys = set(before_map) | set(after_map)
        delta = {
            key: after_map.get(key, 0) - before_map.get(key, 0)
            for key in keys
            if after_map.get(key, 0) != before_map.get(key, 0)
        }
        assert delta == {grant.item_id: grant.quantity}
        return
    if offer.destination == "shop_inventory":
        before_map, after_map = before["shop"], after["shop"]
    elif offer.destination == "pet_inventory":
        before_map, after_map = before["pet"], after["pet"]
    else:
        before_map, after_map = None, None

    if before_map is not None:
        keys = set(before_map) | set(after_map)
        delta = {
            key: after_map.get(key, 0) - before_map.get(key, 0)
            for key in keys
            if after_map.get(key, 0) != before_map.get(key, 0)
        }
        assert delta == {offer.item_id: offer.quantity}
        return

    assert offer.destination == "player_wardrobe"
    before_items = set(item for item, _source in before["wardrobe"])
    after_items = set(item for item, _source in after["wardrobe"])
    assert after_items - before_items == {offer.item_id}
    assert len(after_items) == len(before_items) + 1
    assert after["appearance"] == before["appearance"]


def _assert_no_mutation(before: dict[str, Any], after: dict[str, Any]) -> None:
    assert after == before


def test_shop_e_candidate_contains_all_16_server_owned_offers(shop_e_postgres):
    """The explicit gate fails with the exact missing/invalid SKU set."""

    try:
        offers = _candidate_offers(shop_e_postgres["database_url"])
    except CandidateIncomplete as exc:
        pytest.fail(str(exc))
    assert tuple(offers) == LAUNCH_SKUS


def test_existing_c019_postgres_probe_proves_response_loss_replay(
    shop_e_postgres, monkeypatch
):
    """The currently available canonical hint offer has durable replay proof."""

    database_url = shop_e_postgres["database_url"]
    candidate = _available_offer(database_url, "hint_ticket")
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price * 3 + 100)
    before = _snapshot(database_url)

    first = _purchase(client, candidate, "shop-e-response-loss")
    # Treat the first response as lost.  The committed database fact, not the
    # response body, is the source for the retry.
    assert first.status_code == 200, first.get_json()
    replay = _purchase(client, candidate, "shop-e-response-loss")
    body = _assert_committed_purchase(
        database_url, candidate, "shop-e-response-loss", replay
    )
    assert body["replayed"] is True
    after = _snapshot(database_url)
    _assert_single_grant_delta(before, after, candidate)
    assert len(after["currency_logs"]) == 1
    assert len(after["operations"]) == 1


def test_existing_c019_postgres_probe_rolls_back_after_grant_exception(
    shop_e_postgres, monkeypatch
):
    """The available canonical hint path cannot leave a debit without grant."""

    database_url = shop_e_postgres["database_url"]
    candidate = _available_offer(database_url, "hint_ticket")
    app_module = _app_module()
    from coin_purchase_authority import AcquisitionFailed

    def fail_acquisition(*args, **kwargs):
        raise AcquisitionFailed("SHOP-E baseline rollback probe")

    monkeypatch.setattr(
        app_module.SqlAcquisitionAuthority,
        "acquire",
        fail_acquisition,
    )
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price * 3 + 100)
    before = _snapshot(database_url)
    client = _session_client(database_url, monkeypatch)

    response = _purchase(client, candidate, "shop-e-baseline-rollback")

    assert response.status_code == 422
    assert response.get_json()["code"] == "ACQUISITION_FAILED"
    _assert_no_mutation(before, _snapshot(database_url))


def test_existing_c019_postgres_probe_concurrent_duplicate_is_idempotent(
    shop_e_postgres, monkeypatch
):
    database_url = shop_e_postgres["database_url"]
    candidate = _available_offer(database_url, "hint_ticket")
    app_module = _app_module()
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _PostgresDbContext(database_url),
    )
    app_module.app.config.update(
        TESTING=True,
        PROPAGATE_EXCEPTIONS=False,
        SESSION_COOKIE_SECURE=False,
    )
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price * 3 + 100)
    before = _snapshot(database_url)

    def submit():
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "shop-e-baseline-concurrent"
        return _purchase(client, candidate, "shop-e-baseline-concurrent")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: submit(), (1, 2)))

    assert [response.status_code for response in responses] == [200, 200]
    assert sorted(response.get_json()["replayed"] for response in responses) == [
        False,
        True,
    ]
    after = _snapshot(database_url)
    _assert_single_grant_delta(before, after, candidate)
    assert len(after["currency_logs"]) == 1
    assert len(after["operations"]) == 1


def test_existing_c019_postgres_probe_same_operation_different_offer_conflicts(
    shop_e_postgres, monkeypatch
):
    database_url = shop_e_postgres["database_url"]
    first_candidate = _available_offer(database_url, "hint_ticket")
    second_candidate = _available_offer(database_url, "ai_explain_ticket")
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, first_candidate.offer.server_price * 3 + 100)

    first = _purchase(client, first_candidate, "shop-e-baseline-conflict")
    assert first.status_code == 200, first.get_json()
    after_first = _snapshot(database_url)
    conflict = _purchase(client, second_candidate, "shop-e-baseline-conflict")

    assert conflict.status_code == 409
    assert conflict.get_json()["code"] == "PURCHASE_OPERATION_CONFLICT"
    assert _snapshot(database_url) == after_first


def test_existing_c019_postgres_probe_insufficient_coins_is_atomic(
    shop_e_postgres, monkeypatch
):
    database_url = shop_e_postgres["database_url"]
    candidate = _available_offer(database_url, "ai_explain_ticket")
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price - 1)
    before = _snapshot(database_url)

    response = _purchase(client, candidate, "shop-e-baseline-insufficient")

    assert response.status_code == 400
    assert response.get_json()["code"] == "INSUFFICIENT_COINS"
    _assert_no_mutation(before, _snapshot(database_url))


def test_existing_c019_postgres_probe_cosmetic_purchase_does_not_equip(
    shop_e_postgres, monkeypatch
):
    database_url = shop_e_postgres["database_url"]
    candidate = _available_offer(database_url, "robe_bamboo")
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price * 3 + 100)
    before = _snapshot(database_url)

    first = _purchase(client, candidate, "shop-e-baseline-cosmetic")
    assert first.status_code == 200, first.get_json()
    _assert_committed_purchase(
        database_url, candidate, "shop-e-baseline-cosmetic", first
    )
    after_first = _snapshot(database_url)
    _assert_single_grant_delta(before, after_first, candidate)
    assert after_first["appearance"] == before["appearance"]

    second = _purchase(client, candidate, "shop-e-baseline-cosmetic-owned")
    assert second.status_code in {200, 409, 422}
    if second.status_code == 200:
        assert second.get_json()["status"] == "already_owned"
        assert second.get_json()["granted"] is False
    assert _snapshot(database_url) == after_first


def test_closed_gate_fails_closed_without_mutation(shop_e_postgres, monkeypatch):
    database_url = shop_e_postgres["database_url"]
    candidate = _available_offer(database_url, "hint_ticket")
    client = _session_client(database_url, monkeypatch)
    monkeypatch.delenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", raising=False)
    before = _snapshot(database_url)

    response = _purchase(client, candidate, "shop-e-closed-gate")

    assert response.status_code == 409
    assert response.get_json()["code"] == "SHOP_PURCHASE_DISABLED"
    _assert_no_mutation(before, _snapshot(database_url))


def test_purchase_operation_migration_is_additive_idempotent_and_not_production(
    shop_e_postgres,
):
    database_url = shop_e_postgres["database_url"]
    conn = _connect(database_url)
    try:
        conn.execute(f"DROP TABLE {PURCHASE_OPERATIONS_TABLE}")
        dry_run = upgrade_purchase_operations(conn, dry_run=True)
        assert dry_run["dry_run"] is True
        assert dry_run["missing"] == [PURCHASE_OPERATIONS_TABLE]
        assert validate_purchase_schema(conn)["present"] is False

        first = upgrade_purchase_operations(conn)
        conn.commit()
        second = upgrade_purchase_operations(conn)
        conn.commit()
        assert first["created"] == [PURCHASE_OPERATIONS_TABLE]
        assert second["created"] == []
        assert validate_purchase_schema(conn)["present"] is True
        assert first["schema_version"] == "coin_purchase_operations_v1"
        assert second["schema_version"] == "coin_purchase_operations_v1"
    finally:
        conn.close()


def test_c019_postgres_transaction_boundary_rolls_back_partial_bundle_probe(
    shop_e_postgres,
):
    """A test-owned multi-grant failure cannot leave a debit or partial grant."""

    database_url = shop_e_postgres["database_url"]
    from coin_purchase_authority import (
        AcquisitionFailed,
        purchase_with_coins,
    )
    from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority

    offer = CoinShopOffer(
        offer_id="shop.test.bundle",
        item_id="hint_ticket",
        quantity=2,
        currency_type="COINS",
        price=17,
        destination="shop_inventory",
        acquisition_class="CONSUMABLE",
        offer_type="ITEM",
        offer_version="shop-e-test-bundle-v1",
        status="ACTIVE",
        duplicate_policy="STACK",
        eligibility_metadata={"source": "shop-e-test"},
        presentation_metadata={},
    )

    class PartialGrantThenFail:
        def acquire(self, conn, *, user_id, offer, purchase_operation_id):
            del purchase_operation_id
            conn.execute(
                "INSERT INTO shop_inventory(user_id,item_key,qty) "
                "VALUES(?,?,?) ON CONFLICT(user_id,item_key) DO UPDATE "
                "SET qty=shop_inventory.qty+excluded.qty",
                (user_id, offer.item_id, offer.quantity),
            )
            conn.execute(
                "INSERT INTO shop_inventory(user_id,item_key,qty) "
                "VALUES(?,?,?) ON CONFLICT(user_id,item_key) DO UPDATE "
                "SET qty=shop_inventory.qty+excluded.qty",
                (user_id, "shop_e_partial_probe", 1),
            )
            raise AcquisitionFailed("SHOP-E synthetic bundle sub-grant failure")

    _set_coins(database_url, 100)
    before = _snapshot(database_url)
    conn = _connect(database_url)
    try:
        with pytest.raises(AcquisitionFailed):
            purchase_with_coins(
                conn,
                1,
                "shop-e-synthetic-bundle-failure",
                offer.offer_id,
                offer_authority=StaticShopOfferAuthority([offer]),
                acquisition_authority=PartialGrantThenFail(),
            )
        conn.rollback()
    finally:
        conn.close()
    _assert_no_mutation(before, _snapshot(database_url))


@pytest.fixture()
def complete_matrix(shop_e_postgres):
    try:
        return _candidate_offers(shop_e_postgres["database_url"])
    except CandidateIncomplete as exc:
        pytest.skip(f"SHOP-F candidate precondition blocked: {exc}")


@pytest.mark.parametrize("spec", SKU_MATRIX, ids=lambda spec: spec.sku)
def test_launch_sku_server_price_debit_log_grant_replay_and_presentation_boundary(
    shop_e_postgres, monkeypatch, complete_matrix, spec
):
    database_url = shop_e_postgres["database_url"]
    candidate = complete_matrix[spec.sku]
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price * 3 + 100)
    before = _snapshot(database_url)

    first = _purchase(client, candidate, f"shop-e-{spec.sku}-first")
    assert first.status_code == 200, first.get_json()
    first_body = _assert_committed_purchase(
        database_url, candidate, f"shop-e-{spec.sku}-first", first
    )
    after_first = _snapshot(database_url)
    assert after_first["coins"] == (
        before["coins"] - candidate.offer.server_price
    )
    _assert_single_grant_delta(before, after_first, candidate)

    # A replay is also a tampered-client retry.  It must not debit or grant
    # again, and its result must come from the committed operation row.
    replay = _purchase(client, candidate, f"shop-e-{spec.sku}-first")
    assert replay.status_code == 200, replay.get_json()
    assert replay.get_json()["replayed"] is True
    assert _snapshot(database_url) == after_first

    if spec.sku in EFFECT_SKUS:
        assert _snapshot(database_url)["effects"] == before["effects"]
    if spec.kind == "cosmetic":
        assert _snapshot(database_url)["appearance"] == before["appearance"]
    assert first_body["canonical_acquisition_result"]


@pytest.mark.parametrize("spec", SKU_MATRIX, ids=lambda spec: spec.sku)
def test_insufficient_coins_rolls_back_everything(
    shop_e_postgres, monkeypatch, complete_matrix, spec
):
    database_url = shop_e_postgres["database_url"]
    candidate = complete_matrix[spec.sku]
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, max(0, candidate.offer.server_price - 1))
    before = _snapshot(database_url)

    response = _purchase(client, candidate, f"shop-e-{spec.sku}-poor")

    assert response.status_code == 400, response.get_json()
    assert response.get_json()["code"] == "INSUFFICIENT_COINS"
    _assert_no_mutation(before, _snapshot(database_url))


@pytest.mark.parametrize("spec", COSMETIC_SKUS, ids=lambda sku: sku)
def test_cosmetics_reject_owned_and_never_mutate_player_appearance(
    shop_e_postgres, monkeypatch, complete_matrix, spec
):
    database_url = shop_e_postgres["database_url"]
    candidate = complete_matrix[spec]
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price * 3 + 100)

    first = _purchase(client, candidate, f"shop-e-{spec}-owned-first")
    assert first.status_code == 200, first.get_json()
    after_first = _snapshot(database_url)
    second = _purchase(client, candidate, f"shop-e-{spec}-owned-second")

    if second.status_code == 200:
        assert second.get_json()["status"] == "already_owned"
        assert second.get_json()["granted"] is False
    else:
        assert second.status_code in {409, 422}
        assert second.get_json().get("code") in {
            "EQUIPMENT_ALREADY_OWNED",
            "ACQUISITION_FAILED",
            "PURCHASE_OPERATION_CONFLICT",
        }
    assert _snapshot(database_url) == after_first
    assert _snapshot(database_url)["appearance"] == after_first["appearance"]


def test_concurrent_duplicate_has_one_debit_one_grant_and_one_replay(
    shop_e_postgres, monkeypatch, complete_matrix
):
    database_url = shop_e_postgres["database_url"]
    candidate = complete_matrix[CONSUMABLE_SKUS[0]]
    app_module = _app_module()
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _PostgresDbContext(database_url),
    )
    app_module.app.config.update(
        TESTING=True,
        PROPAGATE_EXCEPTIONS=False,
        SESSION_COOKIE_SECURE=False,
    )
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price * 3 + 100)

    def submit():
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "shop-e-concurrent"
        return _purchase(client, candidate, "shop-e-concurrent-duplicate")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: submit(), (1, 2)))

    assert [response.status_code for response in responses] == [200, 200]
    assert sorted(response.get_json()["replayed"] for response in responses) == [
        False,
        True,
    ]
    snapshot = _snapshot(database_url)
    assert len(snapshot["currency_logs"]) == 1
    assert len(snapshot["operations"]) == 1


def test_same_operation_id_different_offer_is_conflict_without_second_debit(
    shop_e_postgres, monkeypatch, complete_matrix
):
    database_url = shop_e_postgres["database_url"]
    first_candidate = complete_matrix[CONSUMABLE_SKUS[0]]
    second_candidate = complete_matrix[COSMETIC_SKUS[0]]
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, first_candidate.offer.server_price * 3 + 100)

    first = _purchase(client, first_candidate, "shop-e-operation-conflict")
    assert first.status_code == 200, first.get_json()
    after_first = _snapshot(database_url)
    conflict = _purchase(client, second_candidate, "shop-e-operation-conflict")

    assert conflict.status_code == 409
    assert conflict.get_json()["code"] == "PURCHASE_OPERATION_CONFLICT"
    assert _snapshot(database_url) == after_first


def test_unknown_sku_is_rejected_before_any_mutation(shop_e_postgres, monkeypatch):
    database_url = shop_e_postgres["database_url"]
    client = _session_client(database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    before = _snapshot(database_url)

    response = client.post(
        "/api/shop/buy",
        json={
            "item_key": "shop_e_unknown_sku",
            "purchase_operation_id": "shop-e-unknown",
            "price": 1,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "UNKNOWN_OFFER"
    _assert_no_mutation(before, _snapshot(database_url))


def test_grant_exception_after_debit_rolls_back_coin_and_ownership(
    shop_e_postgres, monkeypatch, complete_matrix
):
    database_url = shop_e_postgres["database_url"]
    candidate = complete_matrix[CONSUMABLE_SKUS[0]]
    app_module = _app_module()
    from coin_purchase_authority import AcquisitionFailed

    def fail_acquisition(*args, **kwargs):
        raise AcquisitionFailed("SHOP-E forced acquisition exception")

    monkeypatch.setattr(
        app_module.SqlAcquisitionAuthority,
        "acquire",
        fail_acquisition,
    )
    monkeypatch.setenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", "1")
    _set_coins(database_url, candidate.offer.server_price * 3 + 100)
    before = _snapshot(database_url)
    client = _session_client(database_url, monkeypatch)

    response = _purchase(client, candidate, "shop-e-grant-exception")

    assert response.status_code == 422
    assert response.get_json()["code"] == "ACQUISITION_FAILED"
    _assert_no_mutation(before, _snapshot(database_url))


def test_bundle_sub_grant_failure_is_fully_atomic(
    shop_e_postgres, complete_matrix
):
    database_url = shop_e_postgres["database_url"]
    candidate = complete_matrix["premium_hint_bundle"]
    from coin_purchase_authority import (
        AcquisitionFailed,
        SqlAcquisitionAuthority,
        purchase_with_coins,
    )
    from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority

    bound_offer = bind_bundle_acquisition_facts(
        CoinShopOffer.from_mapping(candidate.offer.as_c019_mapping()),
        canonical_bundle_acquisition_facts("premium_hint_bundle"),
    )

    class PartialGrantThenFail(SqlAcquisitionAuthority):
        def _acquire_bundle_grant(self, conn, *, user_id, parent_offer, grant):
            super()._acquire_bundle_grant(
                conn,
                user_id=user_id,
                parent_offer=parent_offer,
                grant=grant,
            )
            conn.execute(
                "INSERT INTO shop_inventory(user_id,item_key,qty) "
                "VALUES(?,?,?) ON CONFLICT(user_id,item_key) DO UPDATE "
                "SET qty=shop_inventory.qty+excluded.qty",
                (user_id, "shop_e_partial_probe", 1),
            )
            raise AcquisitionFailed("SHOP-E forced sub-grant failure")

    _set_coins(database_url, candidate.offer.server_price * 3 + 100)
    before = _snapshot(database_url)
    conn = _connect(database_url)
    try:
        with pytest.raises(AcquisitionFailed):
            purchase_with_coins(
                conn,
                1,
                "shop-e-bundle-partial-failure",
                bound_offer.offer_id,
                offer_authority=StaticShopOfferAuthority([bound_offer]),
                acquisition_authority=PartialGrantThenFail(),
            )
        conn.rollback()
    finally:
        conn.close()
    after = _snapshot(database_url)
    _assert_no_mutation(before, after)
