"""LC013-R1 — the genesis bootstrap must be cryptographically bound to the exact
LC012-R2 artifacts, and must reject wrong-but-valid inputs.

The full 42,804-row manifest is regenerated read-only from C:\\go-website git
history (the LC012-R2 P2 pin, commit b162f9e72) and every digest is recomputed
with the accepted LC012-R2 serialisation.  Nothing is written to any real DB.
"""
from __future__ import annotations

import copy
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
from puzzle_identity_store import PuzzleIdentityStore
from puzzle_identity_genesis_bootstrap import (
    GenesisBootstrap,
    GenesisBootstrapError,
    GenesisReceiptVerifier,
    KNOWN_MANIFEST_SHA256,
    KNOWN_RECEIPT_SHA256,
    KNOWN_RENAME_MAP_SHA256,
)
from tools.lc011_identity_registry_prototype import mint_genesis_uuid
from tools.lc012_p2_genesis_freeze import (
    manifest_sha256_from_rows,
    uuid_list_sha256_from_uuids,
    run as p2_run,
)
from tools.lc012_sgf_source_tree_freeze import GENESIS_SNAPSHOT_SHA256, EXPECTED_RECORD_COUNT

_C_REPO = Path(r"C:\go-website")
_FROZEN = _REPO.parents[2] / "questions.json"  # D:\go-website\questions.json
_B162 = "b162f9e72b93b73c08c1b044f365cb9287efae70"
_DE7 = "de7cd979d838b441bd570e4d0eec3b3a46ef0c5c"
_UUID_LIST_SHA = "cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2"
_FIXED = "2026-08-28T12:00:00+00:00"
_RECEIPT_PATH = _REPO / "docs" / "planning" / "lc012_p2_genesis_receipt.json"
_RENAME_MAP_PATH = _REPO / "docs" / "planning" / "lc012_p2_historical_rename_map.json"


