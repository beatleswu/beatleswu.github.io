"""LC020-R1 — genesis must admit all 42,804 distinct source_record_uuid
identities even though the frozen corpus carries 11 legitimate
legacy_question_id collision groups (22 records).

Policy: FAIL_CLOSED_AMBIGUOUS.  A legacy_question_id shared by >1 genesis
identity gets its LEGACY_QUESTION_ID alias recorded NOT-current, so a raw
legacy lookup resolves AMBIGUOUS instead of arbitrarily binding one member.
The uq_pia_current_alias unique-current-alias constraint is never weakened.

Synthetic tests run everywhere; the full 42,804-row disposable apply is gated
on C:\\go-website + the frozen questions.json (same as test_lc013_r1_genesis_binding).
"""
from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from migrations.puzzle_identity_registry_v1 import upgrade
from puzzle_identity_store import PuzzleIdentityStore, AmbiguousAliasError
from puzzle_identity_read_window import DualIdReadWindow, ResolutionStatus
from identity_read_adapter import BootstrapGatedIdentityReader, IdentityKeyKind
from puzzle_identity_genesis_bootstrap import (
    GenesisBootstrap, GenesisBootstrapError, GenesisReceiptVerifier,
    legacy_id_collision_census, KNOWN_LEGACY_ID_COLLISION_IDS,
    KNOWN_LEGACY_ID_COLLISION_RECORD_COUNT,
)
from tools.lc011_identity_registry_prototype import mint_genesis_uuid
from tools.lc012_p2_genesis_freeze import manifest_sha256_from_rows, uuid_list_sha256_from_uuids, run as p2_run
from tools.lc012_sgf_source_tree_freeze import GENESIS_SNAPSHOT_SHA256, EXPECTED_RECORD_COUNT

_FIXED = "2026-08-30T12:00:00+00:00"
_B162 = "b162f9e72b93b73c08c1b044f365cb9287efae70"


def _row(cs, lqid, rel="DIRECT_PATH_MATCH", hist=None):
    return {
        "source_record_uuid_proposed": mint_genesis_uuid(cs),
        "canonical_source": cs, "historical_source": hist or cs,
        "provenance_relation": rel, "legacy_question_id": lqid,
        "record_index": 0, "content_evidence_sha256": "a" * 64,
    }


def _synth_receipt(rows):
    return {
        "frozen_corpus_sha256": GENESIS_SNAPSHOT_SHA256, "frozen_record_count": len(rows),
        "identity_namespace": "c70b30f4-b745-5585-b5c3-64021901ad76",
        "canonicalization_version": "canon-source-v1", "genesis_key_version": "genesis-key-v1",
        "historical_tree_commit": _B162,
        "historical_tree_manifest_sha256": "12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53",
        "historical_rename_map_sha256": "bb" * 32,
        "genesis_record_manifest_sha256": manifest_sha256_from_rows(rows),
        "proposed_uuid_list_sha256": uuid_list_sha256_from_uuids(
            [r["source_record_uuid_proposed"] for r in rows]),
        "provenance_rank": "B", "exact_build_binding": False,
        "genesis_bootstrap_once_only_gate": {"genesis_bootstrap_safe_to_run": True},
    }


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    yield c
    c.close()


def _bs(c, rows, canonical=False):
    st = PuzzleIdentityStore(c, clock=lambda: _FIXED)
    v = GenesisReceiptVerifier(receipt_bytes=json.dumps(_synth_receipt(rows)).encode(),
                               manifest_rows=rows, rename_map_bytes=None,
                               require_canonical_genesis=canonical)
    return GenesisBootstrap(st, v)


# ---------------------------------------------------------------- census

def test_census_counts_and_distinctness():
    rows = [_row("a/1.sgf", 500), _row("b/2.sgf", 500), _row("c/3.sgf", 501),
            _row("d/4.sgf", 501), _row("e/5.sgf", 999)]
    cen = legacy_id_collision_census(rows)
    assert cen["legacy_id_collision_group_count"] == 2
    assert cen["legacy_id_collision_record_count"] == 4
    assert cen["collided_ids"] == frozenset({"500", "501"})
    assert cen["unsupported_collision_count"] == 0
    assert cen["collision_uuid_distinctness_ok"] is True


def test_census_flags_unsupported_when_members_share_uuid():
    u = mint_genesis_uuid("a/1.sgf")
    rows = [_row("a/1.sgf", 500), dict(_row("b/2.sgf", 500), source_record_uuid_proposed=u)]
    cen = legacy_id_collision_census(rows)
    assert cen["unsupported_collision_count"] == 1
    assert cen["collision_uuid_distinctness_ok"] is False


# ---------------------------------------------------------------- apply admits collisions

