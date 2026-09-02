"""Repository for the Immutable Puzzle Identity registry, aliases and lineage.

Storage foundation only (LC013).  This module never populates the 42,804 frozen
genesis identities and never wires application call sites.  It provides the
narrow, transaction-safe operations a future owner-gated bootstrap and a future
resolver will build on:

  * create a HISTORICAL_GENESIS identity (UUIDv5, genesis-receipt bound)
  * create a NATIVE_UUIDV4 identity (persisted once)
  * rename / move  -> same source_record_uuid, superseded alias + lineage event
  * content-correction  -> lineage only, and only with explicit reviewed continuity
  * replacement / split / merge  -> never reuse an existing UUID
  * retire / restore  -> status change, identity stays resolvable
  * resolve(alias)  -> exact / missing / ambiguous(fail-closed) / retired

The current/live source path is an *alias*, never the identity key.
``source_record_uuid`` is immutable (DB-enforced) and lineage is append-only
(DB-enforced); this module additionally fails closed *before* touching the DB.
"""
from __future__ import annotations

import uuid as _uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Sequence

from migrations.puzzle_identity_registry_v1 import (
    ALIAS_KINDS,
    IDENTITY_SCHEMA_VERSION,
    LINEAGE_EVENT_TYPES,
    LINEAGE_MUTATION_EVENTS,
)

GENESIS_CREATED_BY = "lc012_p2_genesis_bootstrap"
NATIVE_CREATED_BY_DEFAULT = "native_authoring"
DEFAULT_ALIAS_CONTEXT = "genesis-v1"
POST_GENESIS_ALIAS_CONTEXT = "post-genesis"

# SQLite's default host-parameter limit is commonly 999, so keep the
# established conservative batch size there.  PostgreSQL accepts materially
# larger parameter lists; the production resolver was otherwise issuing one
# query per 400 ids for a corpus-sized aggregate read.
_RESOLVE_BATCH_SIZE_SQLITE = 400
_RESOLVE_BATCH_SIZE_POSTGRES = 10_000


class PuzzleIdentityError(RuntimeError):
    """Fail-closed puzzle-identity storage error."""


class AmbiguousAliasError(PuzzleIdentityError):
    """An alias resolves to more than one identity — never auto-merge."""

    candidates: tuple[str, ...] = ()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_uuid(value: str, *, expect_version: int | None = None) -> str:
    try:
        parsed = _uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise PuzzleIdentityError(f"not a valid UUID: {value!r}") from exc
    if str(parsed) != str(value).lower():
        raise PuzzleIdentityError(f"non-canonical UUID text: {value!r}")
    if expect_version is not None and parsed.version != expect_version:
        raise PuzzleIdentityError(
            f"expected UUIDv{expect_version}, got v{parsed.version}: {value}"
        )
    return str(parsed)


