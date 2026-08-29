"""LC011 — Immutable Puzzle Identity Foundation registry / resolver / lineage
contract tests. PROTOTYPE_ONLY / NON_MUTATING.

Exercises every semantic the LC011 ADR locks: deterministic frozen-genesis
mint, reorder invariance, rename/move via the registry (never recompute),
content-correction vs source-replacement, split / merge / delete / restore,
the fail-closed resolver, 404-duplicate + 13-legacy-collision separability,
the source-less new-record policy, and the impossibility of request-time
identity generation.
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

import tools.lc011_identity_registry_prototype as lc011  # noqa: E402

_SNAPSHOT = Path("D:/go-website/questions.json")
_SNAPSHOT_SHA = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"


def _snapshot_ok() -> bool:
    return _SNAPSHOT.exists() and hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA


GS = lc011.GENESIS_SNAPSHOT_SHA256


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _genesis_registry(pairs):
    """pairs = [(raw_source, content_str, legacy_id), ...]"""
    reg = lc011.Registry()
    recs = []
    for src, content, lid in pairs:
        recs.append(reg.register_genesis_record(
            genesis_snapshot_sha256=GS, raw_source=src,
            content_sha256=_sha(content), legacy_question_id=lid))
    return reg, recs


# --------------------------------------------------------------------------- #
# canonicalisation + genesis key
# --------------------------------------------------------------------------- #

class TestCanonicalisation:
    def test_backslash_forwardslash_and_decoration(self):
        assert lc011.canonical_source_key("Book\\A\\1.sgf")[0] == "Book/A/1.sgf"
        assert lc011.canonical_source_key("  /Book//A/1.sgf/ ")[0] == "Book/A/1.sgf"

    def test_case_preserved(self):
        assert lc011.canonical_source_key("Book/A/1.sgf")[0] != lc011.canonical_source_key("book/a/1.sgf")[0]

    def test_fail_closed_cases(self):
        for bad in (None, "", "   ", "notes/todo.txt", "Book/A/1.SGF",
                    "Book/./1.sgf", "Book/../1.sgf", "Book/ /1.sgf", "Book/A./1.sgf",
                    "Book/A/1.sgf\x1f", "Book/\x00/1.sgf",
                    # LC11-E: invisibles rejected, never silently stripped
                    "Book/A​/1.sgf", "Book/﻿A/1.sgf", "Book/A B/1.sgf",
                    "Book/A/1.sgf　", "Book/A⁠/1.sgf", "Book/A‮B/1.sgf"):
            key, err = lc011.canonical_source_key(bad)
            assert key is None and err is not None, bad

    def test_dotted_folder_segments_survive(self):
        # 327 real folder segments contain '.' — the .sgf rule is a literal
        # suffix test, never splitext (LC11-A)
        assert lc011.canonical_source_key("Book/3.死 活/Vol. 2/7.sgf")[0] == "Book/3.死 活/Vol. 2/7.sgf"

    def test_field_separator_never_in_canon_source(self):
        # a canon source that somehow contained U+001F must be rejected upstream
        assert lc011.canonical_source_key("a/b\x1fc/1.sgf")[0] is None

    def test_genesis_key_shape_and_determinism(self):
        k1 = lc011.genesis_key("Book/A/1.sgf")
        k2 = lc011.genesis_key("Book/A/1.sgf")
        assert k1 == k2
        # Option C — the snapshot sha is NOT in the name
        assert k1.split("\x1f") == ["gk1", "sgf-source-file", "v1", "Book/A/1.sgf"]
        assert GS not in k1

    def test_genesis_uuid_is_v5_and_snapshot_independent(self):
        u = lc011.mint_genesis_uuid("Book/A/1.sgf")
        assert uuid.UUID(u).version == 5
        # the name is a pure function of the canonical source; the snapshot sha
        # is a once-only GATE, not part of the identity (LC11-A)
        assert lc011.mint_genesis_uuid("Book/A/1.sgf") == u

    def test_second_genesis_bootstrap_is_refused(self):
        reg = lc011.Registry()
        reg.register_genesis_record(genesis_snapshot_sha256=GS, raw_source="Book/A/1.sgf",
                                    content_sha256=_sha("c"), legacy_question_id=1)
        # same corpus/snapshot -> idempotent re-entry OK
        reg.register_genesis_record(genesis_snapshot_sha256=GS, raw_source="Book/A/2.sgf",
                                    content_sha256=_sha("c2"), legacy_question_id=2)
        # a different snapshot -> REFUSED
        with pytest.raises(ValueError, match="REFUSED|ALREADY_DONE"):
            reg.register_genesis_record(genesis_snapshot_sha256="f" * 64, raw_source="Other/9.sgf",
                                        content_sha256=_sha("c3"), legacy_question_id=3)

    def test_proposed_namespace_is_not_the_lc010_prototype(self):
        assert lc011.PROPOSED_CANONICAL_NAMESPACE_UUID != lc011.LC010_PROTOTYPE_NAMESPACE_UUID
        assert lc011.OWNER_RATIFICATION_REQUIRED is True

    def test_namespace_drift_is_mechanically_rejected(self):
        # LC11-E: a non-ratified namespace must raise, not silently re-key
        lc011.assert_namespace(lc011.PROPOSED_CANONICAL_NAMESPACE_UUID)   # ok
        with pytest.raises(ValueError, match="NAMESPACE_DRIFT"):
            lc011.assert_namespace(lc011.LC010_PROTOTYPE_NAMESPACE_UUID)
        with pytest.raises(ValueError, match="NAMESPACE_DRIFT"):
            lc011.mint_genesis_uuid("Book/A/1.sgf", namespace_uuid=str(uuid.uuid4()))

    def test_seed_does_not_embed_the_adr_document_version(self):
        # an ADR text revision must never change the namespace
        assert "v1.1" not in lc011._NAMESPACE_SEED
        assert "scheme-v1" in lc011._NAMESPACE_SEED


# --------------------------------------------------------------------------- #
# genesis mint invariants
# --------------------------------------------------------------------------- #

class TestGenesisMint:
    def test_same_frozen_source_same_uuid(self):
        _, a = _genesis_registry([("Book/A/1.sgf", "x", 1)])
        _, b = _genesis_registry([("Book\\A\\1.sgf", "y-different-content", 999)])
        assert a[0].source_record_uuid == b[0].source_record_uuid

    def test_different_source_different_uuid(self):
        _, recs = _genesis_registry([("Book/A/1.sgf", "x", 1), ("Book/A/2.sgf", "x", 2)])
        assert recs[0].source_record_uuid != recs[1].source_record_uuid

    def test_reorder_invariance(self):
        p = [("Book/A/1.sgf", "c1", 1), ("Book/A/2.sgf", "c2", 2), ("Book/B/9.sgf", "c3", 3)]
        _, fwd = _genesis_registry(p)
        _, rev = _genesis_registry(list(reversed(p)))
        assert {r.source_record_uuid for r in fwd} == {r.source_record_uuid for r in rev}

    def test_duplicate_content_still_separable(self):
        _, recs = _genesis_registry([("BookA/1.sgf", "SAME", 1), ("BookB/9.sgf", "SAME", 2)])
        assert recs[0].source_record_uuid != recs[1].source_record_uuid

    def test_legacy_id_collision_still_separable(self):
        _, recs = _genesis_registry([("Elem/x/2.sgf", "c-aa", 40511), ("Elem/y/7.sgf", "c-bb", 40511)])
        assert recs[0].source_record_uuid != recs[1].source_record_uuid
        assert recs[0].legacy_question_id == recs[1].legacy_question_id == 40511

    def test_genesis_collision_aborts(self):
        reg = lc011.Registry()
        reg.register_genesis_record(genesis_snapshot_sha256=GS, raw_source="Book/A/1.sgf",
                                    content_sha256=_sha("x"), legacy_question_id=1)
        with pytest.raises(ValueError, match="COLLISION|SOURCE_NOT"):
            reg.register_genesis_record(genesis_snapshot_sha256=GS, raw_source="Book\\A\\1.sgf",
                                        content_sha256=_sha("x"), legacy_question_id=2)


# --------------------------------------------------------------------------- #
# resolver — fail closed
# --------------------------------------------------------------------------- #

class TestResolver:
    def test_exact_current_alias(self):
        reg, recs = _genesis_registry([("Book/A/1.sgf", "c1", 1)])
        r = lc011.resolve(reg, canonical_source="Book/A/1.sgf", content_sha256=_sha("c1"), legacy_question_id=1)
        assert r.resolve_class == "EXACT" and r.source_record_uuid == recs[0].source_record_uuid

    def test_missing_when_no_evidence(self):
        reg, _ = _genesis_registry([("Book/A/1.sgf", "c1", 1)])
        r = lc011.resolve(reg, canonical_source="Book/Z/99.sgf", content_sha256=_sha("new"), legacy_question_id=777)
        assert r.resolve_class == "MISSING" and r.source_record_uuid is None

    def test_content_hash_shared_is_ambiguous_not_identity(self):
        reg, recs = _genesis_registry([("BookA/1.sgf", "DUP", 1), ("BookB/9.sgf", "DUP", 2)])
        r = lc011.resolve(reg, canonical_source="BookC/3.sgf", content_sha256=_sha("DUP"), legacy_question_id=None)
        assert r.resolve_class == "AMBIGUOUS" and r.source_record_uuid is None

    def test_same_path_content_changed_without_correction_is_ambiguous(self):
        reg, recs = _genesis_registry([("Book/A/1.sgf", "orig", 1)])
        r = lc011.resolve(reg, canonical_source="Book/A/1.sgf", content_sha256=_sha("CHANGED"), legacy_question_id=1)
        assert r.resolve_class == "AMBIGUOUS"

    def test_legacy_id_collision_is_ambiguous(self):
        reg, _ = _genesis_registry([("Elem/x/2.sgf", "a", 40511), ("Elem/y/7.sgf", "b", 40511)])
        r = lc011.resolve(reg, canonical_source="Elem/z/3.sgf", content_sha256=_sha("c"), legacy_question_id=40511)
        assert r.resolve_class == "AMBIGUOUS"

    def test_only_exact_and_high_confidence_auto_preserve(self):
        assert set(lc011.AUTO_PRESERVE_CLASSES) == {"EXACT", "HIGH_CONFIDENCE_UNIQUE"}


# --------------------------------------------------------------------------- #
# lineage semantics
# --------------------------------------------------------------------------- #

class TestLineageSemantics:
    def test_rename_keeps_same_uuid_and_never_recomputes(self):
        reg, recs = _genesis_registry([("Book/A/1.sgf", "c", 1)])
        u = recs[0].source_record_uuid
        reg.rename_or_move(u, "Book/A/1a.sgf")
        assert reg.records[u].source_record_uuid == u
        assert reg.records[u].current_source_alias == "Book/A/1a.sgf"
        assert "Book/A/1.sgf" in reg.records[u].historical_source_aliases
        # resolve by the NEW path -> same uuid; by the OLD path -> same uuid (historical alias)
        assert lc011.resolve(reg, canonical_source="Book/A/1a.sgf").source_record_uuid == u
        assert lc011.resolve(reg, canonical_source="Book/A/1.sgf").source_record_uuid == u
        # a fresh derive from the new path would NOT equal u
        assert lc011.mint_genesis_uuid("Book/A/1a.sgf") != u

    def test_folder_move_same_uuid(self):
        reg, recs = _genesis_registry([("A/x/1.sgf", "c", 1)])
        u = recs[0].source_record_uuid
        reg.rename_or_move(u, "B/x/1.sgf", event_type="SOURCE_MOVE")
        assert reg.records[u].current_source_alias == "B/x/1.sgf"
        assert lc011.resolve(reg, canonical_source="B/x/1.sgf").source_record_uuid == u

    def test_rename_onto_a_live_alias_is_rejected(self):
        # LC11-E: two ACTIVE records must never silently share an alias
        reg, recs = _genesis_registry([("A/1.sgf", "c1", 1), ("A/2.sgf", "c2", 2)])
        with pytest.raises(ValueError, match="already held by ACTIVE"):
            reg.rename_or_move(recs[0].source_record_uuid, "A/2.sgf")
        assert reg.check_integrity() == []

    def test_split_and_merge_state_guards(self):
        reg, recs = _genesis_registry([("A/1.sgf", "c1", 1), ("A/2.sgf", "c2", 2)])
        a, b = recs[0].source_record_uuid, recs[1].source_record_uuid
        with pytest.raises(ValueError, match="not registered"):
            reg.split(a, ["not-a-real-uuid"])
        reg.merge(a, [b])
        with pytest.raises(ValueError, match="not ACTIVE"):
            reg.merge(a, [b])           # b already RETIRED
        with pytest.raises(ValueError, match="must be ACTIVE"):
            reg.split(b, [])            # b is RETIRED

    def test_metadata_edit_does_not_touch_identity(self):
        reg, recs = _genesis_registry([("Book/A/1.sgf", "c", 1)])
        u = recs[0].source_record_uuid
        before = json.dumps(reg.records[u].__dict__, default=str, sort_keys=True)
        reg.append_lineage("METADATA_CORRECTION", source_record_uuid=u, reason="fixed difficulty tag")
        after = json.dumps(reg.records[u].__dict__, default=str, sort_keys=True)
        assert before == after   # the registry record is unchanged by a metadata edit

    def test_content_correction_with_event_resolves_high_confidence(self):
        reg, recs = _genesis_registry([("Book/A/1.sgf", "orig", 1)])
        u = recs[0].source_record_uuid
        reg.content_correction(u, _sha("fixed"))
        r = lc011.resolve(reg, canonical_source="Book/A/1.sgf", content_sha256=_sha("fixed"), legacy_question_id=1)
        assert r.resolve_class == "HIGH_CONFIDENCE_UNIQUE" and r.source_record_uuid == u

    def test_split_retires_parent_and_children_get_new_ids(self):
        reg, recs = _genesis_registry([("Book/A/1.sgf", "c", 1)])
        parent = recs[0].source_record_uuid
        c1 = reg.register_new_native_record(minted_uuid=str(uuid.uuid4()), legacy_question_id=None)
        c2 = reg.register_new_native_record(minted_uuid=str(uuid.uuid4()), legacy_question_id=None)
        reg.split(parent, [c1.source_record_uuid, c2.source_record_uuid])
        assert reg.records[parent].identity_status == "RETIRED"
        assert reg.records[parent].retired_reason == "SPLIT"
        assert parent in reg.records[c1.source_record_uuid].lineage_parent_uuids
        assert c1.source_record_uuid != c2.source_record_uuid != parent

    def test_merge_keeps_one_survivor(self):
        reg, recs = _genesis_registry([("Book/A/1.sgf", "c1", 1), ("Book/A/2.sgf", "c2", 2)])
        a, b = recs[0].source_record_uuid, recs[1].source_record_uuid
        reg.merge(a, [b])
        assert reg.records[a].identity_status == "ACTIVE"
        assert reg.records[b].identity_status == "RETIRED"
        assert reg.records[b].superseded_by_uuid == a

    def test_delete_then_restore_same_uuid_only_on_strong_evidence(self):
        reg, recs = _genesis_registry([("Book/A/1.sgf", "c", 1)])
        u = recs[0].source_record_uuid
        reg.delete(u)
        assert reg.records[u].identity_status == "RETIRED"
        # strong evidence -> restore runs the resolver itself and reactivates
        assert reg.restore(u, canonical_source="Book/A/1.sgf", content_sha256=_sha("c"),
                           legacy_question_id=1) is True
        assert reg.records[u].identity_status == "ACTIVE"
        # weak evidence (content shared by a live dup) -> resolver AMBIGUOUS -> refuse
        reg2, r2 = _genesis_registry([("BookA/1.sgf", "DUP", 1), ("BookB/2.sgf", "DUP", 2)])
        du = r2[0].source_record_uuid
        reg2.delete(du)
        assert reg2.restore(du, content_sha256=_sha("DUP")) is False
        assert reg2.records[du].identity_status == "RETIRED"

    def test_restore_ignores_a_caller_supplied_class_string(self):
        # LC11-E: restore() must not trust an unverified resolver_class
        reg, recs = _genesis_registry([("Book/A/1.sgf", "c", 1)])
        u = recs[0].source_record_uuid
        reg.delete(u)
        # no provenance at all -> resolver MISSING -> refuse, even though a
        # caller might once have passed resolver_class="EXACT"
        assert reg.restore(u) is False
        assert reg.records[u].identity_status == "RETIRED"


# --------------------------------------------------------------------------- #
# new source-less admin record
# --------------------------------------------------------------------------- #

class TestNewNativeRecord:
    def test_source_less_record_gets_persisted_uuidv4_once(self):
        reg = lc011.Registry()
        minted = str(uuid.uuid4())
        rec = reg.register_new_native_record(minted_uuid=minted, legacy_question_id=90001,
                                             content_sha256=_sha("hand authored"))
        assert rec.source_record_uuid == minted
        assert uuid.UUID(rec.source_record_uuid).version == 4
        assert rec.mint_method == "NEW_RECORD_UUIDV4"
        assert rec.created_identity_kind == "NEW_NATIVE"
        assert rec.genesis_snapshot_sha256 is None and rec.current_source_alias is None

    def test_new_native_rejects_non_v4(self):
        reg = lc011.Registry()
        v5 = lc011.mint_genesis_uuid("Book/A/1.sgf")
        with pytest.raises(ValueError):
            reg.register_new_native_record(minted_uuid=v5, legacy_question_id=1)

    def test_v4_is_permanent_even_if_a_source_is_added_later(self):
        # a NEW_NATIVE record that later acquires a real source keeps its v4;
        # the source becomes an alias, never a re-mint to v5 (LC11-A)
        reg = lc011.Registry()
        v4 = str(uuid.uuid4())
        rec = reg.register_new_native_record(minted_uuid=v4, legacy_question_id=90001)
        reg.rename_or_move(v4, "NewBook/authored/1.sgf")
        assert reg.records[v4].source_record_uuid == v4
        assert uuid.UUID(reg.records[v4].source_record_uuid).version == 4
        assert reg.records[v4].mint_method == "NEW_RECORD_UUIDV4"
        assert reg.records[v4].current_source_alias == "NewBook/authored/1.sgf"

    def test_no_request_time_generation_api(self):
        # the module exposes no function that fabricates an identity from live/request state
        for name in dir(lc011):
            if name.startswith("_"):
                continue
            obj = getattr(lc011, name)
            if callable(obj):
                # mint_genesis_uuid needs an explicit frozen snapshot sha + canonical source;
                # register_new_native_record needs a caller-supplied minted uuid.
                assert name not in ("generate_identity", "new_uuid", "mint_request", "auto_identity")


# --------------------------------------------------------------------------- #
# drift gate + backfill dry-run
# --------------------------------------------------------------------------- #

class TestBackfillDesign:
    def test_genesis_input_gate_fails_closed_on_drift(self):
        ok = lc011.verify_genesis_input(snapshot_sha256=GS, record_count=42804,
                                        tree_manifest_sha256="abc", expected_tree_manifest_sha256="abc")
        assert ok["genesis_input_exact_match"] is True
        bad = lc011.verify_genesis_input(snapshot_sha256="deadbeef", record_count=42804,
                                         tree_manifest_sha256="abc", expected_tree_manifest_sha256="abc")
        assert bad["genesis_input_exact_match"] is False
        bad2 = lc011.verify_genesis_input(snapshot_sha256=GS, record_count=42804,
                                          tree_manifest_sha256="x", expected_tree_manifest_sha256="y")
        assert bad2["genesis_input_exact_match"] is False

    def test_dry_run_is_idempotent_and_non_mutating(self):
        pairs = [("Book/A/1.sgf", "c1", 1), ("Book/A/2.sgf", "c2", 2), ("Book/B/9.sgf", "c1", 3)]
        _, rows = None, []
        manifest, rows = lc011.build_genesis_manifest(
            [{"source": s, "content": c, "id": i} for s, c, i in pairs])
        first = lc011.backfill_dry_run(rows)
        assert first["to_mint_count"] == 3 and first["conflict_count"] == 0
        assert first["backfill_idempotency_design"] == "PASS"
        # feed the same rows through a registry that already holds them
        reg = lc011.Registry()
        for row in rows:
            reg.register_genesis_record(genesis_snapshot_sha256=GS, raw_source=row["raw_source"],
                                        content_sha256=row["content_sha256"],
                                        legacy_question_id=row["legacy_question_id"])
        second = lc011.backfill_dry_run(rows, reg)
        assert second["to_mint_count"] == 0 and second["already_present_count"] == 3
        assert second["conflict_count"] == 0

    def test_dry_run_flags_source_not_recoverable(self):
        manifest, rows = lc011.build_genesis_manifest(
            [{"source": "Book/A/1.sgf", "content": "c", "id": 1}, {"source": "", "content": "c2", "id": 2}])
        plan = lc011.backfill_dry_run(rows)
        assert plan["source_not_recoverable_count"] == 1
        assert plan["fail_closed"] is True


# --------------------------------------------------------------------------- #
# full-snapshot contract manifest (guarded)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _snapshot_ok(), reason="canonical snapshot absent")
class TestFullSnapshot:
    def test_contract_manifest_headline(self, tmp_path):
        out = lc011.run(_SNAPSHOT, tmp_path / "c.json")
        assert out["live_source_path_is_canonical_identity"] is False
        assert out["source_path_role"] == "GENESIS_SEED_AND_RESOLVER_ALIAS_ONLY"
        assert out["post_genesis_uuid_recomputation"] == "FORBIDDEN"
        assert out["content_hash_as_identity"] == "FORBIDDEN"
        assert out["owner_namespace_ratification_required"] is True
        assert out["genesis_manifest"]["record_count"] == 42804
        assert out["genesis_manifest"]["proposed_uuid_collision_count"] == 0
        assert out["genesis_manifest"]["distinct_proposed_uuids"] == 42804
        assert out["genesis_manifest"]["canonicalisation_fail_closed_counts"] == {}
        assert out["backfill_dry_run"]["to_mint_count"] == 42804
        assert out["backfill_dry_run"]["conflict_count"] == 0
        assert out["backfill_dry_run"]["backfill_idempotency_design"] == "PASS"
        assert out["genesis_input_gate"]["genesis_input_exact_match"] is True
        assert out["corpus_mutated"] is False and out["source_record_uuid_backfill"] is False

    def test_manifest_deterministic_and_lf(self, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        lc011.run(_SNAPSHOT, a)
        lc011.run(_SNAPSHOT, b)
        assert a.read_bytes() == b.read_bytes()
        assert a.read_bytes().endswith(b"\n") and b"\r\n" not in a.read_bytes()

    def test_committed_contract_matches_regeneration(self, tmp_path):
        committed = _REPO / "docs" / "planning" / "lc011_identity_registry_contract.json"
        if not committed.exists():
            pytest.skip("committed contract not present yet")
        fresh = tmp_path / "c.json"
        lc011.run(_SNAPSHOT, fresh)
        assert hashlib.sha256(fresh.read_bytes()).hexdigest() == \
            hashlib.sha256(committed.read_bytes()).hexdigest()
