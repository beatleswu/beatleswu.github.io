"""Map Battle v1 schema and persistence primitives.

This module deliberately stops below the HTTP and judging layers.  It owns
only additive persistence for the server-authoritative Map Battle design.
Callers must execute settlement inside their existing database transaction;
the module never commits a battle settlement itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import uuid


MAP_BATTLE_V1_MODE_ENV = "E10_MAP_BATTLE_V1_MODE"
MAP_BATTLE_V1_MODES = (
    "off",
    "dark",
    "admin",
    "allowlist",
    "percentage",
    "global",
)
DEFAULT_MAP_BATTLE_V1_MODE = "off"
MAP_BATTLE_JUDGE_VERSION = "map-battle-judge-v1"
ATTEMPT_TTL_HOURS = 24
IDEMPOTENCY_RETENTION_DAYS = 30
SETTLED_SUBMISSION_AUDIT_RETENTION_DAYS = 90

LEGACY_SAFE_TO_MIGRATE = "SAFE_TO_MIGRATE"
LEGACY_READ_ONLY_REQUIRES_FRESH_BATTLE = "READ_ONLY_REQUIRES_FRESH_BATTLE"
LEGACY_ALREADY_V1 = "ALREADY_V1"
LEGACY_INVALID_STATE = "INVALID_LEGACY_STATE"

_SCHEMA_ADVISORY_LOCK_KEY = 778899789
_ALLOWED_BATTLE_STATES = ("OPEN", "COMPLETED", "EXPIRED")
_ALLOWED_ATTEMPT_STATES = ("ISSUED", "RESERVED", "SETTLED", "REJECTED", "EXPIRED")
_ALLOWED_SUBMISSION_STATES = ("RESERVED", "SETTLED", "REJECTED")
_ALLOWED_JUDGE_RESULTS = ("CORRECT", "INCORRECT", "INVALID")


class MapBattlePersistenceError(RuntimeError):
    """Base error for an expected persistence-layer rejection."""

    code = "map_battle_persistence_error"


class MapBattleNotFound(MapBattlePersistenceError):
    code = "map_battle_not_found"


class MapBattleOwnershipError(MapBattlePersistenceError):
    code = "map_battle_ownership_error"


class StaleBattleRevision(MapBattlePersistenceError):
    code = "stale_battle_revision"


class SubmissionConflict(MapBattlePersistenceError):
    code = "submission_conflict"


class InvalidSettlement(MapBattlePersistenceError):
    code = "invalid_settlement"


def get_map_battle_v1_mode(environ=None):
    """Return the server-controlled mode, failing closed for any bad value."""

    source = os.environ if environ is None else environ
    value = str(source.get(MAP_BATTLE_V1_MODE_ENV, DEFAULT_MAP_BATTLE_V1_MODE)).strip().lower()
    return value if value in MAP_BATTLE_V1_MODES else DEFAULT_MAP_BATTLE_V1_MODE


def _utc_now_text():
    return datetime.now(timezone.utc).isoformat()


def _timestamp_text(value):
    if value is None:
        return _utc_now_text()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _expires_at_for(issued_at):
    if isinstance(issued_at, datetime):
        value = issued_at
    else:
        value = datetime.fromisoformat(str(issued_at).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (value + timedelta(hours=ATTEMPT_TTL_HOURS)).isoformat()


def _raw_connection(conn):
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn):
    return _raw_connection(conn).__class__.__module__.startswith("sqlite3")


def _row_as_dict(row):
    if row is None:
        return None
    if isinstance(row, Mapping):
        return dict(row)
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in row.keys()}
    if isinstance(row, (tuple, list)):
        raise TypeError("map battle queries require mapping rows")
    return dict(row)


def _fetchone(conn, statement, parameters=()):
    return _row_as_dict(conn.execute(statement, parameters).fetchone())


def _require_nonempty(value, name, maximum=255):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a non-empty string of at most {maximum} characters")
    return value


def _validate_nonnegative(value, name):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _canonical_json_text(value):
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_submission_nonce(submission_nonce):
    """Hash a nonce without ever persisting or returning the raw value."""

    _require_nonempty(submission_nonce, "submission_nonce", 512)
    return hashlib.sha256(submission_nonce.encode("utf-8")).hexdigest()


def _acquire_schema_lock(conn):
    # The application uses PostgreSQL.  The SQLite branch exists only for
    # deterministic schema/unit tests; it must not be presented as a locking
    # equivalent to PostgreSQL.
    if not _is_sqlite(conn):
        conn.execute(f"SELECT pg_advisory_xact_lock({_SCHEMA_ADVISORY_LOCK_KEY})")


def ensure_map_battle_tables(conn):
    """Install the additive Map Battle v1 schema through the app DB framework."""

    _acquire_schema_lock(conn)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS map_battles (
            id                  TEXT PRIMARY KEY,
            user_id             INTEGER NOT NULL,
            zone_key            TEXT NOT NULL,
            state               TEXT NOT NULL DEFAULT 'OPEN',
            player_hp           INTEGER NOT NULL,
            player_hp_max       INTEGER NOT NULL,
            monster_hp          INTEGER NOT NULL,
            monster_hp_max      INTEGER NOT NULL,
            battle_revision     INTEGER NOT NULL DEFAULT 0,
            migration_source    TEXT,
            migration_version   TEXT,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            completed_at        TEXT,
            CONSTRAINT map_battles_state_ck
                CHECK (state IN ('OPEN', 'COMPLETED', 'EXPIRED')),
            CONSTRAINT map_battles_zone_key_ck
                CHECK (length(trim(zone_key)) > 0),
            CONSTRAINT map_battles_player_hp_ck
                CHECK (player_hp >= 0 AND player_hp_max > 0 AND player_hp <= player_hp_max),
            CONSTRAINT map_battles_monster_hp_ck
                CHECK (monster_hp >= 0 AND monster_hp_max > 0 AND monster_hp <= monster_hp_max),
            CONSTRAINT map_battles_revision_ck
                CHECK (battle_revision >= 0),
            CONSTRAINT map_battles_completed_ck
                CHECK ((state = 'COMPLETED') = (completed_at IS NOT NULL)),
            CONSTRAINT map_battles_owner_key_uq UNIQUE (user_id, id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS map_battle_attempts (
            id                          TEXT PRIMARY KEY,
            battle_id                   TEXT NOT NULL,
            user_id                     INTEGER NOT NULL,
            question_id                 INTEGER NOT NULL,
            question_revision           TEXT NOT NULL,
            initial_position_identity   TEXT NOT NULL,
            board_size                  INTEGER NOT NULL,
            player_color                TEXT NOT NULL,
            transform_version           TEXT NOT NULL,
            transform_id                TEXT NOT NULL,
            judge_version               TEXT NOT NULL DEFAULT 'map-battle-judge-v1',
            state                       TEXT NOT NULL DEFAULT 'ISSUED',
            issued_at                   TEXT NOT NULL,
            expires_at                  TEXT NOT NULL,
            settled_at                  TEXT,
            battle_revision_at_issue   INTEGER NOT NULL,
            created_at                  TEXT NOT NULL,
            updated_at                  TEXT NOT NULL,
            CONSTRAINT map_battle_attempts_state_ck
                CHECK (state IN ('ISSUED', 'RESERVED', 'SETTLED', 'REJECTED', 'EXPIRED')),
            CONSTRAINT map_battle_attempts_question_revision_ck
                CHECK (length(trim(question_revision)) > 0),
            CONSTRAINT map_battle_attempts_position_ck
                CHECK (length(trim(initial_position_identity)) > 0),
            CONSTRAINT map_battle_attempts_board_size_ck
                CHECK (board_size > 1 AND board_size <= 25),
            CONSTRAINT map_battle_attempts_color_ck
                CHECK (player_color IN ('B', 'W')),
            CONSTRAINT map_battle_attempts_transform_ck
                CHECK (length(trim(transform_version)) > 0 AND length(trim(transform_id)) > 0),
            CONSTRAINT map_battle_attempts_expiry_ck
                CHECK (expires_at > issued_at),
            CONSTRAINT map_battle_attempts_revision_ck
                CHECK (battle_revision_at_issue >= 0),
            CONSTRAINT map_battle_attempts_owner_key_uq UNIQUE (user_id, battle_id, id),
            FOREIGN KEY (user_id, battle_id)
                REFERENCES map_battles(user_id, id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS map_battle_submissions (
            id                      TEXT PRIMARY KEY,
            battle_id              TEXT NOT NULL,
            attempt_id             TEXT NOT NULL,
            user_id                INTEGER NOT NULL,
            submission_nonce_hash  TEXT NOT NULL,
            request_hash           TEXT NOT NULL,
            canonical_move_json    TEXT NOT NULL,
            settlement_state        TEXT NOT NULL DEFAULT 'RESERVED',
            judge_result            TEXT,
            authoritative_grade     INTEGER,
            damage_to_monster       INTEGER NOT NULL DEFAULT 0,
            damage_to_player        INTEGER NOT NULL DEFAULT 0,
            monster_hp_before       INTEGER,
            monster_hp_after        INTEGER,
            player_hp_before        INTEGER,
            player_hp_after         INTEGER,
            battle_revision_before  INTEGER,
            battle_revision_after   INTEGER,
            received_at             TEXT NOT NULL,
            settled_at              TEXT,
            created_at              TEXT NOT NULL,
            updated_at              TEXT NOT NULL,
            CONSTRAINT map_battle_submissions_state_ck
                CHECK (settlement_state IN ('RESERVED', 'SETTLED', 'REJECTED')),
            CONSTRAINT map_battle_submissions_result_ck
                CHECK (judge_result IS NULL OR judge_result IN ('CORRECT', 'INCORRECT', 'INVALID')),
            CONSTRAINT map_battle_submissions_grade_ck
                CHECK (authoritative_grade IS NULL OR (authoritative_grade >= 0 AND authoritative_grade <= 5)),
            CONSTRAINT map_battle_submissions_hash_ck
                CHECK (length(trim(submission_nonce_hash)) > 0 AND length(trim(request_hash)) > 0),
            CONSTRAINT map_battle_submissions_damage_ck
                CHECK (damage_to_monster >= 0 AND damage_to_player >= 0),
            CONSTRAINT map_battle_submissions_hp_ck
                CHECK (
                    (monster_hp_before IS NULL OR monster_hp_before >= 0) AND
                    (monster_hp_after IS NULL OR monster_hp_after >= 0) AND
                    (player_hp_before IS NULL OR player_hp_before >= 0) AND
                    (player_hp_after IS NULL OR player_hp_after >= 0)
                ),
            CONSTRAINT map_battle_submissions_revision_ck
                CHECK (
                    (battle_revision_before IS NULL AND battle_revision_after IS NULL) OR
                    (battle_revision_before IS NOT NULL AND battle_revision_after IS NOT NULL
                     AND battle_revision_after > battle_revision_before)
                ),
            CONSTRAINT map_battle_submissions_invalid_ck
                CHECK (
                    settlement_state <> 'REJECTED' OR
                    (judge_result = 'INVALID' AND damage_to_monster = 0 AND damage_to_player = 0)
                ),
            CONSTRAINT map_battle_submissions_settled_ck
                CHECK (
                    settlement_state <> 'SETTLED' OR
                    (judge_result IN ('CORRECT', 'INCORRECT') AND settled_at IS NOT NULL
                     AND battle_revision_before IS NOT NULL AND battle_revision_after IS NOT NULL)
                ),
            CONSTRAINT map_battle_submissions_attempt_uq UNIQUE (user_id, battle_id, attempt_id),
            CONSTRAINT map_battle_submissions_nonce_uq
                UNIQUE (user_id, battle_id, attempt_id, submission_nonce_hash),
            FOREIGN KEY (user_id, battle_id)
                REFERENCES map_battles(user_id, id) ON DELETE CASCADE,
            FOREIGN KEY (user_id, battle_id, attempt_id)
                REFERENCES map_battle_attempts(user_id, battle_id, id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_battles_user_active "
        "ON map_battles(user_id, state, updated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_battles_revision "
        "ON map_battles(id, user_id, battle_revision)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_battles_migration "
        "ON map_battles(migration_source, migration_version)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_battle_attempts_battle "
        "ON map_battle_attempts(battle_id, user_id, state)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_battle_attempts_expiry "
        "ON map_battle_attempts(state, expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_battle_submissions_nonce "
        "ON map_battle_submissions(user_id, battle_id, attempt_id, submission_nonce_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_battle_submissions_processing "
        "ON map_battle_submissions(settlement_state, received_at)"
    )
    if hasattr(conn, "commit"):
        conn.commit()


def create_map_battle(
    conn,
    *,
    user_id,
    zone_key,
    player_hp,
    player_hp_max,
    monster_hp,
    monster_hp_max,
    battle_id=None,
    state="OPEN",
    migration_source=None,
    migration_version=None,
    now=None,
):
    if state not in _ALLOWED_BATTLE_STATES:
        raise ValueError("invalid map battle state")
    _require_nonempty(zone_key, "zone_key")
    for name, value in (
        ("player_hp", player_hp),
        ("player_hp_max", player_hp_max),
        ("monster_hp", monster_hp),
        ("monster_hp_max", monster_hp_max),
    ):
        _validate_nonnegative(value, name)
    if player_hp_max <= 0 or monster_hp_max <= 0:
        raise ValueError("maximum HP must be positive")
    if player_hp > player_hp_max or monster_hp > monster_hp_max:
        raise ValueError("current HP cannot exceed maximum HP")
    if state == "COMPLETED":
        raise ValueError("completed battles require an explicit settlement transition")
    battle_id = battle_id or uuid.uuid4().hex
    timestamp = _timestamp_text(now)
    conn.execute(
        """INSERT INTO map_battles (
            id, user_id, zone_key, state, player_hp, player_hp_max,
            monster_hp, monster_hp_max, battle_revision, migration_source,
            migration_version, created_at, updated_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, NULL)""",
        (
            battle_id,
            user_id,
            zone_key,
            state,
            player_hp,
            player_hp_max,
            monster_hp,
            monster_hp_max,
            migration_source,
            migration_version,
            timestamp,
            timestamp,
        ),
    )
    return battle_id


def issue_map_battle_attempt(
    conn,
    *,
    user_id,
    battle_id,
    question_id,
    question_revision,
    initial_position_identity,
    board_size,
    player_color,
    transform_version,
    transform_id,
    battle_revision_at_issue,
    attempt_id=None,
    judge_version=MAP_BATTLE_JUDGE_VERSION,
    issued_at=None,
    expires_at=None,
):
    _require_nonempty(question_revision, "question_revision")
    _require_nonempty(initial_position_identity, "initial_position_identity")
    _require_nonempty(transform_version, "transform_version")
    _require_nonempty(transform_id, "transform_id")
    if board_size <= 1 or board_size > 25:
        raise ValueError("board_size must be between 2 and 25")
    if player_color not in ("B", "W"):
        raise ValueError("player_color must be B or W")
    _validate_nonnegative(battle_revision_at_issue, "battle_revision_at_issue")
    issued_text = _timestamp_text(issued_at)
    expires_text = _timestamp_text(expires_at) if expires_at is not None else _expires_at_for(issued_at or issued_text)
    if expires_text <= issued_text:
        raise ValueError("expires_at must be later than issued_at")
    attempt_id = attempt_id or uuid.uuid4().hex
    timestamp = issued_text
    conn.execute(
        """INSERT INTO map_battle_attempts (
            id, battle_id, user_id, question_id, question_revision,
            initial_position_identity, board_size, player_color,
            transform_version, transform_id, judge_version, state,
            issued_at, expires_at, settled_at, battle_revision_at_issue,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ISSUED', ?, ?, NULL, ?, ?, ?)""",
        (
            attempt_id,
            battle_id,
            user_id,
            question_id,
            question_revision,
            initial_position_identity,
            board_size,
            player_color,
            transform_version,
            transform_id,
            judge_version,
            issued_text,
            expires_text,
            battle_revision_at_issue,
            timestamp,
            timestamp,
        ),
    )
    return attempt_id