def test_apply_admits_all_identities_with_a_collision_group(conn):
    rows = [_row("a/1.sgf", 700), _row("b/2.sgf", 700), _row("c/3.sgf", 701)]
    pf = _bs(conn, rows).preflight()
    assert pf["ok"], pf["problems"]
    assert pf["legacy_id_collisions"]["collision_policy_supported"] is True
    assert pf["legacy_id_collisions"]["collision_policy"] == "FAIL_CLOSED_AMBIGUOUS"
    res = _bs(conn, rows).apply(applied_by="t", when=_FIXED)
    assert res["status"] == "APPLIED" and res["identities_written"] == 3
    assert conn.execute("SELECT COUNT(*) FROM puzzle_identity_registry").fetchone()[0] == 3
    cur = conn.execute("SELECT COUNT(*) FROM puzzle_identity_alias "
                       "WHERE alias_kind='LEGACY_QUESTION_ID' AND is_current").fetchone()[0]
    notcur = conn.execute("SELECT COUNT(*) FROM puzzle_identity_alias "
                          "WHERE alias_kind='LEGACY_QUESTION_ID' AND NOT is_current").fetchone()[0]
    assert cur == 1 and notcur == 2               # only 701 is uniquely current


def test_collided_legacy_id_resolves_ambiguous_not_missing(conn):
    rows = [_row("a/1.sgf", 700), _row("b/2.sgf", 700), _row("c/3.sgf", 701)]
    _bs(conn, rows).apply(applied_by="t", when=_FIXED)
    w = DualIdReadWindow(conn)
    r700 = w.resolve_legacy_question_id(700)
    assert r700.status == ResolutionStatus.AMBIGUOUS
    assert len(r700.candidates) == 2 and len(set(r700.candidates)) == 2
    assert w.resolve_legacy_question_id(701).status == ResolutionStatus.EXACT
    assert w.resolve_legacy_question_id(123456).status == ResolutionStatus.MISSING
    batch = w.resolve_many_legacy_question_ids([700, 701, 123456])
    assert batch["700"].status == ResolutionStatus.AMBIGUOUS
    assert batch["701"].status == ResolutionStatus.EXACT
    assert batch["123456"].status == ResolutionStatus.MISSING


def test_collided_reader_group_key_is_unresolved_never_random_uuid(conn):
    rows = [_row("a/1.sgf", 700), _row("b/2.sgf", 700), _row("c/3.sgf", 701)]
    _bs(conn, rows).apply(applied_by="t", when=_FIXED)
    rdr = BootstrapGatedIdentityReader(conn)
    assert rdr.hot is True
    k = rdr.key_for(700)
    assert k.kind == IdentityKeyKind.UNRESOLVED
    assert k.group_key == ("unresolved", "700")
    assert rdr.key_for(701).kind == IdentityKeyKind.UUID


def test_unique_current_alias_constraint_still_enforced(conn):
    rows = [_row("a/1.sgf", 700), _row("b/2.sgf", 700), _row("c/3.sgf", 701)]
    _bs(conn, rows).apply(applied_by="t", when=_FIXED)
    # the partial-unique index is intact: a manual 2nd *current* LEGACY_QUESTION_ID
    # for the same (value, context) must still be rejected
    u = conn.execute("SELECT source_record_uuid FROM puzzle_identity_registry LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO puzzle_identity_alias(source_record_uuid, alias_kind, alias_value, "
            "alias_context, confidence, is_current, recorded_at, recorded_by) "
            "VALUES (?, 'LEGACY_QUESTION_ID', '701', 'genesis-v1', 'EXACT', 1, ?, 't')",
            (u, _FIXED))


# ---------------------------------------------------------------- preflight collision census gate

def test_preflight_rejects_unsupported_collision(conn):
    u = mint_genesis_uuid("a/1.sgf")
    rows = [_row("a/1.sgf", 700), dict(_row("b/2.sgf", 700), source_record_uuid_proposed=u,
                                       canonical_source="a/1.sgf")]
    pf = _bs(conn, rows).preflight()
    assert not pf["ok"]
    assert any("unsupported" in p for p in pf["problems"])
    with pytest.raises(GenesisBootstrapError):
        _bs(conn, rows).apply(applied_by="t", when=_FIXED)
    assert conn.execute("SELECT COUNT(*) FROM puzzle_identity_registry").fetchone()[0] == 0


def test_non_collision_genesis_unchanged(conn):
    rows = [_row("a/1.sgf", 800), _row("b/2.sgf", 801), _row("c/3.sgf", 802)]
    _bs(conn, rows).apply(applied_by="t", when=_FIXED)
    w = DualIdReadWindow(conn)
    for q, cs in [(800, "a/1.sgf"), (801, "b/2.sgf"), (802, "c/3.sgf")]:
        r = w.resolve_legacy_question_id(q)
        assert r.status == ResolutionStatus.EXACT
        assert r.source_record_uuid == mint_genesis_uuid(cs)
    assert conn.execute("SELECT COUNT(*) FROM puzzle_identity_alias "
                        "WHERE alias_kind='LEGACY_QUESTION_ID' AND NOT is_current").fetchone()[0] == 0


