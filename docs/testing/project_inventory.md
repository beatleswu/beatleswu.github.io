# Project Inventory

Discovery date: 2026-06-27
Branch: `testing-baseline`
Scope: tracked files from `git ls-files`. User-authorized untracked files are excluded.

Status labels:

- **Verified**: directly observed in tracked source or configuration.
- **Inferred**: behavior follows from code/configuration but was not executed against production services.
- **Unknown**: intent or live behavior cannot be established from the repository alone.

## System shape

| Area | Status | Inventory |
|---|---|---|
| Web application | Verified | Root-level Flask monolith in `app.py`; 280 `@app.route` decorators. |
| Blueprint | Verified | `grimoire_api.py` registers `grimoire_bp`; 8 routes. |
| Realtime | Verified | Flask-SocketIO in `app.py`; 31 event handlers for lobby, invitations, games, counting, undo, rematch, and chat. |
| Database | Verified | PostgreSQL through `db.py` and `psycopg2`; no ORM models. Schema is declared by SQL in `app.init_db()` and `grimoire_api.ensure_node_mastery_table()`. |
| Puzzle truth currently used | Verified | `questions.json` plus SGF content embedded per question; loaded by `app._load_questions()`. |
| Frontend | Verified | Root-level HTML pages with large browser-global inline scripts plus 11 active standalone JavaScript files. There is no `templates/`, `static/`, or active `src/` application tree. |
| Production process | Verified | Gunicorn, one gevent-websocket worker, `wsgi.py`, Nginx, PostgreSQL, and a separate scheduler container. |
| Redis | Verified / inactive | Dependency and Socket.IO message-queue option exist, but `docker-compose.prod.yml` intentionally leaves `SOCKETIO_MESSAGE_QUEUE` unset for the single worker. |
| External programs | Verified | GNU Go subprocesses for bot play; optional KataGo executable/files for analysis. |
| External APIs | Verified | Cloudflare Turnstile, Resend, Google tokeninfo, OpenAI-facing explanation code, NewebPay, and PayPal. |

## Backend modules

### Runtime modules

| Module | Status | Responsibility |
|---|---|---|
| `app.py` | Verified | Flask app, route handlers, schema initialization, authentication, puzzle APIs, SRS/progression/economy/social systems, GNU Go, Socket.IO arena, and rating test. |
| `db.py` | Verified | Lazy `ThreadedConnectionPool`, PostgreSQL wrappers, and SQLite-style `?` placeholder translation. |
| `grimoire_api.py` | Verified | Grimoire Blueprint, daily training selection, training answers, contamination/purity, weakness reporting. |
| `wsgi.py` | Verified | gevent and psycopg monkey patching, imports app, runs `init_db()`, and preloads questions. |
| `scheduler.py` | Verified | Separate process that initializes DB and starts the weekly scheduler thread. |
| `premium_weekly.py` | Verified | Deterministic weekly statistics and rating calculations. |
| `premium_weekly_service.py` | Verified | Weekly report/training set persistence and public payloads. |
| `premium_weekly_job.py` | Verified | Idempotent scheduled report generation. |
| `question_taxonomy.py` | Verified | Puzzle discipline/stage taxonomy and enrichment. |
| `monster_taxonomy.py` | Verified | Monster/encounter classification and question mutation during load/build. |
| `chapter_i18n.py`, `backend_i18n.py` | Verified | Backend localization lookup. |
| `explain_overrides.py` | Verified | mtime-cached, source-keyed explanation override loader; separate from answer overrides. |
| `newebpay.py`, `paypal_api.py` | Verified | Payment provider clients/helpers. |
| `rating_calibration.py` | Verified | Rating calibration calculations. |
| `posts_data.py` | Verified | Blog metadata. |

### Tools and offline jobs

**Verified** first-party tools include question building/classification/auditing, KataGo batch analysis and rollback scripts, rating-bank/calibration builders, migrations, social-media generation, image/asset generation, and SGF repair/export/import utilities. These are listed file-by-file in `coverage_of_discovery.md`.

`chattts_worker.py`, `daily_problem.py`, and `compose_daily.py` are executable/offline worker-style scripts. Their production invocation is **Unknown** because no tracked service definition calls them.

### Flask route families

The route decorators were extracted directly from `app.py`.

