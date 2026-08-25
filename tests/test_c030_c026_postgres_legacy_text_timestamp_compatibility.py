"""C030 disposable PostgreSQL proof for C026 legacy TEXT timestamps."""

from __future__ import annotations

from datetime import datetime, timezone
import shutil
import subprocess
import time
from typing import Any
from uuid import uuid4

import pytest

from coin_purchase_authority import (
    AcquisitionFailed,
    SqlAcquisitionAuthority,
    purchase_with_coins,
)
from db import PostgresConnectionWrapper
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033
from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority


POSTGRES_IMAGE = "postgres:16.14-alpine"
POSTGRES_USER = "c030"
POSTGRES_PASSWORD = "c030_disposable_password"
POSTGRES_DATABASE = "c030"
FIXED_NOW = datetime(2026, 8, 26, 4, 0, 0, tzinfo=timezone.utc)
SLOT_DEFS = (
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "cloth_robe", "slot": "armor"},
    {"id": "lucky_stone", "slot": "accessory"},
)
SLOT_SOURCE = {
    "iron_sword": "weapon",
    "cloth_robe": "armor",
    "lucky_stone": "accessory",
}


def _run_docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _wait_for_postgres(database_url: str, timeout: float = 60.0) -> None:
    import psycopg2

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            raw = psycopg2.connect(database_url, connect_timeout=2)
            raw.close()
            return
        except Exception as error:  # pragma: no cover - timing dependent
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(f"disposable PostgreSQL did not become ready: {last_error}")


@pytest.fixture(scope="module")
def disposable_postgres() -> dict[str, str]:
    if shutil.which("docker") is None:
        pytest.skip("docker is unavailable; disposable PostgreSQL proof skipped")

    container_name = f"c030-pg-{uuid4().hex[:12]}"
    run = _run_docker(
        "run",
        "--rm",
        "--detach",
        "--name",
        container_name,
        "--env",
        f"POSTGRES_USER={POSTGRES_USER}",
        "--env",
        f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
        "--env",
        f"POSTGRES_DB={POSTGRES_DATABASE}",
        "--publish",
        "127.0.0.1::5432",
        POSTGRES_IMAGE,
    )
    if run.returncode != 0:
        pytest.skip(
            "disposable PostgreSQL unavailable: "
            f"{run.stderr.strip() or run.stdout.strip()}"
        )

    try:
        port_result = _run_docker(
            "inspect",
            "--format",
            "{{(index (index .NetworkSettings.Ports \"5432/tcp\") 0).HostPort}}",
            container_name,
            check=True,
        )
        host_port = port_result.stdout.strip()
        if not host_port.isdigit():
            raise RuntimeError("disposable PostgreSQL host port was not published")
        database_url = (
            f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@127.0.0.1:"
            f"{host_port}/{POSTGRES_DATABASE}"
        )
        _wait_for_postgres(database_url)

        import psycopg2

        raw = psycopg2.connect(database_url)
        with raw.cursor() as cursor:
            cursor.execute("SELECT version()")
            server_version = str(cursor.fetchone()[0])
        raw.close()
        if "PostgreSQL 16.14" not in server_version:
            raise RuntimeError(f"unexpected disposable PostgreSQL version: {server_version}")
        yield {
            "database_url": database_url,
            "container_name": container_name,
            "image": POSTGRES_IMAGE,
            "server_version": server_version,
        }
    finally:
        _run_docker("rm", "--force", container_name)


