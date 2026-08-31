"""Incident 019B Adventure mastery compatibility helpers.

The current trusted review path and the historical visible-product baseline
are intentionally separate sets:

``visible = frozen_historical_baseline UNION trusted_current_reviews``

The baseline is captured once by the controlled runner in
``tools/incident_019b_progression_continuity.py``.  No request path writes to
it, and the runner refuses to add live card state after the baseline has been
frozen.  The helpers in this module never mutate ``review_log`` or
``srs_cards``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from migrations.adventure_historical_mastery_v1 import (
    BASELINE_TABLE_NAME,
    BASELINE_VERSION,
    CUTOFF_LITERAL,
    SOURCE_CARD_MASK,
    SOURCE_REVIEW_MASK,
    STATUS_CAPTURING,
    STATUS_FROZEN,
    TABLE_NAME,
    upgrade as upgrade_schema,
)


TRUSTED_REVIEW_SOURCE_PREFIXES = ("mbv1:",)
_QUERY_CHUNK_SIZE = 500


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _table_exists(conn: Any, table_name: str) -> bool:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=?""",
            (table_name,),
        ).fetchone()
    return row is not None


def _table_ref(conn: Any, table_name: str) -> str:
    return table_name if _is_sqlite(conn) else f"public.{table_name}"


def _normalize_question_ids(question_ids: Iterable[Any] | None) -> tuple[int, ...] | None:
    if question_ids is None:
        return None
    normalized = set()
    for question_id in question_ids:
        if question_id is None:
            continue
        try:
            normalized.add(int(question_id))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"question id is not an integer: {question_id!r}") from exc
    return tuple(sorted(normalized))


def _question_filter_sql(question_ids: tuple[int, ...] | None) -> tuple[str, tuple[int, ...]]:
    if question_ids is None:
        return "", ()
    if not question_ids:
        return " AND 1=0", ()
    placeholders = ",".join("?" for _ in question_ids)
    return f" AND question_id IN ({placeholders})", question_ids


def _fetch_memberships(
    conn: Any,
    sql: str,
    params: Sequence[Any],
    question_ids: tuple[int, ...] | None,
) -> dict[int, set[int]]:
    """Fetch ``user_id -> question_id`` rows without leaking account data."""

    if question_ids is None or len(question_ids) <= _QUERY_CHUNK_SIZE:
        batches = (question_ids,)
    else:
        batches = tuple(
            question_ids[start : start + _QUERY_CHUNK_SIZE]
            for start in range(0, len(question_ids), _QUERY_CHUNK_SIZE)
        )

    output: dict[int, set[int]] = defaultdict(set)
    for batch in batches:
        filter_sql, filter_params = _question_filter_sql(batch)
        rows = conn.execute(sql.format(question_filter=filter_sql), (*params, *filter_params)).fetchall()
        for row in rows:
            output[int(_value(row, 0, "user_id"))].add(int(_value(row, 1, "question_id")))
    return dict(output)


def pre_cutoff_review_memberships(
    conn: Any,
    *,
    cutoff_literal: str = CUTOFF_LITERAL,
    question_ids: Iterable[Any] | None = None,
    user_id: int | None = None,
) -> dict[int, set[int]] | set[int]:
    """Return the historical qualifying review set using strict cutoff semantics."""

    normalized_ids = _normalize_question_ids(question_ids)
    user_sql = " AND user_id=?" if user_id is not None else ""
    params_list: list[Any] = [cutoff_literal]
    if user_id is not None:
        params_list.append(int(user_id))
    sql = (
        "SELECT DISTINCT user_id, question_id FROM review_log "
        f"WHERE grade>=3 AND reviewed_at < ?{user_sql}"
        "{question_filter}"
    )
    result = _fetch_memberships(conn, sql, tuple(params_list), normalized_ids)
    if user_id is None:
        return result
    return result.get(int(user_id), set())


def qualifying_card_memberships(
    conn: Any,
    *,
    question_ids: Iterable[Any] | None = None,
    user_id: int | None = None,
) -> dict[int, set[int]] | set[int]:
    """Return the exact pre-B050 qualifying SRS card predicate."""

    normalized_ids = _normalize_question_ids(question_ids)
    user_sql = " AND user_id=?" if user_id is not None else ""
    params: tuple[Any, ...] = (int(user_id),) if user_id is not None else ()
    sql = (
        "SELECT DISTINCT user_id, question_id FROM srs_cards "
        f"WHERE (progress_credited <> 0 OR last_grade >= 3){user_sql}"
        "{question_filter}"
    )
    result = _fetch_memberships(conn, sql, params, normalized_ids)
    if user_id is None:
        return result
    return result.get(int(user_id), set())