def _git_ok() -> bool:
    if not (_C_REPO / ".git").exists() or not _FROZEN.exists():
        return False
    r = subprocess.run(["git", "-C", str(_C_REPO), "cat-file", "-t", _B162],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "commit"


pytestmark = pytest.mark.skipif(
    not _git_ok(),
    reason="C:\\go-website historical repo / frozen corpus absent — genesis rebind unprovable",
)


def _archive(commit: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(
        ["git", "-C", str(_C_REPO), "-c", "core.quotepath=false",
         "archive", "--format=tar", commit, "SGF題庫"],
        capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar), mode="r:", encoding="utf-8") as tf:
        tf.extractall(dest, filter="data")
    return dest / "SGF題庫"


@pytest.fixture(scope="module")
def genesis(tmp_path_factory):
    base = tmp_path_factory.mktemp("lc13r1_genesis")
    b162 = _archive(_B162, base / "b162")
    de7 = _archive(_DE7, base / "de7")
    corpus = base / "q_b162.json"
    corpus.write_bytes(subprocess.run(
        ["git", "-C", str(_C_REPO), "cat-file", "blob", f"{_B162}:questions.json"],
        capture_output=True, check=True).stdout)
    out = base / "out"
    res = p2_run(snapshot=_FROZEN, b162_tree_root=b162, de7_tree_root=de7,
                 b162_corpus=corpus, out_dir=out)
    full = json.loads((out / "genesis_record_manifest_full.json").read_bytes())
    return {
        "rows": full["rows"],
        "result": res,
        "receipt_bytes": _RECEIPT_PATH.read_bytes(),
        "rename_map_bytes": _RENAME_MAP_PATH.read_bytes(),
    }


# ------------------------------------------------------------- digest binding

def test_manifest_digest_matches_lc012_r2(genesis):
    assert manifest_sha256_from_rows(genesis["rows"]) == KNOWN_MANIFEST_SHA256
    assert genesis["result"]["genesis_record_manifest_stats"]["manifest_sha256"] == KNOWN_MANIFEST_SHA256


def test_uuid_list_digest_matches_lc012_r2(genesis):
    uuids = [r["source_record_uuid_proposed"] for r in genesis["rows"]]
    assert len(uuids) == EXPECTED_RECORD_COUNT
    assert len(set(uuids)) == EXPECTED_RECORD_COUNT
    assert uuid_list_sha256_from_uuids(uuids) == _UUID_LIST_SHA


def test_receipt_and_rename_map_bytes_are_the_committed_artifacts(genesis):
    import hashlib
    assert hashlib.sha256(genesis["receipt_bytes"]).hexdigest() == KNOWN_RECEIPT_SHA256
    assert hashlib.sha256(genesis["rename_map_bytes"]).hexdigest() == KNOWN_RENAME_MAP_SHA256


def test_every_uuid_is_bound_to_its_canonical_source(genesis):
    mism = sum(1 for r in genesis["rows"]
               if mint_genesis_uuid(r["canonical_source"]) != r["source_record_uuid_proposed"])
    assert mism == 0


def test_provenance_relation_counts_and_rename_binding(genesis):
    rows = genesis["rows"]
    direct = [r for r in rows if r["provenance_relation"] == "DIRECT_PATH_MATCH"]
    rename = [r for r in rows if r["provenance_relation"] == "HISTORICAL_RENAME_MATCH"]
    assert len(direct) == 41886
    assert len(rename) == 918
    assert len(direct) + len(rename) == EXPECTED_RECORD_COUNT
    ren = {e["pre_reorg_source"]: e["post_reorg_source"]
           for e in json.loads(genesis["rename_map_bytes"])}
    mism = 0
    for r in direct:
        if r["historical_source"] not in (None, r["canonical_source"]):
            mism += 1
    for r in rename:
        if r["canonical_source"] not in ren or r["historical_source"] != ren[r["canonical_source"]]:
            mism += 1
    assert mism == 0


# ------------------------------------------------------------- verifier: canonical PASS

def test_verifier_accepts_the_exact_lc012_r2_artifacts(genesis):
    v = GenesisReceiptVerifier(
        receipt_bytes=genesis["receipt_bytes"],
        manifest_rows=genesis["rows"],
        rename_map_bytes=genesis["rename_map_bytes"],
        require_canonical_genesis=True,
    )
    report = v.verify()
    assert report["ok"], report["problems"][:5]
    assert report["receipt_sha256"] == KNOWN_RECEIPT_SHA256
    assert report["safe_to_run_trusted_without_recompute"] is False
    assert report["genesis_records"] == EXPECTED_RECORD_COUNT
    assert report["direct_path_match_count"] == 41886
    assert report["historical_rename_match_count"] == 918
    assert report["missing"] == 0 and report["ambiguous"] == 0
    assert report["uuid_canonical_source_binding_mismatch"] == 0
    assert report["rename_provenance_mismatch"] == 0
    assert report["recomputed_genesis_record_manifest_sha256"] == KNOWN_MANIFEST_SHA256
    assert report["recomputed_uuid_list_sha256"] == _UUID_LIST_SHA


# ------------------------------------------------------------- adversarial (§16)

def _verify(genesis, rows=None, receipt_mut=None, rename_map_bytes=None, canonical=True):
    rows = genesis["rows"] if rows is None else rows
    rb = genesis["receipt_bytes"]
    if receipt_mut is not None:
        d = json.loads(rb.decode("utf-8"))
        d.update(receipt_mut)
        rb = json.dumps(d).encode("utf-8")
    v = GenesisReceiptVerifier(
        receipt_bytes=rb, manifest_rows=rows,
        rename_map_bytes=(genesis["rename_map_bytes"] if rename_map_bytes is None
                          else rename_map_bytes),
        require_canonical_genesis=canonical,
    )
    return v.verify()


def test_adv_valid_v5_for_a_different_canonical_source(genesis):
    rows = copy.deepcopy(genesis["rows"][:200])
    rows[0]["source_record_uuid_proposed"] = mint_genesis_uuid("totally/other.sgf")
    assert not _verify(genesis, rows, canonical=False)["ok"]


def test_adv_swapped_uuids(genesis):
    rows = copy.deepcopy(genesis["rows"][:200])
    rows[0]["source_record_uuid_proposed"], rows[1]["source_record_uuid_proposed"] = (
        rows[1]["source_record_uuid_proposed"], rows[0]["source_record_uuid_proposed"])
    assert not _verify(genesis, rows, canonical=False)["ok"]


def test_adv_changed_canonical_source_same_uuid(genesis):
    rows = copy.deepcopy(genesis["rows"][:200])
    rows[0]["canonical_source"] = rows[0]["canonical_source"] + ".TAMPER"
    assert not _verify(genesis, rows, canonical=False)["ok"]


def test_adv_tampered_manifest_row(genesis):
    rows = copy.deepcopy(genesis["rows"])
    rows[5]["content_evidence_sha256"] = "0" * 64
    assert not _verify(genesis, rows)["ok"]  # recomputed manifest sha will differ


def test_adv_tampered_manifest_sha_in_receipt(genesis):
    assert not _verify(genesis, receipt_mut={"genesis_record_manifest_sha256": "0" * 64})["ok"]


def test_adv_tampered_rename_map_sha_in_receipt(genesis):
    assert not _verify(genesis, receipt_mut={"historical_rename_map_sha256": "0" * 64})["ok"]


def test_adv_wrong_uuid_list_sha(genesis):
    assert not _verify(genesis, receipt_mut={"proposed_uuid_list_sha256": "0" * 64})["ok"]


def test_adv_wrong_namespace(genesis):
    assert not _verify(genesis, receipt_mut={"identity_namespace": str(uuid.uuid4())})["ok"]


def test_adv_wrong_canonicalization_version(genesis):
    assert not _verify(genesis, receipt_mut={"canonicalization_version": "canon-source-v2"})["ok"]


def test_adv_wrong_historical_tree_pin(genesis):
    assert not _verify(genesis, receipt_mut={"historical_tree_commit": "0" * 40})["ok"]


def test_adv_fake_receipt_digest_when_bytes_dont_match(genesis):
    # in canonical mode the verifier recomputes the sha from the bytes; a receipt
    # dict carrying a bogus self-sha field cannot pass because the bytes changed
    r = _verify(genesis, receipt_mut={"receipt_sha256": "f" * 64})
    assert not r["ok"]


def test_adv_wrong_record_count(genesis):
    rows = copy.deepcopy(genesis["rows"][:-1])  # 42803
    assert not _verify(genesis, rows)["ok"]


def test_adv_duplicate_uuid(genesis):
    rows = copy.deepcopy(genesis["rows"][:200])
    rows[1]["source_record_uuid_proposed"] = rows[0]["source_record_uuid_proposed"]
    assert not _verify(genesis, rows, canonical=False)["ok"]


def test_adv_uuidv4_row(genesis):
    rows = copy.deepcopy(genesis["rows"][:200])
    rows[0]["source_record_uuid_proposed"] = str(uuid.uuid4())
    assert not _verify(genesis, rows, canonical=False)["ok"]


def test_adv_missing_canonical_source(genesis):
    rows = copy.deepcopy(genesis["rows"][:200])
    rows[0]["canonical_source"] = ""
    assert not _verify(genesis, rows, canonical=False)["ok"]


def test_adv_invalid_provenance_relation(genesis):
    rows = copy.deepcopy(genesis["rows"][:200])
    rows[0]["provenance_relation"] = "GUESSED"
    assert not _verify(genesis, rows, canonical=False)["ok"]


# ------------------------------------------------------------- bootstrap atomicity (§17)

def _small_real_manifest(n=4):
    rows = []
    for i in range(n):
        cs = f"lc13r1-atomic/{i}.sgf"
        rows.append({
            "source_record_uuid_proposed": mint_genesis_uuid(cs),
            "canonical_source": cs,
            "historical_source": cs,
            "provenance_relation": "DIRECT_PATH_MATCH",
            "legacy_question_id": 800000 + i,
            "record_index": i,
            "content_evidence_sha256": "a" * 64,
        })
    return rows


def _synthetic_receipt_for(rows):
    return {
        "frozen_corpus_sha256": GENESIS_SNAPSHOT_SHA256,
        "frozen_record_count": len(rows),
        "identity_namespace": "c70b30f4-b745-5585-b5c3-64021901ad76",
        "canonicalization_version": "canon-source-v1",
        "genesis_key_version": "genesis-key-v1",
        "historical_tree_commit": _B162,
        "historical_tree_manifest_sha256": "12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53",
        "historical_rename_map_sha256": "bb" * 32,
        "genesis_record_manifest_sha256": manifest_sha256_from_rows(rows),
        "proposed_uuid_list_sha256": uuid_list_sha256_from_uuids(
            [r["source_record_uuid_proposed"] for r in rows]),
        "provenance_rank": "B",
        "exact_build_binding": False,
        "genesis_bootstrap_once_only_gate": {"genesis_bootstrap_safe_to_run": True},
    }


@pytest.fixture()
def empty_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    upgrade(c)
    yield c
    c.close()


def _mk_bs(conn, rows, receipt):
    st = PuzzleIdentityStore(conn, clock=lambda: _FIXED)
    v = GenesisReceiptVerifier(
        receipt_bytes=json.dumps(receipt).encode("utf-8"),
        manifest_rows=rows, rename_map_bytes=None, require_canonical_genesis=False)
    return st, GenesisBootstrap(st, v)


def test_bootstrap_atomicity_partial_failure_rolls_back(empty_conn):
    rows = _small_real_manifest(4)
    rows[2]["source_record_uuid_proposed"] = rows[1]["source_record_uuid_proposed"][:8] + "XXXX" + \
        rows[1]["source_record_uuid_proposed"][12:]  # malformed -> create fails mid-loop
    st, bs = _mk_bs(empty_conn, rows, _synthetic_receipt_for(rows))
    with pytest.raises(Exception):
        bs.apply(applied_by="lc13r1", when=_FIXED)
    assert empty_conn.execute("SELECT COUNT(*) FROM puzzle_identity_registry").fetchone()[0] == 0
    assert empty_conn.execute("SELECT COUNT(*) FROM puzzle_identity_bootstrap_receipt").fetchone()[0] == 0


def test_bootstrap_same_receipt_idempotent_different_fails_closed(empty_conn):
    rows = _small_real_manifest(3)
    receipt = _synthetic_receipt_for(rows)
    st, bs = _mk_bs(empty_conn, rows, receipt)
    assert bs.apply(applied_by="lc13r1", when=_FIXED)["status"] == "APPLIED"
    assert empty_conn.execute("SELECT COUNT(*) FROM puzzle_identity_registry").fetchone()[0] == 3
    _, bs2 = _mk_bs(empty_conn, rows, receipt)
    assert bs2.apply(applied_by="lc13r1", when=_FIXED)["status"] == "ALREADY_APPLIED"
    other = dict(receipt, historical_tree_commit="different")
    _, bs3 = _mk_bs(empty_conn, rows, other)
    with pytest.raises(GenesisBootstrapError):
        bs3.apply(applied_by="lc13r1", when=_FIXED)


def test_bootstrap_second_different_genesis_fails_closed(empty_conn):
    rows_a = _small_real_manifest(2)
    st, bs_a = _mk_bs(empty_conn, rows_a, _synthetic_receipt_for(rows_a))
    bs_a.apply(applied_by="a", when=_FIXED)
    rows_b = _small_real_manifest(5)
    _, bs_b = _mk_bs(empty_conn, rows_b, _synthetic_receipt_for(rows_b))
    with pytest.raises(GenesisBootstrapError):
        bs_b.apply(applied_by="b", when=_FIXED)
    assert empty_conn.execute("SELECT COUNT(*) FROM puzzle_identity_registry").fetchone()[0] == 2
