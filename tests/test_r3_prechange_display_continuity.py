"""R3 grandfathered legacy continuity: behavioural contracts.

Two tiers that must never be conflated:

* Tier 1 ``GRANDFATHERED_LEGACY_PROGRESS`` -- the reconstructed pre-change
  player-facing display predicate.  Continuity entitlement only.
* Tier 2 ``TRUSTED_SERVER_CORRECT_PROGRESS`` -- the canonical server judge.
  The only correctness authority.

These tests exercise real behaviour: SQL predicates, the published baseline
relation, the star writers and the Lord gates.  Source-substring assertions
are deliberately not used as proof of any of it.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from adventure_progress_compatibility import (
    frozen_historical_memberships,
    frozen_reconstruction_classes,
    frozen_source_masks,
    populate_frozen_historical_baseline,
    prechange_display_reconstruction,
    trusted_correct_count_after,
    visible_adventure_question_count,
    visible_adventure_question_ids,
    current_adventure_question_count,
)
from adventure_zone_progression_authority import (
    LORD_RETRY_REQUIRED_NEW_CORRECT,
    is_lord_retry_satisfied,
    lord_retry_requirement,
)
from migrations.adventure_historical_mastery_v1 import (
    CUTOFF_DOMAIN,
    CUTOFF_LITERAL,
    CUTOFF_OPERATOR,
    GRANDFATHERED_ENTITLEMENT_SOURCE,
    PRECHANGE_PREDICATE_REFERENCE_SHA,
    RECONSTRUCTION_CLASS_CONSERVATIVE,
    RECONSTRUCTION_CLASS_EXACT,
    SOURCE_LAST_GRADE_MASK,
    SOURCE_PROGRESS_CREDITED_MASK,
    SOURCE_REVIEW_GRADE_MASK,
    STATUS_FAILED_OR_INVALID,
    STATUS_READY,
    TABLE_NAME,
    baseline_readiness,
    upgrade,
)


PRE = "2026-08-01T00:00:00"
POST = "2026-09-05T00:00:00"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE review_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            source_context TEXT
        );
        CREATE TABLE srs_cards(
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            last_grade INTEGER,
            progress_credited INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, question_id)
        );
        CREATE TABLE adventure_boss_progress(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            cleared INTEGER NOT NULL DEFAULT 0,
            stars INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            best_score INTEGER NOT NULL DEFAULT 0,
            cooldown_until_seen INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT,
            cleared_at TEXT,
            updated_at TEXT,
            PRIMARY KEY(user_id, zone_key)
        );
        """
    )
    return conn


def _review(conn, uid, qid, grade=3, at=PRE, ctx="practice"):
    conn.execute(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES (?,?,?,?,?)",
        (uid, qid, grade, at, ctx),
    )


def _card(conn, uid, qid, last_grade=0, credited=0):
    conn.execute(
        "INSERT INTO srs_cards(user_id,question_id,last_grade,progress_credited) "
        "VALUES (?,?,?,?)",
        (uid, qid, last_grade, credited),
    )


# ---------------------------------------------------------------------------
# Reference implementation for the parity test (section 25).
#
# Transcribed from the historical implementation at
# 4f2547a6defd60a228f77a4457b96f24b916e22c.  It deliberately does NOT call the
# production reconstruction, so the parity test cannot pass by both sides
# sharing one newly written function.
# ---------------------------------------------------------------------------
def reference_prechange_display_set(conn, uid):
    correct = {
        int(row[0])
        for row in conn.execute(
            "SELECT DISTINCT question_id FROM review_log WHERE user_id=? AND grade>=3",
            (uid,),
        ).fetchall()
    }
    cards = conn.execute(
        "SELECT question_id, last_grade, progress_credited FROM srs_cards WHERE user_id=?",
        (uid,),
    ).fetchall()
    for row in cards:
        progress_credited = row["progress_credited"] or 0
        if progress_credited or (row["last_grade"] or 0) >= 3:
            correct.add(int(row["question_id"]))
    return correct


def reference_exact_subset(conn, uid, cutoff=CUTOFF_LITERAL):
    """The provable part: a qualifying review strictly before the cutoff."""

    return {
        int(row[0])
        for row in conn.execute(
            "SELECT DISTINCT question_id FROM review_log "
            "WHERE user_id=? AND grade>=3 AND reviewed_at < ?",
            (uid, cutoff),
        ).fetchall()
    }


