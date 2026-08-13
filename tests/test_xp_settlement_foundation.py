"""Focused R1A tests that do not import app.py or contact a database."""

from pathlib import Path

import pytest

from xp_settlement import (
    FACTOR_SCALE,
    LEDGER_COLUMNS,
    LEDGER_CONSTRAINT_NAMES,
    LEDGER_INDEXES,
    LEDGER_SCHEMA_SQL,
    LOCK_TIMEOUT_VALUE,
    MAX_RETRY_VALUE,
    NO_PREMIUM_FACTOR_PPM,
    PREMIUM_18_FACTOR_PPM,
    ROUNDING_POLICY_VERSION,
    SettlementRequest,
    XPSettlement,
    XPSettlementConflict,
    XPSettlementDisabled,
    calculate_xp,
    canonical_modifier_payload,
    ensure_xp_settlement_schema,
    multiply_factors_final_round,
    round_half_up_fraction,
    xp_ledger_schema_enabled,
    xp_settlement_enabled,
)


def test_server_side_flags_default_off(monkeypatch):
    monkeypatch.delenv("XP_LEDGER_SCHEMA_ENABLED", raising=False)
    monkeypatch.delenv("XP_SETTLEMENT_ENABLED", raising=False)
    assert xp_ledger_schema_enabled() is False
    assert xp_settlement_enabled() is False

    monkeypatch.setenv("XP_LEDGER_SCHEMA_ENABLED", "true")
    monkeypatch.setenv("XP_SETTLEMENT_ENABLED", "1")
    assert xp_ledger_schema_enabled() is True
    assert xp_settlement_enabled() is True


def test_fixed_point_constants_are_integer_and_single_scale():
    assert FACTOR_SCALE == 1_000_000
    assert NO_PREMIUM_FACTOR_PPM == 1_000_000
    assert PREMIUM_18_FACTOR_PPM == 1_180_000
    assert ROUNDING_POLICY_VERSION == "r1a-round-half-up-v1"


def test_round_half_up_locked_vectors():
    assert multiply_factors_final_round(1, [1_500_000]) == 2
    assert multiply_factors_final_round(5, [1_180_000]) == 6
    assert multiply_factors_final_round(15, [1_500_000, 1_180_000]) == 27
    assert multiply_factors_final_round(1300, [1_180_000]) == 1534
    assert multiply_factors_final_round(1, [1_150_000]) == 1

    # Exact tie, below tie and above tie; no Python banker-rounding behavior.
    assert round_half_up_fraction(150, 100) == 2
    assert round_half_up_fraction(149, 100) == 1
    assert round_half_up_fraction(151, 100) == 2
    # Signed admin adjustments use the same away-from-zero tie rule.
    assert round_half_up_fraction(-150, 100) == -2
    assert round_half_up_fraction(-149, 100) == -1
    assert round_half_up_fraction(-151, 100) == -2


def test_modifier_pipeline_rounds_only_once_and_records_integer_factors():
    calculation = calculate_xp(
        10,
        (5,),
        combo_factor_ppm=1_500_000,
        support_factor_ppm=1_000_000,
        premium_factor_ppm=1_180_000,
    )
    assert calculation.additive_learning_xp == 5
    assert calculation.final_xp == 27
    assert calculation.modifier_payload == {
        "factor_scale": 1_000_000,
        "combo_factor_ppm": 1_500_000,
        "support_factor_ppm": 1_000_000,
        "premium_factor_ppm": 1_180_000,
    }
    assert calculation.numerator == 15 * 1_500_000 * 1_000_000 * 1_180_000
    assert calculation.denominator == 1_000_000 ** 3


def test_modifier_payload_rejects_float_authority():
    assert canonical_modifier_payload({"premium_factor_ppm": 1_180_000}) == (
        '{"premium_factor_ppm":1180000}'
    )
    with pytest.raises(TypeError, match="floating-point"):
        canonical_modifier_payload({"premium_factor": 1.18})


