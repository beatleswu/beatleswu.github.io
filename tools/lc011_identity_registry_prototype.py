"""LC011 — Immutable Puzzle Identity Foundation: registry / resolver / lineage
PROTOTYPE (READ-ONLY, PROTOTYPE_ONLY, NON-MUTATING).

Turns the LC010 finding (Model D — persistent identity registry, frozen-genesis
bootstrap) into an executable contract sketch: the exact genesis-key encoding,
the canonicalisation rules, the registry record shape + field authority, the
fail-closed resolver, the append-only lineage ledger, and a NON-mutating
idempotent backfill dry-run.

It mints only HYPOTHETICAL identities in memory. It never writes a
``source_record_uuid`` to the corpus, an SGF file, a database, a runtime
record, or Production. It does not modify LC009 semantics, ``app.py``, any
schema, or ``questions.json``.

Locked design decisions (see docs/planning/lc011_immutable_puzzle_identity_foundation_adr.md):
  * LIVE_SOURCE_PATH_IS_CANONICAL_IDENTITY = NO
  * SOURCE_PATH_ROLE = GENESIS_SEED_AND_RESOLVER_ALIAS_ONLY
  * POST_GENESIS_UUID_RECOMPUTATION = FORBIDDEN
  * CONTENT_HASH_AS_IDENTITY = FORBIDDEN (resolver evidence only)
  * genesis UUID  = UUIDv5(namespace, genesis_key)         [historical external SGF]
  * new-record UUID = persisted UUIDv4, minted once        [admin-authored / source-less]
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import re
import sys
import unicodedata
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

LC011_TOOL_VERSION = "lc011-identity-registry-prototype-v1"
GENESIS_SNAPSHOT_SHA256 = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"
EXPECTED_RECORD_COUNT = 42804

# --------------------------------------------------------------------------- #
# Namespace (PROPOSED CANONICAL — OWNER_RATIFICATION_REQUIRED = YES)
# --------------------------------------------------------------------------- #
# Deterministically derived from a canonical seed string so it is reconstructible
# from this contract alone. LC11-E: the seed deliberately does NOT embed the ADR
# *document* version — only "scheme-v1", the identity-generation scheme version.
# A future INCOMPATIBLE scheme uses "scheme-v2" (a new namespace); an ADR text
# revision NEVER changes the namespace. The owner may instead ratify an opaque
# random UUIDv4 — the contract does not depend on how the namespace was made,
# only that it is frozen, owner-ratified, and asserted against every record.
_NAMESPACE_SEED = "godokoro:immutable-puzzle-identity:source-record-namespace:scheme-v1"
PROPOSED_CANONICAL_NAMESPACE_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, _NAMESPACE_SEED))
OWNER_RATIFICATION_REQUIRED = True


def assert_namespace(namespace_uuid: str) -> None:
    """LC11-E: mechanically prevent careless namespace rotation. Every genesis
    mint and every stored record MUST use the ratified constant."""
    if str(namespace_uuid) != PROPOSED_CANONICAL_NAMESPACE_UUID:
        raise ValueError(
            f"NAMESPACE_DRIFT: {namespace_uuid} != ratified {PROPOSED_CANONICAL_NAMESPACE_UUID}")

# LC010 prototype namespace — recorded so it is NEVER silently promoted.
LC010_PROTOTYPE_NAMESPACE_UUID = "892f7446-c0ca-5320-806f-798d5acc3c27"

# --------------------------------------------------------------------------- #
# Canonicalisation v1  (docs ADR §8)
# --------------------------------------------------------------------------- #
CANONICALISATION_RULES_VERSION = "canon-source-v1"
_FIELD_SEP = "\x1f"           # ASCII Unit Separator — never valid in a source path

_CANON_RULES = {
    "unicode_normalization": "NFC",          # NOT NFKC (would merge meaningful fullwidth chars)
    "path_separator": "/ (every '\\\\' -> '/')",
    "leading_separator": "stripped",
    "trailing_separator": "stripped",
    "duplicate_separator": "collapsed ('/'+ -> '/')",
    "whitespace": "whole-string leading/trailing stripped; internal preserved verbatim",
    "case_policy": "PRESERVE (source FS case-sensitivity unproven; never casefold)",
    "file_extension_policy": "the check is a LITERAL '.sgf' suffix test (no splitext / last-dot). "
                             "kept verbatim; '.SGF' -> fail closed. 327 folder segments contain '.' "
                             "(chapter prefixes / 'Vol. 2') and are preserved (LC11-A).",
    "relative_root_policy": "collection-relative; the SGF題庫 tree root is NOT in the key "
                            "(pinned separately by SGF_SOURCE_TREE_GENESIS_MANIFEST)",
    "collection_name_policy": "first path segment; preserved verbatim under the global rules",
    "reject_segments": "empty, '.', '..', or ending in ' ' or '.'  -> SOURCE_NOT_RECOVERABLE (fail closed)",
    "reject_control_chars": "any C0/C1 control, BOM, or the field separator -> SOURCE_NOT_RECOVERABLE",
}

# LC11-E: reject (not silently strip) every invisible / bidi / non-ASCII space,
# so a homograph cannot split one identity into two. 0 corpus paths contain any.
# LC11-E: reject (never silently strip) every C0/C1 control, BOM, zero-width,
# bidi-control and non-ASCII space, so a homograph cannot split one identity
# into two. 0 of the 42,804 corpus source paths contain any of these.
_INVISIBLE_CODEPOINTS = frozenset(
    list(range(0x00, 0x20)) + list(range(0x7f, 0xa0))
    + [0xa0, 0xad, 0xfeff, 0x2060, 0x200b, 0x200c, 0x200d, 0x200e, 0x200f,
       0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069,
       0x3000, 0x205f, 0x1680, 0x180e]
    + list(range(0x2000, 0x200b))            # EN QUAD .. HAIR SPACE
    + [0x2028, 0x2029]
)


def _has_invisible(s: str) -> bool:
    return any(ord(ch) in _INVISIBLE_CODEPOINTS for ch in s)


class CanonError(Enum):
    EMPTY = "empty_source"
    CONTROL = "control_or_bom_char"
    NOT_SGF = "not_a_dot_sgf_path"
    BAD_SEGMENT = "empty_dot_or_trailing_space_segment"


def canonical_source_key(raw_source: Any) -> tuple[str | None, str | None]:
    """(canonical_key, error). error is a CanonError.value on fail-closed."""
    if raw_source is None:
        return None, CanonError.EMPTY.value
    s = unicodedata.normalize("NFC", str(raw_source))
    if _has_invisible(s) or _FIELD_SEP in s:
        return None, CanonError.CONTROL.value
    s = s.replace("\\", "/").strip(" \t\r\n")     # ASCII ws only (invisibles already rejected)
    s = re.sub(r"/{2,}", "/", s).strip("/")
    if not s:
        return None, CanonError.EMPTY.value
    segments = s.split("/")
    for seg in segments:
        if seg in ("", ".", "..") or seg[-1:] in (" ", "."):
            return None, CanonError.BAD_SEGMENT.value
    if not s.endswith(".sgf") or s.endswith(".SGF"):
        return None, CanonError.NOT_SGF.value
    return s, None


# --------------------------------------------------------------------------- #
# Genesis key contract v1  (docs ADR §9 / §10 — Option C: NO snapshot SHA in the
# name; the snapshot SHA is immutable REGISTRY provenance + a once-only gate)
# --------------------------------------------------------------------------- #
GENESIS_KEY_SPEC_VERSION = "genesis-key-v1"

# LC11-A: hashing the whole-file genesis_sha256 into the UUIDv5 name (Option B)
# would make "mint exactly once" load-bearing with nothing enforcing it — an
# operator re-running the bootstrap on a refreshed questions.json would silently
# reassign all 42,804 identities. Option C keeps the name a pure function of the
# canonical source (benign rebuilds reproducible, re-imports idempotent) and
# turns "the mint was re-run" from silent reassignment into a REFUSED operation
# via GENESIS_BOOTSTRAP_ONCE_ONLY + GENESIS_INPUT_EXACT_MATCH.
GENESIS_NAME_OPTION = "C — namespace + 'sgf-source-file' + 'v1' + canonical_source (NO snapshot sha in the name)"


def genesis_key(canonical_source: str) -> str:
    """Exact deterministic UUIDv5 *name*. Fields joined with U+001F, which the
    canonicaliser forbids inside a source key, so the join is unambiguous and a
    maliciously named SGF file cannot forge another record's key."""
    if _FIELD_SEP in canonical_source:
        raise ValueError("canonical_source contains the field separator")
    return _FIELD_SEP.join(("gk1", "sgf-source-file", "v1", canonical_source))


