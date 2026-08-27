"""LC008 — content-duplicate identity & review-fanout audit tests.

Exercises the audit's classification logic on synthetic records and, when the
canonical snapshot is present + hash-verified, asserts the headline aggregate
results (404 groups / 940 dup records / 0 safe fanout / 0 savings / all 13
DUPLICATE_IDENTITY_BLOCKED accounted for) and deterministic manifest bytes.

The audit is READ-ONLY: it never mutates the corpus, never generates a
source_record_uuid, never touches LC009 semantics.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import tools.lc008_content_duplicate_identity_audit as lc008  # noqa: E402

_SNAPSHOT = Path("D:/go-website/questions.json")
_SNAPSHOT_SHA = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"


def _snapshot_ok() -> bool:
    return _SNAPSHOT.exists() and hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA


_BASE_SGF = "(;SZ[19];B[pd];W[dd];B[qf])"
_DUP_LEGACY: frozenset = frozenset()


def _rec(**kw):
    r = {"id": kw.pop("id", 1), "content": kw.pop("content", _BASE_SGF)}
    r.update(kw)
    return r


# --------------------------------------------------------------------------- #
# grouping + census
# --------------------------------------------------------------------------- #

class TestGrouping:
    def test_identical_content_groups_together_distinct_content_does_not(self, tmp_path):
        recs = [
            _rec(id=1, source="a.sgf"),
            _rec(id=2, source="b.sgf"),                       # same content as id 1
            _rec(id=3, content="(;SZ[19];B[dp])", source="c.sgf"),
        ]
        snap = tmp_path / "q.json"
        raw = json.dumps(recs).encode()
        snap.write_bytes(raw)
        import tools.lc008_content_duplicate_identity_audit as m
        m2_sha = hashlib.sha256(raw).hexdigest()
        # monkeypatch the expected hash so verify_snapshot proceeds
        old = m.EXPECTED_SNAPSHOT_SHA256
        m.EXPECTED_SNAPSHOT_SHA256 = m2_sha
        try:
            out = m.run(snap, None)
        finally:
            m.EXPECTED_SNAPSHOT_SHA256 = old
        s = out["summary"]
        assert s["content_duplicate_groups"] == 1
        assert s["content_duplicate_records"] == 2
        assert s["distinct_content_hashes"] == 2


# --------------------------------------------------------------------------- #
# per-group classification — fail closed
# --------------------------------------------------------------------------- #

class TestClassifyGroup:
    def test_no_uuid_is_incomplete_identity_and_blocked(self):
        recs = [_rec(id=1, source="a.sgf"), _rec(id=2, source="b.sgf")]
        g = lc008.classify_group([0, 1], recs, _DUP_LEGACY)
        assert g["primary_identity_classification"] == "SAME_CONTENT_IDENTITY_INCOMPLETE"
        assert g["fanout_classification"] == "BLOCKED_BY_INCOMPLETE_IDENTITY"
        assert g["potential_review_savings"] == 0
        assert g["safe_primary_review_record"] is None

    def test_metadata_drift_is_flagged(self):
        recs = [_rec(id=1, source="a.sgf", discipline="tesuji"),
                _rec(id=2, source="b.sgf", discipline="life_death")]
        g = lc008.classify_group([0, 1], recs, _DUP_LEGACY)
        assert "discipline" in g["metadata_drift"]
        assert "SAME_CONTENT_WITH_METADATA_DRIFT" in g["identity_flags"]

    def test_provenance_drift_is_flagged(self):
        recs = [_rec(id=1, source="a.sgf", katago_best_move="G4"),
                _rec(id=2, source="b.sgf", katago_best_move="H4")]
        g = lc008.classify_group([0, 1], recs, _DUP_LEGACY)
        assert "katago_best_move" in g["provenance_drift"]
        assert "SAME_CONTENT_WITH_PROVENANCE_DRIFT" in g["identity_flags"]

    def test_authoring_drift_is_flagged(self):
        recs = [_rec(id=1, source="a.sgf", comment="正解"),
                _rec(id=2, source="b.sgf", comment=None)]
        g = lc008.classify_group([0, 1], recs, _DUP_LEGACY)
        assert "comment" in g["authoring_context_drift"]

    def test_uuid_mismatch_blocks_by_source_identity(self):
        recs = [_rec(id=1, source="a.sgf", source_record_uuid="uuid-aaaaaaaa"),
                _rec(id=2, source="b.sgf", source_record_uuid="uuid-bbbbbbbb")]
        g = lc008.classify_group([0, 1], recs, _DUP_LEGACY)
        assert g["primary_identity_classification"] == "SAME_CONTENT_DIFFERENT_SOURCE_IDENTITY"
        assert g["fanout_classification"] == "BLOCKED_BY_SOURCE_IDENTITY"
        assert g["potential_review_savings"] == 0

    def test_safe_fanout_only_with_shared_uuid_shared_source_and_no_drift(self):
        recs = [_rec(id=1, source="same.sgf", source_record_uuid="uuid-shared-1"),
                _rec(id=2, source="same.sgf", source_record_uuid="uuid-shared-1")]
        g = lc008.classify_group([0, 1], recs, _DUP_LEGACY)
        assert g["fanout_classification"] == "SAFE_REVIEW_FANOUT"
        # even then it is review-labour fanout, never a merge
        assert g["member_count"] == 2
        assert len(g["record_indexes"]) == 2

    def test_shared_uuid_but_distinct_source_still_requires_independent_review(self):
        recs = [_rec(id=1, source="a.sgf", source_record_uuid="uuid-x"),
                _rec(id=2, source="b.sgf", source_record_uuid="uuid-x")]
        g = lc008.classify_group([0, 1], recs, _DUP_LEGACY)
        assert g["fanout_classification"] == "REQUIRES_INDEPENDENT_REVIEW"
        assert g["potential_review_savings"] == 0


# --------------------------------------------------------------------------- #
# snapshot-bound headline assertions
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _snapshot_ok(), reason="canonical snapshot absent")
class TestFullSnapshot:
    def test_headline_aggregates(self, tmp_path):
        out = lc008.run(_SNAPSHOT, tmp_path / "m.json")
        s = out["summary"]
        assert s["snapshot_hash_match"] is True
        assert s["corpus_record_count"] == 42804
        assert s["distinct_content_hashes"] == 42268
        assert s["content_duplicate_groups"] == 404
        assert s["content_duplicate_records"] == 940
        assert s["duplicate_group_size_min"] == 2
        assert s["duplicate_group_size_max"] == 5
        assert sum(int(k) * v for k, v in s["duplicate_group_size_distribution"].items()) == 940

    def test_no_safe_fanout_no_savings_all_blocked_by_incomplete_identity(self, tmp_path):
        out = lc008.run(_SNAPSHOT, tmp_path / "m.json")
        s = out["summary"]
        assert s["safe_review_fanout_groups"] == 0
        assert s["potential_manual_review_dedup_savings"] == 0
        assert s["fanout_classification_counts"] == {"BLOCKED_BY_INCOMPLETE_IDENTITY": 404}
        assert s["primary_identity_classification_counts"] == {"SAME_CONTENT_IDENTITY_INCOMPLETE": 404}

    def test_source_record_uuid_absent_and_not_generated(self, tmp_path):
        out = lc008.run(_SNAPSHOT, tmp_path / "m.json")
        s = out["summary"]
        assert s["source_record_uuid_present_count"] == 0
        assert s["source_record_uuid_missing_count"] == 42804
        assert s["source_record_uuid_generated"] is False
        assert s["content_dedup_does_not_rewrite_identity"] is True

    def test_thirteen_duplicate_identity_blocked_reconciled(self, tmp_path):
        out = lc008.run(_SNAPSHOT, tmp_path / "m.json")
        s = out["summary"]
        assert s["duplicate_identity_blocked_records"] == 13
        assert s["duplicate_identity_blocked_in_content_duplicate_groups"] == []
        assert s["duplicate_identity_blocked_distinct_content_hashes"] == 13
        assert s["all_13_accounted_for"] is True
        assert s["duplicate_legacy_id_groups"] == 11

    def test_lc009_semantics_untouched_and_no_mutation(self, tmp_path):
        out = lc008.run(_SNAPSHOT, tmp_path / "m.json")
        s = out["summary"]
        assert s["lc009_semantics_changed"] is False
        assert s["corpus_mutation"] is False

    def test_manifest_deterministic_bytes(self, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        lc008.run(_SNAPSHOT, a)
        lc008.run(_SNAPSHOT, b)
        assert a.read_bytes() == b.read_bytes()
        assert a.read_bytes().endswith(b"\n")
        assert b"\r\n" not in a.read_bytes()

    def test_committed_manifest_matches_regeneration(self, tmp_path):
        committed = _REPO / "docs" / "planning" / "lc008_content_duplicate_manifest.json"
        if not committed.exists():
            pytest.skip("committed manifest not present yet")
        fresh = tmp_path / "m.json"
        lc008.run(_SNAPSHOT, fresh)
        assert hashlib.sha256(fresh.read_bytes()).hexdigest() == \
            hashlib.sha256(committed.read_bytes()).hexdigest()
