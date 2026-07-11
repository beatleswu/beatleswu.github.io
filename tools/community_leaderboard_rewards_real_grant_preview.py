"""Phase 3C: real production grant-function dry-run preview.

This module is the ONLY place in the Community Leaderboard Rewards
toolset that references the real production coin-granting helper,
shop-purchase-granting helper, and the real badge storage table by
name -- and even here, it never CALLS or writes through any of them.
Every reference is either:

  - `getattr(module, "<name>", None)` + `inspect.signature(...)`
    (existence + signature-compatibility checking only), or
  - a read-only `SELECT` (badge ownership check).

The real coin/item functions' names are only ever followed by a comma,
closing paren, or end of line in this file -- never by an opening
parenthesis, i.e. they are never actually invoked as a function call
anywhere in this source. This is verified by a dedicated test in
tests/test_community_leaderboard_rewards_real_grant_preview.py, which
also injects "dangerous" fake functions that raise if actually called
and confirms they never fire.

`tools/community_leaderboard_rewards_manual.py` deliberately delegates
to this module via a single import local to one function body (inside
`run_grant_real_preview`, not at module load time) so its own top-level
source stays free of any real production-helper reference, preserving
every pre-existing safety test on that file unchanged (it has asserted
"this file never mentions the real coin/item/badge/wardrobe grant
helpers or storage tables by name" since Phase 1 / PR 5).
"""

import inspect

import community_leaderboard_rewards as lbr

REAL_COIN_FUNCTION_NAME = "_grant_coins"
REAL_ITEM_FUNCTION_NAME = "_grant_shop_purchase"
REAL_SHOP_ITEMS_ATTR = "SHOP_ITEMS"
REAL_BADGE_DEFS_ATTR = "BADGE_DEFS"
REAL_BADGE_TABLE = "badges_earned"

EXPECTED_COIN_FUNCTION_PARAMS = ["conn", "uid", "amount", "reason", "bypass_daily_cap"]
EXPECTED_ITEM_FUNCTION_PARAMS = ["conn", "uid", "item", "qty"]


def load_app_module():
    """Import app.py lazily -- only when actually building real dry-run
    wrappers. app.py's own module-level code has no side effect beyond
    defining functions/routes/constants, so importing it does not write
    anything by itself."""
    import app as app_module
    return app_module