def mint_genesis_uuid(canonical_source: str,
                      namespace_uuid: str = PROPOSED_CANONICAL_NAMESPACE_UUID) -> str:
    assert_namespace(namespace_uuid)          # LC11-E: no arbitrary namespace
    return str(uuid.uuid5(uuid.UUID(namespace_uuid), genesis_key(canonical_source)))


# --------------------------------------------------------------------------- #
# Registry record  (docs ADR §11 — field authority)
# --------------------------------------------------------------------------- #
class IdentityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    AMBIGUOUS = "AMBIGUOUS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SOURCE_MISSING = "SOURCE_MISSING"


class MintMethod(str, Enum):
    GENESIS_UUIDV5 = "GENESIS_UUIDV5"
    NEW_RECORD_UUIDV4 = "NEW_RECORD_UUIDV4"


# field -> authority class (AUTHORITY | ALIAS | AUDIT | DERIVED | OPTIONAL)
REGISTRY_FIELD_AUTHORITY = {
    "source_record_uuid": "AUTHORITY",
    "identity_status": "AUTHORITY",
    "mint_method": "AUTHORITY",
    "namespace_uuid": "AUDIT",
    "genesis_snapshot_sha256": "AUDIT",
    "genesis_key_spec_version": "AUDIT",
    "canonicalisation_rules_version": "AUDIT",
    "genesis_source_raw": "AUDIT",
    "genesis_source_canonical": "ALIAS",
    "genesis_content_sha256": "AUDIT",
    "legacy_question_id": "ALIAS",
    "current_source_alias": "ALIAS",
    "historical_source_aliases": "ALIAS",
    "source_collection": "DERIVED",
    "created_identity_kind": "DERIVED",
    "minted_batch_id": "AUDIT",
    "minted_at": "AUDIT",
    "minted_by": "AUDIT",
    "lineage_parent_uuids": "AUDIT",
    "superseded_by_uuid": "AUDIT",
    "retired_reason": "AUDIT",
    "review_note": "OPTIONAL",
}


@dataclasses.dataclass
class RegistryRecord:
    source_record_uuid: str
    identity_status: str
    mint_method: str
    created_identity_kind: str                 # HISTORICAL_EXTERNAL_SGF | NEW_NATIVE
    legacy_question_id: Any = None
    namespace_uuid: str | None = None
    genesis_snapshot_sha256: str | None = None
    genesis_key_spec_version: str | None = None
    canonicalisation_rules_version: str | None = None
    genesis_source_raw: str | None = None
    genesis_source_canonical: str | None = None
    genesis_content_sha256: str | None = None
    current_source_alias: str | None = None
    historical_source_aliases: list[str] = dataclasses.field(default_factory=list)
    lineage_parent_uuids: list[str] = dataclasses.field(default_factory=list)
    superseded_by_uuid: str | None = None
    retired_reason: str | None = None
    minted_batch_id: str | None = None

    @property
    def source_collection(self) -> str | None:
        a = self.current_source_alias or self.genesis_source_canonical
        return a.split("/", 1)[0] if a else None


