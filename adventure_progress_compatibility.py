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
    SOURCE_RULE_VERSION,
    STATUS_CAPTURING,
    STATUS_FAILED_OR_INVALID,
    STATUS_FROZEN,
    STATUS_READY,
    TRUSTED_CARD_ENTITLEMENT_SOURCE,
    TABLE_NAME,
    baseline_readiness,
    upgrade as upgrade_schema,
)
from adventure_zone_progression_authority import (
    lord_eligibility_requirement,
    map_milestone_star,
    second_star_requirement,
    third_star_requirement,
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
    """Return trusted historical Map progress from ``progress_credited``.

    ``last_grade`` is a scheduling/display field and may have been populated
    from a public client grade.  It is intentionally not a continuity
    authority.  The only historical card predicate admitted to the baseline is
    the server-owned sticky ``progress_credited`` bit.
    """

    normalized_ids = _normalize_question_ids(question_ids)
    user_sql = " AND user_id=?" if user_id is not None else ""
    params: tuple[Any, ...] = (int(user_id),) if user_id is not None else ()
    sql = (
        "SELECT DISTINCT user_id, question_id FROM srs_cards "
        f"WHERE progress_credited <> 0{user_sql}"
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

    readiness = baseline_readiness(conn, baseline_version=baseline_version)
    return bool(readiness.get("status") == STATUS_READY and readiness.get("valid"))


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
        f"WHERE baseline_version=? AND source_mask=? "
        f"AND entitlement_source=?{user_sql}",
        (baseline_version, SOURCE_CARD_MASK, TRUSTED_CARD_ENTITLEMENT_SOURCE, *params_list[1:]),
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
        "WHERE baseline_version=? AND source_mask=? AND entitlement_source=?",
        (baseline_version, SOURCE_CARD_MASK, TRUSTED_CARD_ENTITLEMENT_SOURCE),
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


def visible_adventure_question_count(
    conn: Any,
    user_id: int,
    question_ids: Iterable[Any],
    *,
    trusted_source_prefixes: Iterable[str] = TRUSTED_REVIEW_SOURCE_PREFIXES,
    baseline_version: str = BASELINE_VERSION,
    include_baseline: bool = True,
) -> int:
    """Count visible questions with bounded SQL, without materializing history.

    The answer path only needs a Zone numerator.  This query counts the union
    of the ready historical baseline and trusted current ``mbv1`` evidence in
    the database, so its result is independent of the number of historical
    rows.  Question ids are chunked to keep parameter limits bounded.
    """

    normalized_ids = _normalize_question_ids(question_ids) or ()
    if not normalized_ids:
        return 0
    prefixes = tuple(str(prefix) for prefix in trusted_source_prefixes if str(prefix))
    if not prefixes:
        return 0
    # ``include_baseline=False`` is used only by the explicitly owner-gated
    # retroactive-milestone policy seam.  It lets the application distinguish
    # coverage newly proved by the current Map authority from coverage restored
    # by the historical baseline, without introducing a second progression
    # authority or materializing either set in Python.
    baseline_ready = include_baseline and _frozen_baseline_ready(
        conn, baseline_version=baseline_version
    )
    total = 0
    for start in range(0, len(normalized_ids), _QUERY_CHUNK_SIZE):
        batch = normalized_ids[start : start + _QUERY_CHUNK_SIZE]
        placeholders = ",".join("?" for _ in batch)
        current_clauses = " OR ".join("source_context LIKE ?" for _ in prefixes)
        current_params: list[Any] = [int(user_id), *[f"{prefix}%" for prefix in prefixes], *batch]
        if baseline_ready:
            sql = (
                "SELECT COUNT(*) FROM ("
                f"SELECT question_id FROM {_table_ref(conn, TABLE_NAME)} "
                "WHERE user_id=? AND baseline_version=? AND source_mask=? "
                "AND entitlement_source=? AND question_id IN (" + placeholders + ") "
                "UNION "
                "SELECT question_id FROM review_log WHERE user_id=? AND grade>=3 "
                "AND (" + current_clauses + ") AND question_id IN (" + placeholders + ")"
                ") visible_questions"
            )
            params = [
                int(user_id),
                baseline_version,
                SOURCE_CARD_MASK,
                TRUSTED_CARD_ENTITLEMENT_SOURCE,
                *batch,
                *current_params,
            ]
        else:
            sql = (
                "SELECT COUNT(DISTINCT question_id) FROM review_log "
                "WHERE user_id=? AND grade>=3 AND (" + current_clauses + ") "
                "AND question_id IN (" + placeholders + ")"
            )
            params = current_params
        total += int(conn.execute(sql, tuple(params)).fetchone()[0] or 0)
    return total


def current_adventure_question_count(
    conn: Any,
    user_id: int,
    question_ids: Iterable[Any],
    *,
    trusted_source_prefixes: Iterable[str] = TRUSTED_REVIEW_SOURCE_PREFIXES,
) -> int:
    """Count only current trusted Map evidence for policy comparison.

    This is not a new gameplay authority: it is the same trusted current
    source used by :func:`visible_adventure_question_count`, with the frozen
    historical compatibility projection intentionally excluded.
    """

    return visible_adventure_question_count(
        conn,
        user_id,
        question_ids,
        trusted_source_prefixes=trusted_source_prefixes,
        include_baseline=False,
    )


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


def membership_fingerprint(memberships: Mapping[int, Iterable[int]]) -> str:
    """Return a deterministic integrity id for a baseline membership set."""

    pairs = sorted(
        (int(user_id), int(question_id))
        for user_id, question_ids in memberships.items()
        for question_id in set(question_ids)
    )
    digest = hashlib.sha256()
    for user_id, question_id in pairs:
        digest.update(f"{user_id}:{question_id}\n".encode("ascii"))
    return digest.hexdigest()


def entitlement_source_for_mask(source_mask: int) -> str:
    if source_mask == SOURCE_CARD_MASK:
        return TRUSTED_CARD_ENTITLEMENT_SOURCE
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
    """Build and publish the trusted baseline, without committing.

    Only the server-owned ``srs_cards.progress_credited`` snapshot is copied.
    Metadata is inserted as ``BASELINE_BUILDING`` and is switched to
    ``BASELINE_READY`` only after count and fingerprint verification.  The
    caller owns the transaction and the owner gate; an interrupted transaction
    therefore cannot expose a partial ready baseline.
    """

    normalized_ids = _normalize_question_ids(question_ids)
    if not normalized_ids:
        raise ValueError(
            "non-empty canonical question_ids are required to build the historical baseline"
        )
    upgrade_schema(conn)
    metadata_ref = _table_ref(conn, BASELINE_TABLE_NAME)
    membership_ref = _table_ref(conn, TABLE_NAME)
    existing = conn.execute(
        f"SELECT baseline_version, cutoff_literal, captured_at, frozen_at, status, membership_count, "
        f"source_rule_version, expected_membership_count, actual_membership_count, "
        f"membership_fingerprint, ready_at, failure_reason "
        f"FROM {metadata_ref} WHERE baseline_version=?",
        (baseline_version,),
    ).fetchone()
    if existing is not None:
        if str(_value(existing, 1, "cutoff_literal")) != str(cutoff_literal):
            raise ValueError("existing compatibility baseline cutoff differs")
        status = str(_value(existing, 4, "status") or "")
        if status == STATUS_READY:
            readiness = baseline_readiness(
                conn, baseline_version=baseline_version, verify_fingerprint=True
            )
            if not readiness.get("valid"):
                raise RuntimeError("ready compatibility baseline is inconsistent")
            return {
                "baseline_version": baseline_version,
                "already_ready": True,
                "already_frozen": True,
                "membership_count": int(readiness["actual_membership_count"]),
                "review_memberships": 0,
                "card_memberships": int(readiness["actual_membership_count"]),
            }
        if status not in (STATUS_CAPTURING, STATUS_FAILED_OR_INVALID):
            raise RuntimeError(f"unsupported compatibility baseline state: {status}")
        # A failed/building state is migration-owned and non-authoritative.
        # Clean only rows owned by this baseline version so a committed
        # interrupted run can converge on rerun.  Original review/SRS source
        # records are never touched.
        conn.execute(
            f"DELETE FROM {membership_ref} WHERE baseline_version=?",
            (baseline_version,),
        )
        conn.execute(
            f"UPDATE {metadata_ref} SET status=?, frozen_at='', membership_count=0, "
            "expected_membership_count=0, actual_membership_count=0, "
            "membership_fingerprint='', failure_reason=NULL, ready_at=NULL "
            "WHERE baseline_version=?",
            (STATUS_CAPTURING, baseline_version),
        )
    else:
        orphan_count = int(
            conn.execute(
                f"SELECT COUNT(*) FROM {membership_ref} WHERE baseline_version=?",
                (baseline_version,),
            ).fetchone()[0]
        )
        if orphan_count:
            raise RuntimeError("compatibility memberships exist without a baseline")

        capture_time = str(captured_at or _utc_naive_now())
        conn.execute(
            f"INSERT INTO {metadata_ref} "
            "(baseline_version, cutoff_literal, captured_at, frozen_at, status, membership_count, "
            " source_rule_version, expected_membership_count, actual_membership_count, "
            " membership_fingerprint, ready_at, failure_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                baseline_version,
                cutoff_literal,
                capture_time,
                "",
                STATUS_CAPTURING,
                0,
                SOURCE_RULE_VERSION,
                0,
                0,
                "",
                None,
                None,
            ),
        )

    existing_metadata = conn.execute(
        f"SELECT captured_at FROM {metadata_ref} WHERE baseline_version=?",
        (baseline_version,),
    ).fetchone()
    capture_time = str(captured_at or _value(existing_metadata, 0, "captured_at"))

    # The historical review and public last_grade predicates are intentionally
    # measured nowhere in the publish set.  They remain available as separate
    # diagnostics, but cannot become continuity authority.
    cards = qualifying_card_memberships(conn, question_ids=normalized_ids)
    assert isinstance(cards, dict)
    masks = {
        (int(user_id), int(question_id)): SOURCE_CARD_MASK
        for user_id, question_ids_for_user in cards.items()
        for question_id in question_ids_for_user
    }
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
    expected_count = len(masks)
    fingerprint = membership_fingerprint(cards)
    conn.execute(
        f"UPDATE {metadata_ref} SET source_rule_version=?, expected_membership_count=?, "
        "membership_fingerprint=? WHERE baseline_version=? AND status=?",
        (SOURCE_RULE_VERSION, expected_count, fingerprint, baseline_version, STATUS_CAPTURING),
    )
    count = int(
        conn.execute(
            f"SELECT COUNT(*) FROM {membership_ref} WHERE baseline_version=?",
            (baseline_version,),
        ).fetchone()[0]
    )
    actual_memberships: dict[int, set[int]] = defaultdict(set)
    for row in conn.execute(
        f"SELECT user_id, question_id FROM {membership_ref} WHERE baseline_version=?",
        (baseline_version,),
    ).fetchall():
        actual_memberships[int(row[0])].add(int(row[1]))
    actual_fingerprint = membership_fingerprint(actual_memberships)
    if count != expected_count or actual_fingerprint != fingerprint:
        conn.execute(
            f"UPDATE {metadata_ref} SET status=?, failure_reason=?, actual_membership_count=? "
            "WHERE baseline_version=? AND status=?",
            (
                STATUS_FAILED_OR_INVALID,
                "count_or_fingerprint_mismatch",
                count,
                baseline_version,
                STATUS_CAPTURING,
            ),
        )
        raise RuntimeError("compatibility baseline count or fingerprint mismatch")
    conn.execute(
        f"UPDATE {metadata_ref} SET status=?, frozen_at=?, membership_count=?, "
        "actual_membership_count=?, ready_at=?, failure_reason=NULL "
        "WHERE baseline_version=? AND status=?",
        (
            STATUS_FROZEN,
            capture_time,
            count,
            count,
            capture_time,
            baseline_version,
            STATUS_CAPTURING,
        ),
    )
    readiness = baseline_readiness(
        conn, baseline_version=baseline_version, verify_fingerprint=True
    )
    if not readiness.get("valid"):
        raise RuntimeError("compatibility baseline did not become integrity-valid")
    return {
        "baseline_version": baseline_version,
        "already_ready": False,
        "already_frozen": False,
        "membership_count": count,
        "review_memberships": 0,
        "card_memberships": sum(len(values_) for values_ in cards.values()),
        "overlap_memberships": 0,
        "source_rule_version": SOURCE_RULE_VERSION,
        "expected_membership_count": expected_count,
        "actual_membership_count": count,
        "membership_fingerprint": fingerprint,
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
    trusted ``progress_credited`` source.  ``historical_mode='frozen'`` reads
    only the durable baseline and is the post-capture verification mode.
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
        # Public review grades and last_grade cards are diagnostic only.  The
        # migration candidate intentionally previews the same trusted source
        # it will publish, so the dry-run cannot overstate continuity.
        review = {}
        cards = qualifying_card_memberships(conn, question_ids=allowed_ids)
        assert isinstance(cards, dict)
        historical = cards
        sticky_only_pairs = {
            (int(user_id), int(question_id))
            for user_id, question_ids_for_user in cards.items()
            for question_id in set(question_ids_for_user)
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
        "baseline_readiness": baseline_readiness(
            conn, baseline_version=baseline_version
        ),
        "player_rows": player_rows,
        "player_zone_rows": player_zone_rows,
    }


def _normalized_membership_map(
    memberships: Mapping[Any, Iterable[Any]] | None,
) -> dict[int, set[int]]:
    return {
        int(user_id): {int(question_id) for question_id in question_ids}
        for user_id, question_ids in (memberships or {}).items()
    }


def build_progression_milestone_dry_run(
    baseline_memberships: Mapping[Any, Iterable[Any]],
    current_memberships: Mapping[Any, Iterable[Any]],
    zone_question_ids: Mapping[str, Iterable[Any]],
    *,
    legacy_first_stars: Mapping[tuple[Any, Any], Any] | None = None,
    current_zone_stars: Mapping[tuple[Any, Any], Any] | None = None,
) -> dict[str, Any]:
    """Calculate the baseline's progression and side-effect blast radius.

    The function is deliberately pure: it accepts already-censused sets and
    performs no database access or writes.  It compares the current trusted
    Map set with the proposed frozen ``progress_credited`` set, then applies
    the single arithmetic authority used by the running app.  A historical
    membership can cross a 30/60/100 threshold, but it can never manufacture
    a Lord clear, first star, Boss clear, unlock, or reward.

    ``legacy_first_stars`` is a server-owned, read-only entitlement input (the
    old Boss projection); it is not a request/client field.  ``current_zone_stars``
    is the separate new star authority.  The result is safe to serialize as
    an aggregate dry-run after replacing user keys with pseudonyms.
    """

    baseline = _normalized_membership_map(baseline_memberships)
    current = _normalized_membership_map(current_memberships)
    zones = {
        str(zone): {int(question_id) for question_id in question_ids}
        for zone, question_ids in zone_question_ids.items()
    }
    legacy = {
        (int(user_id), str(zone)): max(0, min(3, int(value or 0)))
        for (user_id, zone), value in (legacy_first_stars or {}).items()
    }
    new_stars = {
        (int(user_id), str(zone)): max(0, min(3, int(value or 0)))
        for (user_id, zone), value in (current_zone_stars or {}).items()
    }
    users = sorted(set(baseline) | set(current) | {key[0] for key in legacy} | {key[0] for key in new_stars})
    crossing = {30: 0, 60: 0, 100: 0}
    valid_first_star_crossings = {60: 0, 100: 0}
    expected_transitions = {2: 0, 3: 0}
    rows: list[dict[str, Any]] = []
    for user_id in users:
        current_ids = current.get(user_id, set())
        effective_ids = current_ids | baseline.get(user_id, set())
        for zone, question_ids in zones.items():
            if not question_ids:
                continue
            current_count = len(current_ids & question_ids)
            effective_count = len(effective_ids & question_ids)
            required_30 = lord_eligibility_requirement(len(question_ids))
            required_60 = second_star_requirement(len(question_ids))
            required_100 = third_star_requirement(len(question_ids))
            for percent, required in ((30, required_30), (60, required_60), (100, required_100)):
                if current_count < required <= effective_count:
                    crossing[percent] += 1
            first_star = max(
                legacy.get((user_id, zone), 0),
                new_stars.get((user_id, zone), 0),
            ) >= 1
            current_milestone = map_milestone_star(
                current_count, len(question_ids), has_first_star=first_star
            )
            effective_milestone = map_milestone_star(
                effective_count, len(question_ids), has_first_star=first_star
            )
            # A legacy 2★/3★ entitlement is already-earned state, not a
            # missing new ledger event.  Use the effective server-owned level
            # when calculating the blast radius so the dry-run never counts a
            # historical star as a replay candidate.
            current_authority_star = max(
                legacy.get((user_id, zone), 0),
                new_stars.get((user_id, zone), 0),
            )
            if first_star and current_milestone < 2 <= effective_milestone and current_authority_star < 2:
                valid_first_star_crossings[60] += 1
                expected_transitions[2] += 1
            if first_star and current_milestone < 3 <= effective_milestone and current_authority_star < 3:
                valid_first_star_crossings[100] += 1
                expected_transitions[3] += 1
            if current_count or effective_count or first_star:
                rows.append(
                    {
                        "user_id": user_id,
                        "zone": zone,
                        "current_correct": current_count,
                        "effective_correct": effective_count,
                        "total": len(question_ids),
                        "current_milestone": current_milestone,
                        "effective_milestone": effective_milestone,
                        "legacy_first_star": legacy.get((user_id, zone), 0),
                        "current_zone_stars": new_stars.get((user_id, zone), 0),
                        "effective_server_star_entitlement": current_authority_star,
                    }
                )

    transition_total = expected_transitions[2] + expected_transitions[3]
    return {
        "users_with_baseline_candidates": len(baseline),
        "baseline_memberships_total": sum(len(question_ids) for question_ids in baseline.values()),
        "zone_user_rows_crossing_30_percent": crossing[30],
        "zone_user_rows_crossing_60_percent": crossing[60],
        "zone_user_rows_crossing_100_percent": crossing[100],
        "zone_user_rows_with_valid_1star_crossing_60": valid_first_star_crossings[60],
        "zone_user_rows_with_valid_1star_crossing_100": valid_first_star_crossings[100],
        "expected_2star_transitions": expected_transitions[2],
        "expected_3star_transitions": expected_transitions[3],
        "star_transitions_current_runtime_would_commit": transition_total,
        # Baseline capture itself owns no progression/reward writers.  The
        # only possible future side effect is the separate Zone-star ledger
        # when an Owner-selected full catch-up policy is enabled.
        "reward_events_current_runtime_would_trigger": 0,
        "reward_types_and_counts": {},
        "coin_total_current_runtime_would_grant": 0,
        "item_grants_current_runtime_would_grant": 0,
        "other_side_effects_current_runtime_would_trigger": {
            "zone_star_ledger_entries_if_full_policy": transition_total,
            "lord_clears": 0,
            "zone_unlocks": 0,
        },
        "rows": rows,
    }


__all__ = [
    "BASELINE_VERSION",
    "CUTOFF_LITERAL",
    "SOURCE_RULE_VERSION",
    "TRUSTED_CARD_ENTITLEMENT_SOURCE",
    "TRUSTED_REVIEW_SOURCE_PREFIXES",
    "baseline_readiness",
    "build_compatibility_census",
    "build_progression_milestone_dry_run",
    "entitlement_source_for_mask",
    "frozen_historical_memberships",
    "frozen_source_masks",
    "membership_fingerprint",
    "populate_frozen_historical_baseline",
    "pre_cutoff_review_memberships",
    "qualifying_card_memberships",
    "trusted_current_memberships",
    "current_adventure_question_count",
    "visible_adventure_question_ids",
]