def test_settlement_request_validates_opening_and_admin_contracts():
    SettlementRequest(
        user_id=7,
        source_type="review",
        source_id="credited:7:42",
        idempotency_key="review:7:42:v1",
    ).validate()

    SettlementRequest(
        user_id=7,
        source_type="admin",
        source_id="ticket-123",
        idempotency_key="admin:ticket-123:v1",
        settlement_kind="ADMIN_ADJUSTMENT",
        actor_type="ADMIN",
        actor_id=99,
        reason_or_ticket="ticket-123",
        admin_xp_delta=-10,
    ).validate()

    SettlementRequest(
        user_id=7,
        source_type="opening_balance",
        source_id="cutover-1:7",
        idempotency_key="opening_balance:cutover-1:7:v1",
        settlement_kind="OPENING_BALANCE",
        actor_type="MIGRATION",
        reason_or_ticket="cutover-1",
        opening_xp=300_000,
    ).validate()

    with pytest.raises(ValueError, match="reason_or_ticket"):
        SettlementRequest(
            user_id=7,
            source_type="admin",
            source_id="ticket-123",
            idempotency_key="admin:ticket-123:v1",
            settlement_kind="ADMIN_ADJUSTMENT",
            actor_type="ADMIN",
            actor_id=99,
            admin_xp_delta=10,
        ).validate()

    with pytest.raises(ValueError, match="opening balances do not contain"):
        SettlementRequest(
            user_id=7,
            source_type="opening_balance",
            source_id="cutover-1:7",
            idempotency_key="opening_balance:cutover-1:7:v1",
            settlement_kind="OPENING_BALANCE",
            actor_type="MIGRATION",
            reason_or_ticket="cutover-1",
            opening_xp=300_000,
            base_xp=1,
        ).validate()


def test_settlement_foundation_is_dormant_by_default():
    class ShouldNotBeCalled:
        def execute(self, *args, **kwargs):  # pragma: no cover - assertion path
            raise AssertionError("disabled foundation touched the database")

    request = SettlementRequest(
        user_id=7,
        source_type="review",
        source_id="credited:7:42",
        idempotency_key="review:7:42:v1",
    )
    with pytest.raises(XPSettlementDisabled):
        XPSettlement(ShouldNotBeCalled()).settle(request)


def test_schema_contract_contains_owner_locked_shape():
    required_columns = {
        "settlement_id",
        "user_id",
        "source_type",
        "source_id",
        "source_version",
        "settlement_kind",
        "base_xp",
        "xp_delta",
        "modifier_payload",
        "premium_eligibility",
        "already_premium_adjusted",
        "premium_factor_ppm",
        "before_xp",
        "after_xp",
        "idempotency_key",
        "settlement_status",
        "grant_policy_version",
        "curve_version",
        "rounding_policy_version",
        "source_context",
        "request_correlation_id",
        "actor_type",
        "actor_id",
        "reason_or_ticket",
        "error_code",
        "created_at",
        "settled_at",
    }
    assert set(LEDGER_COLUMNS) == required_columns
    for column in required_columns:
        assert column in LEDGER_SCHEMA_SQL

    assert "premium_factor_ppm BIGINT" in LEDGER_SCHEMA_SQL
    assert "xp_delta = 0" in LEDGER_SCHEMA_SQL
    assert "before_xp = after_xp" in LEDGER_SCHEMA_SQL
    assert "actor_type = 'MIGRATION'" in LEDGER_SCHEMA_SQL
    assert "settlement_status = 'SETTLED'" in LEDGER_SCHEMA_SQL
    assert "REJECTED" not in LEDGER_SCHEMA_SQL
    assert "UNIQUE (user_id, idempotency_key)" in LEDGER_SCHEMA_SQL
    assert "actor_type = 'ADMIN'" in LEDGER_SCHEMA_SQL
    assert "reason_or_ticket IS NOT NULL" in LEDGER_SCHEMA_SQL
    assert "actor_type IN ('PLAYER', 'SYSTEM', 'ADMIN', 'MIGRATION')" in LEDGER_SCHEMA_SQL

    for constraint_name in LEDGER_CONSTRAINT_NAMES:
        assert constraint_name in LEDGER_SCHEMA_SQL
    for index_name, statement in LEDGER_INDEXES.items():
        assert index_name in statement
        assert "IF NOT EXISTS" in statement


