"""Idempotently seed the isolated local/LAN acceptance database.

This script is mounted into the acceptance container by the acceptance
compose file.  It never reads the canonical repository corpus or writes the
questions fixture; it only creates test users and review evidence in the
dedicated acceptance PostgreSQL database.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

# The launcher mounts this file under /tmp while the application modules live
# under /app in the image.
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

import app as application
from db import get_db
from sgf_admin_workbench import capture_workbench_report


FIXTURE_PATH = os.environ.get("QUESTIONS_JSON_PATH", "/app/data/questions.json")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fixture() -> tuple[list[dict], str]:
    with open(FIXTURE_PATH, "rb") as handle:
        raw = handle.read()
    records = json.loads(raw.decode("utf-8"))
    if not isinstance(records, list) or not records:
        raise RuntimeError("acceptance fixture must be a non-empty JSON list")
    return records, hashlib.sha256(raw).hexdigest()


def _user(conn, username: str, password: str, *, is_admin: bool) -> int:
    password_hash = generate_password_hash(password)
    row = conn.execute(
        "SELECT id FROM users WHERE lower(username)=lower(?)",
        (username,),
    ).fetchone()
    if row:
        user_id = int(row["id"])
        conn.execute(
            "UPDATE users SET password_hash=?, is_admin=?, plan='free' WHERE id=?",
            (password_hash, 1 if is_admin else 0, user_id),
        )
    else:
        created_at = _now()
        row = conn.execute(
            "INSERT INTO users(username, password_hash, is_admin, plan, created_at) "
            "VALUES(?,?,?,?,?) RETURNING id",
            (username, password_hash, 1 if is_admin else 0, "free", created_at),
        ).fetchone()
        user_id = int(row["id"])
    conn.execute("INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)", (user_id,))
    return user_id


def _legacy_player_report(conn, player_id: int, question_id: int, note: str) -> int:
    row = conn.execute(
        "SELECT id FROM question_problem_reports "
        "WHERE user_id=? AND question_id=? AND note=? "
        "ORDER BY id DESC LIMIT 1",
        (player_id, question_id, note),
    ).fetchone()
    if row:
        return int(row["id"])
    row = conn.execute(
        "INSERT INTO question_problem_reports "
        "(user_id, question_id, reason_code, note, status, created_at) "
        "VALUES(?,?,?,?,?,?) RETURNING id",
        (player_id, question_id, "answer_seems_wrong", note, "open", _now()),
    ).fetchone()
    return int(row["id"])


def _record(records: list[dict], question_id: int) -> tuple[dict, int]:
    matches = [(idx, row) for idx, row in enumerate(records) if row.get("id") == question_id]
    if len(matches) != 1:
        raise RuntimeError(f"acceptance fixture question {question_id} must be unique")
    return matches[0][1], matches[0][0]


def _capture(conn, *, records: list[dict], fixture_sha: str, source: str,
             question_id: int, issue_type: str, candidate_move: dict,
             reporter_id: int, external_key: str, legacy_report_id: int | None = None) -> int:
    record, record_index = _record(records, question_id)
    content = str(record.get("content") or record.get("sgf") or "")
    content_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    provenance = {
        "environment": "NON_PRODUCTION_ACCEPTANCE_FIXTURE",
        "fixture_path": "/app/data/questions.json",
        "fixture_sha256": fixture_sha,
        "source": source,
    }
    capture = capture_workbench_report(
        conn,
        source=source,
        reporter_id=reporter_id,
        question_id=question_id,
        record_index=record_index,
        issue_type=issue_type,
        candidate_move=candidate_move,
        observed_system_verdict="WRONG",
        gameplay_surface="main_practice" if source != "CORPUS_SCAN" else "corpus_scan",
        sgf_identity=content_sha,
        node_identity="acceptance-root",
        board_state={"fixture": True, "question_id": question_id},
        question_content_sha256=content_sha,
        authority={
            "native_sgf": None,
            "accepted_moves": record.get("accepted_moves") or [],
            "historical_katago_best_move": None,
            "solution_state": record.get("solution_state") or "open",
            "enabled": bool(record.get("enabled", True)),
        },
        comment="Acceptance fixture: review this item without touching Production.",
        source_provenance=provenance,
        legacy_report_type="question_problem_reports" if legacy_report_id else None,
        legacy_report_id=legacy_report_id,
        external_key=external_key,
        now=_now(),
    )
    return int(capture["review_item_id"])


def main() -> None:
    admin_username = os.environ["ACCEPTANCE_ADMIN_USERNAME"]
    admin_password = os.environ["ACCEPTANCE_ADMIN_PASSWORD"]
    player_username = os.environ["ACCEPTANCE_PLAYER_USERNAME"]
    player_password = os.environ["ACCEPTANCE_PLAYER_PASSWORD"]
    records, fixture_sha = _fixture()

    application.init_db()
    with get_db() as conn:
        admin_id = _user(conn, admin_username, admin_password, is_admin=True)
        player_id = _user(conn, player_username, player_password, is_admin=False)
        legacy_id = _legacy_player_report(
            conn,
            player_id,
            900001,
            "Acceptance fixture: T16 is reported as an alternative candidate.",
        )
        player_item = _capture(
            conn,
            records=records,
            fixture_sha=fixture_sha,
            source="PLAYER_REPORT",
            question_id=900001,
            issue_type="ALTERNATIVE_CORRECT_MOVE",
            candidate_move={"x": 15, "y": 3},
            reporter_id=player_id,
            external_key="acceptance:player-report:900001",
            legacy_report_id=legacy_id,
        )
        admin_item = _capture(
            conn,
            records=records,
            fixture_sha=fixture_sha,
            source="ADMIN_PLAY",
            question_id=900002,
            issue_type="SYSTEM_ANSWER_INCORRECT",
            candidate_move={"x": 14, "y": 3},
            reporter_id=admin_id,
            external_key="acceptance:admin-play:900002",
        )
        scan_item = _capture(
            conn,
            records=records,
            fixture_sha=fixture_sha,
            source="CORPUS_SCAN",
            question_id=900003,
            issue_type="QUESTION_CONTENT_PROBLEM",
            candidate_move={"x": 16, "y": 15},
            reporter_id=admin_id,
            external_key="acceptance:corpus-scan:900003",
        )

    print(json.dumps({
        "seeded": True,
        "fixture_sha256": fixture_sha,
        "record_count": len(records),
        "review_item_ids": [player_item, admin_item, scan_item],
        "production_mutation": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