# ---------------------------------------------------------------------------
# Section 24 -- every branch of the historical predicate
# ---------------------------------------------------------------------------
def _all_branch_fixture(conn):
    _review(conn, 1, 1, at=PRE)                                   # 1 review only
    _review(conn, 1, 2, at=PRE, ctx="practice")                   # 2 practice ctx
    _card(conn, 1, 3, credited=1)                                 # 3 credited orphan
    _card(conn, 1, 4, last_grade=4)                               # 4 last_grade orphan
    _review(conn, 1, 5, at=PRE); _card(conn, 1, 5, 5, 1)          # 5 all three
    _review(conn, 1, 6, grade=2, at=PRE); _card(conn, 1, 6, 2, 0)  # 6 below grade
    _review(conn, 1, 7, at=POST)                                  # 7 after cutoff
    _review(conn, 1, 8, at=CUTOFF_LITERAL)                        # 8 exactly on cutoff
    _review(conn, 1, 9, at=POST); _card(conn, 1, 9, 5, 1)         # 9 post + mutated card
    conn.commit()
    return set(range(1, 10))


def test_every_historical_branch_is_classified_correctly():
    conn = _conn()
    ids = _all_branch_fixture(conn)
    r = prechange_display_reconstruction(conn, question_ids=ids)
    classes = r["classes"]

    # 1, 2, 5 proven before the cutoff by a qualifying review.
    for qid in (1, 2, 5):
        assert classes[(1, qid)] == RECONSTRUCTION_CLASS_EXACT
    # 3, 4 undated orphan cards: preserved, but never called exact.
    for qid in (3, 4):
        assert classes[(1, qid)] == RECONSTRUCTION_CLASS_CONSERVATIVE
    # 6 never qualified under any branch; 7 and 8 have no card and only
    # current-side evidence; 9 is positively post-cutoff.
    for qid in (6, 7, 8):
        assert (1, qid) not in classes
    assert (1, 9) not in classes
    assert (1, 9) in r["post_cutoff_only"]


def test_multi_source_membership_counts_once_but_keeps_all_provenance():
    conn = _conn()
    ids = _all_branch_fixture(conn)
    upgrade(conn)
    populate_frozen_historical_baseline(conn, question_ids=ids, captured_at=POST)
    conn.commit()

    rows = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE user_id=1 AND question_id=5"
    ).fetchone()[0]
    assert rows == 1
    assert frozen_source_masks(conn)[(1, 5)] == (
        SOURCE_REVIEW_GRADE_MASK
        | SOURCE_PROGRESS_CREDITED_MASK
        | SOURCE_LAST_GRADE_MASK
    )


def test_cutoff_boundary_uses_strict_less_than():
    conn = _conn()
    _review(conn, 1, 100, at="2026-08-29T13:17:29")
    _review(conn, 1, 101, at=CUTOFF_LITERAL)
    conn.commit()
    r = prechange_display_reconstruction(conn, question_ids={100, 101})
    assert (1, 100) in r["classes"]
    assert (1, 101) not in r["classes"]
    assert CUTOFF_OPERATOR == "<"


def test_conservative_and_exact_remain_separately_reportable():
    conn = _conn()
    ids = _all_branch_fixture(conn)
    upgrade(conn)
    result = populate_frozen_historical_baseline(conn, question_ids=ids, captured_at=POST)
    conn.commit()
    assert result["exact_membership_count"] == 3
    assert result["conservative_membership_count"] == 2
    classes = frozen_reconstruction_classes(conn)
    assert sorted(v for v in classes.values()) == [
        RECONSTRUCTION_CLASS_CONSERVATIVE,
        RECONSTRUCTION_CLASS_CONSERVATIVE,
        RECONSTRUCTION_CLASS_EXACT,
        RECONSTRUCTION_CLASS_EXACT,
        RECONSTRUCTION_CLASS_EXACT,
    ]
    readiness = baseline_readiness(conn)
    assert readiness["exact_membership_count"] == 3
    assert readiness["conservative_membership_count"] == 2
    assert readiness["predicate_reference_sha"] == PRECHANGE_PREDICATE_REFERENCE_SHA
    assert readiness["cutoff_domain"] == CUTOFF_DOMAIN


def test_new_correct_answer_enters_tier2_only_and_wrong_answer_enters_neither():
    conn = _conn()
    upgrade(conn)
    populate_frozen_historical_baseline(conn, question_ids={200, 201}, captured_at=POST)
    conn.commit()
    _review(conn, 1, 200, grade=5, at=POST, ctx="mbv1:new")
    _review(conn, 1, 201, grade=1, at=POST, ctx="mbv1:new")
    conn.commit()

    assert frozen_historical_memberships(conn, user_id=1) == set()
    assert visible_adventure_question_ids(conn, 1) == {200}


