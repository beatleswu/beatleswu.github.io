"""Static C044-C refresh/inventory consistency contract.

This is deliberately a source contract, not a browser or runtime test.  It
reads only ``shop.html`` and checks that the C044 player-UX candidate keeps
the existing C043 server-authoritative seams intact while adding refresh and
recovery wiring.  Proving that another path such as ``app.py`` is absent from
a Git diff is outside the scope of a test whose only source input is
``shop.html``; the explicit-path Git gate remains authoritative for that
boundary.
"""

from __future__ import annotations

import re
from pathlib import Path


SHOP_HTML = Path(__file__).resolve().parents[1] / "shop.html"
C044_PURE_START = "// C044-B-SHOP-PLAYER-UX-PURE-START"
C044_PURE_END = "// C044-B-SHOP-PLAYER-UX-PURE-END"


def _shop_source() -> str:
    assert SHOP_HTML.is_file(), f"C044 shop source is missing: {SHOP_HTML}"
    return SHOP_HTML.read_text(encoding="utf-8")


def _balanced_js_block(source: str, start: int, label: str) -> str:
    """Return one JavaScript brace-delimited block from ``start``.

    The small scanner ignores quoted strings and comments so template/UI
    text containing braces does not make the source assertions depend on
    whitespace or line layout.
    """

    opening = source.find("{", start)
    assert opening >= 0, f"{label} must have a JavaScript body"

    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if line_comment:
            if char in "\r\n":
                line_comment = False
        elif block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 1
        elif quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char == "/" and next_char == "/":
            line_comment = True
            index += 1
        elif char == "/" and next_char == "*":
            block_comment = True
            index += 1
        elif char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]

        index += 1

    raise AssertionError(f"{label} has an unterminated JavaScript body")


def _js_block(source: str, marker: str, label: str) -> str:
    start = source.find(marker)
    assert start >= 0, f"{label} is required; missing source marker {marker!r}"
    return _balanced_js_block(source, start, label)


def _js_block_matching(source: str, pattern: str, label: str) -> str:
    match = re.search(pattern, source)
    assert match, f"{label} is required; missing pattern {pattern!r}"
    return _balanced_js_block(source, match.start(), label)


def _require(pattern: str, source: str, message: str) -> re.Match[str]:
    match = re.search(pattern, source, re.DOTALL)
    assert match, message
    return match


def _assert_order(source: str, *fragments: str, message: str) -> None:
    positions = [source.find(fragment) for fragment in fragments]
    assert all(position >= 0 for position in positions), message
    assert positions == sorted(positions) and len(set(positions)) == len(positions), message


def _equipment_source(source: str, *, require_c044: bool = False) -> str:
    c043_start = source.find("// C043-E-EQUIPMENT-COMMERCE-FEEDBACK-START")
    c043_end = source.find("// C043-E-EQUIPMENT-COMMERCE-FEEDBACK-END")
    assert c043_start >= 0 and c043_end > c043_start, (
        "C043's bounded equipment adapter must remain present so C044 cannot "
        "replace the canonical result/ownership validator"
    )
    c044_start = source.find(C044_PURE_START)
    c044_end = source.find(C044_PURE_END)
    blocks = [
        source[c043_start : c043_end + len("// C043-E-EQUIPMENT-COMMERCE-FEEDBACK-END")],
        _js_block(source, "function renderEquipmentOffers(", "renderEquipmentOffers"),
        _js_block(source, "function c043EquipmentOfferCardHTML(", "equipment offer card"),
        _js_block(source, "async function purchaseEquipment(", "purchaseEquipment"),
    ]
    if require_c044:
        assert c044_start >= 0 and c044_end > c044_start, (
            "C044-B's bounded pure-helper marker is required; the refresh contract "
            "must not silently pass against the C043-only source"
        )
    if c044_start >= 0 and c044_end > c044_start:
        blocks.insert(1, source[c044_start : c044_end + len(C044_PURE_END)])
    return "\n".join(blocks)


