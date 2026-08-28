"""Narrow, gated interface for the *future* one-time genesis bootstrap.

LC013 / LC013-R1 define and test this interface with **synthetic** data (and by
READING + HASHING the immutable LC012-R2 canonical artifacts).  It is never
invoked for the real 42,804 frozen identities — that remains an explicit
owner-gated operation for a later task.

Correctness contract (LC013-R1):
  * the caller supplies the *exact* immutable LC012-R2 artifacts unchanged
    (``lc012_p2_genesis_receipt.json`` has no self-sha field — the verifier
    computes ``receipt_sha256`` from the file bytes itself);
  * every immutable static fact is re-checked against the frozen constants and
    every dynamic hash is *recomputed* — ``genesis_bootstrap_safe_to_run`` is
    never trusted on its own;
  * the full 42,804-row manifest digest, the proposed-UUID-list digest, the
    918-entry rename-map digest, and the per-row ``uuidv5(namespace, gk1 ...
    canonical_source)`` binding are all recomputed with the accepted LC012-R2
    implementation;
  * apply() runs inside one bounded SAVEPOINT and only becomes durable with
    *all* rows written; a different receipt fails closed (``bootstrap_singleton``
    UNIQUE); the same receipt is an idempotent no-op.
"""
from __future__ import annotations

import hashlib
import json
import uuid as _uuid
from typing import Any, Mapping, Sequence

from puzzle_identity_store import PuzzleIdentityError, PuzzleIdentityStore

# Frozen genesis constants + accepted serialisation helpers (imported, never redefined).
from tools.lc012_p2_genesis_freeze import (
    KNOWN_PROPOSED_UUID_LIST_SHA256,
    OWNER_P2_TREE_COMMIT,
    OWNER_P2_TREE_MANIFEST_SHA256,
    manifest_sha256_from_rows,
    uuid_list_sha256_from_uuids,
)
from tools.lc012_sgf_source_tree_freeze import (
    GENESIS_SNAPSHOT_SHA256,
    EXPECTED_RECORD_COUNT,
)
from tools.lc011_identity_registry_prototype import (
    CANONICALISATION_RULES_VERSION,
    GENESIS_KEY_SPEC_VERSION,
    PROPOSED_CANONICAL_NAMESPACE_UUID,
    mint_genesis_uuid,
)

KNOWN_RECEIPT_SHA256 = "834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c"
KNOWN_RENAME_MAP_SHA256 = "473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d"
KNOWN_MANIFEST_SHA256 = "ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828"
EXPECTED_DIRECT_PATH_MATCH = 41886
EXPECTED_HISTORICAL_RENAME_MATCH = 918

_VALID_RELATIONS = {"DIRECT_PATH_MATCH", "HISTORICAL_RENAME_MATCH"}

# Static receipt facts that MUST equal the frozen constants (canonical mode).
_CANONICAL_RECEIPT_EXPECT = {
    "frozen_corpus_sha256": GENESIS_SNAPSHOT_SHA256,
    "frozen_record_count": EXPECTED_RECORD_COUNT,
    "identity_namespace": PROPOSED_CANONICAL_NAMESPACE_UUID,
    "canonicalization_version": CANONICALISATION_RULES_VERSION,
    "genesis_key_version": GENESIS_KEY_SPEC_VERSION,
    "historical_tree_commit": OWNER_P2_TREE_COMMIT,
    "historical_tree_manifest_sha256": OWNER_P2_TREE_MANIFEST_SHA256,
    "historical_rename_map_sha256": KNOWN_RENAME_MAP_SHA256,
    "genesis_record_manifest_sha256": KNOWN_MANIFEST_SHA256,
    "proposed_uuid_list_sha256": KNOWN_PROPOSED_UUID_LIST_SHA256,
    "provenance_rank": "B",
    "exact_build_binding": False,
}


class GenesisBootstrapError(PuzzleIdentityError):
    """The genesis bootstrap preconditions are not satisfied — fail closed."""


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------- #
# receipt / manifest verifier
# --------------------------------------------------------------------------- #

