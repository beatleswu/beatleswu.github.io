"""Phase 3D: weekly 2026-W27 real grant-commit execution (write path).

This module is the ONLY place in the Community Leaderboard Rewards
toolset that actually CALLS the real production coin-granting helper
(`app._grant_coins`), the real shop-purchase-granting helper
(`app._grant_shop_purchase`), and the real badge-granting helpers
(`app.grant_community_reward_badge` / `app.is_community_reward_badge_owned`).

It is intentionally narrow: it only knows how to grant rewards for
board_type="weekly", period_key="2026-W27", and only the coins/item/
badge components -- title grants are entirely out of scope (there are 0
title payloads in this period, and this module has no title-grant wiring
at all; a claim carrying a title payload is treated as an error, never
silently skipped or silently "succeeded").

Phase 3G: leaderboard reward coins are treated as an internal system
reward, not ordinary gameplay income, and so bypass the real coin
function's normal daily earning cap -- but ONLY through this one
closure; every other caller of the real coin function throughout app.py
is unaffected and still obeys the cap unchanged. Item and badge grant
behavior is unaffected by this policy.

`tools/community_leaderboard_rewards_manual.py`'s own top-level source
never mentions any real production grant-helper by name; it imports this
module lazily, inside its `grant-weekly-2026w27-commit` command function
body only -- the same isolation pattern established in Phase 3C for
community_leaderboard_rewards_real_grant_preview.py.

Idempotency: every component grant is guarded by
`leaderboard_reward_component_log` (checked immediately before granting,
logged immediately after a successful grant) so re-running this against
claims that already have a logged component never calls the real grant
function for that component again. Each claim is processed inside its
own SAVEPOINT: if any component fails, every write made for that claim
in this run (including any already-logged components) is rolled back to
the claim's savepoint and the claim is marked 'failed' -- a failing claim
never leaves a partial grant behind, and never blocks or rolls back any
other claim already committed in this run.
"""

import community_leaderboard_rewards as lbr

BOARD_TYPE = "weekly"
PERIOD_KEY = "2026-W27"


def _real_grant_coins_fn(app_module, conn):
    # Leaderboard reward coins are an internal system reward, not ordinary
    # gameplay income -- bypass_daily_cap=True is passed explicitly here
    # ONLY, for this one closure, never from any public-facing code path.
    # Every other caller of the real coin function throughout app.py
    # still omits this argument (defaulting to False) and still obeys the
    # normal daily cap unchanged.
    def _fn(user_id, amount, reason):
        return app_module._grant_coins(conn, user_id, amount, reason, bypass_daily_cap=True)
    return _fn


def _real_grant_item_fn(app_module, conn):
    def _fn(user_id, item_key, quantity, context=None):
        item = app_module.SHOP_ITEMS[item_key]
        app_module._grant_shop_purchase(conn, user_id, item, quantity)
    return _fn


def _real_grant_badge_fn(app_module, conn):
    def _fn(user_id, badge_key):
        app_module.grant_community_reward_badge(conn, user_id=user_id, badge_key=badge_key)
    return _fn


def _real_is_badge_owned_fn(app_module, conn):
    def _fn(user_id, badge_key):
        return app_module.is_community_reward_badge_owned(
            conn, user_id=user_id, badge_key=badge_key)
    return _fn


def _grant_coin_component(conn, grant_coins_fn, *, board_type, period_key, claim_id, user_id, amount, rank_band):
    if not amount or amount <= 0:
        return None
    if lbr.is_leaderboard_reward_component_logged(conn, claim_id, "coin", "coins"):
        return {
            "claim_id": claim_id, "user_id": user_id, "component": "coin",
            "reward_key": "coins", "quantity": amount, "result": "skipped_existing",
            "detail": "already logged in leaderboard_reward_component_log",
        }
    reason = lbr._leaderboard_grant_reason(board_type, period_key, rank_band)
    result = lbr.grant_community_leaderboard_coins(
        conn, user_id=user_id, amount=amount, reason=reason,
        claim_id=claim_id, grant_coins_fn=grant_coins_fn,
    )
    lbr.log_leaderboard_reward_component(
        conn, claim_id, "coin", "coins", amount, result["result"], result.get("detail"))
    return result


def _grant_badge_component(conn, grant_badge_fn, is_badge_owned_fn, *, claim_id, user_id, badge_key):
    if lbr.is_leaderboard_reward_component_logged(conn, claim_id, "badge", badge_key):
        return {
            "claim_id": claim_id, "user_id": user_id, "component": "badge",
            "reward_key": badge_key, "quantity": 1, "result": "skipped_existing",
            "detail": "already logged in leaderboard_reward_component_log",
        }
    result = lbr.grant_community_leaderboard_badge(
        conn, user_id=user_id, badge_key=badge_key, claim_id=claim_id,
        grant_badge_fn=grant_badge_fn, is_badge_owned_fn=is_badge_owned_fn,
    )
    lbr.log_leaderboard_reward_component(
        conn, claim_id, "badge", badge_key, 1, result["result"], result.get("detail"))
    return result