@pytest.fixture(scope="module")
def pg_connection(disposable_postgres: dict[str, str]):
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(
        disposable_postgres["database_url"],
        cursor_factory=DictCursor,
    )
    conn = PostgresConnectionWrapper(raw, pooled=False)
    try:
        _create_legacy_text_schema(conn)
        conn.commit()
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def _create_legacy_text_schema(conn: PostgresConnectionWrapper) -> None:
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
        """CREATE TABLE public.player_inventory (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop'
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
        """CREATE TABLE public.player_wardrobe (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL,
            UNIQUE (user_id, item_id)
        )"""
    )
    upgrade_b033(conn, equipment_defs=SLOT_DEFS)
    upgrade_purchase_operations(conn)
    upgrade_event_outbox(conn)

    timestamp_columns = {
        (str(row["table_name"]), str(row["column_name"])): str(row["data_type"])
        for row in conn.execute(
            """SELECT table_name, column_name, data_type
                 FROM information_schema.columns
                WHERE table_schema='public'
                  AND (table_name, column_name) IN (
                      ('currency_log', 'created_at'),
                      ('player_inventory', 'obtained_at'),
                      ('player_wardrobe', 'obtained_at')
                  )"""
        ).fetchall()
    }
    assert timestamp_columns == {
        ("currency_log", "created_at"): "text",
        ("player_inventory", "obtained_at"): "text",
        ("player_wardrobe", "obtained_at"): "text",
    }


def _seed_user(conn: PostgresConnectionWrapper, user_id: int, coins: int = 1000) -> None:
    conn.execute(
        "INSERT INTO user_stats(user_id, coins) VALUES(?, ?)",
        (user_id, coins),
    )


def _offer(
    *,
    offer_id: str,
    item_id: str,
    destination: str,
    acquisition_class: str,
    duplicate_policy: str,
    price: int,
) -> CoinShopOffer:
    return CoinShopOffer(
        offer_id=offer_id,
        item_id=item_id,
        quantity=1,
        currency_type="COINS",
        price=price,
        destination=destination,
        acquisition_class=acquisition_class,
        offer_type="ITEM",
        offer_version="v1-c030",
        status="ACTIVE",
        duplicate_policy=duplicate_policy,
    )


def _purchase(
    conn: PostgresConnectionWrapper,
    *,
    user_id: int,
    operation_id: str,
    offer: CoinShopOffer,
    lineage_writer: Any = None,
):
    authority = StaticShopOfferAuthority({offer.offer_id: offer})
    return purchase_with_coins(
        conn,
        user_id,
        operation_id,
        offer.offer_id,
        offer_authority=authority,
        acquisition_authority=SqlAcquisitionAuthority(
            equipment_slot_source=SLOT_SOURCE
        ),
        lineage_writer=lineage_writer,
        now=FIXED_NOW,
    )


def _column_type(
    conn: PostgresConnectionWrapper, table_name: str, column_name: str
) -> str:
    row = conn.execute(
        """SELECT data_type FROM information_schema.columns
            WHERE table_schema='public' AND table_name=? AND column_name=?""",
        (table_name, column_name),
    ).fetchone()
    assert row is not None
    return str(row["data_type"])


def test_stackable_and_equipment_accept_timezone_aware_datetime_into_text(
    pg_connection: PostgresConnectionWrapper,
    disposable_postgres: dict[str, str],
) -> None:
    conn = pg_connection
    _seed_user(conn, 1)
    _seed_user(conn, 2)

    stackable = _offer(
        offer_id="shop.static.hint_ticket",
        item_id="hint_ticket",
        destination="shop_inventory",
        acquisition_class="CONSUMABLE",
        duplicate_policy="STACK",
        price=30,
    )
    stack_result = _purchase(
        conn,
        user_id=1,
        operation_id="c030-stack-a",
        offer=stackable,
    )
    conn.commit()
    stack_replay = _purchase(
        conn,
        user_id=1,
        operation_id="c030-stack-a",
        offer=stackable,
    )

    equipment = _offer(
        offer_id="shop.static.iron_sword",
        item_id="iron_sword",
        destination="player_inventory",
        acquisition_class="WEAPON",
        duplicate_policy="ALLOW_DUPLICATE",
        price=100,
    )
    equipment_result = _purchase(
        conn,
        user_id=2,
        operation_id="c030-equipment-a",
        offer=equipment,
    )
    conn.commit()
    equipment_replay = _purchase(
        conn,
        user_id=2,
        operation_id="c030-equipment-a",
        offer=equipment,
    )

    assert _column_type(conn, "currency_log", "created_at") == "text"
    assert _column_type(conn, "player_inventory", "obtained_at") == "text"
    assert _column_type(conn, "player_wardrobe", "obtained_at") == "text"
    assert FIXED_NOW.tzinfo is not None
    assert FIXED_NOW.utcoffset() is not None

    currency_row = conn.execute(
        "SELECT delta, balance_after, created_at FROM currency_log "
        "WHERE user_id=? AND reason=?",
        (1, "coin_purchase:shop.static.hint_ticket:c030-stack-a"),
    ).fetchone()
    assert currency_row is not None
    assert currency_row["delta"] == -30
    assert currency_row["balance_after"] == 970
    assert isinstance(currency_row["created_at"], str)
    assert currency_row["created_at"]
    assert stack_result.coins_before == 1000
    assert stack_result.coins_after == 970
    assert stack_replay.replayed is True
    assert conn.execute(
        "SELECT coins FROM user_stats WHERE user_id=1"
    ).fetchone()["coins"] == 970
    assert conn.execute(
        "SELECT COUNT(*) FROM currency_log WHERE user_id=1"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_ticket'"
    ).fetchone()["qty"] == 1
    operation = conn.execute(
        "SELECT operation_status FROM coin_purchase_operations "
        "WHERE user_id=1 AND purchase_operation_id='c030-stack-a'"
    ).fetchone()
    assert operation["operation_status"] == "COMMITTED"

    inventory_row = conn.execute(
        "SELECT id, equipped, canonical_slot, obtained_at FROM player_inventory "
        "WHERE user_id=2 AND equip_id='iron_sword'"
    ).fetchone()
    assert inventory_row is not None
    assert inventory_row["id"] > 0
    assert inventory_row["equipped"] == 0
    assert inventory_row["canonical_slot"] == "weapon"
    assert isinstance(inventory_row["obtained_at"], str)
    assert inventory_row["obtained_at"]
    assert equipment_result.ownership_reference == (
        f"player_inventory:{inventory_row['id']}"
    )
    assert equipment_replay.replayed is True
    assert equipment_replay.ownership_reference == equipment_result.ownership_reference
    assert conn.execute(
        "SELECT COUNT(*) FROM player_inventory WHERE user_id=2"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT coins FROM user_stats WHERE user_id=2"
    ).fetchone()["coins"] == 900

    print(
        "C030_POSTGRES_EVIDENCE="
        f"version={disposable_postgres['server_version']};"
        f"image={disposable_postgres['image']};"
        f"driver=psycopg2;time_type={type(FIXED_NOW).__name__};"
        f"stack_created_at={currency_row['created_at']!r};"
        f"equipment_obtained_at={inventory_row['obtained_at']!r}"
    )


def test_wardrobe_text_timestamp_replay_and_duplicate_policy(
    pg_connection: PostgresConnectionWrapper,
) -> None:
    conn = pg_connection
    _seed_user(conn, 3)
    wardrobe = _offer(
        offer_id="shop.cosmetic.cosmetic.outfit.robe_plain",
        item_id="robe_plain",
        destination="player_wardrobe",
        acquisition_class="COSMETIC",
        duplicate_policy="REJECT_IF_OWNED",
        price=120,
    )

    result = _purchase(
        conn,
        user_id=3,
        operation_id="c030-wardrobe-a",
        offer=wardrobe,
    )
    conn.commit()
    replay = _purchase(
        conn,
        user_id=3,
        operation_id="c030-wardrobe-a",
        offer=wardrobe,
    )
    assert replay.replayed is True
    assert replay.offer_id == result.offer_id

    row = conn.execute(
        "SELECT obtained_at FROM player_wardrobe "
        "WHERE user_id=3 AND item_id='robe_plain'"
    ).fetchone()
    assert row is not None
    assert isinstance(row["obtained_at"], str)
    assert row["obtained_at"]
    assert conn.execute(
        "SELECT coins FROM user_stats WHERE user_id=3"
    ).fetchone()["coins"] == 880

    with pytest.raises(AcquisitionFailed):
        _purchase(
            conn,
            user_id=3,
            operation_id="c030-wardrobe-b",
            offer=wardrobe,
        )
    conn.rollback()
    assert conn.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=3 AND item_id='robe_plain'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT coins FROM user_stats WHERE user_id=3"
    ).fetchone()["coins"] == 880
    assert conn.execute(
        "SELECT COUNT(*) FROM coin_purchase_operations "
        "WHERE user_id=3 AND purchase_operation_id='c030-wardrobe-b'"
    ).fetchone()[0] == 0
    print(
        "C030_WARDROBE_EVIDENCE="
        f"obtained_at={row['obtained_at']!r};"
        f"replay={replay.replayed};duplicate_rows=1"
    )


def test_caller_rollback_removes_coin_inventory_operation_and_outbox_mutations(
    pg_connection: PostgresConnectionWrapper,
) -> None:
    conn = pg_connection
    _seed_user(conn, 4)
    conn.commit()
    equipment = _offer(
        offer_id="shop.static.cloth_robe",
        item_id="cloth_robe",
        destination="player_inventory",
        acquisition_class="ARMOR",
        duplicate_policy="ALLOW_DUPLICATE",
        price=100,
    )

    def fail_lineage(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("C030 forced D5A failure")

    with pytest.raises(AcquisitionFailed):
        _purchase(
            conn,
            user_id=4,
            operation_id="c030-rollback-a",
            offer=equipment,
            lineage_writer=fail_lineage,
        )
    conn.rollback()

    assert conn.execute(
        "SELECT coins FROM user_stats WHERE user_id=4"
    ).fetchone()["coins"] == 1000
    assert conn.execute(
        "SELECT COUNT(*) FROM currency_log WHERE user_id=4"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM player_inventory WHERE user_id=4"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM coin_purchase_operations "
        "WHERE user_id=4 AND purchase_operation_id='c030-rollback-a'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id='4'"
    ).fetchone()[0] == 0
