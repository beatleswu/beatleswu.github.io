# Risk Register

This register records repository-specific regression risks. It does not assert that a production defect has occurred.

## Critical

| Risk | Evidence | Impact / regression signal |
|---|---|---|
| Client-authoritative puzzle correctness | `index.html` matches SGF moves and sends only grade to `/api/srs/review`; the endpoint trusts grade and does not replay the move. | A modified client can submit a correct grade without a correct move, affecting XP, level, rewards, rating-adjacent data and leaderboards. |
| Arena state is process-local | `_lobby`, `_invites`, `_games`, `_sid_room` are dictionaries in `app.py`; Docker is pinned to one worker. | Multi-worker configuration or process restart can split/lose active games, invitations and reconnect state. |
| Single worker is an architectural requirement | Docker explicitly uses `-w 1`; compose does not configure a Socket.IO message queue. | Scaling worker count without redesign is system-breaking even though Redis is a declared dependency. |
| Monolithic high-fan-out review transaction | `/api/srs/review` updates SRS, logs, XP, badges, equipment effects, pets, monsters, quests and more. | A schema/helper regression can break the primary answer flow or partially update user progression. |
| Import/startup side effects | `wsgi.py` monkey-patches globally, initializes schema, then preloads the large dataset and DB overrides. | A test or tool importing the wrong entrypoint can require production-like services, mutate schema, or load tens of MB unexpectedly. |

## High

| Risk | Evidence | Impact / regression signal |
|---|---|---|
| Question cache plus mtime | `_questions_cache` returns the same mutable list while mtime is unchanged. | In-place mutations can persist process-locally and differ between processes; timestamp-preserving replacements can evade reload. |
| DB override vs JSON divergence | `question_overrides` is applied only during question-cache rebuild; admin resolution can persist accepted moves/disable state separately from JSON. | Two truth sources can disagree; stale cache or rebuild ordering can expose different accepted answers. |
| Multiple override systems | DB answer overrides, `explain_overrides.json`, `katago_answer_overrides.json`, and accepted moves in question JSON serve different purposes. | Reusing the wrong override layer can alter correctness or explanations silently. |
| Production dataset fallback decoding | `_load_questions()` retries invalid UTF-8 with replacement decoding and may retain old cache/empty list. | Corrupt data may be served partially or silently instead of failing startup. |
| In-memory authentication throttling | `_auth_fail_log` is per process and reset on restart. | Protection changes with worker count/restarts and is not a global rate limit. |
| Asynchronous mail/notification threads | registration returns before mail/admin notification finishes. | User-visible registration success can coexist with failed verification email delivery. |
| External subprocess lifecycle | GNU Go and KataGo processes are stored in module state with locks/timeouts. | Leaks, stalls or restarts can affect bot/explanation availability within the only web worker. |
| Scheduler duplication if misconfigured | app can start a scheduler thread; separate scheduler service also imports app. | Enabling scheduler in web and scheduler services can run jobs more than once. |
| Service worker cache coupling | `sw.js` has manual versioned caches and mixed strategies. | HTML/JS/data versions can drift on clients after release. |
| Browser-global script order | major pages and shared JS overwrite/use globals such as `onLangChange`, `WGo`, `SFX`, Socket.IO state. | Reordering script tags or renaming a function can break unrelated UI flows. |

## Medium

| Risk | Evidence | Impact / regression signal |
|---|---|---|
| Raw SQL schema is embedded in `app.py` | 80+ tables and ALTER statements live in startup code rather than migrations. | Schema review, rollback and isolated testing are difficult. |
| PostgreSQL wrapper emulates SQLite syntax | `db.py` translates placeholders and selected syntax. | SQL may work differently between test SQLite and production PostgreSQL. |
| Duplicate function definition | `_gtp_to_xy` is defined twice in `app.py`; later definition shadows earlier at import. | Edits to the first definition may have no runtime effect. |
| Large inline scripts | Core pages contain thousands of lines of DOM, business and state logic. | No module boundary for Jest; global state leaks and test setup is expensive. |
| Page-local modal systems | Similar modal/overlay patterns are reimplemented. | Escape/close/accessibility behavior can regress inconsistently. |
| Tracked archive and virtual environment | repository includes 26,907 archived files and 13,087 vendored Python files under `venv311`. | Discovery, search, security review and CI can scan obsolete/vendor code unless explicitly scoped. |
| Huge tracked dataset | 72,931 SGF files plus `questions.json`. | Test discovery or accidental load can be slow and memory-heavy. |
| Utility freshness | many repair/build scripts target mutable schemas and data formats. | Running an old utility may produce incompatible data; current ownership is unclear. |
| Legacy persistent SQLite files | entrypoint maintains several SQLite symlinks while active app DB is PostgreSQL. | Operators may mistake legacy files for authoritative application state. |
| No deterministic SGF engine module | current puzzle matching is duplicated in browser pages and rating backend helpers. | Matching/auto-reply semantics can drift across surfaces. |