class PuzzleIdentityStore:
    def __init__(self, conn: Any, *, clock: Any = _iso_now) -> None:
        self._conn = conn
        self._clock = clock
        self._sp = 0

    # ---- low level -------------------------------------------------------- #

    def _exec(self, sql: str, params: Sequence[Any] = ()) -> Any:
        p = tuple(params)
        if hasattr(self._conn, "execute"):
            return self._conn.execute(sql, p) if p else self._conn.execute(sql)
        cur = self._conn.cursor()
        if p:
            cur.execute(sql.replace("?", "%s"), p)
        else:
            cur.execute(sql)
        return cur

    def _one(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cur = self._exec(sql, params)
        row = cur.fetchone()
        if not hasattr(self._conn, "execute"):
            cur.close()
        return row

    def _all(self, sql: str, params: Sequence[Any] = ()) -> list[Any]:
        cur = self._exec(sql, params)
        rows = list(cur.fetchall())
        if not hasattr(self._conn, "execute"):
            cur.close()
        return rows

    @staticmethod
    def _resolve_batch_size(conn: Any) -> int:
        raw = getattr(conn, "_conn", conn)
        module = raw.__class__.__module__.lower()
        return (
            _RESOLVE_BATCH_SIZE_SQLITE
            if module.startswith("sqlite3")
            else _RESOLVE_BATCH_SIZE_POSTGRES
        )

    @staticmethod
    def _val(row: Any, idx: int, key: str) -> Any:
        if row is None:
            return None
        if hasattr(row, "keys"):
            try:
                return row[key]
            except (KeyError, IndexError):
                return row[idx]
        return row[idx]

    @contextmanager
    def _unit(self, tag: str) -> Iterator[None]:
        """Atomic sub-operation: SAVEPOINT / RELEASE / ROLLBACK-on-error.

        Independent of the caller's outer transaction — a failed operation
        leaves no partial registry/alias/lineage state.
        """
        self._sp += 1
        name = f"pis_{tag}_{self._sp}"
        self._exec(f"SAVEPOINT {name}")
        try:
            yield
        except Exception:
            self._exec(f"ROLLBACK TO SAVEPOINT {name}")
            self._exec(f"RELEASE SAVEPOINT {name}")
            raise
        else:
            self._exec(f"RELEASE SAVEPOINT {name}")

    # ---- reads --------------------------------------------------------- #

    def get_identity(self, source_record_uuid: str) -> dict[str, Any] | None:
        u = _validate_uuid(source_record_uuid)
        row = self._one(
            "SELECT source_record_uuid, identity_kind, identity_version, origin_class, "
            "identity_status, created_at, created_by_process, creation_reason, "
            "genesis_receipt_ref, retired_at, retire_reason, provenance_note "
            "FROM puzzle_identity_registry WHERE source_record_uuid=?",
            (u,),
        )
        if row is None:
            return None
        cols = [
            "source_record_uuid", "identity_kind", "identity_version", "origin_class",
            "identity_status", "created_at", "created_by_process", "creation_reason",
            "genesis_receipt_ref", "retired_at", "retire_reason", "provenance_note",
        ]
        return {c: self._val(row, i, c) for i, c in enumerate(cols)}

    def list_aliases(self, source_record_uuid: str, *, current_only: bool = False) -> list[dict[str, Any]]:
        u = _validate_uuid(source_record_uuid)
        sql = (
            "SELECT alias_kind, alias_value, alias_context, confidence, is_current, "
            "recorded_at, recorded_by FROM puzzle_identity_alias WHERE source_record_uuid=?"
        )
        params: list[Any] = [u]
        if current_only:
            sql += " AND is_current = ?"
            params.append(True)          # dialect-adapted: PG TRUE / SQLite 1
        sql += " ORDER BY id"
        cols = ["alias_kind", "alias_value", "alias_context", "confidence",
                "is_current", "recorded_at", "recorded_by"]
        return [
            {c: self._val(r, i, c) for i, c in enumerate(cols)}
            for r in self._all(sql, tuple(params))
        ]

    def get_lineage(self, source_record_uuid: str) -> list[dict[str, Any]]:
        u = _validate_uuid(source_record_uuid)
        cols = ["seq", "event_type", "occurred_at", "actor", "from_value", "to_value",
                "related_source_record_uuid", "relationship_role", "reason", "evidence_ref"]
        rows = self._all(
            "SELECT seq, event_type, occurred_at, actor, from_value, to_value, "
            "related_source_record_uuid, relationship_role, reason, evidence_ref "
            "FROM puzzle_identity_lineage WHERE source_record_uuid=? ORDER BY seq",
            (u,),
        )
        return [{c: self._val(r, i, c) for i, c in enumerate(cols)} for r in rows]

    def _next_seq(self, source_record_uuid: str) -> int:
        row = self._one(
            "SELECT COALESCE(MAX(seq), 0) FROM puzzle_identity_lineage "
            "WHERE source_record_uuid=?",
            (source_record_uuid,),
        )
        return int(self._val(row, 0, "coalesce") or 0) + 1

    def _require_identity(self, source_record_uuid: str) -> dict[str, Any]:
        ident = self.get_identity(source_record_uuid)
        if ident is None:
            raise PuzzleIdentityError(f"unknown identity: {source_record_uuid}")
        return ident

    # ---- alias write helpers ----------------------------------------- #

    def _insert_alias(self, u: str, kind: str, value: str, *, context: str,
                      confidence: str, recorded_by: str, when: str,
                      is_current: bool = True) -> None:
        if kind not in ALIAS_KINDS:
            raise PuzzleIdentityError(f"unsupported alias_kind: {kind}")
        self._exec(
            "INSERT INTO puzzle_identity_alias "
            "(source_record_uuid, alias_kind, alias_value, alias_context, confidence, "
            " is_current, recorded_at, recorded_by) VALUES (?,?,?,?,?,?,?,?)",
            (u, kind, value, context, confidence, bool(is_current), when, recorded_by),
        )

    def _current_aliases(self, u: str, kind: str) -> list[tuple[str, str]]:
        rows = self._all(
            "SELECT alias_value, alias_context FROM puzzle_identity_alias "
            "WHERE source_record_uuid=? AND alias_kind=? AND is_current = ? ORDER BY id",
            (u, kind, True),
        )
        return [(str(self._val(r, 0, "alias_value")),
                 str(self._val(r, 1, "alias_context"))) for r in rows]

    def _supersede_current(self, u: str, kind: str) -> None:
        self._exec(
            "UPDATE puzzle_identity_alias SET is_current = ? "
            "WHERE source_record_uuid=? AND alias_kind=? AND is_current = ?",
            (False, u, kind, True),
        )

    def _append_lineage(self, u: str, event_type: str, *, actor: str, reason: str,
                        when: str, from_value: str | None = None,
                        to_value: str | None = None,
                        related: str | None = None,
                        role: str | None = None,
                        evidence_ref: str | None = None) -> int:
        if event_type not in LINEAGE_EVENT_TYPES:
            raise PuzzleIdentityError(f"unsupported lineage event_type: {event_type}")
        seq = self._next_seq(u)
        self._exec(
            "INSERT INTO puzzle_identity_lineage "
            "(source_record_uuid, seq, event_type, occurred_at, actor, from_value, "
            " to_value, related_source_record_uuid, relationship_role, reason, "
            " evidence_ref, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (u, seq, event_type, when, actor, from_value, to_value, related, role,
             reason, evidence_ref, when),
        )
        return seq

    # ---- creation --------------------------------------------------- #

    def create_historical_genesis_identity(
        self,
        source_record_uuid: str,
        *,
        receipt_sha256: str,
        canonical_source: str,
        legacy_question_id: str | int | None = None,
        legacy_question_id_is_current: bool = True,
        historical_source_path: str | None = None,
        created_by_process: str = GENESIS_CREATED_BY,
        creation_reason: str,
        when: str | None = None,
    ) -> str:
        u = _validate_uuid(source_record_uuid, expect_version=5)
        when = when or self._clock()
        with self._unit("genesis"):
            self._exec(
                "INSERT INTO puzzle_identity_registry "
                "(source_record_uuid, identity_kind, identity_version, origin_class, "
                " identity_status, created_at, created_by_process, creation_reason, "
                " genesis_receipt_ref) "
                "VALUES (?, 'HISTORICAL_GENESIS', ?, 'GENESIS', 'ACTIVE', ?, ?, ?, ?)",
                (u, IDENTITY_SCHEMA_VERSION, when, created_by_process,
                 creation_reason, receipt_sha256),
            )
            self._insert_alias(u, "CANONICAL_SOURCE_KEY", canonical_source,
                               context=DEFAULT_ALIAS_CONTEXT, confidence="EXACT",
                               recorded_by=created_by_process, when=when)
            self._insert_alias(u, "CURRENT_SOURCE_PATH", canonical_source,
                               context=DEFAULT_ALIAS_CONTEXT, confidence="EXACT",
                               recorded_by=created_by_process, when=when)
            if historical_source_path:
                self._insert_alias(u, "HISTORICAL_SOURCE_PATH", historical_source_path,
                                   context=DEFAULT_ALIAS_CONTEXT, confidence="EXACT",
                                   recorded_by=created_by_process, when=when)
            if legacy_question_id is not None:
                # LC020-R1: a legacy_question_id shared by >1 genesis identity
                # (11 known collision groups in the frozen corpus) gets its
                # LEGACY_QUESTION_ID alias recorded NOT-current, so a raw legacy
                # lookup fails closed AMBIGUOUS instead of arbitrarily binding one
                # member.  The unique-current-alias constraint is untouched.
                self._insert_alias(u, "LEGACY_QUESTION_ID", str(legacy_question_id),
                                   context=DEFAULT_ALIAS_CONTEXT, confidence="EXACT",
                                   recorded_by=created_by_process, when=when,
                                   is_current=legacy_question_id_is_current)
            self._append_lineage(u, "GENESIS", actor=created_by_process,
                                 reason=creation_reason, when=when)
        return u

    def create_native_identity(
        self,
        *,
        source_record_uuid: str | None = None,
        created_by_process: str = NATIVE_CREATED_BY_DEFAULT,
        creation_reason: str,
        current_source_path: str | None = None,
        legacy_question_id: str | int | None = None,
        when: str | None = None,
    ) -> str:
        if source_record_uuid is None:
            u = str(_uuid.uuid4())
        else:
            u = _validate_uuid(source_record_uuid, expect_version=4)
        when = when or self._clock()
        with self._unit("native"):
            self._exec(
                "INSERT INTO puzzle_identity_registry "
                "(source_record_uuid, identity_kind, identity_version, origin_class, "
                " identity_status, created_at, created_by_process, creation_reason, "
                " genesis_receipt_ref) "
                "VALUES (?, 'NATIVE_UUIDV4', ?, 'NATIVE', 'ACTIVE', ?, ?, ?, NULL)",
                (u, IDENTITY_SCHEMA_VERSION, when, created_by_process, creation_reason),
            )
            if current_source_path:
                self._insert_alias(u, "CURRENT_SOURCE_PATH", current_source_path,
                                   context=POST_GENESIS_ALIAS_CONTEXT,
                                   confidence="EXACT", recorded_by=created_by_process,
                                   when=when)
            if legacy_question_id is not None:
                self._insert_alias(u, "LEGACY_QUESTION_ID", str(legacy_question_id),
                                   context=POST_GENESIS_ALIAS_CONTEXT,
                                   confidence="RECORDED", recorded_by=created_by_process,
                                   when=when)
            self._append_lineage(u, "NATIVE_CREATE", actor=created_by_process,
                                 reason=creation_reason, when=when)
        return u

    # ---- generic append ------------------------------------------- #

    def append_lineage_event(self, source_record_uuid: str, event_type: str, *,
                             actor: str, reason: str, from_value: str | None = None,
                             to_value: str | None = None,
                             related_source_record_uuid: str | None = None,
                             relationship_role: str | None = None,
                             evidence_ref: str | None = None,
                             when: str | None = None) -> int:
        u = _validate_uuid(source_record_uuid)
        if event_type not in LINEAGE_MUTATION_EVENTS:
            raise PuzzleIdentityError(
                f"append_lineage_event only accepts mutation events, not {event_type!r}"
            )
        self._require_identity(u)
        when = when or self._clock()
        rel = _validate_uuid(related_source_record_uuid) if related_source_record_uuid else None
        with self._unit("lineage"):
            return self._append_lineage(u, event_type, actor=actor, reason=reason,
                                        when=when, from_value=from_value,
                                        to_value=to_value, related=rel,
                                        role=relationship_role, evidence_ref=evidence_ref)

    # ---- rename / move (same UUID) ------------------------------- #

    def _relocate(self, u: str, event_type: str, *, from_path: str, to_path: str,
                  actor: str, reason: str, alias_context: str, when: str) -> int:
        self._require_identity(u)
        # Fail closed BEFORE any mutation: the identity must have exactly one
        # current CURRENT_SOURCE_PATH and its value must equal the supplied
        # from_path.  A stale or fabricated from_path mutates nothing.
        current = self._current_aliases(u, "CURRENT_SOURCE_PATH")
        if len(current) != 1:
            raise PuzzleIdentityError(
                f"{event_type}: identity {u} has {len(current)} current "
                f"CURRENT_SOURCE_PATH aliases (expected exactly 1)"
            )
        if current[0][0] != from_path:
            raise PuzzleIdentityError(
                f"{event_type}: stale from_path {from_path!r}; current path is "
                f"{current[0][0]!r} — no mutation performed"
            )
        if to_path == from_path:
            raise PuzzleIdentityError(f"{event_type}: to_path equals from_path")
        with self._unit("relocate"):
            self._supersede_current(u, "CURRENT_SOURCE_PATH")
            self._insert_alias(u, "CURRENT_SOURCE_PATH", to_path, context=alias_context,
                               confidence="EXACT", recorded_by=actor, when=when)
            return self._append_lineage(u, event_type, actor=actor, reason=reason,
                                        when=when, from_value=from_path, to_value=to_path)

    def record_rename(self, source_record_uuid: str, *, from_path: str, to_path: str,
                      actor: str, reason: str,
                      alias_context: str = POST_GENESIS_ALIAS_CONTEXT,
                      when: str | None = None) -> int:
        u = _validate_uuid(source_record_uuid)
        return self._relocate(u, "RENAME", from_path=from_path, to_path=to_path,
                              actor=actor, reason=reason, alias_context=alias_context,
                              when=when or self._clock())

    def record_move(self, source_record_uuid: str, *, from_path: str, to_path: str,
                    actor: str, reason: str,
                    alias_context: str = POST_GENESIS_ALIAS_CONTEXT,
                    when: str | None = None) -> int:
        u = _validate_uuid(source_record_uuid)
        return self._relocate(u, "MOVE", from_path=from_path, to_path=to_path,
                              actor=actor, reason=reason, alias_context=alias_context,
                              when=when or self._clock())

    # ---- content correction (fail closed) ---------------------- #

    def record_content_correction(self, source_record_uuid: str, *, reviewed: bool,
                                  actor: str, reason: str,
                                  from_content_sha256: str | None = None,
                                  to_content_sha256: str | None = None,
                                  evidence_ref: str | None = None,
                                  when: str | None = None) -> int:
        u = _validate_uuid(source_record_uuid)
        self._require_identity(u)
        if not reviewed:
            raise PuzzleIdentityError(
                "content correction does not auto-preserve identity: a reviewed "
                "continuity decision (reviewed=True) is required"
            )
        when = when or self._clock()
        with self._unit("content"):
            return self._append_lineage(
                u, "CONTENT_CORRECTION", actor=actor, reason=reason, when=when,
                from_value=from_content_sha256, to_value=to_content_sha256,
                evidence_ref=evidence_ref,
            )

    # ---- replacement / split / merge (never reuse a UUID) ----- #

    def record_replacement(self, *, old_source_record_uuid: str,
                           new_source_record_uuid: str, actor: str, reason: str,
                           retire_old: bool = True, when: str | None = None) -> None:
        old = _validate_uuid(old_source_record_uuid)
        new = _validate_uuid(new_source_record_uuid)
        if old == new:
            raise PuzzleIdentityError("replacement must not reuse the old UUID")
        self._require_identity(old)
        if self.get_identity(new) is None:
            raise PuzzleIdentityError(
                "replacement target identity must be created before replacement"
            )
        when = when or self._clock()
        with self._unit("replace"):
            if retire_old:
                self._set_status(old, "RETIRED", reason=reason, when=when)
            self._append_lineage(old, "REPLACED", actor=actor, reason=reason, when=when,
                                 related=new, role="SUPERSEDED_BY")
            self._append_lineage(new, "REPLACED", actor=actor, reason=reason, when=when,
                                 related=old, role="SUPERSEDES")

    def record_split(self, *, parent_source_record_uuid: str,
                     child_source_record_uuids: Iterable[str], actor: str, reason: str,
                     retire_parent: bool = True, when: str | None = None) -> None:
        parent = _validate_uuid(parent_source_record_uuid)
        children = [_validate_uuid(c) for c in child_source_record_uuids]
        if not children:
            raise PuzzleIdentityError("split requires at least one child identity")
        if parent in children:
            raise PuzzleIdentityError("split child must not reuse the parent UUID")
        if len(set(children)) != len(children):
            raise PuzzleIdentityError("split children must be distinct")
        self._require_identity(parent)
        for c in children:
            if self.get_identity(c) is None:
                raise PuzzleIdentityError(f"split child identity {c} must exist first")
        when = when or self._clock()
        with self._unit("split"):
            if retire_parent:
                self._set_status(parent, "RETIRED", reason=reason, when=when)
            for c in children:
                self._append_lineage(parent, "SPLIT", actor=actor, reason=reason,
                                     when=when, related=c, role="PARENT")
                self._append_lineage(c, "SPLIT", actor=actor, reason=reason, when=when,
                                     related=parent, role="CHILD")

    def record_merge(self, *, survivor_source_record_uuid: str,
                     non_survivor_source_record_uuids: Iterable[str], actor: str,
                     reason: str, when: str | None = None) -> None:
        survivor = _validate_uuid(survivor_source_record_uuid)
        losers = [_validate_uuid(x) for x in non_survivor_source_record_uuids]
        if not losers:
            raise PuzzleIdentityError("merge requires at least one non-survivor")
        if survivor in losers:
            raise PuzzleIdentityError("merge survivor cannot also be a non-survivor")
        if len(set(losers)) != len(losers):
            raise PuzzleIdentityError("merge non-survivors must be distinct")
        self._require_identity(survivor)
        for x in losers:
            self._require_identity(x)
        when = when or self._clock()
        with self._unit("merge"):
            for x in losers:
                self._set_status(x, "RETIRED", reason=reason, when=when)
                self._append_lineage(survivor, "MERGE", actor=actor, reason=reason,
                                     when=when, related=x, role="SURVIVOR")
                self._append_lineage(x, "MERGE", actor=actor, reason=reason, when=when,
                                     related=survivor, role="NON_SURVIVOR")

    # ---- retire / restore --------------------------------------- #

    def _set_status(self, u: str, status: str, *, reason: str, when: str) -> None:
        if status == "RETIRED":
            self._exec(
                "UPDATE puzzle_identity_registry SET identity_status='RETIRED', "
                "retired_at=?, retire_reason=? WHERE source_record_uuid=?",
                (when, reason, u),
            )
        else:
            self._exec(
                "UPDATE puzzle_identity_registry SET identity_status='ACTIVE', "
                "retired_at=NULL, retire_reason=NULL WHERE source_record_uuid=?",
                (u,),
            )

    def retire_identity(self, source_record_uuid: str, *, reason: str, actor: str,
                        when: str | None = None) -> int:
        u = _validate_uuid(source_record_uuid)
        self._require_identity(u)
        when = when or self._clock()
        with self._unit("retire"):
            self._set_status(u, "RETIRED", reason=reason, when=when)
            return self._append_lineage(u, "DELETE", actor=actor, reason=reason, when=when)

    def restore_identity(self, source_record_uuid: str, *, reason: str, actor: str,
                         when: str | None = None) -> int:
        u = _validate_uuid(source_record_uuid)
        self._require_identity(u)
        when = when or self._clock()
        with self._unit("restore"):
            self._set_status(u, "ACTIVE", reason=reason, when=when)
            return self._append_lineage(u, "RESTORE", actor=actor, reason=reason, when=when)

    # ---- resolver (exact / missing / ambiguous fail-closed) ---- #

    def has_identity_tables(self) -> bool:
        """True iff this candidate's tables exist on the connection.

        A missing table surfaces as a driver error (SQLite ``OperationalError``,
        PostgreSQL ``UndefinedTable``); either way the read window degrades to
        UNAVAILABLE rather than raising into a caller.
        """
        try:
            self._one("SELECT 1 FROM puzzle_identity_alias WHERE 1=0")
            self._one("SELECT 1 FROM puzzle_identity_registry WHERE 1=0")
            return True
        except Exception:  # noqa: BLE001
            try:
                if hasattr(self._conn, "rollback"):
                    self._conn.rollback()  # clear an aborted PG transaction
            except Exception:  # noqa: BLE001
                pass
            return False

    def resolve(self, alias_kind: str, alias_value: str, *,
                alias_context: str | None = DEFAULT_ALIAS_CONTEXT) -> dict[str, Any]:
        """Resolve one alias.  ``alias_context=None`` means *any* context — the
        distinct-uuid check across contexts is what makes cross-context
        ambiguity fail closed."""
        if alias_kind not in ALIAS_KINDS:
            raise PuzzleIdentityError(f"unsupported alias_kind: {alias_kind}")
        if alias_context is None:
            rows = self._all(
                "SELECT source_record_uuid FROM puzzle_identity_alias "
                "WHERE alias_kind=? AND alias_value=? AND is_current = ?",
                (alias_kind, str(alias_value), True),
            )
        else:
            rows = self._all(
                "SELECT source_record_uuid FROM puzzle_identity_alias "
                "WHERE alias_kind=? AND alias_value=? AND alias_context=? AND is_current = ?",
                (alias_kind, str(alias_value), alias_context, True),
            )
        uuids = sorted({str(self._val(r, 0, "source_record_uuid")) for r in rows})
        if not uuids:
            # LC020-R1: a genesis legacy_question_id collision id has NO current
            # LEGACY_QUESTION_ID binding by design, but >1 identity carries it.
            # That is an ambiguous lookup, not a missing one — fail closed.
            if alias_kind == "LEGACY_QUESTION_ID":
                hist = self._all(
                    "SELECT source_record_uuid FROM puzzle_identity_alias "
                    "WHERE alias_kind=? AND alias_value=?",
                    (alias_kind, str(alias_value)),
                )
                hu = sorted({str(self._val(r, 0, "source_record_uuid")) for r in hist})
                if len(hu) > 1:
                    exc = AmbiguousAliasError(
                        f"legacy_question_id {alias_value} is a genesis collision id: "
                        f"{len(hu)} identities carry it, none uniquely current: {hu}"
                    )
                    exc.candidates = tuple(hu)
                    raise exc
            return {"status": "MISSING", "source_record_uuid": None}
        if len(uuids) > 1:
            exc = AmbiguousAliasError(
                f"alias ({alias_kind}, {alias_value}, {alias_context}) resolves to "
                f"{len(uuids)} identities: {uuids}"
            )
            exc.candidates = tuple(uuids)
            raise exc
        ident = self.get_identity(uuids[0]) or {}
        status = "RETIRED" if ident.get("identity_status") == "RETIRED" else "EXACT"
        return {
            "status": status,
            "source_record_uuid": uuids[0],
            "identity_status": ident.get("identity_status"),
        }

    def resolve_batch(self, alias_kind: str, alias_values: Sequence[Any], *,
                      alias_context: str | None = None) -> dict[str, dict[str, Any]]:
        """Resolve many alias values in one query (SRS / review_log aggregates).

        Returns ``{str(value): {status, source_record_uuid, identity_status,
        candidates}}`` — EXACT / RETIRED / MISSING / AMBIGUOUS, never raises for
        an ambiguous value (it is reported as its own fail-closed row)."""
        if alias_kind not in ALIAS_KINDS:
            raise PuzzleIdentityError(f"unsupported alias_kind: {alias_kind}")
        # The result is keyed by string value, so duplicate inputs cannot
        # produce distinct output.  Preserve first-seen order while ensuring
        # direct callers cannot pay for repeated alias batches.
        wanted = list(dict.fromkeys(str(v) for v in alias_values))
        out: dict[str, dict[str, Any]] = {
            v: {"status": "MISSING", "source_record_uuid": None} for v in wanted
        }
        if not wanted:
            return out
        batch_size = self._resolve_batch_size(self._conn)
        by_value: dict[str, set[str]] = {}
        for chunk_start in range(0, len(wanted), batch_size):
            chunk = wanted[chunk_start:chunk_start + batch_size]
            placeholders = ",".join("?" * len(chunk))
            if alias_context is None:
                sql = ("SELECT alias_value, source_record_uuid FROM puzzle_identity_alias "
                       f"WHERE alias_kind=? AND is_current = ? AND alias_value IN ({placeholders})")
                params = [alias_kind, True, *chunk]
            else:
                sql = ("SELECT alias_value, source_record_uuid FROM puzzle_identity_alias "
                       f"WHERE alias_kind=? AND alias_context=? AND is_current = ? "
                       f"AND alias_value IN ({placeholders})")
                params = [alias_kind, alias_context, True, *chunk]
            for r in self._all(sql, tuple(params)):
                v = str(self._val(r, 0, "alias_value"))
                by_value.setdefault(v, set()).add(str(self._val(r, 1, "source_record_uuid")))
        statuses: dict[str, str] = {}
        for v, us in by_value.items():
            if len(us) > 1:
                out[v] = {"status": "AMBIGUOUS", "source_record_uuid": None,
                          "candidates": tuple(sorted(us))}
            else:
                statuses[v] = next(iter(us))
        if alias_kind == "LEGACY_QUESTION_ID":
            # LC020-R1: values with no current binding but >1 identity carrying
            # them as a LEGACY_QUESTION_ID alias are genesis collision ids —
            # report AMBIGUOUS, not MISSING.  Non-collision unknown ids (0 rows)
            # stay MISSING.
            unbound = [v for v in wanted if v not in by_value]
            hist: dict[str, set[str]] = {}
            for chunk_start in range(0, len(unbound), batch_size):
                chunk = unbound[chunk_start:chunk_start + batch_size]
                if not chunk:
                    continue
                placeholders = ",".join("?" * len(chunk))
                for r in self._all(
                    "SELECT alias_value, source_record_uuid FROM puzzle_identity_alias "
                    f"WHERE alias_kind='LEGACY_QUESTION_ID' AND alias_value IN ({placeholders})",
                    tuple(chunk),
                ):
                    v = str(self._val(r, 0, "alias_value"))
                    hist.setdefault(v, set()).add(str(self._val(r, 1, "source_record_uuid")))
            for v, us in hist.items():
                if len(us) > 1:
                    out[v] = {"status": "AMBIGUOUS", "source_record_uuid": None,
                              "candidates": tuple(sorted(us))}
        if statuses:
            uniq = sorted(set(statuses.values()))
            ph = ",".join("?" * len(uniq))
            state = {}
            for r in self._all(
                "SELECT source_record_uuid, identity_status FROM puzzle_identity_registry "
                f"WHERE source_record_uuid IN ({ph})", tuple(uniq)
            ):
                state[str(self._val(r, 0, "source_record_uuid"))] = self._val(r, 1, "identity_status")
            for v, u in statuses.items():
                st = "RETIRED" if state.get(u) == "RETIRED" else "EXACT"
                out[v] = {"status": st, "source_record_uuid": u,
                          "identity_status": state.get(u)}
        return out

    def aliases_of_kind(self, source_record_uuid: str, alias_kind: str, *,
                        current_only: bool = True) -> list[str]:
        """Reverse lookup: an identity's alias values of one kind (admin/audit)."""
        u = _validate_uuid(source_record_uuid)
        if alias_kind not in ALIAS_KINDS:
            raise PuzzleIdentityError(f"unsupported alias_kind: {alias_kind}")
        sql = ("SELECT alias_value FROM puzzle_identity_alias "
               "WHERE source_record_uuid=? AND alias_kind=?")
        params: list[Any] = [u, alias_kind]
        if current_only:
            sql += " AND is_current = ?"
            params.append(True)
        sql += " ORDER BY id"
        return [str(self._val(r, 0, "alias_value")) for r in self._all(sql, tuple(params))]

    def count_identities(self) -> int:
        row = self._one("SELECT COUNT(*) FROM puzzle_identity_registry")
        return int(self._val(row, 0, "count") or 0)

    def genesis_bootstrap_applied(self) -> bool:
        row = self._one(
            "SELECT status FROM puzzle_identity_bootstrap_receipt "
            "WHERE bootstrap_singleton='GENESIS'"
        )
        return bool(row) and str(self._val(row, 0, "status")) == "APPLIED"


__all__ = [
    "AmbiguousAliasError",
    "DEFAULT_ALIAS_CONTEXT",
    "GENESIS_CREATED_BY",
    "POST_GENESIS_ALIAS_CONTEXT",
    "PuzzleIdentityError",
    "PuzzleIdentityStore",
]