class Registry:
    """In-memory PROTOTYPE registry. Insert-only for identities; lineage is a
    separate append-only log. Post-genesis UUIDs are NEVER recomputed."""

    def __init__(self) -> None:
        self.records: dict[str, RegistryRecord] = {}
        self.lineage: list[dict[str, Any]] = []
        self._seq = 0
        # GENESIS_BOOTSTRAP_ONCE_ONLY — records the (corpus_id, snapshot sha) the
        # single genesis bootstrap ran against. A second genesis mint against a
        # different snapshot is REFUSED (LC11-A).
        self.genesis_provenance: dict[str, Any] | None = None

    # -- minting ------------------------------------------------------------ #
    def begin_genesis_bootstrap(self, *, corpus_id: str, genesis_snapshot_sha256: str) -> None:
        if self.genesis_provenance is not None:
            p = self.genesis_provenance
            if (p["corpus_id"], p["genesis_snapshot_sha256"]) != (corpus_id, genesis_snapshot_sha256):
                raise ValueError("GENESIS_BOOTSTRAP_ALREADY_DONE for a different corpus/snapshot — REFUSED")
            return  # idempotent re-entry for the identical bootstrap
        if any(r.mint_method == MintMethod.GENESIS_UUIDV5.value for r in self.records.values()):
            raise ValueError("registry already holds genesis rows — second bootstrap REFUSED")
        self.genesis_provenance = {"corpus_id": corpus_id,
                                   "genesis_snapshot_sha256": genesis_snapshot_sha256.strip().lower()}

    def register_genesis_record(self, *, genesis_snapshot_sha256: str, raw_source: str,
                                content_sha256: str, legacy_question_id: Any,
                                namespace_uuid: str = PROPOSED_CANONICAL_NAMESPACE_UUID,
                                batch_id: str = "prototype", corpus_id: str = "godokoro-canonical") -> RegistryRecord:
        self.begin_genesis_bootstrap(corpus_id=corpus_id, genesis_snapshot_sha256=genesis_snapshot_sha256)
        canon, err = canonical_source_key(raw_source)
        if err:
            raise ValueError(f"SOURCE_NOT_RECOVERABLE: {err}")
        u = mint_genesis_uuid(canon, namespace_uuid)
        if u in self.records:
            raise ValueError(f"GENESIS_UUID_COLLISION on {u}")
        rec = RegistryRecord(
            source_record_uuid=u, identity_status=IdentityStatus.ACTIVE.value,
            mint_method=MintMethod.GENESIS_UUIDV5.value,
            created_identity_kind="HISTORICAL_EXTERNAL_SGF",
            legacy_question_id=legacy_question_id, namespace_uuid=namespace_uuid,
            genesis_snapshot_sha256=genesis_snapshot_sha256,
            genesis_key_spec_version=GENESIS_KEY_SPEC_VERSION,
            canonicalisation_rules_version=CANONICALISATION_RULES_VERSION,
            genesis_source_raw=raw_source, genesis_source_canonical=canon,
            genesis_content_sha256=content_sha256, current_source_alias=canon,
            minted_batch_id=batch_id,
        )
        self.records[u] = rec
        return rec

    def register_new_native_record(self, *, minted_uuid: str, legacy_question_id: Any,
                                   content_sha256: str | None = None,
                                   batch_id: str = "prototype") -> RegistryRecord:
        """The authoring flow mints ONE random UUIDv4 at authoritative creation
        and passes it here. Never recomputed, never request-time regenerated."""
        parsed = uuid.UUID(minted_uuid)
        if parsed.version != 4:
            raise ValueError("new-native identity must be a random UUIDv4")
        if minted_uuid in self.records:
            raise ValueError("duplicate new-native uuid")
        rec = RegistryRecord(
            source_record_uuid=minted_uuid, identity_status=IdentityStatus.ACTIVE.value,
            mint_method=MintMethod.NEW_RECORD_UUIDV4.value,
            created_identity_kind="NEW_NATIVE", legacy_question_id=legacy_question_id,
            genesis_content_sha256=content_sha256, current_source_alias=None,
            minted_batch_id=batch_id,
        )
        self.records[minted_uuid] = rec
        return rec

    # -- lineage ---------------------------------------------------------- #
    def append_lineage(self, event_type: str, *, source_record_uuid: str | None = None,
                       old_provenance: dict | None = None, new_provenance: dict | None = None,
                       reason: str = "", evidence: dict | None = None,
                       authority: str = "RESOLVER_AUTO", parent_uuids: list[str] | None = None,
                       child_uuids: list[str] | None = None, occurred_at: str | None = None) -> dict:
        self._seq += 1
        ev = {
            "sequence": self._seq, "event_type": event_type,
            "source_record_uuid": source_record_uuid,
            "parent_uuids": parent_uuids or [], "child_uuids": child_uuids or [],
            "old_provenance": old_provenance or {}, "new_provenance": new_provenance or {},
            "reason": reason, "evidence": evidence or {}, "authority": authority,
            "occurred_at": occurred_at,
        }
        self.lineage.append(ev)
        return ev

    def check_integrity(self) -> list[str]:
        """LC11-E: no two ACTIVE records may claim the same current alias."""
        seen: dict[str, str] = {}
        problems = []
        for uu, r in self.records.items():
            if r.identity_status != IdentityStatus.ACTIVE.value or not r.current_source_alias:
                continue
            if r.current_source_alias in seen:
                problems.append(f"alias {r.current_source_alias!r} claimed by {seen[r.current_source_alias]} and {uu}")
            seen[r.current_source_alias] = uu
        return problems

    def rename_or_move(self, u: str, new_canonical_source: str, *, event_type: str = "SOURCE_RENAME",
                       authority: str = "OWNER_REVIEW", occurred_at: str | None = None) -> None:
        """SAME UUID. Update the alias; keep the old one as a historical alias.
        The UUID is NEVER recomputed from the new path."""
        rec = self.records[u]
        if rec.identity_status != IdentityStatus.ACTIVE.value:
            raise ValueError("cannot rename a non-ACTIVE identity")
        clash = [x for x, rr in self.records.items()
                 if x != u and rr.identity_status == IdentityStatus.ACTIVE.value
                 and rr.current_source_alias == new_canonical_source]
        if clash:
            raise ValueError(f"alias {new_canonical_source!r} already held by ACTIVE {clash[0]}")
        old = rec.current_source_alias
        if old and old not in rec.historical_source_aliases:
            rec.historical_source_aliases.append(old)
        rec.current_source_alias = new_canonical_source
        self.append_lineage(event_type, source_record_uuid=u,
                            old_provenance={"canonical_source": old},
                            new_provenance={"canonical_source": new_canonical_source},
                            reason="curator rename/move", authority=authority, occurred_at=occurred_at)

    def content_correction(self, u: str, new_content_sha256: str, *, authority: str = "OWNER_REVIEW",
                           occurred_at: str | None = None) -> None:
        """SAME UUID iff the curator attests the source ENTITY is unchanged."""
        rec = self.records[u]
        self.append_lineage("CONTENT_CORRECTION", source_record_uuid=u,
                            old_provenance={"content_sha256": rec.genesis_content_sha256},
                            new_provenance={"content_sha256": new_content_sha256},
                            reason="attested content fix, same source entity", authority=authority,
                            occurred_at=occurred_at)

    def delete(self, u: str, *, occurred_at: str | None = None) -> None:
        self.records[u].identity_status = IdentityStatus.RETIRED.value
        self.records[u].retired_reason = "DELETED"
        self.append_lineage("DELETE", source_record_uuid=u, reason="record deleted",
                            authority="ADMIN", occurred_at=occurred_at)

    def restore(self, u: str, *, canonical_source: str | None = None, content_sha256: str | None = None,
                legacy_question_id: Any = None, occurred_at: str | None = None) -> bool:
        """LC11-E: the resolver is run HERE against real provenance — no
        caller-supplied class string is trusted. Reactivate the SAME UUID only
        when the resolver returns EXACT / HIGH_CONFIDENCE_UNIQUE AND it points
        at this exact uuid."""
        if self.records[u].identity_status != IdentityStatus.RETIRED.value:
            raise ValueError("can only restore a RETIRED identity")
        rr = resolve(self, canonical_source=canonical_source, content_sha256=content_sha256,
                     legacy_question_id=legacy_question_id)
        if rr.resolve_class not in AUTO_PRESERVE_CLASSES or rr.source_record_uuid != u:
            return False
        self.records[u].identity_status = IdentityStatus.ACTIVE.value
        self.records[u].retired_reason = None
        self.append_lineage("RESTORE", source_record_uuid=u, reason="restored on strong resolver evidence",
                            evidence={"resolver_class": rr.resolve_class, "matched_on": rr.matched_on},
                            authority="OWNER_REVIEW", occurred_at=occurred_at)
        return True

    def split(self, parent_u: str, child_uuids: list[str], *, occurred_at: str | None = None) -> None:
        if self.records[parent_u].identity_status != IdentityStatus.ACTIVE.value:
            raise ValueError("split subject must be ACTIVE")
        missing = [c for c in child_uuids if c not in self.records]
        if missing:
            raise ValueError(f"split children not registered: {missing}")
        self.records[parent_u].identity_status = IdentityStatus.RETIRED.value
        self.records[parent_u].retired_reason = "SPLIT"
        for c in child_uuids:
            self.records[c].lineage_parent_uuids.append(parent_u)
        self.append_lineage("SOURCE_SPLIT", source_record_uuid=parent_u, child_uuids=child_uuids,
                            reason="one source record became several", authority="OWNER_REVIEW",
                            occurred_at=occurred_at)

    def merge(self, survivor_u: str, retired_uuids: list[str], *, occurred_at: str | None = None) -> None:
        if self.records[survivor_u].identity_status != IdentityStatus.ACTIVE.value:
            raise ValueError("merge survivor must be ACTIVE")
        for r in retired_uuids:
            if r not in self.records:
                raise ValueError(f"merge input not registered: {r}")
            if self.records[r].identity_status != IdentityStatus.ACTIVE.value:
                raise ValueError(f"merge input {r} is not ACTIVE")
            self.records[r].identity_status = IdentityStatus.RETIRED.value
            self.records[r].retired_reason = "MERGED"
            self.records[r].superseded_by_uuid = survivor_u
        self.append_lineage("SOURCE_MERGE", source_record_uuid=survivor_u, parent_uuids=retired_uuids,
                            reason="several source records became one", authority="OWNER_REVIEW",
                            occurred_at=occurred_at)