def test_tier1_membership_is_never_a_correctness_or_reward_source():
    """Tier 1 is readable as progress, and is absent from trusted evidence."""

    conn = _conn()
    _card(conn, 1, 300, credited=1)
    conn.commit()
    upgrade(conn)
    populate_frozen_historical_baseline(conn, question_ids={300}, captured_at=POST)
    conn.commit()

    assert frozen_historical_memberships(conn, user_id=1) == {300}
    # Visible progress: yes.  Trusted current evidence: no.
    assert visible_adventure_question_count(conn, 1, {300}) == 1
    assert current_adventure_question_count(conn, 1, {300}) == 0
    # And it can never satisfy a post-failure retry measurement.
    assert trusted_correct_count_after(conn, 1, {300}, PRE) == 0
    entitlements = {
        row[0]
        for row in conn.execute(
            f"SELECT DISTINCT entitlement_source FROM {TABLE_NAME}"
        ).fetchall()
    }
    assert entitlements == {GRANDFATHERED_ENTITLEMENT_SOURCE}
    assert "trusted" not in GRANDFATHERED_ENTITLEMENT_SOURCE


# ---------------------------------------------------------------------------
# Section 25 -- parity against an independent reference implementation
# ---------------------------------------------------------------------------
def test_exact_subset_parity_against_reference_implementation():
    conn = _conn()
    ids = _all_branch_fixture(conn)
    reconstructed_exact = {
        qid
        for (uid, qid), value in prechange_display_reconstruction(
            conn, question_ids=ids
        )["classes"].items()
        if uid == 1 and value == RECONSTRUCTION_CLASS_EXACT
    }
    reference_exact = reference_exact_subset(conn, 1) & ids
    assert reconstructed_exact - reference_exact == set()
    assert reference_exact - reconstructed_exact == set()


def test_no_reconstructable_legacy_membership_is_silently_lost():
    """The product promise, stated as an executable assertion.

    Everything the old predicate displayed is either published as Tier 1 or
    positively classified as post-cutoff -- nothing is dropped in silence.
    """

    conn = _conn()
    ids = _all_branch_fixture(conn)
    reference = reference_prechange_display_set(conn, 1) & ids
    r = prechange_display_reconstruction(conn, question_ids=ids)
    published = {qid for (uid, qid) in r["classes"] if uid == 1}
    post_cutoff = {qid for (uid, qid) in r["post_cutoff_only"] if uid == 1}
    unaccounted = reference - published - post_cutoff
    assert unaccounted == set(), f"legacy memberships lost without a class: {unaccounted}"


# ---------------------------------------------------------------------------
# Section 14/15 -- post-failure Lord retry
# ---------------------------------------------------------------------------
def _app_module():
    import app as app_module

    return app_module


def _fail_lord(conn, uid, zone_key, at):
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,cleared_at,updated_at) VALUES (?,?,0,0,1,0,0,?,NULL,?) "
        "ON CONFLICT(user_id,zone_key) DO UPDATE SET attempts=attempts+1, "
        "last_attempt_at=excluded.last_attempt_at",
        (uid, zone_key, at, at),
    )


def _trusted_answers(conn, uid, start_qid, count, at):
    for offset in range(count):
        _review(conn, uid, start_qid + offset, grade=5, at=at, ctx="mbv1:map")


ZONE_IDS = set(range(1000, 1200))


@pytest.mark.parametrize(
    "new_correct,expected_locked",
    [(0, True), (1, True), (29, True), (30, False)],
)
def test_post_failure_retry_requires_exactly_thirty_new_trusted_answers(
    new_correct, expected_locked
):
    app_module = _app_module()
    conn = _conn()
    upgrade(conn)
    # A large grandfathered baseline must not help.
    for qid in range(1000, 1100):
        _card(conn, 7, qid, credited=1)
    conn.commit()
    populate_frozen_historical_baseline(conn, question_ids=ZONE_IDS, captured_at=PRE)
    _fail_lord(conn, 7, "zone1", "2026-09-01T00:00:00")
    _trusted_answers(conn, 7, 1000, new_correct, "2026-09-02T00:00:00")
    conn.commit()

    state = app_module._adventure_lord_retry_state(conn, 7, "zone1", ZONE_IDS)
    assert state["required"] == LORD_RETRY_REQUIRED_NEW_CORRECT == 30
    assert state["achieved"] == new_correct
    assert state["locked"] is expected_locked


