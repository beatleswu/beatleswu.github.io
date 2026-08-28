"""C045 evidence-first starter assortment and price boundary.

This module is deliberately not a second functional Equipment authority.  The
caller supplies the existing server-owned ``EQUIPMENT_DEFS`` snapshot and this
module derives an audit projection from it.  It owns neither player state nor
HTTP behavior, does not import ``app.py``, and performs no database writes.

The current repository has no authoritative Coins price for functional
Equipment.  Consequently the executable offer factory is fail-closed: it
returns no offers until a future caller supplies an explicitly Owner-accepted
price and price-reference mapping.  A client/display price must never be used
as that mapping.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from shop_offer_identity_projection import ServerShopOfferFacts


C045_FUNCTIONAL_EQUIPMENT_IDS = (
    "wooden_sword",
    "iron_sword",
    "fox_fang",
    "dragon_claw",
    "celestial_blade",
    "cloth_robe",
    "leather_armor",
    "fox_pelt",
    "dragon_scale",
    "void_mantle",
    "lucky_stone",
    "xp_amulet",
    "fox_mask",
    "dragon_eye",
    "go_stone_black",
)
FUNCTIONAL_EQUIPMENT_ID_SET = frozenset(C045_FUNCTIONAL_EQUIPMENT_IDS)
FUNCTIONAL_SLOTS = frozenset({"weapon", "armor", "accessory"})

STARTER_SHOP_CANDIDATE_IDS = (
    "wooden_sword",
    "iron_sword",
    "cloth_robe",
    "leather_armor",
    "lucky_stone",
)
RECOMMENDED_STARTER_ASSORTMENT_IDS = (
    "wooden_sword",
    "cloth_robe",
    "lucky_stone",
)

HIGH_VALUE_DEFAULT_EXCLUDED_IDS = (
    "fox_fang",
    "fox_pelt",
    "fox_mask",
    "dragon_claw",
    "dragon_scale",
    "dragon_eye",
    "celestial_blade",
    "void_mantle",
)
LOCKED_DEFAULT_EXCLUDED_IDS = ("xp_amulet", "go_stone_black")

# This is a product decision boundary, not a price or a runtime feature flag.
PRICING_AUTHORITY_STATUS = "OWNER_DECISION_REQUIRED"
PRICING_AUTHORITY_READY = False
OFFERS_ACTIVATABLE = False


class StarterCatalogContractError(ValueError):
    """The supplied server Equipment snapshot cannot support this audit."""


@dataclass(frozen=True)
class EquipmentAcquisitionAudit:
    """A read-only C045 projection of one canonical Equipment definition."""

    item_id: str
    slot: str
    current_acquisition_sources: tuple[str, ...]
    monster_drop_sources: tuple[str, ...]
    rarity: str
    progression_role: str
    shop_overlap_risk: str
    recommended_shop_eligibility: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "slot": self.slot,
            "current_acquisition_sources": list(self.current_acquisition_sources),
            "monster_drop_sources": list(self.monster_drop_sources),
            "rarity": self.rarity,
            "progression_role": self.progression_role,
            "shop_overlap_risk": self.shop_overlap_risk,
            "recommended_shop_eligibility": self.recommended_shop_eligibility,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OwnerPricingDecision:
    """A non-canonical pricing decision row awaiting explicit acceptance."""

    item_id: str
    current_acquisition_role: str
    estimated_player_earning_context: str
    existing_comparable_price: str
    recommended_price_range: str | None
    recommended_default: int | None
    confidence: str
    evidence: str
    owner_decision_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "current_acquisition_role": self.current_acquisition_role,
            "estimated_player_earning_context": self.estimated_player_earning_context,
            "existing_comparable_price": self.existing_comparable_price,
            "recommended_price_range": self.recommended_price_range,
            "recommended_default": self.recommended_default,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "owner_decision_required": self.owner_decision_required,
        }


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StarterCatalogContractError(f"{field_name} must be non-empty text")
    return value.strip()


def _normalize_equipment_defs(
    equipment_defs: Iterable[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if equipment_defs is None:
        raise StarterCatalogContractError("server Equipment definitions are required")
    by_id: dict[str, Mapping[str, Any]] = {}
    for definition in equipment_defs:
        if not isinstance(definition, Mapping):
            raise StarterCatalogContractError("Equipment definitions must be mappings")
        item_id = _text(definition.get("id"), "equipment id")
        if item_id in by_id:
            raise StarterCatalogContractError(f"duplicate Equipment id: {item_id}")
        by_id[item_id] = definition
    if set(by_id) != FUNCTIONAL_EQUIPMENT_ID_SET:
        missing = sorted(FUNCTIONAL_EQUIPMENT_ID_SET.difference(by_id))
        unexpected = sorted(set(by_id).difference(FUNCTIONAL_EQUIPMENT_ID_SET))
        raise StarterCatalogContractError(
            f"canonical Equipment pool mismatch; missing={missing}, unexpected={unexpected}"
        )
    return by_id


def _recommendation(item_id: str) -> tuple[str, str]:
    if item_id in RECOMMENDED_STARTER_ASSORTMENT_IDS:
        return (
            "PROPOSED_STARTER_SHOP_CANDIDATE",
            "Common entry-tier item covers a starter slot, but still overlaps the Monster drop pool; Owner pricing and product acceptance are required.",
        )
    if item_id in STARTER_SHOP_CANDIDATE_IDS:
        return (
            "EVALUATE_ONLY_STARTER_CANDIDATE",
            "Common item is a plausible early alternative, but the three-item starter proposal already covers this slot and its Monster drop value must be protected.",
        )
    if item_id == "xp_amulet":
        return (
            "DEFAULT_DO_NOT_LIST_LOCKED_NEW_EQUIP",
            "New XP Amulet equip behavior is HOLD; do not create a Coin Shop sale path while that authority is disabled.",
        )
    if item_id == "go_stone_black":
        return (
            "DEFAULT_DO_NOT_LIST_INVENTORY_ONLY",
            "Go stone black is an inventory/trophy record and has no combat-equipment Shop authority.",
        )
    return (
        "DEFAULT_DO_NOT_LIST",
        "Higher-value regional or dragon-pool equipment should preserve Monster/Adventure progression identity rather than fill an empty Shop.",
    )


def build_equipment_acquisition_audit(
    equipment_defs: Iterable[Mapping[str, Any]],
) -> tuple[EquipmentAcquisitionAudit, ...]:
    """Derive the exact 15-item audit from the existing server definitions."""

    definitions = _normalize_equipment_defs(equipment_defs)
    rows: list[EquipmentAcquisitionAudit] = []
    for item_id in C045_FUNCTIONAL_EQUIPMENT_IDS:
        definition = definitions[item_id]
        slot = _text(definition.get("slot"), f"{item_id} slot").lower()
        if slot not in FUNCTIONAL_SLOTS:
            raise StarterCatalogContractError(
                f"{item_id} has unsupported functional slot: {slot}"
            )
        rarity = _text(definition.get("rarity"), f"{item_id} rarity").lower()
        raw_drop_sources = definition.get("drop_from") or ()
        if not isinstance(raw_drop_sources, (list, tuple)):
            raise StarterCatalogContractError(
                f"{item_id} drop_from must be a list or tuple"
            )
        drop_sources = tuple(_text(source, f"{item_id} drop source") for source in raw_drop_sources)
        current_sources = ("MONSTER_DROP", "ADMIN/LEGACY") if drop_sources else ("ADMIN/LEGACY",)
        recommendation, reason = _recommendation(item_id)
        progression_role = f"rarity={rarity}; no separate progression authority is defined"
        rows.append(
            EquipmentAcquisitionAudit(
                item_id=item_id,
                slot=slot,
                current_acquisition_sources=current_sources,
                monster_drop_sources=drop_sources,
                rarity=rarity,
                progression_role=progression_role,
                shop_overlap_risk=(
                    "MONSTER_DROP_OVERLAP" if drop_sources else "NO_CURRENT_PLAYER_DROP_SOURCE"
                ),
                recommended_shop_eligibility=recommendation,
                reason=reason,
            )
        )
    return tuple(rows)


def build_owner_pricing_decision_matrix(
    audit: Iterable[EquipmentAcquisitionAudit],
    *,
    comparable_shop_items: Mapping[str, Mapping[str, Any]],
    economy_context: Mapping[str, Any],
) -> tuple[OwnerPricingDecision, ...]:
    """Build a deliberately unresolved matrix when no equipment price exists.

    Existing Shop prices are recorded as comparables only.  They are not
    copied onto Equipment, because a consumable/utility price is not an
    authoritative Equipment price.
    """

    audit_rows = tuple(audit)
    if len(audit_rows) != len(C045_FUNCTIONAL_EQUIPMENT_IDS):
        raise StarterCatalogContractError("pricing matrix requires the complete 15-item audit")
    comparable_pairs: list[tuple[str, int]] = []
    for item_id, item in comparable_shop_items.items():
        if item_id in FUNCTIONAL_EQUIPMENT_ID_SET or not isinstance(item, Mapping):
            continue
        price = item.get("price")
        if isinstance(price, int) and not isinstance(price, bool) and price > 0:
            comparable_pairs.append((item_id, price))
    comparable_pairs.sort(key=lambda pair: (pair[1], pair[0]))
    if comparable_pairs:
        comparable_summary = (
            f"existing non-equipment Shop prices span {comparable_pairs[0][1]}"
            f"–{comparable_pairs[-1][1]} Coins ({len(comparable_pairs)} valid products);"
            " no equipment comparable"
        )
    else:
        comparable_summary = "no valid existing non-equipment Shop price comparable"

    required_context = (
        "daily earning rules: global cap={daily_cap}, Monster={monster_each} each "
        "with Monster cap={monster_cap}, daily quest={daily_quest_each} each, "
        "all-quests bonus={all_quests_bonus}, Adventure first-clear={first_clear}"
    ).format(
        daily_cap=economy_context.get("daily_cap", "UNKNOWN"),
        monster_each=economy_context.get("monster_each", "UNKNOWN"),
        monster_cap=economy_context.get("monster_cap", "UNKNOWN"),
        daily_quest_each=economy_context.get("daily_quest_each", "UNKNOWN"),
        all_quests_bonus=economy_context.get("all_quests_bonus", "UNKNOWN"),
        first_clear=economy_context.get("first_clear", "UNKNOWN"),
    )
    rows: list[OwnerPricingDecision] = []
    for row in audit_rows:
        rows.append(
            OwnerPricingDecision(
                item_id=row.item_id,
                current_acquisition_role=(
                    f"{row.rarity} {row.slot}; "
                    f"Monster sources={','.join(row.monster_drop_sources) or 'none'}; "
                    "admin/legacy grant exists"
                ),
                estimated_player_earning_context=required_context,
                existing_comparable_price=comparable_summary,
                recommended_price_range=None,
                recommended_default=None,
                confidence="LOW",
                evidence=(
                    "EQUIPMENT_DEFS has no price field and current Shop prices belong to "
                    "non-equipment products; numeric pricing would be an unsupported guess."
                ),
                owner_decision_required=True,
            )
        )
    return tuple(rows)


def build_authoritative_starter_offer_facts(
    equipment_defs: Iterable[Mapping[str, Any]],
    *,
    accepted_prices: Mapping[str, int] | None = None,
    price_references: Mapping[str, str] | None = None,
) -> tuple[ServerShopOfferFacts, ...]:
    """Create C025/C029 facts only from explicit Owner-accepted prices.

    With no accepted price authority (the current C045 state), this returns an
    empty tuple.  The future runtime must call this with source-owned mappings,
    never with request or frontend fields.  It deliberately does not enable a
    Shop gate and it never mutates ownership or Coins.
    """

    definitions = _normalize_equipment_defs(equipment_defs)
    if accepted_prices is None:
        return ()
    if not isinstance(accepted_prices, Mapping):
        raise StarterCatalogContractError("accepted_prices must be a mapping")
    unknown = set(accepted_prices).difference(RECOMMENDED_STARTER_ASSORTMENT_IDS)
    if unknown:
        raise StarterCatalogContractError(
            f"accepted Equipment prices contain non-starter ids: {sorted(unknown)}"
        )
    references = price_references or {}
    if not isinstance(references, Mapping):
        raise StarterCatalogContractError("price_references must be a mapping")

    facts: list[ServerShopOfferFacts] = []
    for item_id in RECOMMENDED_STARTER_ASSORTMENT_IDS:
        if item_id not in accepted_prices:
            continue
        price = accepted_prices[item_id]
        if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
            raise StarterCatalogContractError(
                f"accepted price for {item_id} must be a positive integer"
            )
        price_reference = references.get(item_id)
        if not isinstance(price_reference, str) or not price_reference.strip():
            raise StarterCatalogContractError(
                f"accepted price reference for {item_id} is required"
            )
        definition = definitions[item_id]
        slot = _text(definition.get("slot"), f"{item_id} slot").lower()
        facts.append(
            ServerShopOfferFacts(
                offer_family="STATIC_SHOP_ITEM",
                item_key=item_id,
                item_id=item_id,
                server_price=price,
                quantity=1,
                destination="player_inventory",
                acquisition_class=slot.upper(),
                duplicate_policy="REJECT_IF_OWNED",
                eligibility_reference="authenticated_shop_player",
                price_reference=price_reference.strip(),
                catalog_reference="equipment_shop_starter_catalog:owner_accepted",
                metadata={
                    "name": definition.get("name", item_id),
                    "description": definition.get("desc", ""),
                    "slot": slot,
                    "rarity": definition.get("rarity", ""),
                    "icon": definition.get("icon", ""),
                    "starter_assortment": True,
                },
            )
        )
    return tuple(facts)


__all__ = [
    "C045_FUNCTIONAL_EQUIPMENT_IDS",
    "EquipmentAcquisitionAudit",
    "FUNCTIONAL_EQUIPMENT_ID_SET",
    "HIGH_VALUE_DEFAULT_EXCLUDED_IDS",
    "LOCKED_DEFAULT_EXCLUDED_IDS",
    "OFFERS_ACTIVATABLE",
    "OwnerPricingDecision",
    "PRICING_AUTHORITY_READY",
    "PRICING_AUTHORITY_STATUS",
    "RECOMMENDED_STARTER_ASSORTMENT_IDS",
    "STARTER_SHOP_CANDIDATE_IDS",
    "StarterCatalogContractError",
    "build_authoritative_starter_offer_facts",
    "build_equipment_acquisition_audit",
    "build_owner_pricing_decision_matrix",
]