def test_catalog_response_owns_coin_balance_and_equipment_offers() -> None:
    """The one server catalog response must drive both Shop projections."""

    source = _shop_source()
    load_catalog = _js_block(source, "async function loadCatalog(", "loadCatalog")

    fetch = _require(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+api\(\s*['\"]\/api\/shop\/catalog['\"]",
        load_catalog,
        "loadCatalog must fetch the authoritative /api/shop/catalog endpoint",
    )
    response_name = re.escape(fetch.group(1))
    _require(
        rf"\bcatalog\s*=\s*{response_name}\b",
        load_catalog,
        "the catalog state must be assigned from the fetched server response",
    )
    inline_balance = re.search(
        rf"getElementById\(\s*['\"]coin-bal['\"]\s*\)\s*\.textContent\s*=\s*"
        rf"money\(\s*{response_name}\.coins\s*\)",
        load_catalog,
    )
    if not inline_balance:
        balance_call = _require(
            rf"\b([A-Za-z_$][\w$]*(?:balance|coins)[A-Za-z_$\d]*)\s*\(\s*"
            rf"{response_name}\s*\)",
            load_catalog,
            "loadCatalog must pass its server response to the authoritative balance projector",
        )
        balance_projector = _js_block_matching(
            source,
            rf"(?:async\s+)?function\s+{re.escape(balance_call.group(1))}\s*"
            rf"\([^)]*\)\s*|(?:const|let|var)\s+"
            rf"{re.escape(balance_call.group(1))}\s*=\s*(?:async\s*)?"
            rf"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*",
            "authoritative catalog balance projector",
        )
        _require(
            r"Number\.isInteger\(\s*[A-Za-z_$][\w$]*\??\.coins\s*\)",
            balance_projector,
            "the catalog balance projector must validate the server coins fact",
        )
        _require(
            r"\b[A-Za-z_$][\w$]*\.textContent\s*=\s*money\(\s*"
            r"[A-Za-z_$][\w$]*\.coins\s*\)",
            balance_projector,
            "coin-bal must be rendered from the projector's catalog coins fact",
        )
    _require(
        rf"renderEquipmentOffers\(\s*{response_name}\s*\)",
        load_catalog,
        "equipment offers must be rendered from that same catalog response",
    )

    render_equipment = _js_block(
        source, "function renderEquipmentOffers(", "renderEquipmentOffers"
    )
    _require(
        r"equipmentOffers\s*=\s*c043EquipmentOffers\(\s*data\s*\)",
        render_equipment,
        "equipment rendering must consume the server equipment_offers projection",
    )
    _require(
        r"Array\.isArray\(\s*data\?\.equipment_offers\s*\)",
        source,
        "the equipment offer adapter must reject a missing/non-array server field",
    )


def test_success_uses_authoritative_coins_after_then_reloads_catalog() -> None:
    """A validated purchase may display response coins_after, then refresh."""

    source = _shop_source()
    purchase = _js_block(source, "async function purchaseEquipment(", "purchaseEquipment")

    _require(
        r"requestShopPurchase\(\s*['\"]\/api\/shop\/buy['\"]",
        purchase,
        "equipment purchase must use the existing authoritative Shop purchase route",
    )
    _require(
        r"c043EquipmentPurchaseResult\(\s*response\s*,\s*offer\s*\)",
        purchase,
        "success must be gated by the C043 canonical acquisition-result validator",
    )
    _require(
        r"Number\.isInteger\(\s*response\.coins_after\s*\)[\s\S]*?"
        r"getElementById\(\s*['\"]coin-bal['\"]\s*\)\s*\.textContent\s*=\s*"
        r"money\(\s*response\.coins_after\s*\)",
        purchase,
        "successful equipment feedback must use server-supplied response.coins_after",
    )
    assert not re.search(
        r"(?:coin-bal|coinBalance|balance|coins?)\s*[-+]=|"
        r"(?:offer\.price|response\.coins_after)\s*[-+*/]|"
        r"[-+*/]\s*(?:offer\.price|response\.coins_after)",
        purchase,
        re.IGNORECASE,
    ), "purchase success/failure paths must not fake-decrement or derive a local coin balance"

    _assert_order(
        purchase,
        "const result = c043EquipmentPurchaseResult(response, offer);",
        "if (!result)",
        "Number.isInteger(response.coins_after)",
        "await loadCatalog();",
        message=(
            "the purchase must validate the authoritative result, apply response.coins_after "
            "as a response fact, and only then reload the server catalog/ownership projection"
        ),
    )
    _require(
        r"c043EquipmentOwnershipFocus\(\s*result\.ownership_reference\s*\)",
        purchase,
        "success Backpack navigation must consume the validated canonical ownership reference",
    )


def test_c044_ownership_projection_is_server_supplied_and_not_a_second_store() -> None:
    """C044 may project catalog ownership facts but cannot own them locally."""

    source = _shop_source()
    pure_helpers = (
        _equipment_source(source, require_c044=True)
        .split(C044_PURE_START, 1)[1]
        .split(C044_PURE_END, 1)[0]
    )
    card = _js_block(
        source, "function c043EquipmentOfferCardHTML(", "equipment offer card"
    )

    _require(
        r"function c044EquipmentOwnership\(\s*data\s*,\s*offer\s*\)",
        pure_helpers,
        "C044 ownership presentation must be a pure projection of catalog/offer input",
    )
    assert "data?.equipment_ownership" in pure_helpers or "data?.equipment_inventory" in pure_helpers, (
        "C044 ownership badges must consume an authoritative catalog ownership projection"
    )
    assert "return { supplied: false, owned: false, quantity: null, state: '' }" in pure_helpers, (
        "missing ownership must remain unreported instead of being invented by the frontend"
    )
    assert "const ownership = c044EquipmentOwnership(catalog, offer);" in card, (
        "equipment cards must derive ownership from the current server catalog and offer"
    )
    assert "c044EquipmentOwnershipBadgeHTML(ownership)" in card, (
        "equipment ownership presentation must use the server-derived projection"
    )
    assert "catalog?.inventory" not in card, (
        "equipment cards must not reuse the legacy stackable-item inventory as ownership"
    )
    for forbidden, message in [
        (r"\b(?:fetch|XMLHttpRequest)\s*\(", "a second ownership request inside the pure helper"),
        (r"\b(?:localStorage|sessionStorage)\b", "browser storage as an ownership store"),
        (r"\b(?:catalog|equipmentOffers|c044EquipmentPurchaseInFlight)\s*=", "a frontend ownership/state store"),
        (r"\b(?:MAX|ORDER\s+BY|latest|newest|mostRecent|inferred)\b", "inferred/latest ownership selection"),
    ]:
        assert not re.search(forbidden, pure_helpers, re.IGNORECASE), (
            f"C044 pure ownership projection must not use {message}"
        )


def test_failed_purchase_paths_refresh_without_writing_a_fake_balance() -> None:
    """Stale, network, server, and unverified-result failures recover safely."""

    source = _shop_source()
    purchase = _js_block(source, "async function purchaseEquipment(", "purchaseEquipment")
    branches = {
        "stale or unknown offer": _js_block(
            purchase, "if (!offer)", "unknown equipment-offer recovery branch"
        ),
        "network/timeout failure": _js_block_matching(
            purchase,
            r"catch\s*\([^)]*\)\s*",
            "equipment purchase network/timeout recovery branch",
        ),
        "server-reported failure": _js_block_matching(
            purchase,
            r"if\s*\([^)]*response[^)]*error[^)]*\)\s*",
            "equipment purchase server-error recovery branch",
        ),
        "unverified authoritative result": _js_block(
            purchase, "if (!result)", "unverified purchase-result recovery branch"
        ),
    }

    for label, branch in branches.items():
        assert not re.search(
            r"coin-bal|coinBalance|coins_after|offer\.price",
            branch,
            re.IGNORECASE,
        ), f"{label} must not write or fake-adjust the displayed coin balance"
        error_state_source = branch
        refresh = re.search(
            r"\b(loadCatalog|[A-Za-z_$][\w$]*(?:refresh|recover|reload)[A-Za-z_$\d]*)\s*\([^)]*\)",
            branch,
            re.IGNORECASE,
        )
        assert refresh, (
            f"{label} must attempt a safe authoritative catalog/ownership refresh "
            "before returning to the caller"
        )
        if refresh.group(1).lower() != "loadcatalog":
            helper_name = re.escape(refresh.group(1))
            helper_definition = _js_block_matching(
                source,
                rf"(?:async\s+)?function\s+{helper_name}\s*\([^)]*\)\s*|"
                rf"(?:const|let|var)\s+{helper_name}\s*=\s*"
                rf"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*",
                f"{label} refresh/recovery helper",
            )
            assert re.search(r"\bloadCatalog\s*\([^)]*\)", helper_definition), (
                f"{label} refresh/recovery helper must reload /api/shop/catalog"
            )
            error_state_source = f"{branch}\n{helper_definition}"
        assert re.search(
            r"setEquipmentPurchaseFeedback\(\s*['\"]error['\"]",
            error_state_source,
            re.DOTALL,
        ), f"{label} must resolve to an explicit error state"
        last_return = branch.rfind("return")
        assert refresh.start() < last_return, (
            f"{label} must refresh before returning so stale Shop state can recover"
        )


def test_ownership_and_backpack_use_exact_canonical_player_inventory_reference() -> None:
    """No client-side row reconstruction may replace C043's exact reference."""

    source = _shop_source()
    ownership = _js_block(
        source, "function c043EquipmentOwnershipFocus(", "canonical ownership focus helper"
    )
    result_validator = _js_block(
        source,
        "function c043EquipmentPurchaseResult(",
        "canonical equipment purchase-result validator",
    )
    purchase = _js_block(source, "async function purchaseEquipment(", "purchaseEquipment")

    assert "/^player_inventory:([1-9]\\d*)$/.exec(reference)" in ownership, (
        "Backpack focus must accept only an exact positive player_inventory row reference"
    )
    assert "`/inventory?equipment=${encodeURIComponent(match[1])}`" in ownership, (
        "Backpack focus must derive its link from the exact validated reference, not a guessed row"
    )
    for fragment, message in [
        ("response.canonical_acquisition_result", "purchase result must come from canonical server evidence"),
        ("result.destination !== 'PLAYER_INVENTORY'", "purchase result must target PLAYER_INVENTORY"),
        ("result.ownership_authority !== 'player_inventory'", "player_inventory must remain the ownership authority"),
        ("result.source_reference !== offer.offer_id", "ownership result must remain bound to the server offer"),
        ("!c043EquipmentOwnershipFocus(result.ownership_reference)", "invalid ownership references must fail closed"),
    ]:
        assert fragment in result_validator, message

    _require(
        r"c043EquipmentOwnershipFocus\(\s*result\.ownership_reference\s*\)",
        purchase,
        "the success presentation must pass the canonical result reference to Backpack navigation",
    )

    equipment_scope = _equipment_source(source)
    for forbidden, message in [
        (r"\bMAX\s*\(", "MAX/latest-row ownership lookup"),
        (r"\bORDER\s+BY\b", "database ordering used to guess ownership"),
        (r"\b(?:latest|newest|mostRecent|inferred)\b", "latest/inferred frontend ownership state"),
        (r"\b(?:localStorage|sessionStorage)\b", "browser storage as a second ownership store"),
    ]:
        assert not re.search(forbidden, equipment_scope, re.IGNORECASE), (
            f"equipment presentation must not use {message}"
        )


def test_shop_backpack_convergence_and_equip_boundaries_remain_explicit() -> None:
    """Shop refresh and Backpack navigation stay additive and non-equip."""

    source = _shop_source()
    purchase = _js_block(source, "async function purchaseEquipment(", "purchaseEquipment")
    render_equipment = _js_block(
        source, "function renderEquipmentOffers(", "renderEquipmentOffers"
    )
    load_catalog = _js_block(source, "async function loadCatalog(", "loadCatalog")

    assert re.search(
        r"<a\b[^>]*href=['\"]\/inventory['\"]",
        source,
        re.IGNORECASE,
    ), "Shop must retain a direct /inventory Backpack convergence link"
    assert "await loadCatalog();" in purchase, (
        "successful equipment purchases must refresh the server catalog used by Shop and Backpack links"
    )
    assert "renderEquipmentOffers(res)" in load_catalog or re.search(
        r"renderEquipmentOffers\(\s*[A-Za-z_$][\w$]*\s*\)", load_catalog
    ), "catalog refresh must re-render equipment offers from the refreshed response"
    _require(
        r"equipmentOffers\.map\(\s*c043EquipmentOfferCardHTML\s*\)",
        render_equipment,
        "equipment offer presentation must converge on the refreshed server-derived offer list"
    )

    assert not re.search(
        r"/api/(?:player/)?inventory/equip",
        source,
        re.IGNORECASE,
    ), "Shop must not call an equipment equip endpoint"
    assert not re.search(
        r"\b(?:autoEquip|auto_equip|equipEquipment|equip_owned_item)\b|"
        r"data-equipment-(?:equip|auto-equip)",
        _equipment_source(source),
        re.IGNORECASE,
    ), "Shop must not add an auto-equip action or a second equipment equip path"
    assert not re.search(
        r"\bLOADOUT_(?:ENABLE|ENABLED)\b",
        source,
        re.IGNORECASE,
    ), "the C044 source candidate must not enable LOADOUT"
