"""G114 isolated DB regression of safe auto-assignment and preservation."""
import sqlite3
import pytest

import app as product

BAD = {"id": 15483, "content": "(;SZ[19](;B[aa])(;B[bb]))"}
GOOD = {"id": 12345, "content": "(;SZ[19];B[cc];W[dd];B[ee])"}


@pytest.fixture
def ctx(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE daily_challenge("
        "challenge_date TEXT PRIMARY KEY, question_id INTEGER, "
        "set_by TEXT, note TEXT)"
    )
    conn.execute(
        "CREATE TABLE daily_challenge_log("
        "id INTEGER PRIMARY KEY, user_id INTEGER, challenge_date TEXT, correct INTEGER)"
    )
    monkeypatch.setattr(product, "get_db", lambda: conn)
    monkeypatch.setattr(product, "_load_questions", lambda: [BAD, GOOD])
    yield conn
    conn.close()


def test_unsubmitted_auto_legacy_15483_replaced_atomically(ctx):
    ctx.execute(
        "INSERT INTO daily_challenge VALUES(?,?,?,?)",
        ("2026-10-26", 15483, "auto", None),
    )
    chosen = product.get_or_create_daily_challenge("2026-10-26")
    assert chosen["question_id"] == 12345
    assert ctx.execute("SELECT COUNT(*) FROM daily_challenge_log").fetchone()[0] == 0


def test_incorrect_only_15483_rotates_without_rewriting_old_log(ctx):
    ctx.execute(
        "INSERT INTO daily_challenge VALUES(?,?,?,?)",
        ("2026-10-26", 15483, "auto", None),
    )
    ctx.execute(
        "INSERT INTO daily_challenge_log(user_id,challenge_date,correct) VALUES(?,?,?)",
        (99, "2026-10-26", 0),
    )
    chosen = product.get_or_create_daily_challenge("2026-10-26")
    assert chosen["question_id"] == 12345
    assert chosen["set_by"] == "auto_g114_rotated"
    assert ctx.execute(
        "SELECT correct FROM daily_challenge_log WHERE user_id=99"
    ).fetchone()[0] == 0
    # Further calls are stable; the same date cannot rotate twice.
    assert product.get_or_create_daily_challenge("2026-10-26") == chosen


def test_admin_curated_assignment_is_never_overridden(ctx):
    ctx.execute(
        "INSERT INTO daily_challenge VALUES(?,?,?,?)",
        ("2026-10-26", 15483, "admin", None),
    )
    chosen = product.get_or_create_daily_challenge("2026-10-26")
    assert chosen["question_id"] == 15483


def test_uncreated_day_only_draws_from_authoritative_pool(ctx):
    chosen = product.get_or_create_daily_challenge("2026-10-27")
    assert chosen["question_id"] == 12345
    assert ctx.execute("SELECT COUNT(*) FROM daily_challenge").fetchone()[0] == 1


def test_no_eligible_question_does_not_create_any_assignment(ctx, monkeypatch):
    monkeypatch.setattr(product, "_load_questions", lambda: [BAD])
    result = product.get_or_create_daily_challenge("2026-10-28")
    assert result is None
    assert ctx.execute("SELECT COUNT(*) FROM daily_challenge").fetchone()[0] == 0