def trusted_current_memberships(
    conn: Any,
    *,
    source_prefixes: Iterable[str] = TRUSTED_REVIEW_SOURCE_PREFIXES,
    question_ids: Iterable[Any] | None = None,
    user_id: int | None = None,
) -> dict[int, set[int]] | set[int]:
    """Return current server-trusted Adventure review memberships.

    ``source_context`` is deliberately the only current authority consulted;
    public SRS grades and live card state are not trusted correctness input.
    """

    prefixes = tuple(str(prefix) for prefix in source_prefixes if str(prefix))
    if not prefixes:
        return {} if user_id is None else set()
    normalized_ids = _normalize_question_ids(question_ids)
    user_sql = " AND user_id=?" if user_id is not None else ""
    clauses = " OR ".join("source_context LIKE ?" for _ in prefixes)
    params_list: list[Any] = [f"{prefix}%" for prefix in prefixes]
    if user_id is not None:
        params_list.append(int(user_id))
    sql = (
        "SELECT DISTINCT user_id, question_id FROM review_log "
        f"WHERE grade>=3 AND ({clauses}){user_sql}"
        "{question_filter}"
    )
    result = _fetch_memberships(conn, sql, tuple(params_list), normalized_ids)
    if user_id is None:
        return result
    return result.get(int(user_id), set())


def _frozen_baseline_ready(conn: Any, *, baseline_version: str) -> bool:
    """Return whether a complete frozen baseline is safe for request reads.

    A partially captured or mismatched baseline must never be mistaken for a
    valid historical entitlement set.  Database errors intentionally bubble
    up instead of silently falling back to trusted-only progress, which could
    recreate the Incident019B regression during an operational fault.
    """

    if not _table_exists(conn, TABLE_NAME) or not _table_exists(conn, BASELINE_TABLE_NAME):
        return False
    row = conn.execute(
        f"SELECT cutoff_literal, status FROM {_table_ref(conn, BASELINE_TABLE_NAME)} "
        "WHERE baseline_version=?",
        (baseline_version,),
    ).fetchone()
    if row is None:
        return False
    return (
        str(_value(row, 0, "cutoff_literal")) == CUTOFF_LITERAL
        and str(_value(row, 1, "status")) == STATUS_FROZEN
    )


def frozen_historical_memberships(
    conn: Any,
    *,
    baseline_version: str = BASELINE_VERSION,
    user_id: int | None = None,
) -> dict[int, set[int]] | set[int]:
    """Read only the durable frozen baseline; missing schema means empty in tests."""

    if not _frozen_baseline_ready(conn, baseline_version=baseline_version):
        return {} if user_id is None else set()
    user_sql = " AND user_id=?" if user_id is not None else ""
    params_list: list[Any] = [baseline_version]
    if user_id is not None:
        params_list.append(int(user_id))
    rows = conn.execute(
        f"SELECT DISTINCT user_id, question_id FROM {_table_ref(conn, TABLE_NAME)} "
        f"WHERE baseline_version=?{user_sql}",
        tuple(params_list),
    ).fetchall()
    result: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        result[int(_value(row, 0, "user_id"))].add(int(_value(row, 1, "question_id")))
    if user_id is None:
        return dict(result)
    return result.get(int(user_id), set())


def frozen_source_masks(
    conn: Any,
    *,
    baseline_version: str = BASELINE_VERSION,
) -> dict[tuple[int, int], int]:
    """Return audit provenance for the immutable baseline without account PII."""

    if not _frozen_baseline_ready(conn, baseline_version=baseline_version):
        return {}
    rows = conn.execute(
        f"SELECT user_id, question_id, source_mask FROM {_table_ref(conn, TABLE_NAME)} "
        "WHERE baseline_version=?",
        (baseline_version,),
    ).fetchall()
    return {
        (
            int(_value(row, 0, "user_id")),
            int(_value(row, 1, "question_id")),
        ): int(_value(row, 2, "source_mask"))
        for row in rows
    }


def visible_adventure_question_ids(
    conn: Any,
    user_id: int,
    *,
    trusted_source_prefixes: Iterable[str] = TRUSTED_REVIEW_SOURCE_PREFIXES,
    baseline_version: str = BASELINE_VERSION,
) -> set[int]:
    """Return the set-union read model for one authenticated player."""

    historical = frozen_historical_memberships(
        conn, baseline_version=baseline_version, user_id=int(user_id)
    )
    trusted = trusted_current_memberships(
        conn,
        source_prefixes=trusted_source_prefixes,
        user_id=int(user_id),
    )
    return set(historical) | set(trusted)