# --------------------------------------------------------------------------- #
# Resolver  (docs ADR §13 / §14 — fail closed; content hash is evidence only)
# --------------------------------------------------------------------------- #
class ResolveClass(str, Enum):
    EXACT = "EXACT"
    HIGH_CONFIDENCE_UNIQUE = "HIGH_CONFIDENCE_UNIQUE"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"
    COLLISION = "COLLISION"


# only these auto-preserve identity; everything else is fail-closed / mint-new
AUTO_PRESERVE_CLASSES = (ResolveClass.EXACT.value, ResolveClass.HIGH_CONFIDENCE_UNIQUE.value)

# --------------------------------------------------------------------------- #
# Static contract data (docs ADR §13, §15, §16–§22, §27)
# --------------------------------------------------------------------------- #
RESOLVER_PRIORITY_LADDER = [
    {"rank": 1.0, "evidence": "incoming canonical_source == a record's current OR historical alias (exactly 1 ACTIVE) "
     "AND incoming content matches genesis_content_sha256 (or no content supplied)",
     "result": "EXACT", "auto_preserve": True},
    {"rank": 1.1, "evidence": "same alias match, content CHANGED, a CONTENT_CORRECTION lineage event exists for it",
     "result": "HIGH_CONFIDENCE_UNIQUE", "auto_preserve": True},
    {"rank": 1.2, "evidence": "same alias match, content CHANGED, NO correction event",
     "result": "AMBIGUOUS", "auto_preserve": False,
     "note": "content-correction vs 'different puzzle at same filename' — human decides"},
    {"rank": 1.9, "evidence": ">1 ACTIVE record claims that alias",
     "result": "COLLISION", "auto_preserve": False, "note": "registry integrity error — fail closed, human"},
    {"rank": 2.0, "evidence": "genesis_source_canonical AND genesis_content_sha256 both match (exactly 1; retired incl. -> restore)",
     "result": "EXACT", "auto_preserve": True},
    {"rank": 3.0, "evidence": "content_sha256 matches exactly 1 ACTIVE record, no path relationship",
     "result": "HIGH_CONFIDENCE_UNIQUE", "auto_preserve": True},
    {"rank": 3.1, "evidence": "content_sha256 shared by >1 ACTIVE record (the 404 duplicate groups)",
     "result": "AMBIGUOUS", "auto_preserve": False, "note": "CONTENT_HASH_AS_IDENTITY = FORBIDDEN (ADR §14)"},
    {"rank": 4.0, "evidence": "legacy_question_id maps to exactly 1 ACTIVE record",
     "result": "HIGH_CONFIDENCE_UNIQUE", "auto_preserve": True},
    {"rank": 4.1, "evidence": "legacy_question_id maps to >1 ACTIVE record (the 11 collision groups)",
     "result": "AMBIGUOUS", "auto_preserve": False},
    {"rank": 9.0, "evidence": "no evidence matches", "result": "MISSING", "auto_preserve": False,
     "note": "mint a NEW identity — correct for a genuinely new source file"},
]