def lookup_attempt_for_owner(conn, *, user_id, attempt_id):
    return _fetchone(
        conn,
        "SELECT * FROM map_battle_attempts WHERE id=? AND user_id=?",
        (attempt_id, user_id),
    )


def load_authoritative_battle_state(conn, *, user_id, battle_id):
    return _fetchone(
        conn,
        "SELECT * FROM map_battles WHERE id=? AND user_id=?",
        (battle_id, user_id),
    )


def load_battle_for_update(conn, *, user_id, battle_id, expected_revision=None):
    statement = "SELECT * FROM map_battles WHERE id=? AND user_id=?"
    if not _is_sqlite(conn):
        statement += " FOR UPDATE"
    row = _fetchone(conn, statement, (battle_id, user_id))
    if row is None:
        raise MapBattleNotFound("battle does not exist for owner")
    if expected_revision is not None and row["battle_revision"] != expected_revision:
        raise StaleBattleRevision("battle revision is stale")
    return row


def compare_and_advance_battle_revision(
    conn,
    *,
    user_id,
    battle_id,
    expected_revision,
    now=None,
):
    _validate_nonnegative(expected_revision, "expected_revision")
    timestamp = _timestamp_text(now)
    cursor = conn.execute(
        """UPDATE map_battles
           SET battle_revision=battle_revision+1, updated_at=?
         WHERE id=? AND user_id=? AND battle_revision=? AND state='OPEN'""",
        (timestamp, battle_id, user_id, expected_revision),
    )
    if cursor.rowcount != 1:
        raise StaleBattleRevision("battle revision compare-and-set failed")
    return expected_revision + 1