| Family | Status | Representative endpoints |
|---|---|---|
| Health/static/pages | Verified | `/healthz`, `/api/healthz`, `/`, `/login`, `/landing`, `/hero`, `/play`, `/games`, `/stats`, `/shop`, `/assets/<path>`, `/sw.js`, blog and icon routes. |
| Authentication/account | Verified | `/api/auth/config`, register, login, Google login, logout, email verification/resend, forgot/reset/change password, `/api/auth/me`, nickname and onboarding endpoints. |
| Questions/admin authoring | Verified | `/api/questions`, `/api/question/<qid>`, save/add/delete/move/reorder, difficulty/discipline, book/chapter operations, manage listing, alternative-answer review. |
| Puzzle review/progression | Verified | `/api/srs/card/<qid>`, `/api/srs/review`, `/api/srs/due`, `/api/xp/status`, quests, map progress, adventure, daily challenge, mistakes, stats. |
| Grimoire Blueprint | Verified | `/api/zones`, zone grimoires, grimoire progress/training, `/api/training/answer`, contaminated nodes, weakness report, flux. |
| Equipment/economy | Verified | player inventory/equip, appearance/wardrobe, skills, class, shop, coins, rewards, badges, pets. |
| Social | Verified | leaderboard, community leaderboard/tournament/reviews, profiles, friends, direct messages, friend challenges. |
| Arena/bot | Verified | game records; bot new/move/pass/undo/estimate/resign/score/end; Socket.IO arena handlers. |
| Rating test | Verified | pool info, start/resume/answer/result, placement finish, anonymous claim, SP claim, and admin metrics/calibration. |
| Premium/payments | Verified | weekly reports/training/admin review, subscription status, trial codes, NewebPay, PayPal, admin payments. |
| AI/analysis | Verified | `/api/katago-move`, `/api/explain`, and `/api/recommend`. |
| Admin | Verified | users, assets, retention, reports, trial-code batches, premium reports, rating-test metrics, payments, and upsell metrics. |

The 280 app routes break down into 226 `/api/...` routes and 54 page/static routes. The Blueprint adds 8 API routes.

### Socket.IO handlers

**Verified** events:

`disconnect`, `enter_lobby`, `toggle_dnd`, `set_availability`, `set_activity`, `heartbeat`, `send_invite`, `accept_invite`, `decline_invite`, `create_game`, `cancel_waiting`, `join_game`, `reconnect_game`, `make_move`, `pass_move`, `resign_game`, `toggle_dead_group`, `confirm_count`, `request_count`, `accept_count`, `reject_count`, `request_position_eval`, `request_auto_dead_stones`, `resume_from_count`, `player_timeout`, `request_undo`, `accept_undo`, `reject_undo`, `request_rematch`, `accept_rematch`, and `send_chat`.

## Database schema

There are no ORM model classes. The following tables are **Verified** from `CREATE TABLE IF NOT EXISTS` statements:

- Identity/account: `users`, `user_stats`, `subscriptions`, `email_preferences`, `email_deliveries`, `trial_code_batches`, `trial_codes`, `trial_code_redemptions`.
- Puzzle/SRS: `srs_cards`, `review_log`, `mistake_log`, `unit_progress`, `daily_training_queue`, `question_comments`, `comment_likes`, `question_overrides`, `question_alternative_reports`, `question_alt_report_audit`.
- Progress/adventure: `zones`, `grimoires`, `daily_quests`, `quest_accepted`, `daily_challenge`, `daily_challenge_log`, `newbie_quest_state`, `newbie_quest_tasks`, `newbie_quest_events`, `adventure_boss_progress`, `adventure_zone_unlocks`, `monster_hp_log`, `monster_kill_log`, `monster_kill_history`, `battlefield_monster`.
- Grimoire extension: `daily_training_cache`, `node_mastery`, `player_grimoire_progress`.
- Equipment/economy: `player_wardrobe`, `player_appearance`, `player_skills`, `player_inventory`, `player_sp`, `skill_tree`, `shop_inventory`, `currency_log`, `active_effects`, `gacha_log`, `daily_shop`, `user_pets`, `pet_inventory`, `pet_action_log`, `pet_collection`, `badges_earned`, `reward_claimed`.
- Social/game: `game_results`, `game_records`, `friendships`, `dm_threads`, `dm_messages`, `dm_reads`, `dm_blocks`, `dm_reports`, `dm_admin_audit`, `friend_challenges`, `friend_challenge_answers`, `challenges`, `challenge_answers`, `teacher_student`, `teacher_comments`, `share_links`.
- Premium/analytics: `weekly_reports`, `weekly_report_disciplines`, `weekly_report_reviews`, `weekly_report_admin_logs`, `premium_training_sets`, `premium_training_items`, `premium_quest_tokens`, `rating_test_sessions`, `rating_test_responses`, `upsell_events`, `payment_orders`, `payment_notify_log`, `app_kv`, `book_bands`.

`katago_cache.db` is a separate read-only SQLite cache used by explanation/move endpoints. Legacy SQLite database files are copied/symlinked by `entrypoint.sh`, but active application persistence goes through PostgreSQL in `db.py`.

## Frontend inventory

### Standalone JavaScript

