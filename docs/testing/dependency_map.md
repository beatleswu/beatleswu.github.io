# Dependency Map

## Runtime sequence

```text
Nginx
  -> Gunicorn (1 gevent-websocket worker)
    -> wsgi.py
      -> gevent.monkey.patch_all()
      -> psycogreen.patch_psycopg()
      -> import app
        -> construct Flask + SocketIO + Blueprint
        -> define globals/routes (no DB connection yet)
      -> app.init_db() -> PostgreSQL
      -> app._load_questions()
        -> questions.json
        -> monster taxonomy mutation
        -> PostgreSQL question_overrides
```

The separate scheduler service imports `app`, calls `init_db()`, starts the premium-weekly daemon thread, and idles.

## Backend dependencies

### Global mutable state

| State | Owner | Status | Consumers / consequence |
|---|---|---|---|
| `_questions_cache`, `_questions_mtime` | `app.py` | Verified | All puzzle/question flows; cache invalidated by admin save and override resolution. Process-local. |
| `_ADVENTURE_STATE_CACHE` | `app.py` | Verified | Adventure/report endpoints; TTL-based, process-local. |
| `_auth_fail_log`, `_auth_fail_lock` | `app.py` | Verified | Registration/login throttling; resets on restart and is not shared across workers. |
| `katago_proc`, `katago_lock`, `pending` | `app.py` | Verified | KataGo process and request correlation. |
| `_gnugo_games`, `_gnugo_lock` | `app.py` | Verified | Bot game processes/state. |
| `_lobby`, `_invites`, `_games`, `_sid_room` | `app.py` | Verified | Entire realtime arena orchestration; reason production is locked to one worker. |
| `_RT_POOL`, `_RT_POOL_READY`, `_RT_POOL_LOCK`, calibration globals | `app.py` | Verified | Rating-test pool construction and selection. |
| `_dm_cleanup_last`, `_dm_cleanup_lock` | `app.py` | Verified | Opportunistic DM retention cleanup. |
| override cache/mtime/path | `explain_overrides.py` | Verified | AI explanation labels, separate from puzzle accepted moves. |
| DB connection pool | `db.py` | Verified | Lazy singleton `ThreadedConnectionPool`, min 2/max 15 connections per process. |

### Singleton services

- **Verified** — Flask `app` and Flask-SocketIO `socketio` are created at module import.
- **Verified** — `grimoire_bp` is created in `grimoire_api.py` and registered once.
- **Verified** — PostgreSQL connection pool is lazy but process-global.
- **Verified** — GNU Go and KataGo are subprocess-backed services managed through module-level state.
- **Verified** — premium weekly scheduling is one daemon thread in the dedicated scheduler process.
- **Inferred** — accidental scheduler enablement in a web worker would duplicate polling; compose prevents it with environment configuration.

### Cache/data dependencies

| Cache/source | Invalidator | Status |
|---|---|---|
| `questions.json` in-memory cache | file mtime change or `_invalidate_questions_cache()` | Verified |
| DB `question_overrides` applied to cached list | only when cache rebuilds | Verified |
| `explain_overrides.json` | its own file mtime | Verified |
| `katago_cache.db` | external replacement/deployment | Verified |
| rating pool | `_RT_POOL_READY` and builder state | Verified |
| adventure cache | explicit clear and TTL | Verified |
| service worker caches | `sw.js` version/cache strategies | Verified |

### Database dependencies

- **Verified** — nearly every authenticated feature uses PostgreSQL through `app.get_db()` -> `db.get_db()`.
- **Verified** — `app.py` SQL is written in a SQLite-like style and translated by wrappers for PostgreSQL.
- **Verified** — schema creation runs during WSGI/scheduler startup, not during bare `import app`.
- **Verified** — `/api/katago-move` and `/api/explain` may additionally read SQLite `katago_cache.db`.
- **Unknown** — legacy `srs.db`, `go_learning.db`, `go_app.db`, and `go_game.db` are persisted/symlinked by entrypoint but active ownership is not consistently documented.

### Module import map