LINEAGE_EVENT_TYPES = [
    "SOURCE_RENAME", "SOURCE_MOVE", "SOURCE_COLLECTION_RENAME", "SOURCE_CASE_ONLY_RENAME",
    "CANONICALISATION_RULE_CHANGE", "CONTENT_CORRECTION", "METADATA_CORRECTION",
    "DELETE", "RESTORE", "SOURCE_SPLIT", "SOURCE_MERGE", "SOURCE_REPLACED",
    "MANUAL_IDENTITY_RECONCILIATION",
]
LINEAGE_EVENT_FIELDS = {
    "sequence": "AUTHORITY (monotonic per registry; ordering, not wall-clock)",
    "event_type": "AUTHORITY (one of LINEAGE_EVENT_TYPES)",
    "source_record_uuid": "AUTHORITY (subject identity; null for split/merge which use parent/child)",
    "parent_uuids": "AUDIT (split parent / merge retired)",
    "child_uuids": "AUDIT (split children)",
    "old_provenance": "AUDIT ({canonical_source?, content_sha256?})",
    "new_provenance": "AUDIT ({canonical_source?, content_sha256?})",
    "reason": "AUDIT (free text)",
    "evidence": "AUDIT ({resolver_class, corroborating_fields})",
    "authority": "AUTHORITY (RESOLVER_AUTO | OWNER_REVIEW | ADMIN)",
    "occurred_at": "OPTIONAL (caller-supplied ISO string; never generated in tooling)",
}

SEMANTICS = {
    "rename_only": {"same_uuid": True, "how": "registry rename_or_move; old path -> historical_source_aliases; UUID never recomputed"},
    "folder_move": {"same_uuid": True, "how": "same as rename (SOURCE_MOVE event)"},
    "collection_rename": {"same_uuid": True, "how": "SOURCE_COLLECTION_RENAME event; every affected record's alias rewritten; UUIDs unchanged"},
    "case_only_rename": {"same_uuid": True, "how": "SOURCE_CASE_ONLY_RENAME event; case is preserved in the alias, UUID unchanged"},
    "canonicalisation_rule_change": {"same_uuid": True, "how": "CANONICALISATION_RULE_CHANGE event; a new canon-source-vN; genesis UUIDs are NEVER re-minted — the registry maps old canonical key -> uuid"},
    "content_correction_same_entity": {"same_uuid": True, "how": "CONTENT_CORRECTION event attested by OWNER_REVIEW; resolver rank 4"},
    "different_puzzle_same_filename": {"same_uuid": False, "how": "SOURCE_REPLACED event; old identity RETIRED or moved; new file gets a MISSING -> new mint; resolver fails closed (AMBIGUOUS) without an explicit event"},
    "split_one_to_many": {"same_uuid": False, "how": "parent RETIRED (reason SPLIT); each child gets a fresh identity; parent kept for audit; child.lineage_parent_uuids = [parent]"},
    "merge_many_to_one": {"same_uuid": False, "how": "one survivor kept; others RETIRED with superseded_by_uuid = survivor; all histories preserved"},
    "delete_then_restore": {"same_uuid": "only on EXACT / HIGH_CONFIDENCE_UNIQUE", "how": "DELETE -> RETIRED; RESTORE reactivates the SAME uuid only if the resolver returns EXACT/HIGH_CONFIDENCE; weak evidence -> new mint; never a request-time fresh UUID"},
    "reimport_identical_frozen_corpus": {"same_uuid": True, "how": "genesis key = f(canonical_source) re-derives identically (Option C); the GENESIS_BOOTSTRAP_ONCE_ONLY gate then refuses a second write — the re-derive is for audit/recovery only"},
    "reimport_under_new_snapshot_sha": {"same_uuid": True, "how": "a second genesis bootstrap is REFUSED by the once-only gate; the new corpus's records go through the resolver (current alias / genesis source+content) -> same uuid for the same entity, MANUAL_IDENTITY_RECONCILIATION for anything ambiguous, a new mint only for a genuinely new file"},
}

NEW_RECORD_IDENTITY_POLICY = {
    "policy": "REGISTRY_MINTED_PERSISTED_UUIDV4",
    "when": "at authoritative creation of a hand-authored canonical question (source == '')",
    "mechanism": "the authoring flow mints ONE random UUIDv4, writes it to the registry "
                 "(mint_method=NEW_RECORD_UUIDV4, created_identity_kind=NEW_NATIVE, genesis_*=null) "
                 "and persists it on the record. Never recomputed. Never request-time regenerated.",
    "rejected_alternative": "UUIDv5(author + counter + content_sha256) — none of those is a stable "
                            "SOURCE ENTITY (author can be wrong, counter is an allocation-order = record_index "
                            "analog, content can change).",
    "hybrid_note": "historical external-SGF records use UUIDv5 genesis; new native records use UUIDv4. "
                   "Both obey one registry contract: mint once, persist, never recompute, resolver+lineage "
                   "carry forward. A consumer must treat the UUID as opaque and MUST NOT branch on uuid.version.",
    "v4_to_v5_upgrade_forbidden": "if a NEW_NATIVE record later acquires a real `source`, the source becomes "
                                  "a current_source_alias — it NEVER triggers a re-mint to a v5. The v4 is permanent.",
    "new_native_storage_requirement": "a v4 exists only in the registry (unlike a v5, which is recomputable), so "
                                      "the identity registry + lineage MUST be append-only and replicated storage.",
}

