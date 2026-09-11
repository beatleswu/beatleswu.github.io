"""Focused ACT-D D1 proof for the atomic ``shop_inventory`` consume seam."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from pathlib import Path
import threading

import pytest

from shop_inventory_authority import (
    CONSUME_SQL,
    ShopInventoryInsufficient,
    ShopInventoryInvalidQuantity,
    ShopInventoryUnexpectedRowCount,
    consume_shop_inventory,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = REPO_ROOT / "app.py"


def _create_inventory_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE shop_inventory("
            "user_id INTEGER NOT NULL, "
            "item_key TEXT NOT NULL, "
            "qty INTEGER NOT NULL, "
            "PRIMARY KEY(user_id, item_key)"
            ")"
        )


def _seed(path: Path, quantity: int, *, item_key: str = "hint_scroll") -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(?,?,?)",
            (1, item_key, quantity),
        )


def _quantity(path: Path, *, user_id: int = 1, item_key: str = "hint_scroll") -> int | None:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
            (user_id, item_key),
        ).fetchone()
    return row[0] if row else None


def test_qty_one_consume_one_succeeds_and_reaches_zero(tmp_path: Path) -> None:
    path = tmp_path / "inventory.sqlite"
    _create_inventory_db(path)
    _seed(path, 1)

    with sqlite3.connect(path) as conn:
        assert consume_shop_inventory(conn, 1, "hint_scroll", 1) is True
        assert _quantity_from_connection(conn) == 0
        conn.commit()

    assert _quantity(path) == 0


def test_zero_quantity_and_missing_row_are_typed_insufficiency_without_cleanup(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inventory.sqlite"
    _create_inventory_db(path)
    _seed(path, 0)

    with sqlite3.connect(path) as conn:
        with pytest.raises(ShopInventoryInsufficient) as zero_error:
            consume_shop_inventory(conn, 1, "hint_scroll", 1)
        with pytest.raises(ShopInventoryInsufficient) as missing_error:
            consume_shop_inventory(conn, 1, "missing_item", 1)
        assert zero_error.value.code == "INSUFFICIENT_QUANTITY"
        assert missing_error.value.details["legacy_error"] == "not_owned"
        assert _quantity_from_connection(conn) == 0
        conn.rollback()

    assert _quantity(path) == 0


@pytest.mark.parametrize("quantity", [0, -1, True, False, 1.0, "1", None])
def test_quantity_must_be_a_positive_non_bool_integer(quantity: object) -> None:
    class NoExecuteConnection:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("invalid quantity must be rejected before SQL")

    with pytest.raises(ShopInventoryInvalidQuantity) as error:
        consume_shop_inventory(NoExecuteConnection(), 1, "hint_scroll", quantity)
    assert error.value.code == "INVALID_QUANTITY"


def test_quantity_greater_than_stock_is_insufficient_and_does_not_go_negative(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inventory.sqlite"
    _create_inventory_db(path)
    _seed(path, 1)

    with sqlite3.connect(path) as conn:
        with pytest.raises(ShopInventoryInsufficient):
            consume_shop_inventory(conn, 1, "hint_scroll", 2)
        assert _quantity_from_connection(conn) == 1
        conn.rollback()

    assert _quantity(path) == 1


@pytest.mark.parametrize("rowcount", [None, -1, 2, True])
def test_unexpected_rowcount_fails_closed_without_incidental_transaction_control(
    rowcount: object,
) -> None:
    class Cursor:
        def __init__(self, affected: object):
            self.rowcount = affected

    class ExecuteOnlyConnection:
        def __init__(self, affected: object):
            self.calls: list[tuple[str, tuple[object, ...]]] = []
            self.cursor = Cursor(affected)

        def execute(self, sql: str, parameters: tuple[object, ...]) -> Cursor:
            self.calls.append((sql, parameters))
            return self.cursor

    conn = ExecuteOnlyConnection(rowcount)
    with pytest.raises(ShopInventoryUnexpectedRowCount) as error:
        consume_shop_inventory(conn, 1, "hint_scroll", 1)

    assert error.value.code == "UNEXPECTED_ROWCOUNT"
    assert error.value.details["rowcount"] == rowcount
    assert len(conn.calls) == 1
    sql, parameters = conn.calls[0]
    assert sql == CONSUME_SQL
    assert "SELECT" not in sql.upper()
    assert "qty>=?" in sql.replace(" ", "")
    assert parameters == (1, 1, "hint_scroll", 1)


def test_caller_rollback_restores_inventory(tmp_path: Path) -> None:
    path = tmp_path / "inventory.sqlite"
    _create_inventory_db(path)
    _seed(path, 1)

    conn = sqlite3.connect(path)
    try:
        assert consume_shop_inventory(conn, 1, "hint_scroll", 1) is True
        assert _quantity_from_connection(conn) == 0
        conn.rollback()
    finally:
        conn.close()

    assert _quantity(path) == 1


def test_domain_service_never_commits_or_rolls_back() -> None:
    raw = sqlite3.connect(":memory:")
    raw.execute(
        "CREATE TABLE shop_inventory("
        "user_id INTEGER, item_key TEXT, qty INTEGER, "
        "PRIMARY KEY(user_id,item_key)"
        ")"
    )
    raw.execute(
        "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(1,'hint_scroll',1)"
    )

    class TransactionSpy:
        def __init__(self, connection: sqlite3.Connection):
            self.connection = connection
            self.commit_calls = 0
            self.rollback_calls = 0

        def execute(self, *args: object, **kwargs: object):
            return self.connection.execute(*args, **kwargs)

        def commit(self) -> None:
            self.commit_calls += 1

        def rollback(self) -> None:
            self.rollback_calls += 1

    conn = TransactionSpy(raw)
    try:
        assert consume_shop_inventory(conn, 1, "hint_scroll") is True
        assert conn.commit_calls == 0
        assert conn.rollback_calls == 0
    finally:
        raw.rollback()
        raw.close()


def _concurrent_consume(path: Path, start: threading.Barrier) -> str:
    conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    try:
        start.wait(timeout=10.0)
        conn.execute("BEGIN IMMEDIATE")
        try:
            consume_shop_inventory(conn, 1, "hint_scroll", 1)
        except ShopInventoryInsufficient:
            # The caller resolves the rejected transaction; the domain
            # service itself must not rollback or retry the race.
            conn.commit()
            return "insufficient"
        else:
            conn.commit()
            return "success"
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_concurrent_consume_one_stock_has_exactly_one_success(tmp_path: Path) -> None:
    path = tmp_path / "inventory.sqlite"
    _create_inventory_db(path)
    _seed(path, 1)
    start = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_concurrent_consume, path, start) for _ in range(2)]
        results = [future.result(timeout=20.0) for future in futures]

    assert results.count("success") == 1
    assert results.count("insufficient") == 1
    assert _quantity(path) == 0


def _quantity_from_connection(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key='hint_scroll'"
    ).fetchone()[0]


def test_existing_explain_and_shop_use_error_mappings_remain_unchanged() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    explain_start = source.index("@app.route('/api/explain'")
    explain_end = source.index("@app.route('/api/recommend'", explain_start)
    explain_route = source[explain_start:explain_end]
    shop_start = source.index("@app.route('/api/shop/use'")
    shop_end = source.index("@app.route('/api/shop/status'", shop_start)
    shop_route = source[shop_start:shop_end]

    assert "if _inv_consume(_c, _uid_t, 'ai_explain_ticket'):" in explain_route
    assert "'error': 'premium_required'" in explain_route
    assert "), 403" in explain_route
    assert "if not _inv_consume(conn, uid, item_key):" in shop_route
    assert "return jsonify({'error': 'not_owned'}), 400" in shop_route


def test_authority_is_scoped_to_shop_inventory_and_does_not_enable_loadout() -> None:
    source = Path(__file__).resolve().parents[1].joinpath(
        "shop_inventory_authority.py"
    ).read_text(encoding="utf-8")
    assert "shop_inventory" in source
    for forbidden_store in (
        "player_inventory",
        "player_wardrobe",
        "player_appearance",
        "EQUIPMENT_CANONICAL_LOADOUT_ENABLED",
    ):
        assert forbidden_store not in source
