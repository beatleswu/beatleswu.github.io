"""Server-authoritative Future30 catalog and character entitlement service.

This module is deliberately separate from ``player_appearance``:

* ``future30_character_catalog`` is admission plus exact C005 runtime mapping;
* ``player_character_entitlements`` is durable ownership and acquisition source;
* ``player_appearance.character_key`` is the applied presentation selection.

Callers own the transaction.  No helper in this module commits or rolls back.
The service never accepts a client asset id and never derives identity from a
GLB filename.
"""

from __future__ import annotations

import datetime as _datetime
from typing import Any

from future30_character_registry import (
    FUTURE30_C005_MANIFEST_SHA256,
    FUTURE30_CHARACTER_REGISTRY_VALID,
    FUTURE30_PRODUCT_MANIFEST_SHA256,
    FUTURE30_CHARACTER_KEYS,
    future30_visual_model_rows,
    future30_catalog_rows,
    future30_character_record,
    is_future30_character_key,
)
from migrations.future30_character_catalog_v1 import (
    ACQUISITION_SOURCES,
    CATALOG_TABLE,
    ENTITLEMENT_TABLE,
    VISUAL_TABLE,
    upgrade,
    validate_schema,
)


DEFAULT_CHARACTER_KEY = "apprentice"
ACCEPTANCE_ENVIRONMENTS = frozenset({"acceptance", "test", "local"})

# Owner-finalized G009 bootstrap authority.  This is the only acquisition
# assignment frozen here; STAGE, PREMIUM, and SHOP remain owner-unassigned.
STARTER_CHARACTER_KEYS = ("A1", "R1", "R2", "R3", "S2")
DEFAULT_STARTER_KEY = "A1"
STARTER_SOURCE_REFERENCE = "g009-starter-lazy-bootstrap"


class Future30ServiceError(RuntimeError):
    """Stable typed failure for server-side Future30 operations."""

    code = "FUTURE30_SERVICE_ERROR"
    status_code = 503

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)


class Future30CatalogUnavailable(Future30ServiceError):
    code = "FUTURE30_CATALOG_UNAVAILABLE"


class Future30UnknownCharacter(Future30ServiceError):
    code = "FUTURE30_UNKNOWN_CHARACTER"
    status_code = 400


class Future30CharacterNotEntitled(Future30ServiceError):
    code = "FUTURE30_CHARACTER_NOT_ENTITLED"
    status_code = 403


class Future30AcquisitionRejected(Future30ServiceError):
    code = "FUTURE30_ACQUISITION_REJECTED"
    status_code = 403


def _now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).replace(tzinfo=None).isoformat()


def _row_value(row: Any, name: str, index: int) -> Any:
    try:
        return row[name]
    except (KeyError, IndexError, TypeError):
        return row[index]


def _catalog_row_matches(expected: dict[str, Any], actual: Any) -> bool:
    for key in (
        "character_key", "display_name", "default_variant", "visual_model_id",
        "character_asset_id", "runtime_glb", "runtime_sha256", "admission_state",
        "license_status", "provenance_status", "authority_ref",
        "product_manifest_sha256", "c005_manifest_sha256",
    ):
        if _row_value(actual, key, 0) != expected[key]:
            return False
    return True


def _visual_row_matches(expected: dict[str, Any], actual: Any) -> bool:
    for key in (
        "visual_model_id", "character_key", "variant", "character_asset_id",
        "runtime_glb", "runtime_sha256", "mapping_status", "c005_manifest_sha256",
    ):
        if _row_value(actual, key, 0) != expected[key]:
            return False
    return True