LIFECYCLE_STATES = {
    "ACTIVE": "well-formed identity in use; the ONLY state runtime may consume as canonical identity",
    "RETIRED": "deleted / split-parent / merge-loser; audit only; runtime treats as canonical_identity_missing",
    "AMBIGUOUS": "resolver could not uniquely resolve; runtime MUST fall back to compatibility mode",
    "NEEDS_REVIEW": "queued for MANUAL_IDENTITY_RECONCILIATION; not consumable as identity",
    "SOURCE_MISSING": "source file absent (delete pending restore); identity preserved; runtime = compatibility mode",
}

RUNTIME_CONTRACT = {
    "consumes": "source_record_uuid from the canonical persisted read-model, identity_status == ACTIVE only",
    "must_not": ["recompute identity (no canonicalise-at-runtime)", "inspect a filesystem path to mint identity",
                 "generate a request-time UUID", "fall back to content_sha256 as identity"],
    "migration_fallback": "if source_record_uuid absent -> use legacy_question_id as a LABELLED non-canonical "
                          "compatibility key and emit canonical_identity_missing=true "
                          "(mirrors the LC003/LC004 canonical_puzzle_id=null / invalid_identity=true pattern)",
}

DUAL_ID_WINDOW = {
    "write_authority": "the offline genesis backfill + the future authoring flow are the ONLY writers of "
                       "source_record_uuid; nothing at request time",
    "read_authority": "the canonical read-model; source_record_uuid preferred, legacy_question_id as a labelled alias",
    "api_serialization": "emit both source_record_uuid (or null) and question_id; question_id is non-unique",
    "logging": "log source_record_uuid where present, else legacy_question_id + canonical_identity_missing=true",
    "admin_tools": "key edits by source_record_uuid where present; the 11 legacy-collision groups are editable "
                   "ONLY via source_record_uuid or the (record_index, legacy_question_id) audit locator",
    "test_fixtures": "may carry a clearly-fake PROTOTYPE_ONLY source_record_uuid or none",
}

BACKFILL_ALGORITHM_DESIGN = {
    "step_1_input_validation": "sha256(questions.json) == GENESIS_SNAPSHOT_SHA256 exactly; record_count == 42804; "
                               "the live SGF tree reproduces SGF_SOURCE_TREE_GENESIS_MANIFEST exactly "
                               "(GENESIS_INPUT_EXACT_MATCH). Any mismatch -> STOP, mint nothing.",
    "step_2_manifest_build": "canonicalise every source; fail closed on any SOURCE_NOT_RECOVERABLE; mint the "
                             "genesis UUID for each; assert 42804 distinct UUIDs (collision detection) -> abort on collision.",
    "step_3_existing_uuid_detection": "for each record consult the registry via the resolver; EXACT match to the "
                                      "proposed UUID -> skip (idempotent); a DIFFERENT existing uuid -> STOP (drift), human.",
    "step_4_dry_run": "emit the full plan (N to mint / 0 to change / M already present) with per-record before/after; NO writes.",
    "step_5_apply": "OWNER-GATED, separate step (NOT LC011): insert-only into the registry; write source_record_uuid "
                    "into a NEW canonical read-model (NOT questions.json — that stays the frozen genesis input); "
                    "append a GENESIS lineage marker per record.",
    "step_6_idempotent_rerun": "same frozen input -> step 3 finds all present -> 0 mint, 0 change.",
    "step_7_rollback_recovery": "registry is additive/insert-only; rollback = drop the read-model overlay; rows "
                                "from a failed run are identifiable by minted_batch_id and are TOMBSTONED "
                                "(never hard-deleted) by an owner-gated recovery step.",
    "owner_gate": "OWNER_IDENTITY_FOUNDATION_APPROVAL_REQUIRED = YES — no mint begins until the owner ratifies "
                  "the identity model, namespace, canonicalisation ADR, genesis key spec, registry contract, "
                  "new-record policy, and the SGF source-tree freeze artifact.",
}

SGF_SOURCE_TREE_GENESIS_MANIFEST_CONTRACT = {
    "purpose": "pin the external SGF題庫 tree so a genesis backfill is reproducible and drift is detectable",
    "per_file": ["relative_path (collection-relative, pre-canonicalisation raw)", "content_sha256 (SGF bytes on disk)",
                 "collection (first path segment)"],
    "tree_level": ["file_count (must == 42804)", "tree_manifest_sha256 (sha256 of the canonically-sorted manifest body)"],
    "storage": "checked into the repo as a path+hash list (a few MB) OR a hashed/compressed form; the raw SGF "
               "corpus is NOT copied into the repo unless separately authorized",
    "gate": "the backfill refuses to run unless the live tree reproduces this manifest exactly",
    "status": "CONTRACT ONLY — LC011 cannot BUILD it (the SGF tree is external / not present); producing it is a "
              "gated prerequisite step before any backfill",
}


@dataclasses.dataclass
class ResolveResult:
    resolve_class: str
    source_record_uuid: str | None
    matched_on: str
    candidates: list[str] = dataclasses.field(default_factory=list)


