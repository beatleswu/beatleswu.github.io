# Golden User Flows

All steps below are traced from tracked source. “Verified” means the path and state mutation are visible in code; it does not mean the flow was exercised against production.

## Authentication

### Login

1. **Verified** — `login.html` collects username/email and password and posts to `/api/auth/login`.
2. **Verified** — `app.auth_login()` validates required fields and checks an in-memory, per-process failure throttle.
3. **Verified** — PostgreSQL looks up username/email; Werkzeug verifies `password_hash`.
4. **Verified** — on success, `last_login` and `user_stats` are updated; expired premium state may be downgraded.
5. **Verified** — Flask session receives `user_id`, username, nickname, admin flag, and plan.
6. **Inferred** — the browser follows the login page’s redirect to the requested/home flow.

Regression checkpoints: valid credentials return 200; invalid credentials return 401; missing fields return 400; the session can subsequently call `/api/auth/me`.

### Registration

1. **Verified** — `login.html` posts account, nickname, email, password/confirmation and optional Turnstile token to `/api/auth/register`.
2. **Verified** — the route applies IP throttling, Turnstile validation when configured, username/email/password validation, and uniqueness checks.
3. **Verified** — a user and initial `user_stats` row are created in one DB context; password is hashed.
4. **Verified** — verification and admin-notification emails are dispatched asynchronously when configured.
5. **Verified** — the new user is automatically signed into the Flask session.
6. **Unknown** — live mail delivery, Turnstile behavior, and the final email-verification link require external credentials/services.

Regression checkpoints: a valid user is persisted and authenticated; duplicate username/email returns 409; invalid payloads do not insert rows.

### Logout

1. **Verified** — client posts `/api/auth/logout`.
2. **Verified** — server clears the Flask session and returns success.
3. **Inferred** — UI returns to `/login` or unauthenticated landing behavior.

## Puzzle

### Load puzzle

1. **Verified** — authenticated client requests `/api/questions`; the response contains enabled summaries and lock state, but no SGF body.
2. **Verified** — server calls `_load_questions()`, which reads `questions.json` only when its mtime changes, mutates classification fields, applies DB `question_overrides`, then caches the list globally.
3. **Verified** — when a question is selected, `/api/question/<qid>` returns SGF `content`, accepted moves, metadata and lock state.
4. **Verified** — `index.html` parses SGF in browser-global `parseSGF()`, creates the WGo board, installs setup stones, determines player color, and sets `currentNode`.
5. **Verified** — tests must replace `_load_questions()` with a small fixture; the production dataset must not be loaded.

Regression checkpoints: authentication required; missing qid returns 404; known fixture returns the expected SGF and accepted moves.

### Submit answer

1. **Verified** — `index.html:onBoardClick()` rejects occupied, ko, and suicide points in the browser.
2. **Verified** — accepted first-move overrides are injected into the answer tree before play.
3. **Verified** — the selected coordinate is compared with the current SGF node’s children in the browser.
4. **Verified** — wrong/off-tree client moves trigger wrong UI and `submitSRS(0)`.
5. **Verified** — a completed correct branch triggers correct UI, explanation, and `submitSRS(3)`.
6. **Verified** — `/api/srs/review` trusts the submitted grade and records SRS/review/progression/economy effects; it does not receive or independently validate the move sequence.

Regression checkpoint for the minimal backend baseline: authenticated POST with invalid grade is rejected before DB mutation. Full success-path testing is partially testable because the route fans out to many economy/progression tables.

### Show answer

1. **Verified** — `showSolutionNow()` delegates to `showAnswer()` after cancelling exploration.
2. **Verified** — solution display traverses the current client-side SGF answer tree and updates board/UI state.
3. **Unknown** — there is no server-side audit event specifically proving that “show answer” was used.

### Retry

1. **Verified** — wrong-answer UI exposes the retry/reset control.
2. **Verified** — `resetProblem()` rebuilds the current question state and board from the already-loaded question.
3. **Verified** — no production dataset reload is required for a retry.

### Next puzzle

1. **Verified** — `nextQuestion()` chooses, in priority order, completed quest handling, quest-next id, friend challenge sequence, daily queue, adventure subset, then circular `allQuestions`.
2. **Verified** — it calls `loadQuestion()` for the selected item.
3. **Unknown** — desired product behavior when multiple modes are simultaneously active is not documented outside the branch order in code.

## Progression

### XP

1. **Verified** — `/api/srs/review` calculates XP only when a correct answer was not previously correct.
2. **Verified** — base difficulty XP, first-correct/mistake-correction bonuses, combo multiplier, appearance bonus, pet bonus and optional potion may contribute.
3. **Verified** — XP and rank progress are persisted in `user_stats`; response returns gain and progress data.

### Level

1. **Verified** — `LV_THRESHOLDS` defines LV1–LV50; `xp_to_lv()` and `lv_progress()` derive level from cumulative XP.
2. **Verified** — `rank_level` is updated on review and exposed by `/api/xp/status`.
3. **Verified** — level changes can unlock appearance/reward behavior.

### Rating

1. **Verified** — `rating_test.html` and `/api/rating_test/*` implement adaptive placement/testing.
2. **Verified** — the server parses/replays answer trees for rating answers and persists sessions/responses.
3. **Verified** — placement finalization writes `users.elo_rating` and adventure unlocks.
4. **Unknown** — live calibration quality and player-facing accuracy require current production data.

## Economy

### Equipment

1. **Verified** — definitions are module constants in `app.py`; owned/equipped state is persisted in inventory/skill/appearance tables.
2. **Verified** — `/api/player/inventory`, `/equip`, `/api/player/appearance*`, `/api/skills/*`, and `/api/class/*` expose state and mutations.
3. **Verified** — review-time bonuses read equipped appearance/pet/effect state.

### Inventory

1. **Verified** — items are granted/consumed through helper functions and persisted in `shop_inventory`, `player_inventory`, `player_wardrobe`, pet inventory, and related tables.
2. **Verified** — shop buy/use/gacha endpoints mutate coins, inventory and logs.
3. **Unknown** — transactional correctness across all reward branches was not executed in this baseline.

### Rewards

1. **Verified** — correct reviews can award XP, badges, appearance drops, pet XP/food, monster progression and daily-quest rewards.
2. **Verified** — `/api/rewards/sync` and multiple quest/boss endpoints add additional rewards.
3. **Verified** — client displays badge, loot, appearance and pet reward toasts from server payloads.

## Social

### Leaderboard

1. **Verified** — `/api/leaderboard` and `/api/community/leaderboard` query persisted user/progression data.
2. **Verified** — `community.html` renders ranking and related social views.
3. **Unknown** — ordering under ties and production-scale performance were not exercised.

### Arena

1. **Verified** — `play.html` connects via Socket.IO, enters lobby, manages presence/invitations, creates/joins a room, sends moves and handles counting/results.
2. **Verified** — server keeps lobby, invitations, games and sid-to-room mappings in module-level dictionaries.
3. **Verified** — completed games are persisted through game result/record tables.
4. **Unknown** — reconnect/failover behavior across process restart cannot be recovered from those in-memory dictionaries.

### Ranking

1. **Verified** — `/api/go-rank` returns persisted rank and recent results.
2. **Verified** — early users may set an initial rank through `/api/set-go-rank`; game outcomes update rank via server logic.
3. **Verified** — rating-test Elo and arena Go rank are separate state dimensions.