def test_schema_key_limits_and_retry_contract_are_bounded():
    assert LEDGER_COLUMNS["source_type"] == ("character varying", 64, "NO")
    assert LEDGER_COLUMNS["source_id"] == ("character varying", 255, "NO")
    assert LEDGER_COLUMNS["source_version"] == ("character varying", 32, "NO")
    assert LEDGER_COLUMNS["idempotency_key"] == ("character varying", 255, "NO")
    assert LEDGER_COLUMNS["request_correlation_id"] == (
        "character varying", 255, "YES"
    )
    assert MAX_RETRY_VALUE == 2
    assert LOCK_TIMEOUT_VALUE is None


def test_r1a_only_gates_schema_creation_in_app():
    app_source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(
        encoding="utf-8"
    )
    assert "if xp_ledger_schema_enabled():" in app_source
    assert "ensure_xp_settlement_schema(conn)" in app_source
    assert "from xp_settlement import" in app_source


class _Cursor:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _SchemaConnection:
    def __init__(self, *, missing_column=None):
        self.statements = []
        self.missing_column = missing_column

    def execute(self, statement, parameters=None):
        self.statements.append(statement)
        if "information_schema.columns" in statement:
            rows = []
            for column, (data_type, max_length, nullable) in LEDGER_COLUMNS.items():
                if column == self.missing_column:
                    continue
                rows.append(
                    {
                        "column_name": column,
                        "data_type": data_type,
                        "character_maximum_length": max_length,
                        "is_nullable": nullable,
                    }
                )
            return _Cursor(rows)
        if "FROM pg_constraint" in statement:
            rows = [
                {"conname": name, "contype": "c", "definition": "CHECK (true)"}
                for name in LEDGER_CONSTRAINT_NAMES
                if name != "xp_settlement_idempotency_unique"
            ]
            rows.append(
                {
                    "conname": "xp_settlement_idempotency_unique",
                    "contype": "u",
                    "definition": "UNIQUE (user_id, idempotency_key)",
                }
            )
            rows.extend(
                [
                    {
                        "conname": "xp_settlement_user_fk",
                        "contype": "f",
                        "definition": "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT",
                    },
                    {
                        "conname": "xp_settlement_actor_fk",
                        "contype": "f",
                        "definition": "FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE RESTRICT",
                    },
                ]
            )
            return _Cursor(rows)
        return _Cursor()


def test_schema_helper_validates_existing_shape_and_is_rerunnable():
    conn = _SchemaConnection()
    ensure_xp_settlement_schema(conn)
    assert conn.statements[0] == LEDGER_SCHEMA_SQL
    assert sum("CREATE INDEX IF NOT EXISTS" in statement for statement in conn.statements) == 4

    incompatible = _SchemaConnection(missing_column="xp_delta")
    with pytest.raises(RuntimeError, match="missing columns"):
        ensure_xp_settlement_schema(incompatible)
    assert not any("CREATE INDEX IF NOT EXISTS" in statement for statement in incompatible.statements)