def _submission_by_id(conn, *, user_id, battle_id, attempt_id, submission_id):
    return _fetchone(
        conn,
        """SELECT * FROM map_battle_submissions
           WHERE id=? AND user_id=? AND battle_id=? AND attempt_id=?""",
        (submission_id, user_id, battle_id, attempt_id),
    )


def reserve_submission_nonce(
    conn,
    *,
    user_id,
    battle_id,
    attempt_id,
    submission_nonce,
    request_hash,
    canonical_move_json="{}",
    submission_id=None,
    received_at=None,
):
    """Atomically reserve one nonce; duplicate handling is DB-constraint based."""

    nonce_hash = hash_submission_nonce(submission_nonce)
    _require_nonempty(request_hash, "request_hash", 128)
    canonical_json = _canonical_json_text(canonical_move_json)
    timestamp = _timestamp_text(received_at)
    submission_id = submission_id or uuid.uuid4().hex
    cursor = conn.execute(
        """INSERT INTO map_battle_submissions (
            id, battle_id, attempt_id, user_id, submission_nonce_hash,
            request_hash, canonical_move_json, settlement_state,
            judge_result, authoritative_grade, damage_to_monster,
            damage_to_player, received_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'RESERVED', NULL, NULL, 0, 0, ?, ?, ?)
        ON CONFLICT DO NOTHING""",
        (
            submission_id,
            battle_id,
            attempt_id,
            user_id,
            nonce_hash,
            request_hash,
            canonical_json,
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    if cursor.rowcount == 1:
        return {
            "created": True,
            "duplicate": False,
            "submission_id": submission_id,
            "submission_nonce_hash": nonce_hash,
        }

    existing = _fetchone(
        conn,
        """SELECT * FROM map_battle_submissions
           WHERE user_id=? AND battle_id=? AND attempt_id=?
             AND submission_nonce_hash=?""",
        (user_id, battle_id, attempt_id, nonce_hash),
    )
    if existing is not None:
        if existing["request_hash"] != request_hash:
            raise SubmissionConflict("same submission nonce was reused for a different request")
        return {
            "created": False,
            "duplicate": True,
            "submission_id": existing["id"],
            "submission_nonce_hash": nonce_hash,
            "record": existing,
        }

    attempt_submission = _fetchone(
        conn,
        """SELECT * FROM map_battle_submissions
           WHERE user_id=? AND battle_id=? AND attempt_id=?""",
        (user_id, battle_id, attempt_id),
    )
    if attempt_submission is not None:
        raise SubmissionConflict("an attempt may have only one submission")
    raise SubmissionConflict("submission reservation was rejected by an ownership constraint")


def record_submission_settlement(
    conn,
    *,
    submission_id,
    user_id,
    battle_id,
    attempt_id,
    settlement_state,
    judge_result,
    authoritative_grade=None,
    damage_to_monster=0,
    damage_to_player=0,
    monster_hp_before=None,
    monster_hp_after=None,
    player_hp_before=None,
    player_hp_after=None,
    battle_revision_before=None,
    battle_revision_after=None,
    settled_at=None,
):
    if settlement_state not in _ALLOWED_SUBMISSION_STATES:
        raise InvalidSettlement("invalid settlement state")
    if judge_result not in _ALLOWED_JUDGE_RESULTS:
        raise InvalidSettlement("invalid judge result")
    for name, value in (
        ("damage_to_monster", damage_to_monster),
        ("damage_to_player", damage_to_player),
    ):
        _validate_nonnegative(value, name)
    if settlement_state == "REJECTED":
        if judge_result != "INVALID" or damage_to_monster or damage_to_player:
            raise InvalidSettlement("invalid submissions cannot settle damage")
    if settlement_state == "SETTLED":
        if judge_result not in ("CORRECT", "INCORRECT") or settled_at is None:
            raise InvalidSettlement("settled submissions require an authoritative result and timestamp")
        if battle_revision_after is None or battle_revision_before is None:
            raise InvalidSettlement("settled submissions require revision evidence")
        if battle_revision_after <= battle_revision_before:
            raise InvalidSettlement("settlement revision must advance")
    timestamp = _timestamp_text(settled_at) if settled_at is not None else None
    cursor = conn.execute(
        """UPDATE map_battle_submissions SET
            settlement_state=?, judge_result=?, authoritative_grade=?,
            damage_to_monster=?, damage_to_player=?, monster_hp_before=?,
            monster_hp_after=?, player_hp_before=?, player_hp_after=?,
            battle_revision_before=?, battle_revision_after=?, settled_at=?,
            updated_at=?
         WHERE id=? AND user_id=? AND battle_id=? AND attempt_id=?
           AND settlement_state='RESERVED'""",
        (
            settlement_state,
            judge_result,
            authoritative_grade,
            damage_to_monster,
            damage_to_player,
            monster_hp_before,
            monster_hp_after,
            player_hp_before,
            player_hp_after,
            battle_revision_before,
            battle_revision_after,
            timestamp,
            _timestamp_text(None),
            submission_id,
            user_id,
            battle_id,
            attempt_id,
        ),
    )
    if cursor.rowcount != 1:
        existing = _submission_by_id(
            conn,
            user_id=user_id,
            battle_id=battle_id,
            attempt_id=attempt_id,
            submission_id=submission_id,
        )
        if existing and existing["settlement_state"] in ("SETTLED", "REJECTED"):
            return {"duplicate": True, "submission": existing}
        raise SubmissionConflict("submission is not reservable")
    return {
        "duplicate": False,
        "submission": _submission_by_id(
            conn,
            user_id=user_id,
            battle_id=battle_id,
            attempt_id=attempt_id,
            submission_id=submission_id,
        ),
    }


def settle_map_battle_submission(
    conn,
    *,
    user_id,
    battle_id,
    attempt_id,
    submission_id,
    expected_revision,
    judge_result,
    authoritative_grade=None,
    damage_to_monster=0,
    damage_to_player=0,
    heal_to_player=0,
    settled_at=None,
):
    """Apply one deterministic server result atomically within caller's tx.

    The function receives an already-authoritative result from the future
    judge adapter; it does not parse moves, trust client grades, or expose an
    HTTP route.  On any exception the caller's transaction must roll back.
    """

    existing = _submission_by_id(
        conn,
        user_id=user_id,
        battle_id=battle_id,
        attempt_id=attempt_id,
        submission_id=submission_id,
    )
    if existing is None:
        raise MapBattleNotFound("submission does not exist for owner")
    if existing["settlement_state"] in ("SETTLED", "REJECTED"):
        return {"duplicate": True, "submission": existing, "battle": load_authoritative_battle_state(conn, user_id=user_id, battle_id=battle_id)}
    if existing["settlement_state"] != "RESERVED":
        raise SubmissionConflict("submission is not in a reservable state")

    battle = load_battle_for_update(
        conn,
        user_id=user_id,
        battle_id=battle_id,
        expected_revision=expected_revision,
    )
    if battle["state"] != "OPEN":
        raise SubmissionConflict("battle is not open")
    if judge_result not in _ALLOWED_JUDGE_RESULTS:
        raise InvalidSettlement("invalid judge result")
    _validate_nonnegative(damage_to_monster, "damage_to_monster")
    _validate_nonnegative(damage_to_player, "damage_to_player")
    _validate_nonnegative(heal_to_player, "heal_to_player")

    timestamp = _timestamp_text(settled_at)
    if judge_result == "INVALID":
        if damage_to_monster or damage_to_player or heal_to_player or authoritative_grade is not None:
            raise InvalidSettlement("invalid submissions cannot carry grade, damage, or healing")
        recorded = record_submission_settlement(
            conn,
            submission_id=submission_id,
            user_id=user_id,
            battle_id=battle_id,
            attempt_id=attempt_id,
            settlement_state="REJECTED",
            judge_result="INVALID",
            settled_at=None,
        )
        conn.execute(
            "UPDATE map_battle_attempts SET state='REJECTED', updated_at=? WHERE id=? AND user_id=? AND battle_id=?",
            (timestamp, attempt_id, user_id, battle_id),
        )
        return {
            "duplicate": recorded["duplicate"],
            "submission": recorded["submission"],
            "battle": load_authoritative_battle_state(conn, user_id=user_id, battle_id=battle_id),
        }

    monster_before = battle["monster_hp"]
    player_before = battle["player_hp"]
    monster_after = max(0, monster_before - damage_to_monster)
    player_after = min(
        int(battle["player_hp_max"]),
        max(0, player_before - damage_to_player) + heal_to_player,
    )
    next_revision = compare_and_advance_battle_revision(
        conn,
        user_id=user_id,
        battle_id=battle_id,
        expected_revision=expected_revision,
        now=timestamp,
    )
    next_state = "COMPLETED" if monster_after == 0 or player_after == 0 else "OPEN"
    completed_at = timestamp if next_state == "COMPLETED" else None
    conn.execute(
        """UPDATE map_battles SET player_hp=?, monster_hp=?, state=?,
            completed_at=?, updated_at=? WHERE id=? AND user_id=?""",
        (
            player_after,
            monster_after,
            next_state,
            completed_at,
            timestamp,
            battle_id,
            user_id,
        ),
    )
    recorded = record_submission_settlement(
        conn,
        submission_id=submission_id,
        user_id=user_id,
        battle_id=battle_id,
        attempt_id=attempt_id,
        settlement_state="SETTLED",
        judge_result=judge_result,
        authoritative_grade=authoritative_grade,
        damage_to_monster=damage_to_monster,
        damage_to_player=damage_to_player,
        monster_hp_before=monster_before,
        monster_hp_after=monster_after,
        player_hp_before=player_before,
        player_hp_after=player_after,
        battle_revision_before=expected_revision,
        battle_revision_after=next_revision,
        settled_at=timestamp,
    )
    conn.execute(
        """UPDATE map_battle_attempts SET state='SETTLED', settled_at=?, updated_at=?
           WHERE id=? AND user_id=? AND battle_id=?""",
        (timestamp, timestamp, attempt_id, user_id, battle_id),
    )
    return {
        "duplicate": recorded["duplicate"],
        "submission": recorded["submission"],
        "battle": load_authoritative_battle_state(conn, user_id=user_id, battle_id=battle_id),
    }


def classify_legacy_battle_for_migration(legacy_battle):
    """Conservatively classify a legacy row without migrating or mutating it."""

    row = dict(legacy_battle or {})
    if row.get("schema_version") == "map-battle-v1" or row.get("judge_version") == MAP_BATTLE_JUDGE_VERSION:
        return LEGACY_ALREADY_V1
    required_identity = ("user_id", "battle_id", "zone_key", "player_hp", "player_hp_max", "monster_hp", "monster_hp_max")
    if any(key not in row or row[key] in (None, "") for key in required_identity):
        return LEGACY_INVALID_STATE
    for key in ("player_hp", "player_hp_max", "monster_hp", "monster_hp_max"):
        if not isinstance(row[key], int) or row[key] < 0:
            return LEGACY_INVALID_STATE
    if row["player_hp_max"] <= 0 or row["monster_hp_max"] <= 0:
        return LEGACY_INVALID_STATE
    if row["player_hp"] > row["player_hp_max"] or row["monster_hp"] > row["monster_hp_max"]:
        return LEGACY_INVALID_STATE
    safe_identity = ("attempt_id", "question_revision", "player_color", "transform_version", "transform_id")
    if any(key not in row or row[key] in (None, "") for key in safe_identity):
        return LEGACY_READ_ONLY_REQUIRES_FRESH_BATTLE
    if row["player_color"] not in ("B", "W"):
        return LEGACY_INVALID_STATE
    return LEGACY_SAFE_TO_MIGRATE


__all__ = [
    "ATTEMPT_TTL_HOURS",
    "DEFAULT_MAP_BATTLE_V1_MODE",
    "IDEMPOTENCY_RETENTION_DAYS",
    "LEGACY_ALREADY_V1",
    "LEGACY_INVALID_STATE",
    "LEGACY_READ_ONLY_REQUIRES_FRESH_BATTLE",
    "LEGACY_SAFE_TO_MIGRATE",
    "MAP_BATTLE_JUDGE_VERSION",
    "MAP_BATTLE_V1_MODE_ENV",
    "MAP_BATTLE_V1_MODES",
    "InvalidSettlement",
    "MapBattleNotFound",
    "MapBattleOwnershipError",
    "MapBattlePersistenceError",
    "StaleBattleRevision",
    "SubmissionConflict",
    "classify_legacy_battle_for_migration",
    "compare_and_advance_battle_revision",
    "create_map_battle",
    "ensure_map_battle_tables",
    "get_map_battle_v1_mode",
    "hash_submission_nonce",
    "issue_map_battle_attempt",
    "load_authoritative_battle_state",
    "load_battle_for_update",
    "lookup_attempt_for_owner",
    "record_submission_settlement",
    "reserve_submission_nonce",
    "settle_map_battle_submission",
]