def _merge_memberships(*memberships: Mapping[int, Iterable[int]]) -> dict[int, set[int]]:
    merged: dict[int, set[int]] = defaultdict(set)
    for mapping in memberships:
        for user_id, question_ids in mapping.items():
            merged[int(user_id)].update(int(question_id) for question_id in question_ids)
    return dict(merged)


def _source_mask_memberships(
    review: Mapping[int, Iterable[int]],
    cards: Mapping[int, Iterable[int]],
) -> dict[tuple[int, int], int]:
    masks: dict[tuple[int, int], int] = {}
    for user_id, question_ids in review.items():
        for question_id in question_ids:
            masks[(int(user_id), int(question_id))] = SOURCE_REVIEW_MASK
    for user_id, question_ids in cards.items():
        for question_id in question_ids:
            key = (int(user_id), int(question_id))
            masks[key] = masks.get(key, 0) | SOURCE_CARD_MASK
    return masks


def entitlement_source_for_mask(source_mask: int) -> str:
    if source_mask == SOURCE_REVIEW_MASK:
        return "pre_cutoff_review"
    if source_mask == SOURCE_CARD_MASK:
        return "frozen_card_snapshot"
    if source_mask == (SOURCE_REVIEW_MASK | SOURCE_CARD_MASK):
        return "pre_cutoff_review+frozen_card_snapshot"
    raise ValueError(f"unsupported compatibility source mask: {source_mask}")


def _utc_naive_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def populate_frozen_historical_baseline(
    conn: Any,
    *,
    question_ids: Iterable[Any] | None = None,
    captured_at: str | None = None,
    cutoff_literal: str = CUTOFF_LITERAL,
    baseline_version: str = BASELINE_VERSION,
) -> dict[str, Any]:
    """Capture the compatibility set once, atomically, without committing.

    A frozen baseline is a one-time snapshot.  Re-running this function after
    the version is frozen performs no source-table reads and cannot add newer
    card state.  The caller must commit or roll back the surrounding
    transaction.
    """

    upgrade_schema(conn)
    normalized_ids = _normalize_question_ids(question_ids)
    metadata_ref = _table_ref(conn, BASELINE_TABLE_NAME)
    membership_ref = _table_ref(conn, TABLE_NAME)
    existing = conn.execute(
        f"SELECT baseline_version, cutoff_literal, captured_at, frozen_at, status, membership_count "
        f"FROM {metadata_ref} WHERE baseline_version=?",
        (baseline_version,),
    ).fetchone()
    if existing is not None:
        if str(_value(existing, 1, "cutoff_literal")) != str(cutoff_literal):
            raise ValueError("existing compatibility baseline cutoff differs")
        if str(_value(existing, 4, "status")) != STATUS_FROZEN:
            raise RuntimeError("compatibility baseline is not frozen; refusing to resume")
        actual = int(
            conn.execute(
                f"SELECT COUNT(*) FROM {membership_ref} WHERE baseline_version=?",
                (baseline_version,),
            ).fetchone()[0]
        )
        recorded = int(_value(existing, 5, "membership_count"))
        if actual != recorded:
            raise RuntimeError("frozen compatibility baseline count is inconsistent")
        return {
            "baseline_version": baseline_version,
            "already_frozen": True,
            "membership_count": actual,
            "review_memberships": None,
            "card_memberships": None,
        }

    orphan_count = int(
        conn.execute(
            f"SELECT COUNT(*) FROM {membership_ref} WHERE baseline_version=?",
            (baseline_version,),
        ).fetchone()[0]
    )
    if orphan_count:
        raise RuntimeError("compatibility memberships exist without a frozen baseline")

    capture_time = str(captured_at or _utc_naive_now())
    conn.execute(
        f"INSERT INTO {metadata_ref} "
        "(baseline_version, cutoff_literal, captured_at, frozen_at, status, membership_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (baseline_version, cutoff_literal, capture_time, capture_time, STATUS_CAPTURING, 0),
    )
    review = pre_cutoff_review_memberships(
        conn, cutoff_literal=cutoff_literal, question_ids=normalized_ids
    )
    cards = qualifying_card_memberships(conn, question_ids=normalized_ids)
    assert isinstance(review, dict)
    assert isinstance(cards, dict)
    masks = _source_mask_memberships(review, cards)
    values = [
        (
            user_id,
            question_id,
            baseline_version,
            source_mask,
            entitlement_source_for_mask(source_mask),
            capture_time,
            cutoff_literal,
        )
        for (user_id, question_id), source_mask in sorted(masks.items())
    ]
    if values:
        conn.executemany(
            f"INSERT INTO {membership_ref} "
            "(user_id, question_id, baseline_version, source_mask, entitlement_source, "
            "captured_at, cutoff_literal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, question_id, baseline_version) DO NOTHING",
            values,
        )
    count = int(
        conn.execute(
            f"SELECT COUNT(*) FROM {membership_ref} WHERE baseline_version=?",
            (baseline_version,),
        ).fetchone()[0]
    )
    conn.execute(
        f"UPDATE {metadata_ref} SET status=?, frozen_at=?, membership_count=? "
        "WHERE baseline_version=? AND status=?",
        (STATUS_FROZEN, capture_time, count, baseline_version, STATUS_CAPTURING),
    )
    return {
        "baseline_version": baseline_version,
        "already_frozen": False,
        "membership_count": count,
        "review_memberships": sum(len(values_) for values_ in review.values()),
        "card_memberships": sum(len(values_) for values_ in cards.values()),
        "overlap_memberships": sum(
            1 for source_mask in masks.values() if source_mask == (SOURCE_REVIEW_MASK | SOURCE_CARD_MASK)
        ),
    }


