-- Offline SQLite candidate ONLY. No users, wallets, XP or QuestV2 tables.
CREATE TABLE course_runs (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL CHECK(user_id > 0),
 version TEXT NOT NULL, lesson INTEGER NOT NULL CHECK(lesson BETWEEN 1 AND 20),
 day TEXT NOT NULL, video_verified INTEGER NOT NULL DEFAULT 0 CHECK(video_verified IN (0,1)),
 items TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
 UNIQUE(user_id, version, lesson)
);
CREATE TABLE course_answers (
 run_id TEXT NOT NULL REFERENCES course_runs(id), slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 7),
 first_correct INTEGER NOT NULL CHECK(first_correct IN (0,1)),
 PRIMARY KEY(run_id, slot)
);
CREATE TABLE course_events (
 user_id INTEGER NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL,
 response TEXT NOT NULL, PRIMARY KEY(user_id, request_id)
);
CREATE TABLE course_retries (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES course_runs(id), day TEXT NOT NULL,
 slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 7), item TEXT NOT NULL,
 result TEXT CHECK(result IN ('CORRECT','INCORRECT') OR result IS NULL)
);
