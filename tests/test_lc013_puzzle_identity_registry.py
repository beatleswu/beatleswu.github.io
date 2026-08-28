"""LC013 — disposable tests for the empty Immutable Puzzle Identity storage.

SQLite in-memory only; clearly-synthetic UUIDs/data.  Nothing here populates or
pretends to be the real 42,804 frozen genesis identities.
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from migrations.puzzle_identity_registry_v1 import (
    LINEAGE_EVENT_TYPES,
    TABLE_NAMES,
    _pg_trigger_ddl,
    _table_ddl,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)
from puzzle_identity_store import (
    AmbiguousAliasError,
    PuzzleIdentityError,
    PuzzleIdentityStore,
)
import json as _json

from puzzle_identity_genesis_bootstrap import (
    GenesisBootstrap,
    GenesisBootstrapError,
    GenesisReceiptVerifier,
)
from tools.lc011_identity_registry_prototype import mint_genesis_uuid
from tools.lc012_p2_genesis_freeze import (
    manifest_sha256_from_rows,
    uuid_list_sha256_from_uuids,
)

_SYNTH_NS = uuid.UUID("00000000-0000-4000-8000-000000000000")
_FIXED_TIME = "2026-08-28T12:00:00+00:00"
_RECEIPT_SHA = "ab" * 32


def _synth_v5(name: str) -> str:
    return str(uuid.uuid5(_SYNTH_NS, "synthetic:" + name))


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    # a synthetic bootstrap-receipt row so HISTORICAL_GENESIS FK resolves
    c.execute(
        "INSERT INTO puzzle_identity_bootstrap_receipt "
        "(receipt_sha256,bootstrap_singleton,frozen_corpus_sha256,record_count,"
        " namespace_uuid,canonicalisation_rules_version,genesis_key_spec_version,"
        " historical_tree_commit,historical_tree_manifest_sha256,"
        " historical_rename_map_sha256,genesis_record_manifest_sha256,"
        " proposed_uuid_list_sha256,status,identities_written,applied_at,applied_by) "
        "VALUES (?, 'GENESIS', ?, 3, 'ns', 'canon-source-v1', 'genesis-key-v1', "
        "'commit', 'tm', 'rm', 'gm', 'ul', 'APPLIED', 0, ?, 'fixture')",
        (_RECEIPT_SHA, "x" * 64, _FIXED_TIME),
    )
    yield c
    c.close()


@pytest.fixture()
def store(conn):
    return PuzzleIdentityStore(conn, clock=lambda: _FIXED_TIME)


def _mk_genesis(store, name="A/1.sgf", legacy="48126", historical=None):
    u = _synth_v5(name)
    store.create_historical_genesis_identity(
        u, receipt_sha256=_RECEIPT_SHA, canonical_source=name,
        legacy_question_id=legacy, historical_source_path=historical,
        creation_reason="synthetic genesis",
    )
    return u


# --------------------------------------------------------------- schema

def test_migration_is_additive_and_reversible(conn):
    v = validate_schema(conn)
    assert v["valid"] and not v["missing_tables"] and not v["missing_triggers"]
    downgrade_for_isolated_test(conn)
    assert validate_schema(conn)["missing_tables"] == list(TABLE_NAMES)
    upgrade(conn)  # re-applies cleanly (idempotent)
    assert validate_schema(conn)["valid"]


def test_postgres_ddl_shape():
    ddl = " ".join(_table_ddl("postgres"))
    assert "BIGSERIAL PRIMARY KEY" in ddl and "TIMESTAMPTZ" in ddl
    assert "REFERENCES puzzle_identity_bootstrap_receipt(receipt_sha256)" in ddl
    assert "bootstrap_singleton TEXT NOT NULL DEFAULT 'GENESIS' UNIQUE" in ddl
    trg = " ".join(_pg_trigger_ddl())
    assert "source_record_uuid is immutable" in trg
    assert "append-only puzzle_identity table" in trg
    assert "BEFORE UPDATE OR DELETE ON puzzle_identity_lineage" in trg


# --------------------------------------------------------------- A/B

def test_A_create_historical_genesis_identity(store):
    u = _mk_genesis(store)
    ident = store.get_identity(u)
    assert ident["identity_kind"] == "HISTORICAL_GENESIS"
    assert ident["origin_class"] == "GENESIS"
    assert ident["identity_status"] == "ACTIVE"
    assert ident["genesis_receipt_ref"] == _RECEIPT_SHA
    assert uuid.UUID(u).version == 5
    assert [e["event_type"] for e in store.get_lineage(u)] == ["GENESIS"]


def test_B_create_native_uuidv4_identity(store):
    u = store.create_native_identity(
        creation_reason="synthetic native", current_source_path="new/native/1.sgf")
    ident = store.get_identity(u)
    assert ident["identity_kind"] == "NATIVE_UUIDV4"
    assert ident["origin_class"] == "NATIVE"
    assert ident["genesis_receipt_ref"] is None
    assert uuid.UUID(u).version == 4
    assert [e["event_type"] for e in store.get_lineage(u)] == ["NATIVE_CREATE"]
    # explicit-UUID native path also works and must be v4
    u2 = store.create_native_identity(
        source_record_uuid=str(uuid.uuid4()), creation_reason="explicit native")
    assert store.get_identity(u2)["identity_kind"] == "NATIVE_UUIDV4"
    with pytest.raises(PuzzleIdentityError):
        store.create_native_identity(
            source_record_uuid=_synth_v5("v5-not-allowed"), creation_reason="bad")


# --------------------------------------------------------------- C/D

def test_C_duplicate_uuid_rejected(store):
    u = _mk_genesis(store)
    with pytest.raises(Exception):
        store.create_historical_genesis_identity(
            u, receipt_sha256=_RECEIPT_SHA, canonical_source="A/1.sgf",
            creation_reason="dup")


def test_D_uuid_mutation_rejected(conn, store):
    u = _mk_genesis(store)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE puzzle_identity_registry SET source_record_uuid=? "
            "WHERE source_record_uuid=?", (str(uuid.uuid4()), u))
    # creation facts are immutable too
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE puzzle_identity_registry SET identity_kind='NATIVE_UUIDV4' "
            "WHERE source_record_uuid=?", (u,))
    # but status/provenance_note may change (retire path)
    conn.execute(
        "UPDATE puzzle_identity_registry SET provenance_note='ok' "
        "WHERE source_record_uuid=?", (u,))


# --------------------------------------------------------------- E/F

def test_E_legacy_alias_resolution(store):
    u = _mk_genesis(store, legacy="70123")
    r = store.resolve("LEGACY_QUESTION_ID", "70123")
    assert r["status"] == "EXACT" and r["source_record_uuid"] == u
    assert store.resolve("LEGACY_QUESTION_ID", "999999")["status"] == "MISSING"


def test_F_historical_path_alias(store):
    u = _mk_genesis(store, name="cur/1.sgf", historical="hist/07folder/1.sgf")
    r = store.resolve("HISTORICAL_SOURCE_PATH", "hist/07folder/1.sgf")
    assert r["status"] == "EXACT" and r["source_record_uuid"] == u
    assert store.resolve("CANONICAL_SOURCE_KEY", "cur/1.sgf")["source_record_uuid"] == u


# --------------------------------------------------------------- G/H

def test_G_rename_keeps_uuid(store):
    u = _mk_genesis(store, name="a/1.sgf")
    store.record_rename(u, from_path="a/1.sgf", to_path="a/2renamed/1.sgf",
                        actor="admin", reason="chapter reorg")
    assert store.get_identity(u) is not None  # same identity
    cur = [a["alias_value"] for a in store.list_aliases(u, current_only=True)
           if a["alias_kind"] == "CURRENT_SOURCE_PATH"]
    assert cur == ["a/2renamed/1.sgf"]
    assert store.resolve("CURRENT_SOURCE_PATH", "a/2renamed/1.sgf",
                         alias_context="post-genesis")["source_record_uuid"] == u
    assert [e["event_type"] for e in store.get_lineage(u)] == ["GENESIS", "RENAME"]


def test_H_move_keeps_uuid(store):
    u = _mk_genesis(store, name="c1/x.sgf")
    store.record_move(u, from_path="c1/x.sgf", to_path="c2/x.sgf",
                      actor="admin", reason="collection move")
    assert store.get_identity(u)["source_record_uuid"] == u
    assert store.get_lineage(u)[-1]["event_type"] == "MOVE"


# --------------------------------------------------------------- I/J/P

def test_I_append_lineage(store):
    u = _mk_genesis(store)
    seq = store.append_lineage_event(u, "METADATA_CORRECTION", actor="admin",
                                     reason="tag fix")
    assert seq == 2
    assert store.get_lineage(u)[-1]["event_type"] == "METADATA_CORRECTION"


def test_J_lineage_update_and_delete_rejected(conn, store):
    u = _mk_genesis(store)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE puzzle_identity_lineage SET reason='x' "
                     "WHERE source_record_uuid=?", (u,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM puzzle_identity_lineage WHERE source_record_uuid=?",
                     (u,))


def test_P_unsupported_lineage_event_rejected(conn, store):
    u = _mk_genesis(store)
    with pytest.raises(PuzzleIdentityError):
        store.append_lineage_event(u, "FROBNICATE", actor="a", reason="r")
    # direct DB insert of a bad event_type also fails closed (CHECK)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO puzzle_identity_lineage "
            "(source_record_uuid,seq,event_type,occurred_at,actor,reason,recorded_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (u, 99, "NOT_A_REAL_EVENT", _FIXED_TIME, "a", "r", _FIXED_TIME))
    assert "FROBNICATE" not in LINEAGE_EVENT_TYPES


# --------------------------------------------------------------- K/L/M

def test_K_replacement_uses_new_uuid(store):
    old = _mk_genesis(store, name="old/1.sgf", legacy="1001")
    new = store.create_native_identity(creation_reason="replacement target",
                                       current_source_path="new/1.sgf")
    store.record_replacement(old_source_record_uuid=old,
                             new_source_record_uuid=new, actor="admin",
                             reason="rebuilt puzzle")
    assert new != old
    assert store.get_identity(old)["identity_status"] == "RETIRED"
    assert store.get_identity(new)["identity_status"] == "ACTIVE"
    assert store.get_lineage(old)[-1]["relationship_role"] == "SUPERSEDED_BY"
    assert store.get_lineage(new)[-1]["relationship_role"] == "SUPERSEDES"
    with pytest.raises(PuzzleIdentityError):
        store.record_replacement(old_source_record_uuid=old,
                                 new_source_record_uuid=old, actor="x", reason="y")


def test_L_split_children_get_new_uuids(store):
    parent = _mk_genesis(store, name="parent/1.sgf", legacy="2001")
    c1 = store.create_native_identity(creation_reason="split child 1")
    c2 = store.create_native_identity(creation_reason="split child 2")
    store.record_split(parent_source_record_uuid=parent,
                       child_source_record_uuids=[c1, c2], actor="admin",
                       reason="one file was two problems")
    assert parent not in (c1, c2) and c1 != c2
    assert store.get_identity(parent)["identity_status"] == "RETIRED"
    roles = {e["relationship_role"] for e in store.get_lineage(parent)}
    assert "PARENT" in roles
    assert store.get_lineage(c1)[-1]["event_type"] == "SPLIT"
    with pytest.raises(PuzzleIdentityError):
        store.record_split(parent_source_record_uuid=parent,
                           child_source_record_uuids=[parent], actor="x", reason="y")


def test_M_merge_requires_explicit_survivor(store):
    survivor = _mk_genesis(store, name="keep/1.sgf", legacy="3001")
    loser = _mk_genesis(store, name="drop/1.sgf", legacy="3002")
    store.record_merge(survivor_source_record_uuid=survivor,
                       non_survivor_source_record_uuids=[loser], actor="admin",
                       reason="exact duplicate puzzle")
    assert store.get_identity(survivor)["identity_status"] == "ACTIVE"
    assert store.get_identity(loser)["identity_status"] == "RETIRED"
    assert store.get_lineage(survivor)[-1]["relationship_role"] == "SURVIVOR"
    assert store.get_lineage(loser)[-1]["relationship_role"] == "NON_SURVIVOR"
    with pytest.raises(PuzzleIdentityError):
        store.record_merge(survivor_source_record_uuid=survivor,
                           non_survivor_source_record_uuids=[survivor],
                           actor="x", reason="y")


# --------------------------------------------------------------- N

def test_N_retired_identity_still_resolvable(store):
    u = _mk_genesis(store, legacy="4001")
    store.retire_identity(u, reason="withdrawn from curriculum", actor="admin")
    assert store.get_identity(u)["identity_status"] == "RETIRED"
    r = store.resolve("LEGACY_QUESTION_ID", "4001")
    assert r["source_record_uuid"] == u and r["status"] == "RETIRED"
    assert store.get_lineage(u)[-1]["event_type"] == "DELETE"
    store.restore_identity(u, reason="reinstated", actor="admin")
    assert store.get_identity(u)["identity_status"] == "ACTIVE"
    assert store.resolve("LEGACY_QUESTION_ID", "4001")["status"] == "EXACT"
    assert store.get_lineage(u)[-1]["event_type"] == "RESTORE"


# --------------------------------------------------------------- O

def test_O_ambiguous_alias_fails_closed(conn, store):
    u1 = _mk_genesis(store, name="p1/1.sgf", legacy="5001")
    u2 = store.create_native_identity(creation_reason="second")
    # a second *current* binding for the same (kind,value,context) must be
    # impossible at the storage layer
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO puzzle_identity_alias "
            "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
            " is_current,recorded_at,recorded_by) "
            "VALUES (?,?,?,?,?,1,?,?)",
            (u2, "LEGACY_QUESTION_ID", "5001", "genesis-v1", "RECORDED",
             _FIXED_TIME, "attacker"))
    # and if one is ever forced in with is_current=0, resolve() still returns one
    conn.execute(
        "INSERT INTO puzzle_identity_alias "
        "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
        " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,0,?,?)",
        (u2, "LEGACY_QUESTION_ID", "5001", "genesis-v1", "RECORDED",
         _FIXED_TIME, "superseded"))
    assert store.resolve("LEGACY_QUESTION_ID", "5001")["source_record_uuid"] == u1
    # a genuinely ambiguous *current* state (a third identity, index dropped) raises
    u3 = store.create_native_identity(creation_reason="third")
    conn.execute("DROP INDEX uq_pia_current_alias")
    conn.execute(
        "INSERT INTO puzzle_identity_alias "
        "(source_record_uuid,alias_kind,alias_value,alias_context,confidence,"
        " is_current,recorded_at,recorded_by) VALUES (?,?,?,?,?,1,?,?)",
        (u3, "LEGACY_QUESTION_ID", "5001", "genesis-v1", "RECORDED",
         _FIXED_TIME, "forced"))
    with pytest.raises(AmbiguousAliasError):
        store.resolve("LEGACY_QUESTION_ID", "5001")


# --------------------------------------------------------------- Q

def test_Q_transaction_rollback_safety(conn, store):
    """A create that violates a constraint mid-way leaves no partial rows."""
    _mk_genesis(store, name="existing/1.sgf", legacy="6001")
    doomed = _synth_v5("doomed")
    # same legacy id -> the alias insert trips the partial-unique index after
    # the registry row is already inserted inside the SAVEPOINT
    with pytest.raises(sqlite3.IntegrityError):
        store.create_historical_genesis_identity(
            doomed, receipt_sha256=_RECEIPT_SHA, canonical_source="doomed/1.sgf",
            legacy_question_id="6001", creation_reason="should roll back")
    assert store.get_identity(doomed) is None
    assert conn.execute(
        "SELECT COUNT(*) FROM puzzle_identity_alias WHERE source_record_uuid=?",
        (doomed,)).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM puzzle_identity_lineage WHERE source_record_uuid=?",
        (doomed,)).fetchone()[0] == 0


# --------------------------------------------------------------- content correction (§15)

def test_content_correction_fails_closed_without_review(store):
    u = _mk_genesis(store)
    with pytest.raises(PuzzleIdentityError):
        store.record_content_correction(u, reviewed=False, actor="admin",
                                        reason="same path, changed bytes")
    seq = store.record_content_correction(
        u, reviewed=True, actor="reviewer", reason="verified continuity",
        from_content_sha256="a" * 64, to_content_sha256="b" * 64)
    assert store.get_lineage(u)[-1]["event_type"] == "CONTENT_CORRECTION"
    assert seq == 2


# --------------------------------------------------------------- bootstrap interface (§31/§32)
#
# Synthetic manifests use the REAL genesis-key algorithm over fake canonical
# sources, so the per-row uuidv5(namespace, gk1 ... canonical_source) binding and
# the digest recomputations are all exercised — just not against the frozen corpus.

def _synth_manifest(n=3):
    rows = []
    for i in range(n):
        cs = f"synthetic-collection/{i}.sgf"
        rows.append({
            "source_record_uuid_proposed": mint_genesis_uuid(cs),
            "canonical_source": cs,
            "historical_source": cs,
            "provenance_relation": "DIRECT_PATH_MATCH",
            "legacy_question_id": 900000 + i,
            "record_index": i,
            "content_evidence_sha256": uuid.uuid5(_SYNTH_NS, cs).hex + uuid.uuid5(_SYNTH_NS, cs).hex,
        })
    return rows


def _synth_receipt(rows, **override):
    r = {
        "frozen_corpus_sha256": "ff" * 32,
        "frozen_record_count": len(rows),
        "identity_namespace": str(_SYNTH_NS),
        "canonicalization_version": "canon-source-v1",
        "genesis_key_version": "genesis-key-v1",
        "historical_tree_commit": "synthcommit",
        "historical_tree_manifest_sha256": "aa" * 32,
        "historical_rename_map_sha256": "bb" * 32,
        "genesis_record_manifest_sha256": manifest_sha256_from_rows(rows),
        "proposed_uuid_list_sha256": uuid_list_sha256_from_uuids(
            [x["source_record_uuid_proposed"] for x in rows]),
        "provenance_rank": "B",
        "exact_build_binding": False,
        "genesis_bootstrap_once_only_gate": {"genesis_bootstrap_safe_to_run": True},
    }
    r.update(override)
    return r


def _verifier(rows, receipt=None, *, canonical=False, rename_map_bytes=None):
    receipt = receipt if receipt is not None else _synth_receipt(rows)
    return GenesisReceiptVerifier(
        receipt_bytes=_json.dumps(receipt).encode("utf-8"),
        manifest_rows=rows,
        rename_map_bytes=rename_map_bytes,
        require_canonical_genesis=canonical,
    )


@pytest.fixture()
def empty_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    yield c
    c.close()


def test_bootstrap_interface_synthetic_apply_and_idempotency(empty_conn):
    st = PuzzleIdentityStore(empty_conn, clock=lambda: _FIXED_TIME)
    rows = _synth_manifest(3)
    receipt = _synth_receipt(rows)
    bs = GenesisBootstrap(st, _verifier(rows, receipt))
    assert bs.preflight()["ok"]
    res = bs.apply(applied_by="lc013-test", when=_FIXED_TIME)
    assert res["status"] == "APPLIED" and res["identities_written"] == 3
    assert empty_conn.execute(
        "SELECT COUNT(*) FROM puzzle_identity_registry").fetchone()[0] == 3
    # re-run identical receipt bytes -> idempotent no-op
    again = GenesisBootstrap(st, _verifier(rows, receipt))
    assert again.apply(applied_by="lc013-test", when=_FIXED_TIME)["status"] == "ALREADY_APPLIED"
    # a different receipt (different bytes -> different sha) -> fails closed
    other = _synth_receipt(rows, historical_tree_commit="different-commit")
    with pytest.raises(GenesisBootstrapError):
        GenesisBootstrap(st, _verifier(rows, other)).apply(applied_by="x", when=_FIXED_TIME)


def test_bootstrap_second_run_fails_closed_on_nonempty_registry(empty_conn):
    st = PuzzleIdentityStore(empty_conn, clock=lambda: _FIXED_TIME)
    st.create_native_identity(creation_reason="pre-existing")
    rows = _synth_manifest(2)
    bs = GenesisBootstrap(st, _verifier(rows))
    assert not bs.preflight()["ok"]
    with pytest.raises(GenesisBootstrapError):
        bs.apply(applied_by="x", when=_FIXED_TIME)


def test_bootstrap_canonical_mode_rejects_non_frozen_receipt(empty_conn):
    st = PuzzleIdentityStore(empty_conn, clock=lambda: _FIXED_TIME)
    rows = _synth_manifest(3)
    bs = GenesisBootstrap(st, _verifier(rows, canonical=True))
    pf = bs.preflight()
    assert not pf["ok"]
    assert any("frozen" in p for p in pf["problems"])
    with pytest.raises(GenesisBootstrapError):
        bs.apply(applied_by="x", when=_FIXED_TIME)


def test_bootstrap_rejects_non_v5_uuid_rows(empty_conn):
    st = PuzzleIdentityStore(empty_conn, clock=lambda: _FIXED_TIME)
    rows = _synth_manifest(3)
    rows[1]["source_record_uuid_proposed"] = str(uuid.uuid4())  # v4 in a genesis manifest
    bs = GenesisBootstrap(st, _verifier(rows))
    assert not bs.preflight()["ok"]
