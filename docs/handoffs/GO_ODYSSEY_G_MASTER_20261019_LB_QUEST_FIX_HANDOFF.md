# Go Odyssey G MASTER — Leaderboard + Quest Client Authority Fix (2026-10-19)

**Scope:** local isolated product candidate only; production Test02 not exercised, official GitHub master / Oracle deployment untouched. Base `cc0b60d0ace5efe695d60fc77fe0e8f22081f209` includes prior real GLB 360 viewer, companion fixes and monthly prize candidate `00e9120d`.

## Actual product changes

1. **Community leaderboard UI** — `community.html`, `i18n.js`:
   - Render tab-specific explanation and header for weekly/monthly/cumulative XP/character LV/best streak/friends. Correct label of `rank`: character LV ranking by accumulated XP, *not* official Go playing strength/dan-kyu.
   - State Taiwan-time period boundaries and tie order for weekly/monthly, avoid claiming ranking alone guarantees rewards.
   - Give server-authoritative `is_you` position/score and the strictly higher score delta for the visible immediately-above user. Top-50 truncated or empty data never invents a rank.
   - Escape all untrusted rank names and context text; only presentation, no reward/leaderboard authority or schema changes.
2. **Quest board state safety** — `curriculum.html`:
   - Remove prior catch branch which synthesized coins, XP and grant flags on a failed `POST /api/rewards/sync`.
   - Require HTTP 2xx + complete nonnegative numeric server settlement before presenting earned coins/XP.
   - On lost/invalid HTTP response, GET `/api/quest-board` with no-store to reconcile current server-owned wallet and accepted/claimable quests. Never blindly resend reward POST; if readback fails, preserve original state and explain uncertainty.
   - Quest accept/abandon must not optimistically write local accepted state on network/HTTP error. Confirm server `ok: true` and authoritative board readback. Preview/file modes cannot send mutations.
   - Existing server idempotency mechanism unchanged.
3. **Regression fixture isolation** — `tests/test_rewards_sync_atomic_idempotency.py`:
   - Import real `app` first before optional stubbing, preventing a fake `grimoire_api` from polluting the same Python test run and breaking monthly Postgres `init_db`.

## Executed evidence

- `node tests/e2e/run_20261019_leaderboard_context_browser.mjs`: **8/8 PASS** in real Chrome, local fixture HTTP APIs, actual `community.html` loaded and tab switched; no actual Test02 login.
- `node tests/e2e/run_20261019_quest_claim_fail_closed.mjs`: **14/14 PASS** executing actual `curriculum.html` client source in local isolated Node VM with controlled failure/success response scenarios; not real production backend.
- Standalone Python backend combined (rewards, quests, monthly): **52/52 PASS** after fixing fixture pollution (the initial mixed run was **46 passed, 6 setup errors**, and is not reported as PASS).
- Broader product Python regression across A–F: **170 passed, 2 skipped, 7 deselected**, exit code 0, including monthly.
- Inline JS in `curriculum.html` and `community.html` parsed; `git diff --check` exit 0.
- Machine-readable immutable receipts:
  - `docs/handoffs/GO_ODYSSEY_LB_R02_R06_BROWSER_20261019.json`
  - `docs/handoffs/GO_ODYSSEY_Q04_QUEST_CLAIM_FAIL_CLOSED_20261019.json`.

**Excluded**: local untracked `secret_key.txt` (never staged/copied; not evidence). Formal Build, Docker release matrix, rollback drill, signed source adoption and deployment remain pending explicit Owner gates. Production Test02 UAT, real iPad UAT, character growth–adventure E2E and V4 autonomous R15 E2E are NOT PASS. V4 stays **NO_GO**.

## A–F

A — companion switching/pat/feed and GLB 360 local candidate PASS, Test02 pending.
B — hero presentation local candidate; growth-to-adventure player E2E pending.
C — **quest accept/abandon/claim fail-closed client fixes** + backend 52 combined PASS; production Quest V2 remains gated.
D — world map candidate held; real iPad UAT pending.
E — **ranking presentation and identity/gap**, monthly settlement relogin isolated PG test retained; production relogin pending.
F — prior shop/backpack changes preserved; official source adoption pending.

No production mutation, new authorization, fake signature, push, merge or deployment.