def initialize_future30_catalog(conn: Any) -> dict[str, Any]:
    """Apply the schema and add missing canonical rows without rewriting any.

    This is called from the normal database initialization/migration path.
    Existing rows that drift from frozen authority are never repaired in place;
    validation fails closed so provenance drift remains visible.
    """

    schema = upgrade(conn)
    if not schema["valid"]:
        raise Future30CatalogUnavailable("Future30 catalog schema is incomplete")
    if (
        not FUTURE30_CHARACTER_REGISTRY_VALID
        or len(future30_catalog_rows()) != 30
        or len(future30_visual_model_rows()) != 33
    ):
        raise Future30CatalogUnavailable("canonical Future30 manifest is unavailable")

    timestamp = _now()
    for row in future30_catalog_rows():
        values = (
            row["character_key"], row["display_name"], row["default_variant"],
            row["visual_model_id"], row["character_asset_id"], row["runtime_glb"],
            row["runtime_sha256"], row["admission_state"], row["license_status"],
            row["provenance_status"], row["authority_ref"],
            FUTURE30_PRODUCT_MANIFEST_SHA256, FUTURE30_C005_MANIFEST_SHA256,
            timestamp, timestamp,
        )
        conn.execute(
            f"""INSERT INTO {CATALOG_TABLE} (
                character_key, display_name, default_variant, visual_model_id,
                character_asset_id, runtime_glb, runtime_sha256, admission_state,
                license_status, provenance_status, authority_ref,
                product_manifest_sha256, c005_manifest_sha256, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(character_key) DO NOTHING""",
            values,
        )
    for visual in future30_visual_model_rows():
        conn.execute(
            f"""INSERT INTO {VISUAL_TABLE} (
                visual_model_id, character_key, variant, character_asset_id,
                runtime_glb, runtime_sha256, mapping_status, c005_manifest_sha256
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(visual_model_id) DO NOTHING""",
            (
                visual["visual_model_id"], visual["character_key"], visual["variant"],
                visual["character_asset_id"], visual["runtime_glb"],
                visual["runtime_sha256"], visual["mapping_status"],
                FUTURE30_C005_MANIFEST_SHA256,
            ),
        )
    return ensure_future30_catalog(conn)


def ensure_future30_catalog(conn: Any) -> dict[str, Any]:
    """Read-only validation of the exact catalog seeded by migration/init."""

    if (
        not FUTURE30_CHARACTER_REGISTRY_VALID
        or not FUTURE30_CHARACTER_KEYS
        or len(future30_visual_model_rows()) != 33
    ):
        raise Future30CatalogUnavailable("canonical Future30 manifest is unavailable")
    schema = validate_schema(conn)
    if not schema["valid"]:
        raise Future30CatalogUnavailable("Future30 catalog schema is incomplete")

    rows = future30_catalog_rows()
    db_rows = conn.execute(
        f"SELECT * FROM {CATALOG_TABLE} ORDER BY character_key"
    ).fetchall()
    expected_by_key = {row["character_key"]: row for row in rows}
    actual_keys = {_row_value(row, "character_key", 0) for row in db_rows}
    if actual_keys != set(expected_by_key) or len(db_rows) != 30:
        raise Future30CatalogUnavailable("Future30 catalog contains an unexpected roster")
    for db_row in db_rows:
        key = _row_value(db_row, "character_key", 0)
        if not _catalog_row_matches(
            {
                **expected_by_key[key],
                "product_manifest_sha256": FUTURE30_PRODUCT_MANIFEST_SHA256,
                "c005_manifest_sha256": FUTURE30_C005_MANIFEST_SHA256,
            },
            db_row,
        ):
            raise Future30CatalogUnavailable(f"Future30 mapping mismatch: {key}")

    visual_rows = future30_visual_model_rows()
    db_visual_rows = conn.execute(
        f"SELECT * FROM {VISUAL_TABLE} ORDER BY visual_model_id"
    ).fetchall()
    expected_visual_by_id = {row["visual_model_id"]: row for row in visual_rows}
    actual_visual_ids = {_row_value(row, "visual_model_id", 0) for row in db_visual_rows}
    if actual_visual_ids != set(expected_visual_by_id) or len(db_visual_rows) != 33:
        raise Future30CatalogUnavailable("Future30 visual catalog contains an unexpected roster")
    for db_row in db_visual_rows:
        visual_id = _row_value(db_row, "visual_model_id", 0)
        if not _visual_row_matches(
            {
                **expected_visual_by_id[visual_id],
                "c005_manifest_sha256": FUTURE30_C005_MANIFEST_SHA256,
            },
            db_row,
        ):
            raise Future30CatalogUnavailable(f"Future30 visual mapping mismatch: {visual_id}")

    return {
        "logical_count": 30,
        "visual_count": 33,
        "character_keys": [row["character_key"] for row in rows],
        "product_manifest_sha256": FUTURE30_PRODUCT_MANIFEST_SHA256,
        "c005_manifest_sha256": FUTURE30_C005_MANIFEST_SHA256,
    }


def _require_canonical_key(character_key: Any) -> str:
    if not isinstance(character_key, str) or not is_future30_character_key(character_key):
        raise Future30UnknownCharacter("Future30 character_key is not in the canonical roster")
    if future30_character_record(character_key) is None:
        raise Future30CatalogUnavailable("Future30 character has no default runtime mapping")
    return character_key


