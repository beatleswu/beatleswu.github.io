"""LC015 — bootstrap-gated adoption of the dual-ID read window by read callers.

This is the single seam a read caller (review_log aggregates, SRS reads, admin
lookup, Learning Core / Adventure identity reads) calls to key a read by the
permanent ``source_record_uuid`` *when it is safe to* — and by the legacy
integer ``question_id`` otherwise.

Gate (LC015 §6), enforced here so no caller re-implements it:

    bootstrap_state().hot is False        -> ("legacy", question_id)   [always today]
    hot True + EXACT                      -> ("uuid",  source_record_uuid), attachable
    hot True + RETIRED                    -> ("uuid",  source_record_uuid), history only, NOT attachable
    hot True + AMBIGUOUS                  -> ("unresolved", question_id)   fail closed, never merged, NOT attachable
    hot True + MISSING                    -> ("legacy", question_id)      compatibility, NOT attachable
    hot True + UNAVAILABLE               -> ("unavailable", question_id) NOT attachable

**No write authority.**  This module imports only the *read* window; it never
creates an identity, mints a UUID, mutates an alias/lineage row, or runs a
bootstrap.  A MISSING / UNAVAILABLE / AMBIGUOUS result is a typed key, never a
fabricated identity and never an exception into the caller (except the explicit
``assert_attachable`` guard, which a would-be *writer* calls on purpose).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from puzzle_identity_read_window import DualIdReadWindow, ResolutionStatus


class IdentityKeyKind:
    UUID = "uuid"
    LEGACY = "legacy"
    UNRESOLVED = "unresolved"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class IdentityKey:
    """How a read caller should key / group a row."""

    kind: str
    value: str                         # a uuid, or str(question_id)
    legacy_question_id: str
    retired: bool = False
    attachable: bool = False           # True only for hot + EXACT
    reason: str = ""
    candidates: tuple[str, ...] = field(default_factory=tuple)

    @property
    def group_key(self) -> tuple[str, str]:
        """The value a caller GROUP BYs on.  An unresolved / unavailable id gets
        its own per-legacy-id bucket, so it is **never** merged into a uuid
        bucket and two distinct ambiguous ids never collapse together."""
        if self.kind == IdentityKeyKind.UUID:
            return ("uuid", self.value)
        if self.kind == IdentityKeyKind.UNRESOLVED:
            return ("unresolved", self.legacy_question_id)
        if self.kind == IdentityKeyKind.UNAVAILABLE:
            return ("unavailable", self.legacy_question_id)
        return ("legacy", self.legacy_question_id)

    @property
    def is_canonical(self) -> bool:
        return self.kind == IdentityKeyKind.UUID


class IdentityNotAttachable(RuntimeError):
    """A would-be writer asked to attach state to a non-EXACT identity."""


class BootstrapGatedIdentityReader:
    """Wraps :class:`DualIdReadWindow` with the LC015 bootstrap gate.

    Construct one per request / per unit of work and reuse it — ``hot`` and the
    tables-present probe are cached for the object's lifetime.
    """

    def __init__(self, conn: Any) -> None:
        self._w = DualIdReadWindow(conn)
        self._hot: bool | None = None

    # ---- gate ----------------------------------------------------- #

    @property
    def hot(self) -> bool:
        if self._hot is None:
            self._hot = bool(self._w.bootstrap_state().get("hot"))
        return self._hot

    def bootstrap_state(self) -> dict[str, Any]:
        return self._w.bootstrap_state()

    def _key_from_resolution(self, question_id: Any, res) -> IdentityKey:
        qid = str(question_id)
        st = res.status
        if st == ResolutionStatus.EXACT:
            return IdentityKey(IdentityKeyKind.UUID, res.source_record_uuid, qid,
                               attachable=True, reason="exact single binding")
        if st == ResolutionStatus.RETIRED:
            return IdentityKey(IdentityKeyKind.UUID, res.source_record_uuid, qid,
                               retired=True, attachable=False,
                               reason="retired identity — resolvable for history only")
        if st == ResolutionStatus.AMBIGUOUS:
            return IdentityKey(IdentityKeyKind.UNRESOLVED, qid, qid, attachable=False,
                               reason="ambiguous alias — fail closed, never merged",
                               candidates=tuple(res.candidates))
        if st == ResolutionStatus.UNAVAILABLE:
            return IdentityKey(IdentityKeyKind.UNAVAILABLE, qid, qid, attachable=False,
                               reason="identity tables unavailable on this connection")
        # MISSING
        return IdentityKey(IdentityKeyKind.LEGACY, qid, qid, attachable=False,
                           reason="no current binding — compatibility (legacy) key")

    # ---- single ------------------------------------------------- #

    def key_for(self, question_id: Any) -> IdentityKey:
        qid = str(question_id)
        if not self.hot:
            return IdentityKey(IdentityKeyKind.LEGACY, qid, qid, attachable=False,
                               reason="bootstrap_state().hot is False — legacy path authoritative")
        return self._key_from_resolution(question_id,
                                         self._w.resolve_legacy_question_id(question_id))

    def assert_attachable(self, question_id: Any) -> str:
        """For a would-be *writer* of new SRS / review / adventure state: return
        the canonical uuid iff the identity is EXACT, else raise.  Never
        fabricates."""
        k = self.key_for(question_id)
        if not k.attachable:
            raise IdentityNotAttachable(
                f"question_id={question_id} resolves as {k.kind} ({k.reason}); "
                f"no new state may attach"
            )
        return k.value

    # ---- aggregate (SRS / review_log) ------------------------- #

    def keys_for(self, question_ids: Iterable[Any]) -> dict[str, IdentityKey]:
        wanted = list(dict.fromkeys(str(q) for q in question_ids))
        if not wanted:
            return {}
        if not self.hot:
            return {
                q: IdentityKey(IdentityKeyKind.LEGACY, q, q, attachable=False,
                               reason="bootstrap_state().hot is False")
                for q in wanted
            }
        batch = self._w.resolve_many_legacy_question_ids(wanted)
        return {q: self._key_from_resolution(q, batch[q]) for q in wanted}

    def group_keys_for(self, question_ids: Iterable[Any]) -> dict[str, tuple[str, str]]:
        """``{str(question_id): group_key}`` — the GROUP BY key per id.  Callers
        that aggregate ``review_log`` / ``srs_cards`` re-bucket their rows on this
        without ever merging historically distinct records."""
        return {q: k.group_key for q, k in self.keys_for(question_ids).items()}

    # ---- admin lookup (LC015 §11) -------------------------- #

    def admin_lookup(self, *, legacy_question_id: Any = None,
                     source_record_uuid: str | None = None,
                     current_source_path: str | None = None,
                     historical_source_path: str | None = None) -> dict[str, Any]:
        """Exactly one of the four selectors.  AMBIGUOUS -> fail closed with the
        candidate list; the operator picks, never this code.  Unknown -> MISSING.
        Never fabricates."""
        given = [(k, v) for k, v in (
            ("legacy_question_id", legacy_question_id),
            ("source_record_uuid", source_record_uuid),
            ("current_source_path", current_source_path),
            ("historical_source_path", historical_source_path),
        ) if v is not None]
        if len(given) != 1:
            return {"status": "BAD_REQUEST",
                    "detail": "exactly one of legacy_question_id / source_record_uuid / "
                              "current_source_path / historical_source_path is required",
                    "given": [k for k, _ in given]}
        selector, value = given[0]

        if selector == "source_record_uuid":
            ident = self._w._store.get_identity(str(value)) if self._w._tables_present() else None
            if ident is None:
                return {"status": "MISSING", "selector": selector, "value": str(value)}
            return {
                "status": "RETIRED" if ident["identity_status"] == "RETIRED" else "EXACT",
                "selector": selector, "value": str(value),
                "source_record_uuid": ident["source_record_uuid"],
                "identity_kind": ident["identity_kind"],
                "identity_status": ident["identity_status"],
                "retired": ident["identity_status"] == "RETIRED",
                "attachable": ident["identity_status"] == "ACTIVE",
                "legacy_question_ids": list(self._w.legacy_question_ids_for(str(value))),
                "current_source_path": self._w.current_source_path_for(str(value)),
            }

        if selector == "legacy_question_id":
            res = self._w.resolve_legacy_question_id(value)
        elif selector == "current_source_path":
            res = self._w.resolve_current_source_path(str(value))
        else:
            res = self._w.resolve_historical_source_path(str(value))

        base = {"status": res.status, "selector": selector, "value": str(value),
                "detail": res.detail}
        if res.status == ResolutionStatus.AMBIGUOUS:
            base["candidates"] = list(res.candidates)
            return base
        if res.status in (ResolutionStatus.MISSING, ResolutionStatus.UNAVAILABLE):
            return base
        u = res.source_record_uuid
        base.update({
            "source_record_uuid": u,
            "retired": res.retired,
            "attachable": res.status == ResolutionStatus.EXACT,
            "legacy_question_ids": list(self._w.legacy_question_ids_for(u)),
            "current_source_path": self._w.current_source_path_for(u),
        })
        return base


# ---- thin functional entry points (what a future app.py wire calls) ------ #

def identity_key_for_read(conn: Any, question_id: Any) -> IdentityKey:
    return BootstrapGatedIdentityReader(conn).key_for(question_id)


def identity_keys_for_aggregate(conn: Any, question_ids: Iterable[Any]) -> dict[str, IdentityKey]:
    return BootstrapGatedIdentityReader(conn).keys_for(question_ids)


def admin_identity_lookup(conn: Any, **selectors: Any) -> dict[str, Any]:
    return BootstrapGatedIdentityReader(conn).admin_lookup(**selectors)


__all__ = [
    "BootstrapGatedIdentityReader",
    "IdentityKey",
    "IdentityKeyKind",
    "IdentityNotAttachable",
    "admin_identity_lookup",
    "identity_key_for_read",
    "identity_keys_for_aggregate",
]
