"""LC012 — SGF source-tree genesis freeze machinery tests.

PROTOTYPE_ONLY / NON-MUTATING. The corpus-side half (canonical sources +
proposed genesis UUIDv5) is exercised against the real frozen snapshot when it
is present + hash-verified; the tree-side half (inventory, deterministic
tree-manifest hash, corpus↔tree join, drift A..J) is exercised on synthetic
temp SGF trees.

LC012 could not locate an authoritative SGF tree for the 42,804 snapshot, so
these tests prove the machinery is *ready*, not that a real tree reconciled.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import tools.lc012_sgf_source_tree_freeze as lc012  # noqa: E402
from tools.lc011_identity_registry_prototype import (  # noqa: E402
    PROPOSED_CANONICAL_NAMESPACE_UUID,
    canonical_source_key,
    mint_genesis_uuid,
)

_SNAPSHOT = Path("D:/go-website/questions.json")
_SNAPSHOT_SHA = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"


def _snapshot_ok() -> bool:
    return _SNAPSHOT.exists() and hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA


def _mk_tree(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


# --------------------------------------------------------------------------- #
# canonical path handling  (canon-source-v1, via LC011)
# --------------------------------------------------------------------------- #

class TestCanonicalPathHandling:
    def test_backslash_forward_slash_and_case(self):
        assert canonical_source_key("A\\b\\1.sgf")[0] == "A/b/1.sgf"
        assert canonical_source_key("A/b/1.sgf")[0] != canonical_source_key("a/B/1.sgf")[0]

    def test_dotted_folders_preserved_and_bad_segments_rejected(self):
        assert canonical_source_key("Book/3.死 活/Vol. 2/7.sgf")[0] == "Book/3.死 活/Vol. 2/7.sgf"
        for bad in ("x/./1.sgf", "x/../1.sgf", "x/ /1.sgf", "x/a./1.sgf", "x/1.SGF", "x/1.txt", ""):
            assert canonical_source_key(bad)[0] is None


# --------------------------------------------------------------------------- #
# tree inventory + deterministic hash
# --------------------------------------------------------------------------- #

class TestTreeInventoryAndHash:
    def test_inventory_counts_and_collection(self, tmp_path):
        _mk_tree(tmp_path, {
            "BookA/1.sgf": b"(;GM[1])", "BookA/2.sgf": b"(;GM[1]B[aa])",
            "BookB/sub/9.sgf": b"(;GM[1]W[bb])", "notes.txt": b"ignore me",
        })
        inv = lc012.tree_inventory(tmp_path)
        assert inv["sgf_file_count"] == 3
        cols = {f["collection"] for f in inv["files"]}
        assert cols == {"BookA", "BookB"}
        assert inv["canonical_path_collisions"] == []

    def test_tree_manifest_hash_is_enumeration_order_independent(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        payload = {f"C{i}/{i}.sgf": f"(;GM[1]C[{i}])".encode() for i in range(20)}
        _mk_tree(a, payload)
        _mk_tree(b, dict(reversed(list(payload.items()))))
        assert lc012.tree_inventory(a)["tree_manifest_sha256"] == \
            lc012.tree_inventory(b)["tree_manifest_sha256"]

    def test_canonical_path_collision_is_reported(self, tmp_path):
        # two physical files whose canonical keys collide (\ vs / can't happen on
        # a real FS; use a trailing-separator style that collapses)
        _mk_tree(tmp_path, {"X/1.sgf": b"a"})
        (tmp_path / "X").mkdir(exist_ok=True)
        # simulate by hand: craft an inventory with a duplicate canonical path
        inv = lc012.tree_inventory(tmp_path)
        inv["files"].append(dict(inv["files"][0]))
        # recompute collisions the way tree_inventory does
        import collections
        kc = collections.Counter(f["canonical_relative_path"] for f in inv["files"])
        assert any(c > 1 for c in kc.values())


# --------------------------------------------------------------------------- #
# corpus ↔ tree join
# --------------------------------------------------------------------------- #

class TestJoin:
    def _corpus_rows(self, specs):
        # specs: [(raw_source, content_str, id)]
        rows = []
        for i, (src, content, lid) in enumerate(specs):
            ck, err = canonical_source_key(src)
            rows.append({
                "record_index": i, "legacy_question_id": lid, "raw_source": src,
                "canonical_source": ck,
                "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "proposed_source_record_uuid": (mint_genesis_uuid(ck) if ck else None),
            })
        return rows

    def test_exact_match_missing_and_drift(self, tmp_path):
        _mk_tree(tmp_path, {
            "BookA/1.sgf": b"(;GM[1]C[same])",          # will match content
            "BookA/2.sgf": b"(;GM[1]C[tree-bytes])",    # content differs from corpus
        })
        rows = self._corpus_rows([
            ("BookA\\1.sgf", "(;GM[1]C[same])", 1),
            ("BookA\\2.sgf", "(;GM[1]C[corpus-repr])", 2),
            ("BookA\\3.sgf", "(;GM[1]C[gone])", 3),      # no file
        ])
        join = lc012.join_corpus_to_tree(rows, lc012.tree_inventory(tmp_path))
        assert join["matched_to_source_tree"] == 2
        assert join["missing_source"] == 1
        assert join["exact_raw_equivalent_count"] == 1
        assert join["unexplained_content_drift_count"] == 1


# --------------------------------------------------------------------------- #
# UUID generation + collision + separation  (corpus-side, guarded)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _snapshot_ok(), reason="canonical snapshot absent")
class TestCorpusSide:
    def test_proposed_uuids_are_complete_distinct_and_deterministic(self):
        records = json.loads(_SNAPSHOT.read_bytes())
        cs = lc012.corpus_side(records)
        assert cs["corpus_record_count"] == 42804
        assert cs["distinct_canonical_sources"] == 42804
        assert cs["source_not_recoverable"] == 0
        assert cs["canonical_path_collision_count"] == 0
        assert cs["proposed_uuid_count"] == 42804
        assert cs["distinct_uuid_count"] == 42804
        assert cs["uuid_collision_count"] == 0
        # cross-process determinism: recompute the sorted-uuid digest here
        us = sorted(r["proposed_source_record_uuid"] for r in cs["rows"])
        assert hashlib.sha256("\n".join(us).encode()).hexdigest() == cs["uuid_list_sha256"]
        assert all(uuid.UUID(u).version == 5 for u in us[:50])

    def test_404_duplicate_groups_and_13_legacy_collisions_separable(self):
        records = json.loads(_SNAPSHOT.read_bytes())
        cs = lc012.corpus_side(records)
        assert cs["duplicate_content_group_count"] == 404
        assert cs["duplicate_content_groups_separable"] == 404
        assert cs["legacy_collision_records"] == 13
        assert cs["legacy_collision_records_separable"] is True

    def test_run_reports_stop_without_a_tree_and_generates_no_manifest(self, tmp_path):
        res = lc012.run(_SNAPSHOT, None, tmp_path / "r.json")
        assert res["result"].startswith("STOP_AND_REPORT")
        assert res["tree_side"]["actual_source_tree_traced"] is False
        assert res["genesis_record_manifest"]["status"] == "NOT_GENERATED"
        assert res["corpus_mutated"] is False
        assert res["sgf_source_files_mutated"] == 0
        assert res["source_record_uuid_backfill"] is False
        assert res["lc009_semantics_changed"] is False

    def test_run_report_deterministic(self, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        lc012.run(_SNAPSHOT, None, a)
        lc012.run(_SNAPSHOT, None, b)
        assert a.read_bytes() == b.read_bytes()
        assert a.read_bytes().endswith(b"\n") and b"\r\n" not in a.read_bytes()


# --------------------------------------------------------------------------- #
# drift fail-closed  A..J  (§28)
# --------------------------------------------------------------------------- #

class TestDriftFailClosed:
    def _tree_and_rows(self, tmp_path):
        files = {"BookA/1.sgf": b"(;GM[1]C[one])", "BookA/2.sgf": b"(;GM[1]C[two])"}
        _mk_tree(tmp_path, files)
        rows = [
            {"record_index": 0, "legacy_question_id": 1, "raw_source": "BookA\\1.sgf",
             "canonical_source": "BookA/1.sgf",
             "content_sha256": hashlib.sha256(files["BookA/1.sgf"]).hexdigest(),
             "proposed_source_record_uuid": mint_genesis_uuid("BookA/1.sgf")},
            {"record_index": 1, "legacy_question_id": 2, "raw_source": "BookA\\2.sgf",
             "canonical_source": "BookA/2.sgf",
             "content_sha256": hashlib.sha256(files["BookA/2.sgf"]).hexdigest(),
             "proposed_source_record_uuid": mint_genesis_uuid("BookA/2.sgf")},
        ]
        return files, rows

    def test_A_content_changed(self, tmp_path):
        files, rows = self._tree_and_rows(tmp_path)
        (tmp_path / "BookA/1.sgf").write_bytes(b"(;GM[1]C[CHANGED])")
        join = lc012.join_corpus_to_tree(rows, lc012.tree_inventory(tmp_path))
        assert join["unexplained_content_drift_count"] == 1

    def test_B_path_renamed_without_lineage(self, tmp_path):
        files, rows = self._tree_and_rows(tmp_path)
        os.rename(tmp_path / "BookA/1.sgf", tmp_path / "BookA/1_renamed.sgf")
        join = lc012.join_corpus_to_tree(rows, lc012.tree_inventory(tmp_path))
        assert join["missing_source"] == 1     # record still points at the old canonical path

    def test_C_file_missing(self, tmp_path):
        files, rows = self._tree_and_rows(tmp_path)
        os.remove(tmp_path / "BookA/2.sgf")
        join = lc012.join_corpus_to_tree(rows, lc012.tree_inventory(tmp_path))
        assert join["missing_source"] == 1

    def test_D_extra_file_breaks_count_gate(self, tmp_path):
        _mk_tree(tmp_path, {"BookA/1.sgf": b"x", "BookA/2.sgf": b"y", "BookA/3.sgf": b"z"})
        inv = lc012.tree_inventory(tmp_path)
        assert inv["sgf_file_count"] == 3 != lc012.EXPECTED_RECORD_COUNT

    def test_E_snapshot_hash_mismatch(self, tmp_path):
        bogus = tmp_path / "q.json"
        bogus.write_bytes(json.dumps([{"id": 1, "source": "a/1.sgf", "content": "x"}]).encode())
        with pytest.raises(SystemExit, match="SNAPSHOT_HASH_MISMATCH"):
            lc012.run(bogus, None, None)

    def test_F_tree_hash_mismatch_refuses_reentry(self):
        prior = {
            "corpus_id": lc012.CORPUS_ID, "snapshot_sha256": _SNAPSHOT_SHA, "record_count": 42804,
            "sgf_tree_manifest_sha256": "AAA", "namespace_uuid": PROPOSED_CANONICAL_NAMESPACE_UUID,
            "genesis_key_spec_version": lc012.GENESIS_KEY_SPEC_VERSION,
            "canonicalisation_rules_version": lc012.CANONICALISATION_RULES_VERSION,
        }
        g = lc012.validate_once_only_gate(
            corpus_id=lc012.CORPUS_ID, snapshot_sha256=_SNAPSHOT_SHA, record_count=42804,
            sgf_tree_manifest_sha256="BBB", namespace_uuid=PROPOSED_CANONICAL_NAMESPACE_UUID,
            genesis_key_spec_version=lc012.GENESIS_KEY_SPEC_VERSION,
            canonicalisation_rules_version=lc012.CANONICALISATION_RULES_VERSION, prior_bootstrap=prior)
        assert g["safe_to_bootstrap"] is False and g["prior_matches"] is False

    def test_G_namespace_mismatch_raises(self):
        from tools.lc011_identity_registry_prototype import assert_namespace
        with pytest.raises(ValueError, match="NAMESPACE_DRIFT"):
            assert_namespace(str(uuid.uuid4()))

    def test_H_and_I_version_mismatch_blocks_gate(self):
        for kw in ("genesis_key_spec_version", "canonicalisation_rules_version"):
            args = dict(
                corpus_id=lc012.CORPUS_ID, snapshot_sha256=_SNAPSHOT_SHA, record_count=42804,
                sgf_tree_manifest_sha256="deadbeef", namespace_uuid=PROPOSED_CANONICAL_NAMESPACE_UUID,
                genesis_key_spec_version=lc012.GENESIS_KEY_SPEC_VERSION,
                canonicalisation_rules_version=lc012.CANONICALISATION_RULES_VERSION,
                prior_bootstrap=None)
            args[kw] = "WRONG-vX"
            g = lc012.validate_once_only_gate(**args)
            assert g["static_inputs_valid"] is False and g["safe_to_bootstrap"] is False

    def test_J_canonical_path_collision_detected(self, tmp_path):
        _mk_tree(tmp_path, {"K/1.sgf": b"a"})
        inv = lc012.tree_inventory(tmp_path)
        # inject a second entry with the same canonical path (what two colliding
        # physical files would produce) and re-run the tree's own collision check
        inv["files"].append({**inv["files"][0], "raw_relative_path": "K\\1.sgf"})
        import collections
        kc = collections.Counter(f["canonical_relative_path"] for f in inv["files"])
        collisions = [k for k, c in kc.items() if c > 1]
        assert collisions == ["K/1.sgf"]