def resolve_future30_mapping(conn: Any, character_key: Any) -> dict[str, Any]:
    key = _require_canonical_key(character_key)
    ensure_future30_catalog(conn)
    row = conn.execute(
        f"SELECT * FROM {CATALOG_TABLE} WHERE character_key=?", (key,)
    ).fetchone()
    if not row or _row_value(row, "admission_state", 0) != "ENABLED":
        raise Future30CatalogUnavailable(f"Future30 character is not admitted: {key}")
    expected = future30_character_record(key)
    if not expected or not _catalog_row_matches(
        {
            **expected,
            "product_manifest_sha256": FUTURE30_PRODUCT_MANIFEST_SHA256,
            "c005_manifest_sha256": FUTURE30_C005_MANIFEST_SHA256,
        },
        row,
    ):
        raise Future30CatalogUnavailable(f"Future30 mapping is not canonical: {key}")
    return {
        "character_key": key,
        "display_name": _row_value(row, "display_name", 1),
        "default_variant": _row_value(row, "default_variant", 2),
        "visual_model_id": _row_value(row, "visual_model_id", 3),
        "character_asset_id": _row_value(row, "character_asset_id", 4),
        "runtime_glb": _row_value(row, "runtime_glb", 5),
        "runtime_sha256": _row_value(row, "runtime_sha256", 6),
        "product_manifest_sha256": _row_value(row, "product_manifest_sha256", 12),
        "c005_manifest_sha256": _row_value(row, "c005_manifest_sha256", 13),
    }


def _entitlement_row(
    conn: Any,
    user_id: int,
    character_key: str,
    *,
    allow_acceptance_test: bool = False,
) -> Any:
    test_clause = "" if allow_acceptance_test else " AND acquisition_source <> 'ACCEPTANCE_TEST'"
    return conn.execute(
        f"SELECT user_id, character_key, acquisition_source, source_reference, acquired_at "
        f"FROM {ENTITLEMENT_TABLE} WHERE user_id=? AND character_key=?{test_clause}",
        (int(user_id), character_key),
    ).fetchone()


def grant_future30_character(
    conn: Any,
    user_id: int,
    character_key: str,
    acquisition_source: str,
    *,
    environment: str = "production",
    allow_acceptance_test: bool = False,
    source_reference: str | None = None,
) -> dict[str, Any]:
    """Grant one permanent entitlement through an authority-owned caller.

    This is intentionally a service API, not a public client route.  A caller
    must choose a declared source; no stage thresholds, shop prices, premium
    cadence, or character assignment policy are created here.
    """

    key = _require_canonical_key(character_key)
    source = str(acquisition_source or "").strip().upper()
    if source not in ACQUISITION_SOURCES:
        raise Future30AcquisitionRejected("unsupported Future30 acquisition source")
    env = str(environment or "production").strip().lower()
    if source == "ACCEPTANCE_TEST" and (
        env not in ACCEPTANCE_ENVIRONMENTS or allow_acceptance_test is not True
    ):
        raise Future30AcquisitionRejected("ACCEPTANCE_TEST is isolated-only and disabled by default")

    resolve_future30_mapping(conn, key)
    ensure_future30_catalog(conn)
    timestamp = _now()
    result = conn.execute(
        f"""INSERT INTO {ENTITLEMENT_TABLE} (
            user_id, character_key, acquisition_source, source_reference, acquired_at
        ) VALUES (?,?,?,?,?)
        ON CONFLICT(user_id, character_key) DO NOTHING""",
        (int(user_id), key, source, source_reference, timestamp),
    )
    # The grant path must see the immutable first source even when it is an
    # isolated ACCEPTANCE_TEST row; user-facing projections remain filtered.
    row = _entitlement_row(conn, int(user_id), key, allow_acceptance_test=True)
    return {
        "user_id": int(user_id),
        "character_key": key,
        "acquisition_source": _row_value(row, "acquisition_source", 2) if row else source,
        "source_reference": _row_value(row, "source_reference", 3) if row else source_reference,
        "acquired_at": _row_value(row, "acquired_at", 4) if row else timestamp,
        "created": bool(getattr(result, "rowcount", 0) == 1),
        "permanent": True,
    }


def _lock_starter_bootstrap_user(conn: Any, user_id: int) -> None:
    """Serialize one authenticated bootstrap transaction per user.

    The existing users row is the lock authority. SQLite already serializes
    its write connection, while PostgreSQL uses the row lock so two Hero/
    Appearance requests cannot race the active-selection decision.
    """

    raw_conn = getattr(conn, "_conn", conn)
    is_sqlite = raw_conn.__class__.__module__.lower().startswith("sqlite3")
    suffix = "" if is_sqlite else " FOR UPDATE"
    row = conn.execute(
        f"SELECT id FROM users WHERE id=?{suffix}", (int(user_id),)
    ).fetchone()
    if not row:
        raise Future30ServiceError("authenticated user does not exist")