class GenesisReceiptVerifier:
    """Recompute and bind every immutable genesis fact before any write."""

    def __init__(
        self,
        *,
        receipt_bytes: bytes,
        manifest_rows: Sequence[Mapping[str, Any]],
        rename_map_bytes: bytes | None = None,
        require_canonical_genesis: bool = True,
    ) -> None:
        self.receipt_bytes = receipt_bytes
        self.receipt_sha256 = _sha256_bytes(receipt_bytes)
        try:
            self.receipt: dict[str, Any] = json.loads(receipt_bytes.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise GenesisBootstrapError(f"receipt is not valid JSON: {exc}") from exc
        self.rows = [dict(r) for r in manifest_rows]
        self.rename_map_bytes = rename_map_bytes
        self._require_canonical = require_canonical_genesis

    # -- individual recomputations ---------------------------------------- #

    def _check_static_facts(self, problems: list[str]) -> None:
        r = self.receipt
        if not self._require_canonical:
            return
        for key, expected in _CANONICAL_RECEIPT_EXPECT.items():
            if r.get(key) != expected:
                problems.append(f"receipt.{key}={r.get(key)!r} != frozen {expected!r}")
        if self.receipt_sha256 != KNOWN_RECEIPT_SHA256:
            problems.append(
                f"recomputed receipt sha256 {self.receipt_sha256} != known "
                f"{KNOWN_RECEIPT_SHA256} (artifact was altered)"
            )

    def _check_rename_map(self, problems: list[str]) -> None:
        if self.rename_map_bytes is None:
            return
        got = _sha256_bytes(self.rename_map_bytes)
        want = self.receipt.get("historical_rename_map_sha256")
        if got != want:
            problems.append(f"rename-map sha {got} != receipt {want}")
        if self._require_canonical and got != KNOWN_RENAME_MAP_SHA256:
            problems.append(f"rename-map sha {got} != frozen {KNOWN_RENAME_MAP_SHA256}")
        try:
            entries = json.loads(self.rename_map_bytes.decode("utf-8"))
        except Exception:  # noqa: BLE001
            problems.append("rename-map is not valid JSON")
            return
        if self._require_canonical and len(entries) != EXPECTED_HISTORICAL_RENAME_MATCH:
            problems.append(
                f"rename-map has {len(entries)} entries != {EXPECTED_HISTORICAL_RENAME_MATCH}"
            )
        self._rename_by_pre = {e["pre_reorg_source"]: e["post_reorg_source"]
                               for e in entries}

    def _check_manifest(self, problems: list[str]) -> dict[str, Any]:
        rows = self.rows
        counts = {"DIRECT_PATH_MATCH": 0, "HISTORICAL_RENAME_MATCH": 0,
                  "OTHER": 0, "missing_canonical": 0, "bad_relation": 0}
        seen: set[str] = set()
        uuid_bind_mismatch = 0
        rename_provenance_mismatch = 0
        rename_by_pre = getattr(self, "_rename_by_pre", None)

        for i, row in enumerate(rows):
            cs = row.get("canonical_source")
            u = row.get("source_record_uuid_proposed")
            rel = row.get("provenance_relation")

            if not cs:
                counts["missing_canonical"] += 1
                problems.append(f"row {i}: missing canonical_source")
            if rel not in _VALID_RELATIONS:
                counts["bad_relation"] += 1
                problems.append(f"row {i}: bad provenance_relation {rel!r}")
            else:
                counts[rel] += 1

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

            # §12 — the UUID must be exactly uuidv5(namespace, gk1 ... canonical_source)
            if cs:
                expected_uuid = mint_genesis_uuid(cs)
                if str(parsed) != expected_uuid:
                    uuid_bind_mismatch += 1
                    problems.append(
                        f"row {i}: uuid {u} != genesis-key uuid {expected_uuid} for {cs!r}"
                    )

            # §14 — rename provenance must be backed by the locked relation
            hist = row.get("historical_source")
            if rel == "DIRECT_PATH_MATCH":
                if hist not in (None, cs):
                    rename_provenance_mismatch += 1
                    problems.append(f"row {i}: DIRECT_PATH_MATCH but historical {hist!r} != {cs!r}")
            elif rel == "HISTORICAL_RENAME_MATCH" and rename_by_pre is not None:
                if cs not in rename_by_pre:
                    rename_provenance_mismatch += 1
                    problems.append(f"row {i}: HISTORICAL_RENAME_MATCH not in rename map: {cs!r}")
                elif hist is not None and hist != rename_by_pre[cs]:
                    rename_provenance_mismatch += 1
                    problems.append(
                        f"row {i}: rename target {hist!r} != map {rename_by_pre[cs]!r}"
                    )

        # digests
        recomputed_manifest_sha = manifest_sha256_from_rows(rows) if not problems else None
        recomputed_uuid_list_sha = uuid_list_sha256_from_uuids(
            [row.get("source_record_uuid_proposed") for row in rows]
        )

        want_manifest = self.receipt.get("genesis_record_manifest_sha256")
        want_uuid_list = self.receipt.get("proposed_uuid_list_sha256")
        if recomputed_manifest_sha is not None and recomputed_manifest_sha != want_manifest:
            problems.append(f"recomputed manifest sha {recomputed_manifest_sha} != receipt {want_manifest}")
        if recomputed_uuid_list_sha != want_uuid_list:
            problems.append(f"recomputed uuid-list sha {recomputed_uuid_list_sha} != receipt {want_uuid_list}")
        if self._require_canonical:
            if recomputed_manifest_sha not in (None, KNOWN_MANIFEST_SHA256):
                problems.append(f"manifest sha {recomputed_manifest_sha} != frozen {KNOWN_MANIFEST_SHA256}")
            if recomputed_uuid_list_sha != KNOWN_PROPOSED_UUID_LIST_SHA256:
                problems.append(f"uuid-list sha {recomputed_uuid_list_sha} != frozen {KNOWN_PROPOSED_UUID_LIST_SHA256}")
            if len(rows) != EXPECTED_RECORD_COUNT:
                problems.append(f"manifest row count {len(rows)} != {EXPECTED_RECORD_COUNT}")
            if counts["DIRECT_PATH_MATCH"] != EXPECTED_DIRECT_PATH_MATCH:
                problems.append(f"DIRECT_PATH_MATCH {counts['DIRECT_PATH_MATCH']} != {EXPECTED_DIRECT_PATH_MATCH}")
            if counts["HISTORICAL_RENAME_MATCH"] != EXPECTED_HISTORICAL_RENAME_MATCH:
                problems.append(f"HISTORICAL_RENAME_MATCH {counts['HISTORICAL_RENAME_MATCH']} != {EXPECTED_HISTORICAL_RENAME_MATCH}")

        return {
            "genesis_records": len(rows),
            "direct_path_match_count": counts["DIRECT_PATH_MATCH"],
            "historical_rename_match_count": counts["HISTORICAL_RENAME_MATCH"],
            "missing": counts["missing_canonical"],
            "ambiguous": 0,
            "distinct_uuid": len(seen),
            "uuid_collisions": len(rows) - len(seen) if not problems else None,
            "uuid_canonical_source_binding_mismatch": uuid_bind_mismatch,
            "rename_provenance_mismatch": rename_provenance_mismatch,
            "recomputed_genesis_record_manifest_sha256": recomputed_manifest_sha,
            "recomputed_uuid_list_sha256": recomputed_uuid_list_sha,
        }

    def verify(self) -> dict[str, Any]:
        problems: list[str] = []
        gate = self.receipt.get("genesis_bootstrap_once_only_gate") or {}
        # recorded for transparency only — NOT trusted as sufficient
        safe_flag = bool(gate.get("genesis_bootstrap_safe_to_run"))
        self._check_static_facts(problems)
        self._check_rename_map(problems)
        stats = self._check_manifest(problems)
        return {
            "ok": not problems,
            "problems": problems,
            "receipt_sha256": self.receipt_sha256,
            "safe_to_run_flag_recorded": safe_flag,
            "safe_to_run_trusted_without_recompute": False,
            **stats,
        }


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #

class GenesisBootstrap:
    def __init__(
        self,
        store: PuzzleIdentityStore,
        verifier: GenesisReceiptVerifier,
    ) -> None:
        self._store = store
        self._conn = store._conn
        self._v = verifier

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

    # ---- preflight / apply ------------------------------------- #

    def preflight(self) -> dict[str, Any]:
        v = self._v.verify()
        prior = self._existing_bootstrap()
        registry_count = self._registry_count()
        problems = list(v["problems"])
        if prior is None and registry_count != 0:
            problems.append(f"registry not empty ({registry_count}) with no bootstrap receipt")
        return {**v, "ok": not problems, "problems": problems,
                "prior_bootstrap": prior, "registry_count": registry_count}

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
            return {"status": "DRY_RUN", "would_write": len(self._v.rows),
                    "receipt_sha256": sha}

        r = self._v.receipt
        rows = self._v.rows
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
                    sha, r.get("frozen_corpus_sha256"),
                    int(r.get("frozen_record_count") or len(rows)),
                    r.get("identity_namespace"), r.get("canonicalization_version"),
                    r.get("genesis_key_version"), r.get("historical_tree_commit"),
                    r.get("historical_tree_manifest_sha256"),
                    r.get("historical_rename_map_sha256"),
                    r.get("genesis_record_manifest_sha256"),
                    r.get("proposed_uuid_list_sha256"),
                    len(rows), when, applied_by,
                ),
            )
            for row in rows:
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
            # §17 atomicity — APPLIED must not become durable with a short count
            cur = self._store._exec(
                "SELECT COUNT(*) FROM puzzle_identity_registry WHERE genesis_receipt_ref = ?",
                (sha,),
            )
            row = cur.fetchone()
            if not hasattr(self._conn, "execute"):
                cur.close()
            written = int((row[0] if not hasattr(row, "keys")
                           else row[list(row.keys())[0]]) or 0)
            if written != len(rows):
                raise GenesisBootstrapError(
                    f"post-write count {written} != expected {len(rows)} — rolling back"
                )

        return {"status": "APPLIED", "identities_written": len(rows), "receipt_sha256": sha}


__all__ = ["GenesisBootstrap", "GenesisBootstrapError", "GenesisReceiptVerifier"]