class _SettlementConnection:
    def __init__(self, xp=10):
        self.xp = xp
        self.ledger = []
        self.next_settlement_id = 1
        self.statements = []

    def execute(self, statement, parameters=None):
        self.statements.append(statement)
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("insert into user_stats"):
            return _Cursor()
        if normalized.startswith("select xp from user_stats"):
            return _Cursor([{"xp": self.xp}])
        if "from xp_settlement_ledger" in normalized:
            user_id, idempotency_key = parameters
            rows = [
                row
                for row in self.ledger
                if row["user_id"] == user_id
                and row["idempotency_key"] == idempotency_key
            ]
            return _Cursor(rows[:1])
        if normalized.startswith("savepoint") or normalized.startswith("release savepoint"):
            return _Cursor()
        if normalized.startswith("insert into xp_settlement_ledger"):
            (
                user_id, source_type, source_id, source_version,
                settlement_kind, _base_xp, xp_delta, _payload,
                _premium_eligibility, _already_premium_adjusted,
                _premium_factor_ppm, before_xp, after_xp, idempotency_key,
                _status, _grant_policy_version, _curve_version,
                _rounding_policy_version, _source_context,
                _request_correlation_id, _actor_type, _actor_id,
                _reason_or_ticket,
            ) = parameters
            row = {
                "settlement_id": self.next_settlement_id,
                "user_id": user_id,
                "source_type": source_type,
                "source_id": source_id,
                "source_version": source_version,
                "settlement_kind": settlement_kind,
                "before_xp": before_xp,
                "xp_delta": xp_delta,
                "after_xp": after_xp,
                "idempotency_key": idempotency_key,
            }
            self.next_settlement_id += 1
            self.ledger.append(row)
            return _Cursor([{"settlement_id": row["settlement_id"]}])
        if normalized.startswith("update user_stats set xp="):
            self.xp = parameters[0]
            return _Cursor()
        raise AssertionError(f"unexpected SQL in foundation fake: {statement}")


def test_enabled_settlement_is_idempotent_and_opening_balance_is_zero_delta():
    conn = _SettlementConnection(xp=10)
    request = SettlementRequest(
        user_id=7,
        source_type="review",
        source_id="credited:7:42",
        idempotency_key="review:7:42:v1",
        base_xp=5,
    )
    settlement = XPSettlement(
        conn,
        enabled=True,
        rank_cache_deriver=lambda total_xp: ("LV1", total_xp),
    )
    first = settlement.settle(request)
    retry = settlement.settle(request)
    assert first.duplicate is False
    assert first.xp_delta == 5
    assert first.after_xp == 15
    assert retry.duplicate is True
    assert retry.settlement_id == first.settlement_id
    assert conn.xp == 15
    assert len(conn.ledger) == 1

    conflicting = SettlementRequest(
        user_id=7,
        source_type="review",
        source_id="credited:7:999",
        idempotency_key="review:7:42:v1",
        base_xp=5,
    )
    with pytest.raises(XPSettlementConflict):
        settlement.settle(conflicting)

    opening_conn = _SettlementConnection(xp=300_000)
    opening = XPSettlement(opening_conn, enabled=True).settle(
        SettlementRequest(
            user_id=7,
            source_type="opening_balance",
            source_id="cutover-1:7",
            idempotency_key="opening_balance:cutover-1:7:v1",
            settlement_kind="OPENING_BALANCE",
            actor_type="MIGRATION",
            reason_or_ticket="cutover-1",
            opening_xp=300_000,
        )
    )
    assert opening.xp_delta == 0
    assert opening.before_xp == opening.after_xp == 300_000
    assert opening_conn.xp == 300_000


def test_admin_adjustment_is_signed_but_cannot_cross_zero():
    conn = _SettlementConnection(xp=10)
    settlement = XPSettlement(
        conn,
        enabled=True,
        rank_cache_deriver=lambda total_xp: ("LV1", total_xp),
    )
    with pytest.raises(ValueError, match="below zero"):
        settlement.settle(
            SettlementRequest(
                user_id=7,
                source_type="admin",
                source_id="ticket-1",
                idempotency_key="admin:ticket-1:v1",
                settlement_kind="ADMIN_ADJUSTMENT",
                actor_type="ADMIN",
                actor_id=99,
                reason_or_ticket="ticket-1",
                admin_xp_delta=-11,
            )
        )
    assert conn.xp == 10
    assert conn.ledger == []
