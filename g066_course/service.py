"""Offline SQLite candidate with serialized writes and injected existing authorities.

Not a production database adapter. Every authority callback is server-owned;
HTTP clients may submit identifiers/moves, never correctness or entitlements.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3


class CourseError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class Rules:
    enabled: bool = False
    owner_approved: bool = False
    new_lessons_per_day: int = 2
    retries_per_day: int = 3
    separate_from_free_daily_20: bool = True


class CourseService:
    def __init__(self, database, catalog, *, resolve, entitled, judge, video_evidence,
                 reward=None, enabled=False, rules=Rules(), clock=None):
        self.database, self.catalog = str(database), json.loads(json.dumps(catalog))
        self.resolve, self.entitled, self.judge = resolve, entitled, judge
        self.video_evidence, self.reward = video_evidence, reward
        self.enabled, self.rules = enabled, rules
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.version = self.catalog["version"]
        self.fingerprint = hashlib.sha256(json.dumps(self.catalog, sort_keys=True).encode()).hexdigest()
        if rules.enabled and (not rules.owner_approved or min(rules.new_lessons_per_day, rules.retries_per_day) < 1):
            raise ValueError("candidate quota requires explicit Owner approval")
        if rules.enabled and not rules.separate_from_free_daily_20:
            raise ValueError("shared free quota requires a G/D integration adapter")

    def _guard(self, user):
        if type(user) is not int or user <= 0:
            raise CourseError("login_required", 401)
        if not self.enabled:
            raise CourseError("course_feature_off", 404)

    @contextmanager
    def _tx(self):
        conn = sqlite3.connect(self.database, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _day(self):
        now = self.clock()
        if now.tzinfo is None:
            raise CourseError("server_clock_unavailable", 503)
        return now.astimezone(timezone(timedelta(hours=8))).date().isoformat()

    def _lesson(self, number):
        if type(number) is not int or not 1 <= number <= 20:
            raise CourseError("invalid_lesson", 400)
        return self.catalog["lessons"][number - 1]

    def _item(self, user, alias):
        item = self.resolve(alias)
        # Provider must bind exact canonical identity, content revision and KataGo receipt.
        if not item or item.get("identity_status") != "EXACT" or not item.get("canonical_id") or not item.get("revision") or item.get("enabled") is not True:
            raise CourseError("canonical_binding_unavailable", 503)
        if item.get("katago_status") != "APPROVED" or item.get("katago_revision") != item["revision"] or not item.get("katago_receipt"):
            raise CourseError("katago_review_required", 403)
        if self.entitled(user, item) is not True:
            raise CourseError("question_entitlement_required", 403)
        return {"alias": alias, "canonical_id": item["canonical_id"], "revision": item["revision"]}

    def _check_item(self, user, item):
        if self._item(user, item["alias"]) != item:
            raise CourseError("question_revision_changed", 409)

    def _bound_run(self, conn, user, run_id):
        run = conn.execute("SELECT * FROM course_runs WHERE id=? AND user_id=? AND version=?",
                           (run_id, user, self.version)).fetchone()
        if run is None:
            raise CourseError("run_not_found", 404)
        items = json.loads(run["items"])
        if items["catalog_sha256"] != self.fingerprint:
            raise CourseError("catalog_changed", 409)
        return run, items["questions"]

    def _event(self, user, key, payload, action):
        self._guard(user)
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise CourseError("request_id_required", 400)
        digest = hashlib.sha256(json.dumps([self.version, self.fingerprint, payload], sort_keys=True).encode()).hexdigest()
        with self._tx() as conn:
            old = conn.execute("SELECT * FROM course_events WHERE user_id=? AND request_id=?", (user, key)).fetchone()
            if old:
                if old["digest"] != digest:
                    raise CourseError("idempotency_conflict")
                return json.loads(old["response"])
            result = action(conn)
            conn.execute("INSERT INTO course_events VALUES(?,?,?,?)", (user, key, digest, json.dumps(result)))
            return result

    def summary(self, user):
        self._guard(user)
        with self._tx() as conn:
            rows = conn.execute("SELECT lesson,completed FROM course_runs WHERE user_id=? AND version=?", (user, self.version)).fetchall()
            completed = {r["lesson"] for r in rows if r["completed"]}
        return {"version": self.version, "candidate": True, "rules_active": self.rules.enabled,
                "lessons": [{"number": l["number"], "title": l["title"], "week": l["week"],
                             "complete": l["number"] in completed,
                             "unlocked": l["number"] == 1 or l["number"] - 1 in completed}
                            for l in self.catalog["lessons"]]}

    def start(self, user, lesson, key):
        def action(conn):
            entry = self._lesson(lesson)
            old = conn.execute("SELECT id FROM course_runs WHERE user_id=? AND version=? AND lesson=?",
                               (user, self.version, lesson)).fetchone()
            if old:
                run, items = self._bound_run(conn, user, old["id"])
                for item in items:
                    self._check_item(user, item)
                answered = [dict(r) for r in conn.execute("SELECT slot,first_correct FROM course_answers WHERE run_id=? ORDER BY slot", (run["id"],))]
                return {"run_id": run["id"], "questions": items, "resumed": True, "answers": answered, "complete": bool(run["completed"])}
            if lesson > 1 and not conn.execute("SELECT 1 FROM course_runs WHERE user_id=? AND version=? AND lesson=? AND completed=1",
                                               (user, self.version, lesson-1)).fetchone():
                raise CourseError("previous_lesson_required", 403)
            day = self._day()
            if self.rules.enabled:
                used = conn.execute("SELECT count(*) FROM course_runs WHERE user_id=? AND day=?", (user, day)).fetchone()[0]
                if used >= self.rules.new_lessons_per_day:
                    raise CourseError("daily_new_lesson_limit", 429)
            aliases = [q["legacy_question_id"] for q in entry["questions"]["practice"]]
            items = [self._item(user, alias) for alias in aliases]
            if len(items) != 8 or len({q["canonical_id"] for q in items}) != 8:
                raise CourseError("duplicate_practice_identity", 503)
            if self.video_evidence(user, entry["id"], self.version) is not True:
                raise CourseError("verified_video_required", 403)
            run_id = secrets.token_urlsafe(24)
            conn.execute("INSERT INTO course_runs(id,user_id,version,lesson,day,video_verified,items) VALUES(?,?,?,?,?,1,?)",
                         (run_id, user, self.version, lesson, day,
                          json.dumps({"catalog_sha256": self.fingerprint, "questions": items})))
            return {"run_id": run_id, "questions": items, "resumed": False, "answers": [], "complete": False}
        return self._event(user, key, ["start", lesson], action)

    def answer(self, user, run_id, slot, moves, key, retry_id=None):
        if type(slot) is not int or not 0 <= slot < 8 or not isinstance(moves, list) or len(moves) > 256:
            raise CourseError("invalid_answer", 400)
        def action(conn):
            run, items = self._bound_run(conn, user, run_id)
            item = items[slot]
            if retry_id:
                retry = conn.execute("SELECT * FROM course_retries WHERE id=? AND run_id=? AND slot=?",
                                     (retry_id, run_id, slot)).fetchone()
                if retry is None or retry["result"] is not None:
                    raise CourseError("retry_unavailable")
                item = json.loads(retry["item"])
            elif conn.execute("SELECT 1 FROM course_answers WHERE run_id=? AND slot=?", (run_id, slot)).fetchone():
                raise CourseError("first_answer_already_recorded")
            self._check_item(user, item)
            outcome = self.judge(user, item, moves)
            if outcome not in ("CORRECT", "INCORRECT"):
                raise CourseError("judge_unavailable_or_invalid", 503)
            if retry_id:
                conn.execute("UPDATE course_retries SET result=? WHERE id=?", (outcome, retry_id))
            else:
                conn.execute("INSERT INTO course_answers VALUES(?,?,?)", (run_id, slot, int(outcome == "CORRECT")))
            score, count = conn.execute("SELECT coalesce(sum(first_correct),0),count(*) FROM course_answers WHERE run_id=?", (run_id,)).fetchone()
            complete = count == 8 and score >= 6
            reward_called = False
            if complete and not run["completed"]:
                for issued in items:
                    self._check_item(user, issued)
                if self.video_evidence(user, self._lesson(run["lesson"])["id"], self.version) is not True:
                    raise CourseError("verified_video_required", 403)
                # Adapter MUST use existing once-only authority in this transaction.
                # None is an explicit no-reward stub; no currency/XP is invented here.
                if self.reward:
                    self.reward(conn, user, f"g066:v1:lesson:{run['lesson']:02}")
                    reward_called = True
                conn.execute("UPDATE course_runs SET completed=1 WHERE id=?", (run_id,))
            return {"outcome": outcome, "first_correct": score, "answered": count, "complete": complete,
                    "reward": "EXISTING_AUTHORITY" if reward_called else "NOT_GRANTED"}
        return self._event(user, key, ["answer", run_id, slot, moves, retry_id], action)

    def retry(self, user, run_id, slot, key, replace=False):
        if type(slot) is not int or not 0 <= slot < 8 or type(replace) is not bool:
            raise CourseError("invalid_retry", 400)
        def action(conn):
            run, items = self._bound_run(conn, user, run_id)
            answer = conn.execute("SELECT first_correct FROM course_answers WHERE run_id=? AND slot=?", (run_id, slot)).fetchone()
            if answer is None or answer[0] != 0:
                raise CourseError("wrong_answer_required")
            day = self._day()
            if self.rules.enabled:
                used = conn.execute("SELECT count(*) FROM course_retries r JOIN course_runs c ON c.id=r.run_id WHERE c.user_id=? AND r.day=?", (user, day)).fetchone()[0]
                if used >= self.rules.retries_per_day:
                    raise CourseError("daily_retry_limit", 429)
            item = items[slot]
            if replace:
                used_ids = {q["canonical_id"] for q in items}
                used_ids.update(json.loads(r[0])["canonical_id"] for r in conn.execute("SELECT item FROM course_retries WHERE run_id=?", (run_id,)))
                item = None
                for q in self._lesson(run["lesson"])["questions"]["reserve"]:
                    try:
                        candidate = self._item(user, q["legacy_question_id"])
                    except CourseError:
                        continue
                    if candidate["canonical_id"] not in used_ids:
                        item = candidate
                        break
                if item is None:
                    raise CourseError("replacement_pool_exhausted", 403)
            self._check_item(user, item)
            retry_id = secrets.token_urlsafe(24)
            conn.execute("INSERT INTO course_retries(id,run_id,day,slot,item) VALUES(?,?,?,?,?)", (retry_id, run_id, day, slot, json.dumps(item)))
            return {"retry_id": retry_id, "question": item, "affects_first_score": False}
        return self._event(user, key, ["retry", run_id, slot, replace], action)

    def question(self, user, run_id, slot, presenter, retry_id=None):
        self._guard(user)
        if type(slot) is not int or not 0 <= slot < 8:
            raise CourseError("invalid_slot", 400)
        with self._tx() as conn:
            run, items = self._bound_run(conn, user, run_id)
            item = items[slot]
            if retry_id:
                row = conn.execute("SELECT item FROM course_retries WHERE id=? AND run_id=? AND slot=? AND result IS NULL", (retry_id, run_id, slot)).fetchone()
                if row is None:
                    raise CourseError("retry_unavailable")
                item = json.loads(row[0])
            self._check_item(user, item)
            # Presenter is the existing server's solution-free board serializer.
            return presenter(user, item)


def create_temporary_schema(conn):
    """Explicit offline test helper. Never registered in startup/migration runners."""
    if not isinstance(conn, sqlite3.Connection):
        raise TypeError("offline SQLite only")
    conn.executescript(Path(__file__).with_name("offline_schema.sql").read_text(encoding="utf-8"))
