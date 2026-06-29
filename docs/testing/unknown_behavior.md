# Unknown Behavior

This document deliberately avoids guessing. Each item is marked **Unknown** and includes only the observed evidence.

## Potentially dead or shadowed code

- **Unknown — `app.py:warmup_katago()`**: a definition exists; no tracked first-party call was found.
- **Unknown — first `app.py:_gtp_to_xy()` definition**: the name is defined again later in the same module, so the earlier function is shadowed after import. Whether any import-time code captures the earlier object was not found.
- **Unknown — `play_server_addon.py`**: no import from active runtime modules was found.
- **Unknown — `chattts_worker.py`, `daily_problem.py`, `compose_daily.py`**: executable logic exists, but no tracked Docker service, scheduler, or module import establishes current invocation.
- **Unknown — underscore-prefixed root tools** (`_check_17_18.py`, `_check_nearby_rank.py`, `_execute_mix.py`, `_mix_plan.py`, `_rename_topics.py`): no documented production owner or scheduled caller was found.
- **Unknown — legacy DB files** (`srs.db`, `go_learning.db`, `go_app.db`, `go_game.db`): entrypoint persists/symlinks them, but active request-path ownership is not documented consistently.

## Undocumented logic

- **Unknown — canonical answer authority**: current code combines SGF embedded in `questions.json`, `accepted_moves`, DB `question_overrides`, rating-test replay, and client-side injected answer nodes. No single repository document defines precedence for all surfaces.
- **Unknown — puzzle result metadata**: SGF data sampled during discovery contains move trees but does not establish a standard per-node success/fail property.
- **Unknown — multiple accepted-move semantics**: DB accepted moves and frontend answer-tree injection are visible, but expected continuation/auto-reply behavior for every equivalent first move is not documented.
- **Unknown — explanation override relationship**: `explain_overrides.json` is explicitly for explanation labels; its operational relationship to accepted answers is not formally documented.
- **Unknown — bot/KataGo availability policy**: executable paths and timeouts exist, but expected behavior when binaries/models/cache files are absent is spread across handlers.
- **Unknown — live rating calibration gate**: shadow/live environment flags and admin endpoints exist; current production release approval cannot be derived from source.

## Orphan-function candidates

The following are **Unknown**, not declared dead. Automated name search found definitions without an obvious tracked first-party caller, but decorators, callbacks, CLI execution, or dynamic lookup may still invoke them:

- `warmup_katago`
- offline builders’ top-level `build`, `main`, and publication helpers
- media-generation functions in `make_*`, `build_godokoro_*`, and `manim_*`
- rollback/import/export helpers intended for manual operations

No code was removed.

## Unexplained state transitions

- **Unknown — arena restart/reconnect**: process-local games support disconnect grace and reconnect, but behavior after worker/container restart has no persisted recovery transition.
- **Unknown — simultaneous puzzle modes**: `nextQuestion()` uses a fixed branch order for quest, challenge, daily and adventure modes; product intent for overlapping state is not documented.
- **Unknown — question cache and override timing**: DB overrides are applied during cache rebuild. The expected maximum delay after an out-of-band DB change is undocumented.
- **Unknown — scheduler recovery**: hourly loop and idempotent job code exist; missed-run/backfill expectations after downtime are not stated.
- **Unknown — external email failure UX**: registration succeeds before background mail completion; repository source does not define how a user is informed of an asynchronous delivery failure.
- **Unknown — legacy/new ranking relationship**: arena Go rank, practice LV, and rating-test Elo coexist. Mapping and user-facing precedence are implemented in several helpers but not governed by one specification.
- **Unknown — malformed question dataset policy**: loader tolerates replacement decoding or old-cache fallback. Whether operations should instead fail closed is undocumented.