def execute_weekly_2026w27_grant_commit(conn, app_module, claims):
    """Grant coins/item/badge components for every claim in `claims`
    (the caller must have already scoped this list to board_type='weekly',
    period_key='2026-W27', status='pending' -- this function does not
    re-check board_type/period_key/status itself). Never processes a
    title payload -- if a claim carries one, that claim is marked
    'failed' with a clear reason and nothing for it is granted.

    Each claim runs inside its own SAVEPOINT: on full success every
    component's write plus the claim's own status='granted' update is
    kept; on any failure, everything written for that claim in this call
    (including any component-log rows already inserted earlier in this
    same claim's processing) is rolled back to the claim's savepoint,
    then the claim is marked 'failed' as a fresh statement after the
    rollback. A claim savepoint failure never affects any other claim.

    Returns a list of per-claim result dicts:
    {"claim_id", "user_id", "status", "components": [...], "error": str|None}
    """
    grant_coins_fn = _real_grant_coins_fn(app_module, conn)
    grant_item_fn = _real_grant_item_fn(app_module, conn)
    grant_badge_fn = _real_grant_badge_fn(app_module, conn)
    is_badge_owned_fn = _real_is_badge_owned_fn(app_module, conn)

    results = []
    for claim in claims:
        claim_id = claim["claim_id"]
        user_id = claim["user_id"]
        savepoint = f"claim_grant_{claim_id}"
        conn.execute(f"SAVEPOINT {savepoint}")
        components = []
        error = None

        try:
            badge_title = lbr.extract_leaderboard_badge_title_payload(claim)
            if badge_title["titles"]:
                raise ValueError(
                    "title grants are out of scope for the Phase 3D weekly "
                    "2026-W27 commit -- refusing to process this claim"
                )

            coin_result = _grant_coin_component(
                conn, grant_coins_fn, board_type=BOARD_TYPE, period_key=PERIOD_KEY,
                claim_id=claim_id, user_id=user_id,
                amount=claim.get("granted_coins") or 0, rank_band=claim.get("rank_band"),
            )
            if coin_result is not None:
                components.append(coin_result)

            items = lbr.extract_leaderboard_item_payload(claim)
            for item_key, qty in items.items():
                result = lbr.grant_community_leaderboard_item(
                    conn, user_id=user_id, item_key=item_key, quantity=qty,
                    claim_id=claim_id, grant_item_fn=grant_item_fn,
                )
                components.append(result)

            for badge_key in badge_title["badges"]:
                result = _grant_badge_component(
                    conn, grant_badge_fn, is_badge_owned_fn,
                    claim_id=claim_id, user_id=user_id, badge_key=badge_key,
                )
                components.append(result)

        except Exception as exc:
            error = str(exc)[:500]
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            lbr.mark_leaderboard_claim_failed(conn, claim_id, error)
            results.append({
                "claim_id": claim_id, "user_id": user_id, "status": "failed",
                "components": [], "error": error,
            })
            continue

        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        lbr.mark_leaderboard_claim_granted(conn, claim_id)
        results.append({
            "claim_id": claim_id, "user_id": user_id, "status": "granted",
            "components": components, "error": None,
        })

    return results


def execute_exact_period_grant_commit(conn, app_module, claims, *, board_type, period_key):
    """Atomic exact-period grant execution.

    Unlike the legacy weekly-2026-W27 helper above, this function does not
    isolate each claim behind its own SAVEPOINT. Any component failure raises
    immediately so the caller can roll back the entire transaction and leave no
    partial grant behind for the period.
    """
    grant_coins_fn = _real_grant_coins_fn(app_module, conn)
    grant_item_fn = _real_grant_item_fn(app_module, conn)
    grant_badge_fn = _real_grant_badge_fn(app_module, conn)
    is_badge_owned_fn = _real_is_badge_owned_fn(app_module, conn)

    results = []
    for claim in claims:
        claim_id = claim["claim_id"]
        user_id = claim["user_id"]
        badge_title = lbr.extract_leaderboard_badge_title_payload(claim)
        if badge_title["titles"]:
            raise ValueError(
                f"title grants are out of scope for exact-period commit "
                f"(claim_id={claim_id}, board_type={board_type}, period_key={period_key})"
            )
        components = []
        coin_result = _grant_coin_component(
            conn,
            grant_coins_fn,
            board_type=board_type,
            period_key=period_key,
            claim_id=claim_id,
            user_id=user_id,
            amount=claim.get("granted_coins") or 0,
            rank_band=claim.get("rank_band"),
        )
        if coin_result is not None:
            components.append(coin_result)
        items = lbr.extract_leaderboard_item_payload(claim)
        for item_key, qty in items.items():
            result = lbr.grant_community_leaderboard_item(
                conn,
                user_id=user_id,
                item_key=item_key,
                quantity=qty,
                claim_id=claim_id,
                grant_item_fn=grant_item_fn,
            )
            components.append(result)
        for badge_key in badge_title["badges"]:
            result = _grant_badge_component(
                conn,
                grant_badge_fn,
                is_badge_owned_fn,
                claim_id=claim_id,
                user_id=user_id,
                badge_key=badge_key,
            )
            components.append(result)
        lbr.mark_leaderboard_claim_granted(conn, claim_id)
        results.append({
            "claim_id": claim_id,
            "user_id": user_id,
            "status": "granted",
            "components": components,
            "error": None,
        })
    return results