def ensure_future30_starter_bootstrap(
    conn: Any,
    user_id: int,
    *,
    source_reference: str = STARTER_SOURCE_REFERENCE,
    allow_acceptance_test: bool = False,
) -> dict[str, Any]:
    """Lazily grant all five permanent STARTER entitlements and choose A1.

    This is deliberately a player-state boundary helper, not middleware and
    not a batch/backfill API.  The caller owns the transaction.  Existing
    valid Future30 selections are preserved; a legacy, missing, or unentitled
    selection is moved to the canonical A1 default only after the five
    idempotent STARTER rows are ensured.
    """

    uid = int(user_id)
    _lock_starter_bootstrap_user(conn, uid)
    ensure_future30_catalog(conn)

    appearance = conn.execute(
        "SELECT character_key FROM player_appearance WHERE user_id=?", (uid,)
    ).fetchone()
    stored_key = _row_value(appearance, "character_key", 0) if appearance else None

    created: list[str] = []
    for key in STARTER_CHARACTER_KEYS:
        result = grant_future30_character(
            conn,
            uid,
            key,
            "STARTER",
            environment="production",
            source_reference=source_reference,
        )
        if result["created"]:
            created.append(key)

    active_key = None
    if is_future30_character_key(stored_key):
        projection = project_applied_character(
            conn,
            uid,
            stored_key,
            allow_acceptance_test=allow_acceptance_test,
        )
        if projection["entitled"]:
            active_key = stored_key

    if active_key is None:
        applied = apply_future30_character(
            conn,
            uid,
            DEFAULT_STARTER_KEY,
            allow_acceptance_test=allow_acceptance_test,
        )
        active_key = applied["character_key"]

    return {
        "user_id": uid,
        "starter_pool": list(STARTER_CHARACTER_KEYS),
        "created": created,
        "active_character_key": active_key,
        "default_used": active_key == DEFAULT_STARTER_KEY and stored_key != DEFAULT_STARTER_KEY,
        "permanent": True,
    }


def list_future30_entitlements(
    conn: Any,
    user_id: int,
    *,
    allow_acceptance_test: bool = False,
) -> list[dict[str, Any]]:
    ensure_future30_catalog(conn)
    test_clause = "" if allow_acceptance_test else " AND e.acquisition_source <> 'ACCEPTANCE_TEST'"
    rows = conn.execute(
        f"""SELECT e.user_id, e.character_key, e.acquisition_source,
                   e.source_reference, e.acquired_at,
                   c.visual_model_id, c.character_asset_id, c.runtime_glb,
                   c.runtime_sha256
              FROM {ENTITLEMENT_TABLE} e
              JOIN {CATALOG_TABLE} c ON c.character_key=e.character_key
             WHERE e.user_id=?{test_clause}
             ORDER BY e.character_key""",
        (int(user_id),),
    ).fetchall()
    return [
        {
            "user_id": _row_value(row, "user_id", 0),
            "character_key": _row_value(row, "character_key", 1),
            "acquisition_source": _row_value(row, "acquisition_source", 2),
            "source_reference": _row_value(row, "source_reference", 3),
            "acquired_at": _row_value(row, "acquired_at", 4),
            "permanent": True,
            "runtime": {
                "visual_model_id": _row_value(row, "visual_model_id", 5),
                "character_asset_id": _row_value(row, "character_asset_id", 6),
                "runtime_glb": _row_value(row, "runtime_glb", 7),
                "runtime_sha256": _row_value(row, "runtime_sha256", 8),
            },
        }
        for row in rows
    ]


def apply_future30_character(
    conn: Any,
    user_id: int,
    character_key: str,
    *,
    allow_acceptance_test: bool = False,
) -> dict[str, Any]:
    """Apply an entitled canonical key to server-owned player appearance."""

    key = _require_canonical_key(character_key)
    mapping = resolve_future30_mapping(conn, key)
    entitlement = _entitlement_row(
        conn, int(user_id), key, allow_acceptance_test=allow_acceptance_test
    )
    if not entitlement:
        raise Future30CharacterNotEntitled("Future30 character entitlement is required")
    now = _now()
    conn.execute(
        """INSERT INTO player_appearance(user_id, character_key, updated_at)
           VALUES(?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
               character_key=excluded.character_key,
               updated_at=excluded.updated_at""",
        (int(user_id), key, now),
    )
    return {
        "character_key": key,
        "character_key_source": "player_appearance.character_key",
        "entitlement_source": _row_value(entitlement, "acquisition_source", 2),
        "permanent": True,
        "runtime": mapping,
    }