def test_trusted_answers_before_the_failure_do_not_count():
    app_module = _app_module()
    conn = _conn()
    _fail_lord(conn, 8, "zone1", "2026-09-10T00:00:00")
    _trusted_answers(conn, 8, 1000, 50, "2026-09-09T23:59:59")
    conn.commit()
    state = app_module._adventure_lord_retry_state(conn, 8, "zone1", ZONE_IDS)
    assert state["achieved"] == 0
    assert state["locked"] is True


def test_duplicate_and_wrong_answers_do_not_pay_off_the_retry_lock():
    app_module = _app_module()
    conn = _conn()
    _fail_lord(conn, 9, "zone1", "2026-09-01T00:00:00")
    # Same canonical question answered correctly many times.
    for _ in range(50):
        _review(conn, 9, 1000, grade=5, at="2026-09-02T00:00:00", ctx="mbv1:map")
    # Wrong answers after the failure.
    for offset in range(50):
        _review(conn, 9, 1100 + offset, grade=1, at="2026-09-02T00:00:00", ctx="mbv1:map")
    conn.commit()
    state = app_module._adventure_lord_retry_state(conn, 9, "zone1", ZONE_IDS)
    assert state["achieved"] == 1
    assert state["locked"] is True


def test_untrusted_and_undated_evidence_cannot_open_a_retry():
    app_module = _app_module()
    conn = _conn()
    _fail_lord(conn, 10, "zone1", "2026-09-01T00:00:00")
    # Practice-context answers are not Tier 2 evidence.
    for offset in range(60):
        _review(conn, 10, 1000 + offset, grade=5, at="2026-09-02T00:00:00", ctx="practice")
    # Undated legacy cards are not evidence at all.
    for offset in range(60):
        _card(conn, 10, 1100 + offset, credited=1)
    conn.commit()
    state = app_module._adventure_lord_retry_state(conn, 10, "zone1", ZONE_IDS)
    assert state["achieved"] == 0
    assert state["locked"] is True


def test_total_zone_coverage_alone_cannot_unlock_a_retry():
    app_module = _app_module()
    conn = _conn()
    upgrade(conn)
    for qid in ZONE_IDS:
        _card(conn, 11, qid, credited=1)
    conn.commit()
    populate_frozen_historical_baseline(conn, question_ids=ZONE_IDS, captured_at=PRE)
    _fail_lord(conn, 11, "zone1", "2026-09-01T00:00:00")
    conn.commit()

    # 100% visible coverage ...
    assert visible_adventure_question_count(conn, 11, ZONE_IDS) == len(ZONE_IDS)
    # ... and still locked, because none of it is post-failure trusted work.
    state = app_module._adventure_lord_retry_state(conn, 11, "zone1", ZONE_IDS)
    assert state["locked"] is True


def test_one_batch_of_thirty_cannot_satisfy_two_failure_cycles():
    app_module = _app_module()
    conn = _conn()
    _fail_lord(conn, 12, "zone1", "2026-09-01T00:00:00")
    _trusted_answers(conn, 12, 1000, 30, "2026-09-02T00:00:00")
    conn.commit()
    assert app_module._adventure_lord_retry_state(conn, 12, "zone1", ZONE_IDS)["locked"] is False

    # The player retries and fails again.  The reference failure moves.
    _fail_lord(conn, 12, "zone1", "2026-09-03T00:00:00")
    conn.commit()
    after_b = app_module._adventure_lord_retry_state(conn, 12, "zone1", ZONE_IDS)
    assert after_b["achieved"] == 0, "the first batch must not pay off the second lock"
    assert after_b["locked"] is True

    _trusted_answers(conn, 12, 1050, 29, "2026-09-04T00:00:00")
    conn.commit()
    assert app_module._adventure_lord_retry_state(conn, 12, "zone1", ZONE_IDS)["locked"] is True

    _trusted_answers(conn, 12, 1079, 1, "2026-09-04T00:00:00")
    conn.commit()
    assert app_module._adventure_lord_retry_state(conn, 12, "zone1", ZONE_IDS)["locked"] is False


def test_cleared_zone_and_never_attempted_zone_are_not_locked():
    app_module = _app_module()
    conn = _conn()
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,cleared_at,updated_at) VALUES (13,'zone1',1,1,3,20,0,?,?,?)",
        ("2026-09-01T00:00:00", "2026-09-01T00:00:00", "2026-09-01T00:00:00"),
    )
    conn.commit()
    assert app_module._adventure_lord_retry_state(conn, 13, "zone1", ZONE_IDS)["locked"] is False
    assert app_module._adventure_lord_retry_state(conn, 14, "zone1", ZONE_IDS)["locked"] is False


