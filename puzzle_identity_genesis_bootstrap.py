"""Narrow, gated interface for the *future* one-time genesis bootstrap.

LC013 defines this interface and tests it with **synthetic** data only.  It is
never invoked for the real 42,804 frozen identities — that remains an explicit
owner-gated operation for a later task.

Contract:
  * validate the LC012-R2 immutable receipt inputs *first* (against the frozen
    constants) — fail closed on any mismatch;
  * require an empty / not-already-bootstrapped target;
  * apply inside one bounded transactional unit (SAVEPOINT) — all-or-nothing;
  * be idempotency-safe: re-running the *same* receipt is a no-op, a *different*
    receipt fails closed (the ``bootstrap_singleton`` UNIQUE row guarantees it).
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any, Mapping, Sequence

from puzzle_identity_store import PuzzleIdentityError, PuzzleIdentityStore

# Frozen genesis constants (LC011 / LC012 / LC012-R2). Imported, never redefined.
from tools.lc012_p2_genesis_freeze import (
    KNOWN_PROPOSED_UUID_LIST_SHA256,
    OWNER_P2_TREE_COMMIT,
    OWNER_P2_TREE_MANIFEST_SHA256,
)
from tools.lc012_sgf_source_tree_freeze import (
    GENESIS_SNAPSHOT_SHA256,
    EXPECTED_RECORD_COUNT,
)
from tools.lc011_identity_registry_prototype import (
    CANONICALISATION_RULES_VERSION,
    GENESIS_KEY_SPEC_VERSION,
    PROPOSED_CANONICAL_NAMESPACE_UUID,
)

_VALID_RELATIONS = {"DIRECT_PATH_MATCH", "HISTORICAL_RENAME_MATCH"}

_CANONICAL_RECEIPT_EXPECT = {
    "frozen_corpus_sha256": GENESIS_SNAPSHOT_SHA256,
    "frozen_record_count": EXPECTED_RECORD_COUNT,
    "identity_namespace": PROPOSED_CANONICAL_NAMESPACE_UUID,
    "canonicalization_version": CANONICALISATION_RULES_VERSION,
    "genesis_key_version": GENESIS_KEY_SPEC_VERSION,
    "historical_tree_commit": OWNER_P2_TREE_COMMIT,
    "historical_tree_manifest_sha256": OWNER_P2_TREE_MANIFEST_SHA256,
    "proposed_uuid_list_sha256": KNOWN_PROPOSED_UUID_LIST_SHA256,
    "provenance_rank": "B",
    "exact_build_binding": False,
}


class GenesisBootstrapError(PuzzleIdentityError):
    """The genesis bootstrap preconditions are not satisfied — fail closed."""


class GenesisBootstrap:
    def __init__(
        self,
        store: PuzzleIdentityStore,
        receipt: Mapping[str, Any],
        manifest_rows: Sequence[Mapping[str, Any]],
        *,
        require_canonical_genesis: bool = True,
    ) -> None:
        self._store = store
        self._conn = store._conn  # same connection / transaction
        self._receipt = dict(receipt)
        self._rows = list(manifest_rows)
        self._require_canonical = require_canonical_genesis

    # ---- preflight ---------------------------------------------------- #

    def preflight(self) -> dict[str, Any]:
        r = self._receipt
        problems: list[str] = []

        sha = r.get("_receipt_sha256") or r.get("receipt_sha256")
        if not sha or not isinstance(sha, str) or len(sha) != 64:
            problems.append("receipt sha256 missing/invalid")

        gate = r.get("genesis_bootstrap_once_only_gate") or {}
        if not gate.get("genesis_bootstrap_safe_to_run"):
            problems.append("receipt once-only gate is not safe_to_run")

        if self._require_canonical:
            for key, expected in _CANONICAL_RECEIPT_EXPECT.items():
                if r.get(key) != expected:
                    problems.append(f"receipt.{key}={r.get(key)!r} != frozen {expected!r}")
            expected_rows = EXPECTED_RECORD_COUNT
        else:
            expected_rows = int(r.get("frozen_record_count") or len(self._rows))

        if len(self._rows) != expected_rows:
            problems.append(f"manifest row count {len(self._rows)} != {expected_rows}")

        seen: set[str] = set()
        for i, row in enumerate(self._rows):
            u = row.get("source_record_uuid_proposed")
            try:
                parsed = _uuid.UUID(str(u))
            except Exception:  # noqa: BLE001
                problems.append(f"row {i}: invalid uuid {u!r}")
                continue
            if parsed.version != 5:
                problems.append(f"row {i}: uuid {u} is not v5")
            if str(parsed) in seen:
                problems.append(f"row {i}: duplicate uuid {u}")
            seen.add(str(parsed))
            if not row.get("canonical_source"):
                problems.append(f"row {i}: missing canonical_source")
            if row.get("provenance_relation") not in _VALID_RELATIONS:
                problems.append(f"row {i}: bad provenance_relation "
                                f"{row.get('provenance_relation')!r}")

        prior = self._existing_bootstrap()
        registry_count = self._registry_count()
        if prior is None and registry_count != 0:
            problems.append(f"registry not empty ({registry_count}) with no bootstrap receipt")

        return {
            "ok": not problems,
            "problems": problems,
            "receipt_sha256": sha,
            "manifest_rows": len(self._rows),
            "prior_bootstrap": prior,
            "registry_count": registry_count,
            "require_canonical_genesis": self._require_canonical,
        }

    # ---- apply ----------------------------------------------------- #

    def apply(self, *, applied_by: str, when: str, dry_run: bool = False) -> dict[str, Any]:
        pf = self.preflight()
        sha = pf["receipt_sha256"]

        prior = pf["prior_bootstrap"]
        if prior is not None:
            if prior["receipt_sha256"] == sha and prior["status"] == "APPLIED":
                if pf["registry_count"] == prior["identities_written"]:
                    return {"status": "ALREADY_APPLIED", "idempotent": True,
                            "identities_written": prior["identities_written"],
                            "receipt_sha256": sha}
                raise GenesisBootstrapError(
                    "bootstrap receipt present but registry count "
                    f"{pf['registry_count']} != recorded {prior['identities_written']}"
                )
            raise GenesisBootstrapError(
                f"a different genesis bootstrap already ran (existing "
                f"{prior['receipt_sha256']}, requested {sha})"
            )

        if not pf["ok"]:
            raise GenesisBootstrapError(f"preflight failed: {pf['problems']}")

        if dry_run:
            return {"status": "DRY_RUN", "would_write": len(self._rows),
                    "receipt_sha256": sha}

        r = self._receipt
        with self._store._unit("bootstrap"):
            self._store._exec(
                "INSERT INTO puzzle_identity_bootstrap_receipt "
                "(receipt_sha256, bootstrap_singleton, frozen_corpus_sha256, record_count, "
                " namespace_uuid, canonicalisation_rules_version, genesis_key_spec_version, "
                " historical_tree_commit, historical_tree_manifest_sha256, "
                " historical_rename_map_sha256, genesis_record_manifest_sha256, "
                " proposed_uuid_list_sha256, status, identities_written, applied_at, applied_by) "
                "VALUES (?, 'GENESIS', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'APPLIED', ?, ?, ?)",
                (
                    sha,
                    r.get("frozen_corpus_sha256"),
                    int(r.get("frozen_record_count") or len(self._rows)),
                    r.get("identity_namespace"),
                    r.get("canonicalization_version"),
                    r.get("genesis_key_version"),
                    r.get("historical_tree_commit"),
                    r.get("historical_tree_manifest_sha256"),
                    r.get("historical_rename_map_sha256"),
                    r.get("genesis_record_manifest_sha256"),
                    r.get("proposed_uuid_list_sha256"),
                    len(self._rows),
                    when,
                    applied_by,
                ),
            )
            for row in self._rows:
                canonical = row["canonical_source"]
                historical = row.get("historical_source")
                self._store.create_historical_genesis_identity(
                    row["source_record_uuid_proposed"],
                    receipt_sha256=sha,
                    canonical_source=canonical,
                    legacy_question_id=row.get("legacy_question_id"),
                    historical_source_path=(historical if historical and historical != canonical
                                            else None),
                    creation_reason="LC012-R2 P2 genesis receipt " + sha,
                    when=when,
                )

        return {"status": "APPLIED", "identities_written": len(self._rows),
                "receipt_sha256": sha}

    # ---- helpers ------------------------------------------------- #

    def _existing_bootstrap(self) -> dict[str, Any] | None:
        cur = self._store._exec(
            "SELECT receipt_sha256, status, identities_written "
            "FROM puzzle_identity_bootstrap_receipt WHERE bootstrap_singleton='GENESIS'"
        )
        row = cur.fetchone()
        if not hasattr(self._conn, "execute"):
            cur.close()
        if row is None:
            return None
        get = (lambda k, i: row[k]) if hasattr(row, "keys") else (lambda k, i: row[i])
        return {
            "receipt_sha256": get("receipt_sha256", 0),
            "status": get("status", 1),
            "identities_written": int(get("identities_written", 2) or 0),
        }

    def _registry_count(self) -> int:
        cur = self._store._exec("SELECT COUNT(*) FROM puzzle_identity_registry")
        row = cur.fetchone()
        if not hasattr(self._conn, "execute"):
            cur.close()
        return int((row[0] if not hasattr(row, "keys") else row[list(row.keys())[0]]) or 0)


__all__ = ["GenesisBootstrap", "GenesisBootstrapError"]