# ---------------------------------------------------------------- full 42,804 (C:-gated)

_C_REPO = Path(r"C:\go-website")
_FROZEN = _REPO.parents[2] / "questions.json"
_DE7 = "de7cd979d838b441bd570e4d0eec3b3a46ef0c5c"
_RECEIPT_PATH = _REPO / "docs" / "planning" / "lc012_p2_genesis_receipt.json"
_RENAME_MAP_PATH = _REPO / "docs" / "planning" / "lc012_p2_historical_rename_map.json"


def _git_ok() -> bool:
    if not (_C_REPO / ".git").exists() or not _FROZEN.exists():
        return False
    r = subprocess.run(["git", "-C", str(_C_REPO), "cat-file", "-t", _B162],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "commit"


def _archive(commit: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "-C", str(_C_REPO), "-c", "core.quotepath=false",
                          "archive", "--format=tar", commit, "SGF題庫"],
                         capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar), mode="r:", encoding="utf-8") as tf:
        tf.extractall(dest, filter="data")
    return dest / "SGF題庫"


@pytest.mark.skipif(not _git_ok(), reason="C:\\go-website / frozen corpus absent")
def test_full_42804_disposable_apply_with_real_collisions(tmp_path):
    b162 = _archive(_B162, tmp_path / "b162")
    de7 = _archive(_DE7, tmp_path / "de7")
    corpus = tmp_path / "q.json"
    corpus.write_bytes(subprocess.run(
        ["git", "-C", str(_C_REPO), "cat-file", "blob", f"{_B162}:questions.json"],
        capture_output=True, check=True).stdout)
    res = p2_run(snapshot=_FROZEN, b162_tree_root=b162, de7_tree_root=de7,
                 b162_corpus=corpus, out_dir=tmp_path / "out")
    rows = json.loads((tmp_path / "out" / "genesis_record_manifest_full.json").read_bytes())["rows"]

    cen = legacy_id_collision_census(rows)
    assert cen["collided_ids"] == KNOWN_LEGACY_ID_COLLISION_IDS
    assert cen["legacy_id_collision_record_count"] == KNOWN_LEGACY_ID_COLLISION_RECORD_COUNT
    assert cen["unsupported_collision_count"] == 0

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    st = PuzzleIdentityStore(c, clock=lambda: _FIXED)
    v = GenesisReceiptVerifier(receipt_bytes=_RECEIPT_PATH.read_bytes(), manifest_rows=rows,
                               rename_map_bytes=_RENAME_MAP_PATH.read_bytes(),
                               require_canonical_genesis=True)
    bs = GenesisBootstrap(st, v)
    assert DualIdReadWindow(c).bootstrap_state()["hot"] is False
    pf = bs.preflight()
    assert pf["ok"], pf["problems"][:5]
    assert pf["legacy_id_collisions"]["collision_policy_supported"] is True
    out = bs.apply(applied_by="lc020r1", when=_FIXED)
    assert out["status"] == "APPLIED" and out["identities_written"] == EXPECTED_RECORD_COUNT
    assert c.execute("SELECT COUNT(*) FROM puzzle_identity_registry").fetchone()[0] == EXPECTED_RECORD_COUNT
    assert c.execute("SELECT COUNT(*) FROM puzzle_identity_alias "
                     "WHERE alias_kind='LEGACY_QUESTION_ID' AND is_current").fetchone()[0] == EXPECTED_RECORD_COUNT - 22
    assert c.execute("SELECT COUNT(*) FROM puzzle_identity_alias "
                     "WHERE alias_kind='LEGACY_QUESTION_ID' AND NOT is_current").fetchone()[0] == 22
    assert DualIdReadWindow(c).bootstrap_state()["hot"] is True
    w = DualIdReadWindow(c)
    for cid in KNOWN_LEGACY_ID_COLLISION_IDS:
        assert w.resolve_legacy_question_id(cid).status == ResolutionStatus.AMBIGUOUS
    # no duplicate current legacy alias value anywhere
    assert c.execute(
        "SELECT COUNT(*) FROM (SELECT alias_value FROM puzzle_identity_alias "
        "WHERE alias_kind='LEGACY_QUESTION_ID' AND is_current GROUP BY alias_value HAVING COUNT(*)>1)"
    ).fetchone()[0] == 0
    # second apply -> idempotent
    assert GenesisBootstrap(PuzzleIdentityStore(c, clock=lambda: _FIXED), v).apply(
        applied_by="again", when=_FIXED)["status"] == "ALREADY_APPLIED"
    c.close()