```text
app.py
  -> db.py (lazy inside get_db)
  -> grimoire_api.py
  -> question_taxonomy.py
  -> monster_taxonomy.py
  -> chapter_i18n.py / backend_i18n.py
  -> explain_overrides.py
  -> katago_explain.py
  -> premium_weekly.py (inside review/rating paths)
  -> premium_weekly_service.py / premium_weekly_job.py (weekly paths)
  -> newebpay.py / paypal_api.py (payment paths)

wsgi.py -> app.py
scheduler.py -> app.py -> premium_weekly_job.py
```

## Frontend dependencies

### Browser globals

| Global | Producer | Consumers |
|---|---|---|
| `WGo` | `wgo/wgo.min.js` | Puzzle, rating, bot, replay, and arena boards. |
| `I18n` / `window.I18n` | `i18n.js` | Nearly all dynamic pages. |
| `SRS` | `srs.js` | Puzzle review helpers. |
| `SFX` / `window.SFX` | `sound.js` | Puzzle, navigation, rewards, arena. |
| `io` | Socket.IO browser library loaded by pages/site nav | `play.html`, shared arena presence. |
| `MONSTER_TRASH`, `getMonsterTrash` | `monster_trash.js` | Puzzle monster UI. |
| `applyStoneSkin`, `applyBoardSkin`, `__skinBoardRef` | `wgo/stone_skin.js` | All WGo boards opting into cosmetics. |
| `onLangChange` | page-specific assignment | Called by `i18n.js`; later scripts can overwrite earlier handlers. |
| `__cgArenaSocket`, auth/presence promises/timers | `site-nav.js` and `play.html` | Shared navigation/arena presence. |

### Puzzle page global state

`index.html` uses browser globals for `allQuestions`, current question/index, parsed problem/tree/current node, WGo board, logical board, player color, solved/answering flags, ko point, daily/adventure/quest/challenge modes, shop status, reward queues, and many modal/tour states. **Verified** by declarations and direct cross-function access.

### DOM coupling

- **Verified** — scripts call `document.getElementById()` with page-specific IDs and often assume elements exist.
- **Verified** — modal visibility is mostly CSS class/display mutation by global functions.
- **Verified** — many controls use inline `onclick`, tying HTML names directly to global function names.
- **Verified** — page initialization is split among `window.onload`, `DOMContentLoaded`, immediate IIFEs, and script load order.
- **Verified** — WGo skin code monkey-patches/observes shared board globals.
- **Inferred** — unit execution under Node/JSDOM will require extensive DOM and browser-global stubs; Jest is therefore scaffolding only.

### Event listeners

- **Verified** — global `window` load/resize/hash/install/PWA events.
- **Verified** — document keydown/click/visibility listeners for modals, boards and navigation.
- **Verified** — Socket.IO event subscriptions in `play.html` and `site-nav.js`.
- **Verified** — service worker install/activate/fetch/message listeners in `sw.js`.
- **Verified** — many page-local button/input listeners and inline handlers.

## External dependency map

| Dependency | Trigger | Test isolation |
|---|---|---|
| PostgreSQL | Runtime DB access/startup init | Replace `app.get_db` with in-memory SQLite adapter for narrow tests. |
| gevent/psycogreen | `wsgi.py` only | Do not import `wsgi`; force `SOCKETIO_ASYNC_MODE=threading` before importing `app`. |
| Socket.IO server startup | `socketio.run()` only under `__main__` | Import app without starting server. |
| `questions.json` | `_load_questions()` | Monkeypatch loader with a tiny in-memory question list. |
| Turnstile | registration when secret configured | Empty test secret or patch verifier. |
| Resend | registration/password mail | Patch async mail functions. |
| Google tokeninfo | Google login | Outside Tier 1 baseline. |
| GNU Go/KataGo | bot/explain endpoints | Outside Tier 1 baseline. |
| NewebPay/PayPal | checkout/webhooks | Outside Tier 1 baseline. |
| OpenAI | AI/recommend/explanation paths | Outside Tier 1 baseline. |
