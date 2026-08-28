"""LC010 — source_record_uuid identity-foundation feasibility PROTOTYPE tests.

Everything here is PROTOTYPE_ONLY / NON_MUTATING. The prototype computes
hypothetical UUIDs in memory; it never writes a UUID into the corpus, an SGF,
a DB, or a runtime record, and it does not touch LC009 semantics.

Snapshot-bound assertions are guarded on the real corpus being present +
hash-verified; the identity logic is fully exercised on synthetic records.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import tools.lc010_source_identity_prototype as lc010  # noqa: E402

_SNAPSHOT = Path("D:/go-website/questions.json")
_SNAPSHOT_SHA = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"


def _snapshot_ok() -> bool:
    return _SNAPSHOT.exists() and hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA


def _rec(**kw):
    r = {"id": kw.pop("id", 1), "content": kw.pop("content", "(;SZ[19];B[pd])")}
    r.update(kw)
    return r


def _key(row_or_src):
    return lc010._canonical_source_key(row_or_src)


# --------------------------------------------------------------------------- #
# canonical key + deterministic UUID
# --------------------------------------------------------------------------- #

class TestCanonicalKey:
    def test_backslash_and_forwardslash_normalise_equal(self):
        assert _key("Book\\A\\001.sgf") == _key("Book/A/001.sgf") == "Book/A/001.sgf"

    def test_leading_trailing_whitespace_and_separators_stripped(self):
        assert _key("  Book\\A\\1.sgf  ") == "Book/A/1.sgf"
        assert _key("\\Book\\A\\1.sgf\\") == "Book/A/1.sgf"

    def test_repeated_separators_collapsed(self):
        assert _key("Book\\\\A\\1.sgf") == "Book/A/1.sgf"

    def test_case_is_preserved(self):
        assert _key("Book/A/1.sgf") != _key("book/a/1.sgf")

    def test_unicode_nfc(self):
        import unicodedata
        nfd = unicodedata.normalize("NFD", "萬化棋局/1.sgf")
        assert _key(nfd) == _key("萬化棋局/1.sgf")

    def test_empty_and_none_give_no_key(self):
        assert _key(None) is None
        assert _key("") is None
        assert _key("   ") is None

    def test_uuid_is_v5_deterministic_and_namespaced(self):
        k = "Book/A/1.sgf"
        u1 = lc010._prototype_uuid(k)
        u2 = lc010._prototype_uuid(k)
        assert u1 == u2
        parsed = uuid.UUID(u1)
        assert parsed.version == 5
        # different key -> different uuid
        assert lc010._prototype_uuid("Book/A/2.sgf") != u1


# --------------------------------------------------------------------------- #
# classification invariants
# --------------------------------------------------------------------------- #

class TestClassification:
    def test_same_source_same_identity(self):
        rows = lc010._classify([_rec(source="C/x/1.sgf"), _rec(id=2, source="C\\x\\1.sgf")])
        # byte-identical-after-canonicalisation -> both flagged, not silently merged
        assert rows[0]["prototype_source_record_uuid"] is None
        assert rows[0]["identity_feasibility_class"] in ("IDENTITY_AMBIGUOUS", "IDENTITY_COLLISION")

    def test_different_sources_different_identity(self):
        rows = lc010._classify([_rec(source="C/x/1.sgf"), _rec(id=2, source="C/x/2.sgf")])
        assert rows[0]["identity_feasibility_class"] == "IDENTITY_PROVABLE"
        assert rows[1]["identity_feasibility_class"] == "IDENTITY_PROVABLE"
        assert rows[0]["prototype_source_record_uuid"] != rows[1]["prototype_source_record_uuid"]

    def test_record_reordering_does_not_change_identity(self):
        a = _rec(id=1, source="C/x/1.sgf")
        b = _rec(id=2, source="C/x/2.sgf")
        fwd = lc010._classify([a, b])
        rev = lc010._classify([b, a])
        assert fwd[0]["prototype_source_record_uuid"] == rev[1]["prototype_source_record_uuid"]
        assert fwd[1]["prototype_source_record_uuid"] == rev[0]["prototype_source_record_uuid"]

    def test_duplicate_sgf_content_still_separable(self):
        dup_sgf = "(;SZ[19];B[pd];W[dd];B[qf])"
        rows = lc010._classify([
            _rec(id=1, source="BookA/1.sgf", content=dup_sgf),
            _rec(id=2, source="BookB/9.sgf", content=dup_sgf),
        ])
        assert rows[0]["prototype_source_record_uuid"] != rows[1]["prototype_source_record_uuid"]
        assert all(r["identity_feasibility_class"] == "IDENTITY_PROVABLE" for r in rows)

    def test_legacy_id_collision_still_separable(self):
        rows = lc010._classify([
            _rec(id=40511, source="Elem/2.行棋/7.綜合測驗/2.sgf", content="(;SZ[19];B[aa])"),
            _rec(id=40511, source="Elem/7.实力测试/第2回/7.sgf", content="(;SZ[19];B[bb])"),
        ])
        assert rows[0]["prototype_source_record_uuid"] != rows[1]["prototype_source_record_uuid"]

    def test_missing_provenance_fails_closed(self):
        rows = lc010._classify([_rec(source=None), _rec(id=2, source="")])
        for r in rows:
            assert r["identity_feasibility_class"] == "IDENTITY_MISSING_SOURCE_PROVENANCE"
            assert r["prototype_source_record_uuid"] is None

    def test_non_sgf_source_is_not_recoverable(self):
        rows = lc010._classify([_rec(source="notes/todo.txt"), _rec(id=2, source="placeholder")])
        for r in rows:
            assert r["identity_feasibility_class"] == "SOURCE_NOT_RECOVERABLE"
            assert r["prototype_source_record_uuid"] is None

    def test_byte_identical_source_is_collision(self):
        rows = lc010._classify([_rec(id=1, source="C/x/1.sgf"), _rec(id=2, source="C/x/1.sgf")])
        assert all(r["identity_feasibility_class"] == "IDENTITY_COLLISION" for r in rows)
        assert all(r["prototype_source_record_uuid"] is None for r in rows)


# --------------------------------------------------------------------------- #
# full-snapshot feasibility census (guarded)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _snapshot_ok(), reason="canonical snapshot absent")
class TestFullSnapshot:
    def test_census_accounts_for_all_42804(self, tmp_path):
        s = lc010.run(_SNAPSHOT, tmp_path / "m.json")["summary"]
        assert s["snapshot_hash_match"] is True
        assert s["record_count"] == 42804
        assert s["identity_census_total"] == 42804
        assert s["identity_census_accounting_pass"] is True
        assert (s["identity_provable_count"] + s["identity_provable_with_registry_count"]
                + s["identity_ambiguous_count"] + s["identity_missing_source_provenance_count"]
                + s["identity_collision_count"] + s["source_not_recoverable_count"]) == 42804

    def test_every_record_is_identity_provable_and_uuids_unique(self, tmp_path):
        s = lc010.run(_SNAPSHOT, tmp_path / "m.json")["summary"]
        assert s["identity_provable_count"] == 42804
        assert s["identity_ambiguous_count"] == 0
        assert s["identity_collision_count"] == 0
        assert s["prototype_uuid_collision_count"] == 0
        assert s["distinct_canonical_source_keys"] == 42804
        assert s["invariants"]["I1_uniqueness_uuid_collision_count"] == 0

    def test_404_duplicate_groups_all_identity_provable(self, tmp_path):
        s = lc010.run(_SNAPSHOT, tmp_path / "m.json")["summary"]
        assert s["duplicate_groups_total"] == 404
        assert s["duplicate_groups_identity_provable"] == 404
        assert s["duplicate_groups_partial"] == 0
        assert s["duplicate_groups_unresolved"] == 0

    def test_13_legacy_collision_records_separable(self, tmp_path):
        s = lc010.run(_SNAPSHOT, tmp_path / "m.json")["summary"]
        assert s["legacy_collision_records"] == 13
        assert s["legacy_collision_records_separable_count"] == 13
        assert s["legacy_collision_records_separable"] is True
        assert s["legacy_collision_blocked_indexes"] == []

    def test_prototype_only_and_no_mutation_flags(self, tmp_path):
        s = lc010.run(_SNAPSHOT, tmp_path / "m.json")["summary"]
        assert s["prototype_only"] is True
        assert s["corpus_mutated"] is False
        assert s["source_record_uuid_backfill"] is False
        assert s["request_time_uuid_generation"] is False
        assert s["lc009_semantics_changed"] is False

    def test_manifest_deterministic_and_lf(self, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        lc010.run(_SNAPSHOT, a)
        lc010.run(_SNAPSHOT, b)
        assert a.read_bytes() == b.read_bytes()
        assert a.read_bytes().endswith(b"\n")
        assert b"\r\n" not in a.read_bytes()

    def test_committed_manifest_matches_regeneration(self, tmp_path):
        committed = _REPO / "docs" / "planning" / "lc010_source_identity_feasibility_manifest.json"
        if not committed.exists():
            pytest.skip("committed manifest not present yet")
        fresh = tmp_path / "m.json"
        lc010.run(_SNAPSHOT, fresh)
        assert hashlib.sha256(fresh.read_bytes()).hexdigest() == \
            hashlib.sha256(committed.read_bytes()).hexdigest()