def resolve(registry: Registry, *, canonical_source: str | None, content_sha256: str | None = None,
            legacy_question_id: Any = None) -> ResolveResult:
    """Deterministic, fail-closed. Only EXACT and HIGH_CONFIDENCE_UNIQUE auto-
    preserve identity; AMBIGUOUS / MISSING / COLLISION never auto-assign.
    content_sha256 is EVIDENCE, never sole identity (ADR §14)."""
    recs = registry.records
    active = {u: r for u, r in recs.items() if r.identity_status == IdentityStatus.ACTIVE.value}

    def _content_ok(rec) -> bool:
        return content_sha256 is None or rec.genesis_content_sha256 == content_sha256

    def _has_content_correction(u) -> bool:
        return any(e["event_type"] == "CONTENT_CORRECTION" and e["source_record_uuid"] == u
                   for e in registry.lineage)

    # 1. path/alias match (current or historical alias)
    if canonical_source:
        by_alias = [u for u, r in active.items()
                    if r.current_source_alias == canonical_source
                    or canonical_source in r.historical_source_aliases]
        if len(by_alias) > 1:
            return ResolveResult(ResolveClass.COLLISION.value, None, "alias_claimed_by_multiple", by_alias)
        if len(by_alias) == 1:
            u = by_alias[0]
            rec = active[u]
            if _content_ok(rec):
                return ResolveResult(ResolveClass.EXACT.value, u, "alias+content")
            if _has_content_correction(u):
                return ResolveResult(ResolveClass.HIGH_CONFIDENCE_UNIQUE.value, u,
                                     "alias+registered_content_correction")
            return ResolveResult(ResolveClass.AMBIGUOUS.value, None,
                                 "same_path_content_changed_no_correction_event", [u])

    # 2. genesis path + content both match (retired records included -> restore)
    if canonical_source and content_sha256:
        both = [u for u, r in recs.items()
                if r.genesis_source_canonical == canonical_source
                and r.genesis_content_sha256 == content_sha256]
        if len(both) == 1:
            return ResolveResult(ResolveClass.EXACT.value, both[0], "genesis_source+content")

    # 3. content-hash only -> NEVER identity where duplicates exist (§14)
    if content_sha256:
        by_content = [u for u, r in active.items() if r.genesis_content_sha256 == content_sha256]
        if len(by_content) == 1:
            return ResolveResult(ResolveClass.HIGH_CONFIDENCE_UNIQUE.value, by_content[0], "content_hash_unique")
        if len(by_content) > 1:
            return ResolveResult(ResolveClass.AMBIGUOUS.value, None, "content_hash_shared_by_multiple", by_content)

    # 4. legacy id -> only if it maps to exactly one ACTIVE record
    if legacy_question_id is not None:
        by_legacy = [u for u, r in active.items() if r.legacy_question_id == legacy_question_id]
        if len(by_legacy) == 1:
            return ResolveResult(ResolveClass.HIGH_CONFIDENCE_UNIQUE.value, by_legacy[0], "legacy_id_unique")
        if len(by_legacy) > 1:
            return ResolveResult(ResolveClass.AMBIGUOUS.value, None, "legacy_id_collision", by_legacy)

    return ResolveResult(ResolveClass.MISSING.value, None, "no_evidence")


