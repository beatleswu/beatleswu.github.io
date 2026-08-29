"""LC012-R2 — P2 genesis freeze & receipt: reconciliation + drift fail-closed tests.

The historical SGF tree lives only in C:\\go-website git history (owner-approved
read-only provenance source). These tests materialise it via `git archive`
(read-only) into a tmp dir and skip cleanly where that repo/commit is absent.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools import lc012_p2_genesis_freeze as p2  # noqa: E402
from tools.lc012_sgf_source_tree_freeze import tree_inventory  # noqa: E402

_C_REPO = Path(r"C:\go-website")
_FROZEN = _REPO.parents[2] / "questions.json"  # D:\go-website\questions.json
_B162 = "b162f9e72b93b73c08c1b044f365cb9287efae70"
_DE7 = "de7cd979d838b441bd570e4d0eec3b3a46ef0c5c"

_OWNER_TREE_MANIFEST = "12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53"
_KNOWN_UUID_LIST_SHA = "cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2"
_RECEIPT_SHA = "834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c"
_RENAME_MAP_SHA = "473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d"
_MANIFEST_FULL_SHA = "ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828"


def _git_ok() -> bool:
    if not (_C_REPO / ".git").exists() or not _FROZEN.exists():
        return False
    r = subprocess.run(["git", "-C", str(_C_REPO), "cat-file", "-t", _B162],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "commit"


pytestmark = pytest.mark.skipif(not _git_ok(),
                                reason="C:\\go-website historical repo / frozen corpus not present")


def _archive(commit: str, dest: Path) -> Path:
    import io
    import tarfile
    dest.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(
        ["git", "-C", str(_C_REPO), "-c", "core.quotepath=false",
         "archive", "--format=tar", commit, "SGF題庫"],
        capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar), mode="r:", encoding="utf-8") as tf:
        tf.extractall(dest, filter="data")
    return dest / "SGF題庫"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    base = tmp_path_factory.mktemp("lc12r2")
    b162_tree = _archive(_B162, base / "b162")
    de7_tree = _archive(_DE7, base / "de7")
    corpus = base / "q_b162.json"
    corpus.write_bytes(subprocess.run(
        ["git", "-C", str(_C_REPO), "cat-file", "blob", f"{_B162}:questions.json"],
        capture_output=True, check=True).stdout)
    res = p2.run(snapshot=_FROZEN, b162_tree_root=b162_tree,
                 de7_tree_root=de7_tree, b162_corpus=corpus, out_dir=base / "out")
    return {"base": base, "b162_tree": b162_tree, "de7_tree": de7_tree,
            "corpus": corpus, "res": res}


# ---------------------------------------------------------------- reconciliation

def test_owner_tree_facts_reproduce(env):
    t = tree_inventory(env["b162_tree"])
    assert t["sgf_file_count"] == 42804
    assert t["canonical_path_collisions"] == []
    assert t["tree_manifest_sha256"] == _OWNER_TREE_MANIFEST


def test_rename_map_is_exactly_918_clean(env):
    rm = env["res"]["rename_map"]
    assert rm["entry_count"] == 918
    assert rm["collision_count"] == 0
    assert rm["ambiguity_count"] == 0
    assert rm["covers_b162_orphans"] is True
    assert rm["all_identity_preserved"] is True
    assert rm["rename_map_sha256"] == _RENAME_MAP_SHA


def test_genesis_join_full_and_unambiguous(env):
    j = env["res"]["genesis_join_summary"]
    assert j["genesis_records_joined"] == 42804
    assert j["genesis_records_missing"] == 0
    assert j["genesis_records_ambiguous"] == 0
    assert j["identity_collision_count"] == 0
    assert j["direct_path_match_count"] + j["historical_rename_match_count"] == 42804
    assert j["historical_rename_match_count"] == 918


def test_proposed_uuid_proof_unchanged(env):
    c = env["res"]["corpus_side_summary"]
    assert c["proposed_uuid_count"] == 42804
    assert c["distinct_uuid_count"] == 42804
    assert c["uuid_collision_count"] == 0
    assert c["uuid_list_sha256"] == _KNOWN_UUID_LIST_SHA


def test_duplicate_and_legacy_separability(env):
    c = env["res"]["corpus_side_summary"]
    assert c["duplicate_content_groups_separable"] == c["duplicate_content_group_count"] == 404
    assert c["legacy_collision_records_separable"] is True


def test_receipt_is_rank_b_not_a(env):
    r = env["res"]["receipt"]
    assert r["provenance_rank"] == "B"
    assert r["exact_build_binding"] is False
    assert r["deterministic_byte_rebuild_from_one_tree"] is False
    assert r["frozen_artifact_reconciled_on_d_drive"] is True
    assert r["builder_transform_reference"]["reproduces_88da3e43_exactly"] is False


def test_receipt_and_manifest_shas_stable(env):
    assert env["res"]["receipt_sha256"] == _RECEIPT_SHA
    assert env["res"]["genesis_record_manifest_stats"]["manifest_sha256"] == _MANIFEST_FULL_SHA


def test_once_only_gate_safe_only_when_inputs_match(env):
    g = env["res"]["receipt"]["genesis_bootstrap_once_only_gate"]
    assert g["genesis_bootstrap_safe_to_run"] is True
    assert set(g["required_keys"]) == {
        "frozen_corpus_sha256", "record_count", "namespace_uuid",
        "canonicalisation_rules_version", "genesis_key_spec_version",
        "historical_tree_commit", "historical_tree_manifest_sha256",
        "historical_rename_map_sha256", "genesis_record_manifest_sha256"}


def test_run_is_deterministic(env):
    r2 = p2.run(snapshot=_FROZEN, b162_tree_root=env["b162_tree"],
                de7_tree_root=env["de7_tree"], b162_corpus=env["corpus"],
                out_dir=env["base"] / "out2")
    assert r2["receipt_sha256"] == env["res"]["receipt_sha256"]
    assert r2["rename_map"]["rename_map_sha256"] == env["res"]["rename_map"]["rename_map_sha256"]
    assert (r2["genesis_record_manifest_stats"]["manifest_sha256"]
            == env["res"]["genesis_record_manifest_stats"]["manifest_sha256"])


# ------------------------------------------------------------------- drift (§19)

def test_drift_frozen_hash_mismatch(env, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b'[{"id":1,"source":"a/1.sgf","content":"x"}]')
    with pytest.raises(SystemExit):
        p2.run(snapshot=bad, b162_tree_root=env["b162_tree"],
               de7_tree_root=env["de7_tree"], b162_corpus=env["corpus"], out_dir=None)


def test_drift_record_count_mismatch(env, tmp_path, monkeypatch):
    # a JSON list that hashes wrong is caught earlier; simulate a hash-OK / count-wrong
    monkeypatch.setattr(p2, "verify_snapshot", lambda p: (p2.GENESIS_SNAPSHOT_SHA256, True, [{"source": "a/1.sgf", "content": "x"}]))
    with pytest.raises(SystemExit):
        p2.run(snapshot=env["corpus"], b162_tree_root=env["b162_tree"],
               de7_tree_root=env["de7_tree"], b162_corpus=env["corpus"], out_dir=None)


def test_drift_tree_commit_or_manifest_mismatch(env):
    # de7 tree in the b162 slot -> owner tree facts (count 42802, manifest) do not reproduce
    with pytest.raises(SystemExit):
        p2.run(snapshot=_FROZEN, b162_tree_root=env["de7_tree"],
               de7_tree_root=env["de7_tree"], b162_corpus=env["corpus"], out_dir=None)


def test_drift_canonical_path_collision(env, tmp_path):
    # NFC vs NFD of one name -> tree_inventory reports a collision -> tree facts fail
    clash = tmp_path / "clash" / "SGF題庫" / "col"
    src = next(env["b162_tree"].rglob("*.sgf"))
    clash.mkdir(parents=True)
    (clash / ("caf\u00e9.sgf")).write_bytes(src.read_bytes())
    (clash / ("cafe\u0301.sgf")).write_bytes(src.read_bytes())
    if len(list(clash.iterdir())) < 2:
        pytest.skip("filesystem folded NFC/NFD names; collision not constructible here")
    with pytest.raises(SystemExit):
        p2.run(snapshot=_FROZEN, b162_tree_root=(tmp_path / "clash" / "SGF題庫"),
               de7_tree_root=env["de7_tree"], b162_corpus=env["corpus"], out_dir=None)


def test_drift_namespace_change(env, monkeypatch):
    monkeypatch.setattr(p2, "PROPOSED_CANONICAL_NAMESPACE_UUID",
                        "00000000-0000-5000-8000-000000000000")
    with pytest.raises(Exception):
        p2.run(snapshot=_FROZEN, b162_tree_root=env["b162_tree"],
               de7_tree_root=env["de7_tree"], b162_corpus=env["corpus"], out_dir=None)


def test_drift_uuid_list_hash_mutation(env, monkeypatch):
    monkeypatch.setattr(p2, "KNOWN_PROPOSED_UUID_LIST_SHA256", "deadbeef" * 8)
    with pytest.raises(SystemExit):
        p2.run(snapshot=_FROZEN, b162_tree_root=env["b162_tree"],
               de7_tree_root=env["de7_tree"], b162_corpus=env["corpus"], out_dir=None)


def test_drift_rename_map_mutation_breaks_gate(env):
    g = p2.validate_p2_once_only_gate(
        inputs={
            "frozen_corpus_sha256": p2.GENESIS_SNAPSHOT_SHA256,
            "record_count": 42804,
            "namespace_uuid": p2.PROPOSED_CANONICAL_NAMESPACE_UUID,
            "canonicalisation_rules_version": p2.CANONICALISATION_RULES_VERSION,
            "genesis_key_spec_version": p2.GENESIS_KEY_SPEC_VERSION,
            "historical_tree_commit": p2.OWNER_P2_TREE_COMMIT,
            "historical_tree_manifest_sha256": _OWNER_TREE_MANIFEST,
            "historical_rename_map_sha256": "TAMPERED",
            "genesis_record_manifest_sha256": _MANIFEST_FULL_SHA,
        },
        rename_map_sha256=_RENAME_MAP_SHA,
        genesis_record_manifest_sha256=_MANIFEST_FULL_SHA,
    )
    assert g["genesis_bootstrap_safe_to_run"] is False
    assert g["dynamic_inputs_consistent"] is False


def test_drift_manifest_mutation_breaks_gate():
    g = p2.validate_p2_once_only_gate(
        inputs={
            "frozen_corpus_sha256": p2.GENESIS_SNAPSHOT_SHA256,
            "record_count": 42804,
            "namespace_uuid": p2.PROPOSED_CANONICAL_NAMESPACE_UUID,
            "canonicalisation_rules_version": p2.CANONICALISATION_RULES_VERSION,
            "genesis_key_spec_version": p2.GENESIS_KEY_SPEC_VERSION,
            "historical_tree_commit": p2.OWNER_P2_TREE_COMMIT,
            "historical_tree_manifest_sha256": _OWNER_TREE_MANIFEST,
            "historical_rename_map_sha256": _RENAME_MAP_SHA,
            "genesis_record_manifest_sha256": "TAMPERED",
        },
        rename_map_sha256=_RENAME_MAP_SHA,
        genesis_record_manifest_sha256=_MANIFEST_FULL_SHA,
    )
    assert g["genesis_bootstrap_safe_to_run"] is False


@pytest.mark.parametrize("key", ["canonicalisation_rules_version", "genesis_key_spec_version"])
def test_drift_version_change_breaks_gate(key):
    inp = {
        "frozen_corpus_sha256": p2.GENESIS_SNAPSHOT_SHA256,
        "record_count": 42804,
        "namespace_uuid": p2.PROPOSED_CANONICAL_NAMESPACE_UUID,
        "canonicalisation_rules_version": p2.CANONICALISATION_RULES_VERSION,
        "genesis_key_spec_version": p2.GENESIS_KEY_SPEC_VERSION,
        "historical_tree_commit": p2.OWNER_P2_TREE_COMMIT,
        "historical_tree_manifest_sha256": _OWNER_TREE_MANIFEST,
        "historical_rename_map_sha256": _RENAME_MAP_SHA,
        "genesis_record_manifest_sha256": _MANIFEST_FULL_SHA,
    }
    inp[key] = "vX-tampered"
    g = p2.validate_p2_once_only_gate(inputs=inp, rename_map_sha256=_RENAME_MAP_SHA,
                                     genesis_record_manifest_sha256=_MANIFEST_FULL_SHA)
    assert g["static_inputs_valid"] is False
    assert g["genesis_bootstrap_safe_to_run"] is False


def test_drift_rename_map_ambiguity_detected(env):
    """A synthetic frozen record with an unmatched source and an unknown legacy id
    must surface as an ambiguity, not a silent drop."""
    _, _, frozen = p2.verify_snapshot(_FROZEN)
    frozen = copy.deepcopy(frozen)
    frozen[0] = dict(frozen[0])
    frozen[0]["source"] = "ZZZ nonexistent collection\\999999.sgf"
    frozen[0]["id"] = -12345
    cs = p2.corpus_side(frozen)
    b162_tree = tree_inventory(env["b162_tree"])
    de7_tree = tree_inventory(env["de7_tree"])
    b162_corpus = json.loads(env["corpus"].read_bytes())
    rm = p2.build_rename_map(cs["rows"], frozen, b162_tree, b162_corpus, de7_tree)
    assert rm["ambiguity_count"] >= 1
    assert any(a["pre_reorg_source"].startswith("ZZZ nonexistent") for a in rm["ambiguities"])
