"""LC014 — the dual-ID resolver / identity read window.

A **read-only** lens between the legacy integer ``question_id`` and the permanent
``source_record_uuid``.  It is safe to call at any time — including before the
real genesis bootstrap has run — and it never mutates anything:

  * exact single current binding      -> ``EXACT`` (uuid returned)
  * exact binding, identity retired    -> ``RETIRED`` (uuid still returned)
  * >1 current identity for the alias  -> ``AMBIGUOUS`` (fail closed, uuid = None)
  * no current binding                 -> ``MISSING`` (explicit unresolved)
  * identity tables absent on the conn -> ``UNAVAILABLE`` (explicit unresolved)

**NO SILENT FALLBACK.**  When an identity cannot be resolved the window returns a
typed unresolved result — it never invents an identity, never calls a
create/mint path, and the legacy integer ``question_id`` stays valid for callers
throughout the dual-ID window.  This module imports only the *read* surface of
``PuzzleIdentityStore``; it has no access to ``create_*`` / ``mint_*`` /
``GenesisBootstrap``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from puzzle_identity_store import (
    AmbiguousAliasError,
    PuzzleIdentityError,
    PuzzleIdentityStore,
)


class ResolutionStatus:
    EXACT = "EXACT"
    RETIRED = "RETIRED"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"


_RESOLVED = (ResolutionStatus.EXACT, ResolutionStatus.RETIRED)
_UNRESOLVED = (ResolutionStatus.AMBIGUOUS, ResolutionStatus.MISSING,
               ResolutionStatus.UNAVAILABLE)


@dataclass(frozen=True)
class IdentityResolution:
    status: str
    alias_kind: str
    alias_value: str
    source_record_uuid: str | None = None
    retired: bool = False
    candidates: tuple[str, ...] = field(default_factory=tuple)
    detail: str = ""

    @property
    def resolved(self) -> bool:
        """A single identity was found (may be retired)."""
        return self.status in _RESOLVED and self.source_record_uuid is not None

    @property
    def attachable(self) -> bool:
        """New data may be bound to this identity (ACTIVE only — never retired)."""
        return self.status == ResolutionStatus.EXACT and self.source_record_uuid is not None

    @property
    def unresolved(self) -> bool:
        return self.status in _UNRESOLVED

    def uuid_or_legacy(self, legacy_question_id: Any) -> tuple[str, str]:
        """The dual-ID join key for the migration window: the UUID once the
        identity resolves exactly, otherwise the legacy id (still valid)."""
        if self.status == ResolutionStatus.EXACT and self.source_record_uuid:
            return ("uuid", self.source_record_uuid)
        return ("legacy", str(legacy_question_id))


class DualIdReadWindow:
    """Read-only resolver over ``puzzle_identity_alias`` for the target callers
    (review_log, SRS, admin lookup, Learning Core / Adventure identity reads)."""

    LEGACY_QUESTION_ID = "LEGACY_QUESTION_ID"
    CURRENT_SOURCE_PATH = "CURRENT_SOURCE_PATH"
    CANONICAL_SOURCE_KEY = "CANONICAL_SOURCE_KEY"
    HISTORICAL_SOURCE_PATH = "HISTORICAL_SOURCE_PATH"

    def __init__(self, conn: Any) -> None:
        self._store = PuzzleIdentityStore(conn)
        self._tables: bool | None = None

    # ---- internals -------------------------------------------------- #

    def _tables_present(self) -> bool:
        if self._tables is None:
            self._tables = self._store.has_identity_tables()
        return self._tables

    def _unavailable(self, kind: str, value: Any) -> IdentityResolution:
        return IdentityResolution(
            status=ResolutionStatus.UNAVAILABLE, alias_kind=kind,
            alias_value=str(value), detail="identity tables not present on this connection",
        )

    def _resolve_one(self, kind: str, value: Any, *,
                     alias_context: str | None = None) -> IdentityResolution:
        if not self._tables_present():
            return self._unavailable(kind, value)
        try:
            res = self._store.resolve(kind, str(value), alias_context=alias_context)
        except AmbiguousAliasError as exc:
            return IdentityResolution(
                status=ResolutionStatus.AMBIGUOUS, alias_kind=kind, alias_value=str(value),
                candidates=tuple(getattr(exc, "candidates", ()) or ()),
                detail=f"{kind}={value!r} resolves to multiple current identities",
            )
        except PuzzleIdentityError as exc:
            # unsupported alias kind / malformed input — treat as explicit MISSING,
            # never fabricate.
            return IdentityResolution(
                status=ResolutionStatus.MISSING, alias_kind=kind, alias_value=str(value),
                detail=str(exc),
            )
        if res["status"] == "MISSING":
            return IdentityResolution(status=ResolutionStatus.MISSING, alias_kind=kind,
                                      alias_value=str(value), detail="no current binding")
        retired = res["status"] == "RETIRED"
        return IdentityResolution(
            status=ResolutionStatus.RETIRED if retired else ResolutionStatus.EXACT,
            alias_kind=kind, alias_value=str(value),
            source_record_uuid=res["source_record_uuid"], retired=retired,
            detail="retired identity (still resolvable)" if retired else "exact single binding",
        )

    # ---- forward resolution -------------------------------------- #

    def resolve_legacy_question_id(self, question_id: Any) -> IdentityResolution:
        """Context-agnostic: a legacy id bound in >1 alias context to different
        identities fails closed as AMBIGUOUS."""
        return self._resolve_one(self.LEGACY_QUESTION_ID, question_id, alias_context=None)

    def resolve_current_source_path(self, path: str) -> IdentityResolution:
        return self._resolve_one(self.CURRENT_SOURCE_PATH, path, alias_context=None)

    def resolve_canonical_source(self, canonical_source: str) -> IdentityResolution:
        return self._resolve_one(self.CANONICAL_SOURCE_KEY, canonical_source, alias_context=None)

    def resolve_historical_source_path(self, path: str) -> IdentityResolution:
        return self._resolve_one(self.HISTORICAL_SOURCE_PATH, path, alias_context=None)

    def resolve_many_legacy_question_ids(
        self, question_ids: Iterable[Any]
    ) -> dict[str, IdentityResolution]:
        wanted = [str(q) for q in question_ids]
        if not self._tables_present():
            return {q: self._unavailable(self.LEGACY_QUESTION_ID, q) for q in wanted}
        batch = self._store.resolve_batch(self.LEGACY_QUESTION_ID, wanted, alias_context=None)
        out: dict[str, IdentityResolution] = {}
        for q in wanted:
            r = batch.get(q, {"status": "MISSING", "source_record_uuid": None})
            st = r["status"]
            if st == "AMBIGUOUS":
                out[q] = IdentityResolution(
                    status=ResolutionStatus.AMBIGUOUS, alias_kind=self.LEGACY_QUESTION_ID,
                    alias_value=q, candidates=tuple(r.get("candidates", ())),
                    detail="multiple current identities")
            elif st == "MISSING":
                out[q] = IdentityResolution(
                    status=ResolutionStatus.MISSING, alias_kind=self.LEGACY_QUESTION_ID,
                    alias_value=q, detail="no current binding")
            else:
                retired = st == "RETIRED"
                out[q] = IdentityResolution(
                    status=ResolutionStatus.RETIRED if retired else ResolutionStatus.EXACT,
                    alias_kind=self.LEGACY_QUESTION_ID, alias_value=q,
                    source_record_uuid=r["source_record_uuid"], retired=retired,
                    detail="retired (still resolvable)" if retired else "exact single binding")
        return out

    # ---- reverse lookup (admin / audit) ------------------------ #

    def legacy_question_ids_for(self, source_record_uuid: str) -> tuple[str, ...]:
        if not self._tables_present():
            return ()
        try:
            return tuple(self._store.aliases_of_kind(
                source_record_uuid, self.LEGACY_QUESTION_ID, current_only=True))
        except PuzzleIdentityError:
            return ()

    def current_source_path_for(self, source_record_uuid: str) -> str | None:
        if not self._tables_present():
            return None
        try:
            paths = self._store.aliases_of_kind(
                source_record_uuid, self.CURRENT_SOURCE_PATH, current_only=True)
        except PuzzleIdentityError:
            return None
        return paths[0] if len(paths) == 1 else None

    # ---- dual-ID window state --------------------------------- #

    def dual_id_key(self, question_id: Any) -> tuple[str, str]:
        """Join key for the migration window: ``("uuid", <uuid>)`` once the
        identity resolves exactly, else ``("legacy", <question_id>)``."""
        return self.resolve_legacy_question_id(question_id).uuid_or_legacy(question_id)

    def bootstrap_state(self) -> dict[str, Any]:
        """Whether the read window is 'hot' — i.e. genesis identities exist and a
        caller may start routing reads through it.  Before that, callers keep
        using the legacy integer ``question_id`` unchanged."""
        if not self._tables_present():
            return {"tables_present": False, "genesis_applied": False,
                    "identity_count": 0, "hot": False}
        try:
            n = self._store.count_identities()
            applied = self._store.genesis_bootstrap_applied()
        except PuzzleIdentityError:
            n, applied = 0, False
        return {"tables_present": True, "genesis_applied": applied,
                "identity_count": n, "hot": bool(applied and n > 0)}


__all__ = [
    "DualIdReadWindow",
    "IdentityResolution",
    "ResolutionStatus",
]