def project_applied_character(
    conn: Any,
    user_id: int,
    stored_key: Any,
    *,
    allow_acceptance_test: bool = False,
) -> dict[str, Any]:
    """Project a persisted key without silently admitting an unowned Future30 key."""

    if not is_future30_character_key(stored_key):
        return {
            "character_key": stored_key if isinstance(stored_key, str) and stored_key else DEFAULT_CHARACTER_KEY,
            "character_key_source": "player_appearance.character_key" if stored_key else "server_default",
            "runtime": None,
            "entitled": True,
        }
    try:
        mapping = resolve_future30_mapping(conn, stored_key)
    except Future30ServiceError:
        return {
            "character_key": DEFAULT_CHARACTER_KEY,
            "character_key_source": "server_default",
            "runtime": None,
            "entitled": False,
        }
    entitlement = _entitlement_row(
        conn, int(user_id), stored_key, allow_acceptance_test=allow_acceptance_test
    )
    if not entitlement:
        return {
            "character_key": DEFAULT_CHARACTER_KEY,
            "character_key_source": "server_default",
            "runtime": None,
            "entitled": False,
        }
    return {
        "character_key": stored_key,
        "character_key_source": "player_appearance.character_key",
        "runtime": mapping,
        "entitled": True,
        "entitlement_source": _row_value(entitlement, "acquisition_source", 2),
        "permanent": True,
    }


def catalog_payload(conn: Any) -> dict[str, Any]:
    """Return the server projection consumed by Hero/Shop/Backpack adapters."""

    meta = ensure_future30_catalog(conn)
    visual_rows = conn.execute(
        f"""SELECT visual_model_id, character_key, variant, character_asset_id,
                   runtime_glb, runtime_sha256, mapping_status
              FROM {VISUAL_TABLE}
             ORDER BY character_key, CASE variant WHEN 'RED' THEN 0 ELSE 1 END"""
    ).fetchall()
    visuals_by_character: dict[str, list[dict[str, Any]]] = {}
    for visual in visual_rows:
        row = {
            "visual_model_id": _row_value(visual, "visual_model_id", 0),
            "character_key": _row_value(visual, "character_key", 1),
            "character_asset_id": _row_value(visual, "character_asset_id", 3),
            "variant": _row_value(visual, "variant", 2),
            "runtime_glb": _row_value(visual, "runtime_glb", 4),
            "runtime_sha256": _row_value(visual, "runtime_sha256", 5),
            "mapping_status": _row_value(visual, "mapping_status", 6),
        }
        visuals_by_character.setdefault(
            _row_value(visual, "character_key", 1), []
        ).append(row)
    return {
        "logical_count": meta["logical_count"],
        "visual_count": meta["visual_count"],
        "character_keys": meta["character_keys"],
        "product_manifest_sha256": meta["product_manifest_sha256"],
        "c005_manifest_sha256": meta["c005_manifest_sha256"],
        "default_variant": "RED",
        "blue_optional": ["AR1", "AR2", "AR3"],
        "acquisition_allocation": [
            {"source": "STARTER", "count": 5, "assignment_status": "UNASSIGNED"},
            {"source": "STAGE", "count": 10, "assignment_status": "UNASSIGNED"},
            {"source": "PREMIUM", "count": 5, "assignment_status": "UNASSIGNED"},
            {"source": "SHOP", "count": 10, "assignment_status": "UNASSIGNED"},
        ],
        "entries": [
            {
                **row,
                "visual_models": visuals_by_character.get(row["character_key"], []),
                "acquisition_group": None,
                "acquisition_group_status": "UNASSIGNED",
                "product_manifest_sha256": FUTURE30_PRODUCT_MANIFEST_SHA256,
                "c005_manifest_sha256": FUTURE30_C005_MANIFEST_SHA256,
                "ownership_authority": ENTITLEMENT_TABLE,
                "applied_authority": "player_appearance.character_key",
            }
            for row in future30_catalog_rows()
        ],
    }


__all__ = [
    "ACCEPTANCE_ENVIRONMENTS", "Future30AcquisitionRejected",
    "Future30CatalogUnavailable", "Future30CharacterNotEntitled",
    "Future30ServiceError", "Future30UnknownCharacter",
    "DEFAULT_STARTER_KEY", "STARTER_CHARACTER_KEYS", "STARTER_SOURCE_REFERENCE",
    "apply_future30_character", "catalog_payload", "ensure_future30_catalog",
    "ensure_future30_starter_bootstrap",
    "grant_future30_character", "initialize_future30_catalog",
    "list_future30_entitlements", "project_applied_character",
    "resolve_future30_mapping",
]