def real_coin_dry_run_wrapper(app_module, *, user_id, amount, reason):
    """Validate inputs and confirm the real coin-granting helper exists
    with a compatible signature. Never calls it -- this proves the real
    production write target exists and would accept these arguments; it
    performs no read or write against any table."""
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError(f"user_id must be an int, got {user_id!r}")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValueError(f"amount must be a positive int, got {amount!r}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"reason must be a non-empty string, got {reason!r}")

    target = getattr(app_module, REAL_COIN_FUNCTION_NAME, None)
    if target is None:
        raise RuntimeError(
            f"app.{REAL_COIN_FUNCTION_NAME} does not exist -- real coin grant target missing")
    actual_params = list(inspect.signature(target).parameters.keys())
    if actual_params != EXPECTED_COIN_FUNCTION_PARAMS:
        raise RuntimeError(
            f"app.{REAL_COIN_FUNCTION_NAME} signature changed: "
            f"expected {EXPECTED_COIN_FUNCTION_PARAMS}, got {actual_params}"
        )
    return {
        "would_call": f"app.{REAL_COIN_FUNCTION_NAME}",
        "args_checked": {"user_id": user_id, "amount": amount, "reason": reason},
        "signature_ok": True,
    }


def real_item_dry_run_wrapper(app_module, *, user_id, item_key, quantity):
    """Validate the item key against the Phase 3B weekly allowlist and
    confirm the item exists in the real shop item catalog and the real
    shop-purchase-granting helper exists with a compatible signature.
    Never calls it."""
    if not lbr.is_phase_3b_item_key_allowed(item_key):
        raise ValueError(f"item_key {item_key!r} is not on the Phase 3B weekly allowlist")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ValueError(f"quantity must be a positive int, got {quantity!r}")

    shop_items = getattr(app_module, REAL_SHOP_ITEMS_ATTR, None)
    if shop_items is None or item_key not in shop_items:
        raise RuntimeError(
            f"app.{REAL_SHOP_ITEMS_ATTR} does not define {item_key!r} -- real item target missing")

    target = getattr(app_module, REAL_ITEM_FUNCTION_NAME, None)
    if target is None:
        raise RuntimeError(
            f"app.{REAL_ITEM_FUNCTION_NAME} does not exist -- real item grant target missing")
    actual_params = list(inspect.signature(target).parameters.keys())
    if actual_params != EXPECTED_ITEM_FUNCTION_PARAMS:
        raise RuntimeError(
            f"app.{REAL_ITEM_FUNCTION_NAME} signature changed: "
            f"expected {EXPECTED_ITEM_FUNCTION_PARAMS}, got {actual_params}"
        )
    return {
        "would_call": f"app.{REAL_ITEM_FUNCTION_NAME}",
        "args_checked": {"user_id": user_id, "item_key": item_key, "quantity": quantity},
        "signature_ok": True,
    }


def real_badge_dry_run_wrapper(app_module, conn, *, user_id, badge_key):
    """Validate the badge key against the Phase 3B weekly allowlist and
    confirm it's defined in the real badge definition list, then perform
    a read-only ownership check (SELECT only) against the real badge
    storage table. Never inserts anything -- there is no INSERT
    statement anywhere in this function."""
    if not lbr.is_phase_3b_badge_key_allowed(badge_key):
        raise ValueError(f"badge_key {badge_key!r} is not on the Phase 3B weekly allowlist")

    badge_defs = getattr(app_module, REAL_BADGE_DEFS_ATTR, None)
    if badge_defs is None or not any(b.get("id") == badge_key for b in badge_defs):
        raise RuntimeError(
            f"badge_key {badge_key!r} is not defined in app.{REAL_BADGE_DEFS_ATTR} "
            "-- real badge target missing"
        )

    already_owned = conn.execute(
        f"SELECT 1 FROM {REAL_BADGE_TABLE} WHERE user_id=%(user_id)s AND badge_id=%(badge_key)s",
        {"user_id": user_id, "badge_key": badge_key},
    ).fetchone() is not None
    return {
        "would_call": f"INSERT OR IGNORE INTO {REAL_BADGE_TABLE}",
        "args_checked": {"user_id": user_id, "badge_key": badge_key},
        "already_owned": already_owned,
        "signature_ok": True,
    }


def verify_real_grant_targets_for_claims(app_module, conn, claims):
    """For every pending/granted claim's actual reward payload, run the
    appropriate dry-run wrapper(s) above and collect any errors (missing
    real target, incompatible signature, disallowed key). Never calls
    any real grant function -- only existence/signature checks and one
    read-only SELECT per badge. Returns a list of
    {"claim_id", "component", "error"} dicts (empty if everything
    checked out)."""
    errors = []
    for claim in claims:
        status = claim.get("status")
        if status in (lbr.CLAIM_STATUS_SKIPPED, lbr.CLAIM_STATUS_FAILED):
            continue
        claim_id = claim.get("claim_id", claim.get("id"))
        user_id = claim.get("user_id")

        if (status == lbr.CLAIM_STATUS_PENDING and claim.get("eligible")
                and (claim.get("granted_coins") or 0) > 0):
            try:
                real_coin_dry_run_wrapper(
                    app_module, user_id=user_id, amount=claim["granted_coins"],
                    reason="phase_3c_real_preview")
            except (ValueError, RuntimeError) as exc:
                errors.append({"claim_id": claim_id, "component": "coin", "error": str(exc)})

        try:
            items = lbr.extract_leaderboard_item_payload(claim)
        except ValueError as exc:
            errors.append({"claim_id": claim_id, "component": "item_payload", "error": str(exc)})
            items = {}
        for item_key, qty in items.items():
            try:
                real_item_dry_run_wrapper(app_module, user_id=user_id, item_key=item_key, quantity=qty)
            except (ValueError, RuntimeError) as exc:
                errors.append({"claim_id": claim_id, "component": "item", "error": str(exc)})

        try:
            badge_title = lbr.extract_leaderboard_badge_title_payload(claim)
        except ValueError as exc:
            errors.append({"claim_id": claim_id, "component": "badge_title_payload", "error": str(exc)})
            badge_title = {"badges": [], "titles": []}
        for badge_key in badge_title["badges"]:
            try:
                real_badge_dry_run_wrapper(app_module, conn, user_id=user_id, badge_key=badge_key)
            except (ValueError, RuntimeError) as exc:
                errors.append({"claim_id": claim_id, "component": "badge", "error": str(exc)})
        if badge_title["titles"]:
            errors.append({
                "claim_id": claim_id, "component": "title",
                "error": "title grants deferred in Phase 3B/3C -- no real target checked",
            })

    return errors