| File | Status | Role / browser globals |
|---|---|---|
| `i18n.js` | Verified | `window.I18n`; translation data and language-change callbacks. |
| `mobile-nav.js` | Verified | Mobile navigation and `window.onLangChange` integration. |
| `site-nav.js` | Verified | Site navigation, shared auth request, Socket.IO loading, arena presence globals/timer. |
| `monster_trash.js` | Verified | `window.MONSTER_TRASH`, aliases, and `window.getMonsterTrash`. |
| `pwa.js` | Verified | Install banner and iOS installation guide. |
| `sound.js` | Verified | `window.SFX`. |
| `srs.js` | Verified | Browser-global `SRS` helper. |
| `sw.js` | Verified | Service worker shell/image caches; cache-first/network-first strategies. |
| `wgo/stone_skin.js` | Verified | `window.applyStoneSkin`, `applyBoardSkin`, `setBoardSkin`, and shared WGo board references. |
| `wgo/wgo.min.js`, `wgo/wgo.player.min.js` | Verified | Vendored WGo board/player browser globals. |

### Pages and UI components

The application has 35 active HTML files. Most page logic is inline and browser-global.

- Puzzle/home: `index.html` — WGo board, SGF parser, client-side move matching, auto reply, solution/retry/next controls, SRS submission, XP/reward UI, quests, adventure, modals, and tours.
- Authentication: `login.html`, `landing.html`.
- Arena/bot: `play.html`, `games.html`, `bot.html`.
- Progress: `curriculum.html`, `mistakes.html`, `stats.html`, `daily_challenge.html`, `rating_test.html`, `premium_weekly.html`.
- Character/economy: `hero.html`, `inventory.html`, `badges.html`, `shop.html`, `upgrade.html`.
- Social: `community.html`, `messages.html`, `profile.html`, `share_view.html`.
- Administration: `admin.html`, `manage.html`.
- Static/legal/content: `terms.html` and 11 files under `blog/`.

### Modal systems

**Verified** modal/overlay implementations are page-local rather than shared components. Important examples:

- `index.html`: answer/explanation panel, alternate-answer reporting, badges, loot/appearance/pet reward toasts, quest/boss overlays, daily/premium flows, and onboarding tours.
- `admin.html`: password reset, deletion, asset editing, DM report context, alternative-answer context, retention and premium review controls.
- `hero.html`: equipment, wardrobe, appearance, skill, pet and progression overlays.
- `play.html`: invitation, game setup, counting, undo/rematch, estimate, reconnect and result overlays.
- `shop.html`: purchase/gacha overlays and merchant state.
- `upgrade.html`: checkout modal and subscription controls.

## Infrastructure

| Component | Status | Evidence |
|---|---|---|
| PostgreSQL 16 | Verified | `docker-compose.prod.yml`; `db.py`. |
| Redis | Verified optional / inactive in current compose | `requirements.txt` and `SocketIO(message_queue=...)`; compose comment explicitly selects single-process mode. |
| Socket.IO | Verified | Flask-SocketIO plus Nginx WebSocket proxy. |
| gevent | Verified production-only | `wsgi.py` monkey patches before importing app; Gunicorn gevent-websocket worker. |
| Gunicorn workers | Verified | `Dockerfile` uses `-w 1`. |
| Scheduler | Verified | Dedicated compose service executes `python scheduler.py`; web disables scheduler. |
| Persistent volume | Verified | `/app/data` and PostgreSQL volume; entrypoint symlinks legacy DB/key paths. |
| Nginx | Verified | Reverse proxy, WebSocket upgrade, gzip, premium-token rate limit. |
| Deployment | Verified but out of mission scope | `deploy.ps1` and `deploy_quick.ps1`; neither is executed by this mission. |

## Admin tools and utilities

**Verified** families:

- Question pipeline: `build_questions.py`, `classify_questions.py`, `apply_chapter_classification.py`, `question_taxonomy.py`, `monster_taxonomy.py`, `tag_difficulty.py`, `refine_database.py`.
- SGF checks/repair: `check_sgf.py`, `convert_mgt_to_sgf.py`, `restore_missing_sgf_from_questions.py`, `sync_katago_answers_to_sgf.py`.
- KataGo audit: `katago_*`, `export_*`, `import_reviewed_sgfs.py`, `rollback_katago_*`.
- Rating: `build_rating_*`, `simulate_rating_anchor_mix.py`, `rating_calibration.py`.
- Migration/backfill: `migrate_sqlite_to_pg.py`, `backfill_newbie_onboarding.py`, `reset_v5.py`.
- Content/media: `build_blog.py`, `build_godokoro_*`, `make_*`, `publish_shorts.py`, `tools/*`.

Whether every utility is still operational against the current schema is **Unknown**; no production services were invoked.