def test_attempt_without_a_usable_failure_timestamp_fails_closed():
    app_module = _app_module()
    conn = _conn()
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,cleared_at,updated_at) VALUES (15,'zone1',0,0,1,0,0,NULL,NULL,?)",
        ("2026-09-01T00:00:00",),
    )
    conn.commit()
    state = app_module._adventure_lord_retry_state(conn, 15, "zone1", ZONE_IDS)
    assert state["locked"] is True


def test_retry_helpers_are_pure_and_agree_with_the_constant():
    assert lord_retry_requirement() == 30
    assert is_lord_retry_satisfied(29) is False
    assert is_lord_retry_satisfied(30) is True
    assert is_lord_retry_satisfied(None) is False


# ---------------------------------------------------------------------------
# Section 17 -- readiness must not scale with unrelated baseline rows
# ---------------------------------------------------------------------------
def _readiness_cost(rows_per_user, users):
    conn = _conn()
    conn.executemany(
        "INSERT INTO srs_cards(user_id,question_id,last_grade,progress_credited) "
        "VALUES (?,?,5,1)",
        [(u, q) for u in range(1, users + 1) for q in range(1, rows_per_user + 1)],
    )
    conn.commit()
    upgrade(conn)
    populate_frozen_historical_baseline(
        conn, question_ids=set(range(1, rows_per_user + 1)), captured_at=POST
    )
    conn.commit()
    total = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    start = time.perf_counter()
    for _ in range(30):
        baseline_readiness(conn)
    return total, (time.perf_counter() - start) / 30


def test_request_path_readiness_does_not_grow_with_unrelated_baseline_rows():
    small_rows, small_cost = _readiness_cost(20, 25)      # ~500 rows
    large_rows, large_cost = _readiness_cost(200, 250)    # ~50,000 rows
    assert large_rows > small_rows * 50
    # The O(N) implementation grew roughly linearly (about 100x here).  An
    # O(1)-shaped metadata lookup must stay within a small constant factor.
    assert large_cost < max(small_cost * 5, 0.005), (
        f"readiness cost scaled with baseline size: {small_cost:.6f}s at "
        f"{small_rows} rows vs {large_cost:.6f}s at {large_rows} rows"
    )


def test_request_path_readiness_issues_no_aggregate_over_the_relation():
    conn = _conn()
    _card(conn, 1, 1, credited=1)
    conn.commit()
    upgrade(conn)
    populate_frozen_historical_baseline(conn, question_ids={1}, captured_at=POST)
    conn.commit()

    statements = []

    class _RecordingConnection:
        """sqlite3.Connection.execute is read-only, so wrap rather than patch."""

        def __init__(self, inner):
            self._conn = inner

        def execute(self, sql, *args, **kwargs):
            statements.append(" ".join(str(sql).split()))
            return self._conn.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    readiness = baseline_readiness(_RecordingConnection(conn))

    assert readiness["status"] == STATUS_READY
    assert readiness["integrity_verified"] is False
    aggregates = [s for s in statements if "COUNT(" in s.upper() and TABLE_NAME in s]
    assert aggregates == [], f"request-path readiness ran an aggregate: {aggregates}"


def test_integrity_verification_is_still_available_on_demand():
    conn = _conn()
    _card(conn, 1, 1, credited=1)
    conn.commit()
    upgrade(conn)
    populate_frozen_historical_baseline(conn, question_ids={1}, captured_at=POST)
    conn.commit()
    verified = baseline_readiness(conn, verify_integrity=True, verify_fingerprint=True)
    assert verified["valid"] is True
    assert verified["integrity_verified"] is True
    assert verified["fingerprint_matches"] is True


def test_ready_can_be_revoked_without_deleting_historical_source_data():
    conn = _conn()
    _card(conn, 1, 1, credited=1)
    conn.commit()
    upgrade(conn)
    populate_frozen_historical_baseline(conn, question_ids={1}, captured_at=POST)
    conn.commit()
    assert visible_adventure_question_ids(conn, 1) == {1}

    conn.execute(
        "UPDATE adventure_historical_mastery_baseline SET status=?, failure_reason=? "
        "WHERE baseline_version IS NOT NULL",
        (STATUS_FAILED_OR_INVALID, "operator_revoked"),
    )
    conn.commit()

    assert baseline_readiness(conn)["valid"] is False
    assert frozen_historical_memberships(conn, user_id=1) == set()
    assert visible_adventure_question_ids(conn, 1) == set()
    # The original sources are untouched.
    assert conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0] == 1
    assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