def _safe_player_id(user_id: int) -> str:
    return hashlib.md5(str(int(user_id)).encode("ascii"), usedforsecurity=False).hexdigest()[:12]


def _zone_sets(zone_question_ids: Mapping[str, Iterable[Any]]) -> dict[str, set[int]]:
    return {
        str(zone): {int(question_id) for question_id in question_ids}
        for zone, question_ids in zone_question_ids.items()
    }


def build_compatibility_census(
    conn: Any,
    zone_question_ids: Mapping[str, Iterable[Any]],
    *,
    historical_mode: str = "preview",
    baseline_version: str = BASELINE_VERSION,
    cutoff_literal: str = CUTOFF_LITERAL,
    trusted_source_prefixes: Iterable[str] = TRUSTED_REVIEW_SOURCE_PREFIXES,
) -> dict[str, Any]:
    """Build a set-aware global/player/player-zone dry-run report.

    ``historical_mode='preview'`` models the one-time future capture from the
    current source tables.  ``historical_mode='frozen'`` reads only the
    durable baseline and is the post-capture verification mode.
    """

    zones = _zone_sets(zone_question_ids)
    allowed_ids = set().union(*zones.values()) if zones else set()
    trusted = trusted_current_memberships(
        conn,
        source_prefixes=trusted_source_prefixes,
        question_ids=allowed_ids,
    )
    assert isinstance(trusted, dict)
    if historical_mode == "preview":
        review = pre_cutoff_review_memberships(
            conn, cutoff_literal=cutoff_literal, question_ids=allowed_ids
        )
        cards = qualifying_card_memberships(conn, question_ids=allowed_ids)
        assert isinstance(review, dict)
        assert isinstance(cards, dict)
        preview_historical = _merge_memberships(review, cards)
        historical = preview_historical
        sticky_only_pairs = {
            (int(user_id), int(question_id))
            for user_id, question_ids_for_user in cards.items()
            for question_id in set(question_ids_for_user) - set(review.get(user_id, set()))
        }
    elif historical_mode == "frozen":
        review = {}
        cards = {}
        frozen = frozen_historical_memberships(conn, baseline_version=baseline_version)
        assert isinstance(frozen, dict)
        historical = {
            user_id: set(question_ids) & allowed_ids
            for user_id, question_ids in frozen.items()
            if set(question_ids) & allowed_ids
        }
        masks = frozen_source_masks(conn, baseline_version=baseline_version)
        snapshot_review: dict[int, set[int]] = defaultdict(set)
        snapshot_cards: dict[int, set[int]] = defaultdict(set)
        sticky_only_pairs = set()
        for (user_id, question_id), source_mask in masks.items():
            if question_id not in allowed_ids:
                continue
            if source_mask & SOURCE_REVIEW_MASK:
                snapshot_review[user_id].add(question_id)
            if source_mask & SOURCE_CARD_MASK:
                snapshot_cards[user_id].add(question_id)
            if source_mask == SOURCE_CARD_MASK:
                sticky_only_pairs.add((user_id, question_id))
        review = dict(snapshot_review)
        cards = dict(snapshot_cards)
    else:
        raise ValueError("historical_mode must be 'preview' or 'frozen'")

    player_ids = sorted(set(review) | set(cards) | set(trusted) | set(historical))
    total_frozen = sum(len(historical.get(uid, set())) for uid in player_ids)
    total_trusted = sum(len(trusted.get(uid, set())) for uid in player_ids)
    total_overlap = sum(
        len(historical.get(uid, set()) & trusted.get(uid, set())) for uid in player_ids
    )
    total_historical_only = sum(
        len(historical.get(uid, set()) - trusted.get(uid, set())) for uid in player_ids
    )
    total_visible = sum(
        len(historical.get(uid, set()) | trusted.get(uid, set())) for uid in player_ids
    )

    player_zone_rows: list[dict[str, Any]] = []
    player_rows: list[dict[str, Any]] = []
    affected_players: set[int] = set()
    affected_rows = 0
    max_historical_only = 0
    max_sticky_only = 0
    visible_decrease_count = 0
    for uid in player_ids:
        historical_ids = historical.get(uid, set())
        trusted_ids = trusted.get(uid, set())
        sticky_only_ids = {
            question_id
            for player_id, question_id in sticky_only_pairs
            if player_id == uid
        }
        player_historical_only = historical_ids - trusted_ids
        player_rows.append(
            {
                "safe_player_id": _safe_player_id(uid),
                "frozen_historical_count": len(historical_ids),
                "trusted_current_count": len(trusted_ids),
                "overlap_count": len(historical_ids & trusted_ids),
                "historical_only_count": len(player_historical_only),
                "trusted_only_count": len(trusted_ids - historical_ids),
                "visible_union_count": len(historical_ids | trusted_ids),
                "sticky_only_count": len(sticky_only_ids),
            }
        )
        for zone, zone_ids in zones.items():
            historical_zone = historical_ids & zone_ids
            trusted_zone = trusted_ids & zone_ids
            card_zone = cards.get(uid, set()) & zone_ids
            review_zone = review.get(uid, set()) & zone_ids
            historical_only = historical_zone - trusted_zone
            visible_union = historical_zone | trusted_zone
            if not (historical_zone or trusted_zone or card_zone or review_zone):
                continue
            if historical_only:
                affected_players.add(uid)
                affected_rows += 1
            max_historical_only = max(max_historical_only, len(historical_only))
            sticky_only_zone = {
                question_id
                for question_id in zone_ids
                if (uid, question_id) in sticky_only_pairs
            }
            max_sticky_only = max(max_sticky_only, len(sticky_only_zone))
            if len(visible_union) < len(trusted_zone):
                visible_decrease_count += 1
            player_zone_rows.append(
                {
                    "safe_player_id": _safe_player_id(uid),
                    "zone": zone,
                    "zone_denominator": len(zone_ids),
                    "pre_cutoff_review_count": len(review_zone),
                    "qualifying_card_count": len(card_zone),
                    "frozen_historical_count": len(historical_zone),
                    "trusted_current_count": len(trusted_zone),
                    "overlap_count": len(historical_zone & trusted_zone),
                    "historical_only_count": len(historical_only),
                    "trusted_only_count": len(trusted_zone - historical_zone),
                    "visible_union_count": len(visible_union),
                    "sticky_only_count": len(sticky_only_zone),
                }
            )

    sticky_ceiling = len(sticky_only_pairs)
    return {
        "historical_mode": historical_mode,
        "baseline_version": baseline_version,
        "cutoff_literal": cutoff_literal,
        "zone_denominators": {zone: len(ids) for zone, ids in zones.items()},
        "total_players_evaluated": len(player_ids),
        "total_frozen_historical_memberships": total_frozen,
        "total_trusted_current_memberships": total_trusted,
        "total_overlap": total_overlap,
        "total_historical_only": total_historical_only,
        "total_visible_union": total_visible,
        "sticky_ceiling_memberships_included": sticky_ceiling,
        "affected_players": len(affected_players),
        "affected_player_zone_rows": affected_rows,
        "max_historical_only_delta": max_historical_only,
        "max_sticky_only_delta": max_sticky_only,
        "visible_decrease_count_after_fix": visible_decrease_count,
        "player_rows": player_rows,
        "player_zone_rows": player_zone_rows,
    }


__all__ = [
    "BASELINE_VERSION",
    "CUTOFF_LITERAL",
    "TRUSTED_REVIEW_SOURCE_PREFIXES",
    "build_compatibility_census",
    "entitlement_source_for_mask",
    "frozen_historical_memberships",
    "frozen_source_masks",
    "populate_frozen_historical_baseline",
    "pre_cutoff_review_memberships",
    "qualifying_card_memberships",
    "trusted_current_memberships",
    "visible_adventure_question_ids",
]