# --------------------------------------------------------------------------- #
# Genesis manifest + backfill dry-run  (docs ADR §24 / §30–§32)
# --------------------------------------------------------------------------- #
def _content_sha256(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def verify_genesis_input(*, snapshot_sha256: str, record_count: int,
                         tree_manifest_sha256: str | None, expected_tree_manifest_sha256: str | None,
                         registry: "Registry | None" = None) -> dict:
    """GENESIS_INPUT_EXACT_MATCH + GENESIS_BOOTSTRAP_ONCE_ONLY gate — STOP on any
    drift or a second bootstrap; mint nothing."""
    ok_snap = snapshot_sha256.strip().lower() == GENESIS_SNAPSHOT_SHA256
    ok_count = record_count == EXPECTED_RECORD_COUNT
    ok_tree = (expected_tree_manifest_sha256 is None
               or tree_manifest_sha256 == expected_tree_manifest_sha256)
    already_bootstrapped = bool(registry and (registry.genesis_provenance is not None
                                or any(r.mint_method == MintMethod.GENESIS_UUIDV5.value
                                       for r in registry.records.values())))
    return {
        "genesis_input_exact_match": bool(ok_snap and ok_count and ok_tree),
        "snapshot_sha_ok": ok_snap, "record_count_ok": ok_count, "tree_manifest_ok": ok_tree,
        "genesis_bootstrap_not_yet_done": not already_bootstrapped,
        "safe_to_bootstrap": bool(ok_snap and ok_count and ok_tree and not already_bootstrapped),
    }


def build_genesis_manifest(records: list[dict[str, Any]], *, verified_snapshot_sha256: str | None = None,
                           sample: int = 25) -> dict:
    """LC11-E: a custom caller MUST pass the snapshot sha it independently
    hashed and verified (== GENESIS_SNAPSHOT_SHA256). This function does not
    re-hash the file itself; refusing to accept an unverified sha is the point.
    ``run()`` passes the sha it computed from the bytes."""
    if verified_snapshot_sha256 is not None and \
            verified_snapshot_sha256.strip().lower() != GENESIS_SNAPSHOT_SHA256:
        raise ValueError("verified_snapshot_sha256 does not match the frozen genesis snapshot — STOP")
    rows = []
    canon_errors = collections.Counter()
    uuids = []
    for i, r in enumerate(records):
        raw = r.get("source")
        canon, err = canonical_source_key(raw)
        if err:
            canon_errors[err] += 1
            u = None
        else:
            u = mint_genesis_uuid(canon)
            uuids.append(u)
        rows.append({
            "record_index": i,                       # AUDIT ONLY — not identity
            "legacy_question_id": r.get("id"),       # ALIAS
            "raw_source": raw,                       # AUDIT
            "canonical_source": canon,               # ALIAS
            "content_sha256": _content_sha256(r.get("content") or ""),   # evidence
            "proposed_source_record_uuid": u,        # genesis mint (PROTOTYPE_ONLY)
        })
    dupes = sum(c for c in collections.Counter(uuids).values() if c > 1)
    manifest = {
        "genesis_key_spec_version": GENESIS_KEY_SPEC_VERSION,
        "canonicalisation_rules_version": CANONICALISATION_RULES_VERSION,
        "namespace_uuid": PROPOSED_CANONICAL_NAMESPACE_UUID,
        "owner_ratification_required": OWNER_RATIFICATION_REQUIRED,
        "snapshot_sha256": GENESIS_SNAPSHOT_SHA256,
        "record_count": len(records),
        "record_count_match": len(records) == EXPECTED_RECORD_COUNT,
        "canonicalisation_fail_closed_counts": dict(canon_errors),
        "distinct_proposed_uuids": len(set(uuids)),
        "proposed_uuid_collision_count": dupes,
        "record_sample_first25_last25": rows[:sample] + rows[-sample:],
    }
    return manifest, rows


def backfill_dry_run(genesis_rows: list[dict[str, Any]], existing_registry: Registry | None = None) -> dict:
    """Idempotent, collision-detecting, fail-closed. Returns a PLAN. No writes."""
    reg = existing_registry or Registry()
    to_mint, already_present, conflicts, not_recoverable = [], [], [], []
    seen = collections.Counter()
    for row in genesis_rows:
        if row["proposed_source_record_uuid"] is None:
            not_recoverable.append(row["record_index"]); continue
        u = row["proposed_source_record_uuid"]
        seen[u] += 1
        rr = resolve(reg, canonical_source=row["canonical_source"],
                     content_sha256=row["content_sha256"], legacy_question_id=row["legacy_question_id"])
        if rr.resolve_class == ResolveClass.MISSING.value:
            to_mint.append(u)
        elif rr.source_record_uuid == u:
            already_present.append(u)
        else:
            conflicts.append({"record_index": row["record_index"], "proposed": u,
                              "resolver": rr.resolve_class, "matched": rr.source_record_uuid})
    plan_collisions = sorted(u for u, c in seen.items() if c > 1)
    return {
        "plan_kind": "DRY_RUN__NO_MUTATION",
        "to_mint_count": len(to_mint),
        "already_present_count": len(already_present),
        "conflict_count": len(conflicts),
        "source_not_recoverable_count": len(not_recoverable),
        "proposed_uuid_collisions_within_batch": plan_collisions,
        "fail_closed": bool(conflicts or plan_collisions or not_recoverable),
        "conflicts": conflicts[:50],
        "backfill_idempotency_design": "PASS" if not plan_collisions else "FAIL",
    }


# --------------------------------------------------------------------------- #
# CLI — feasibility manifest against the frozen snapshot (PROTOTYPE_ONLY)
# --------------------------------------------------------------------------- #
def run(snapshot: Path, out_manifest: Path | None) -> dict[str, Any]:
    raw = snapshot.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != GENESIS_SNAPSHOT_SHA256:
        raise SystemExit(f"SNAPSHOT_HASH_MISMATCH: {sha} != {GENESIS_SNAPSHOT_SHA256}. STOP.")
    records = json.loads(raw)
    manifest, rows = build_genesis_manifest(records, verified_snapshot_sha256=sha)
    dry = backfill_dry_run(rows)
    out = {
        "schema_version": "1.0",
        "authority": "LC011_IMMUTABLE_PUZZLE_IDENTITY_FOUNDATION_ADR_AND_REGISTRY_CONTRACT_001",
        "canonicality": "CONTRACT_AND_PROTOTYPE__NO_MUTATION__NO_BACKFILL__OWNER_RATIFICATION_REQUIRED",
        "lc011_tool_version": LC011_TOOL_VERSION,
        "prototype_only": True, "corpus_mutated": False, "source_record_uuid_backfill": False,
        "request_time_uuid_generation": False, "lc009_semantics_changed": False,
        "live_source_path_is_canonical_identity": False,
        "source_path_role": "GENESIS_SEED_AND_RESOLVER_ALIAS_ONLY",
        "post_genesis_uuid_recomputation": "FORBIDDEN",
        "content_hash_as_identity": "FORBIDDEN",
        "legacy_id_unique_authority": False,
        "record_index_identity_authority": False,
        "recommended_final_model": "MODEL_D_persistent_identity_registry_frozen_genesis_bootstrap",
        "genesis_uuid_version": "UUIDv5",
        "new_native_uuid_version": "UUIDv4 (persisted once)",
        "genesis_name_option": GENESIS_NAME_OPTION,
        "genesis_bootstrap_once_only": "the snapshot SHA is NOT in the UUIDv5 name; it is immutable registry "
        "provenance + a hard once-only gate (a second genesis bootstrap against a different corpus/snapshot "
        "is REFUSED, not silently reassigned) — LC11-A",
        "proposed_canonical_namespace_uuid": PROPOSED_CANONICAL_NAMESPACE_UUID,
        "owner_namespace_ratification_required": OWNER_RATIFICATION_REQUIRED,
        "lc010_prototype_namespace_uuid_not_promoted": LC010_PROTOTYPE_NAMESPACE_UUID,
        "genesis_key_spec_version": GENESIS_KEY_SPEC_VERSION,
        "genesis_key_spec_example": genesis_key("<collection>/<...>/<n>.sgf"),
        "canonicalisation_rules_version": CANONICALISATION_RULES_VERSION,
        "canonicalisation_rules": _CANON_RULES,
        "registry_field_authority": REGISTRY_FIELD_AUTHORITY,
        "resolver_priority_ladder": RESOLVER_PRIORITY_LADDER,
        "resolver_auto_preserve_classes": list(AUTO_PRESERVE_CLASSES),
        "lineage_event_types": LINEAGE_EVENT_TYPES,
        "lineage_event_fields": LINEAGE_EVENT_FIELDS,
        "source_mutation_semantics": SEMANTICS,
        "new_record_identity_policy": NEW_RECORD_IDENTITY_POLICY,
        "lifecycle_states": LIFECYCLE_STATES,
        "runtime_contract": RUNTIME_CONTRACT,
        "dual_id_migration_window": DUAL_ID_WINDOW,
        "backfill_algorithm_design": BACKFILL_ALGORITHM_DESIGN,
        "sgf_source_tree_genesis_manifest_contract": SGF_SOURCE_TREE_GENESIS_MANIFEST_CONTRACT,
        "genesis_manifest": manifest,
        "backfill_dry_run": dry,
        "genesis_input_gate": verify_genesis_input(
            snapshot_sha256=sha, record_count=len(records),
            tree_manifest_sha256=None, expected_tree_manifest_sha256=None),
    }
    manifest_sha = None
    if out_manifest is not None:
        out_manifest.write_bytes(
            (json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        manifest_sha = hashlib.sha256(out_manifest.read_bytes()).hexdigest()
    out["manifest_sha256"] = manifest_sha
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LC011 identity registry prototype (read-only, PROTOTYPE_ONLY).")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--out-manifest", type=Path)
    a = p.parse_args(argv)
    if not a.snapshot.exists():
        raise SystemExit(f"snapshot not found: {a.snapshot}")
    res = run(a.snapshot, a.out_manifest)
    print(json.dumps({k: v for k, v in res.items()
                      if k not in ("genesis_manifest", "canonicalisation_rules",
                                   "registry_field_authority")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
