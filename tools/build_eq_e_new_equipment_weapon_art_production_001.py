"""Build the EQ-E new Equipment art package from generated source art.

This tool is intentionally presentation-only. It does not modify the Equipment
registry, renderer, Shop, authority code, app.py, or index.html. It normalizes
generated source art into the existing PLAYER_FRAME_A_STANDARD_CHIBI canvas,
emits same-ID functional SVG icons, and writes a machine-readable QA report.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs" / "planning" / "eq_e_new_equipment_weapon_art_production_001"
SOURCE_ROOT = PACKAGE / "sources" / "generated_raw"
OVERLAY_ROOT = ROOT / "assets" / "hero" / "equipment" / "wearables" / "overlays"
ICON_ROOT = ROOT / "assets" / "hero" / "equipment" / "functional"
REPORT_PATH = PACKAGE / "eq_e_asset_qa_report.json"
REVIEW_MATRIX_PATH = PACKAGE / "EQ_E_asset_review_matrix.png"
CANVAS = (1056, 1408)


PRODUCTS: dict[str, dict[str, Any]] = {
    "bamboo_shadow_blade": {
        "type": "weapon",
        "rarity": "common",
        "slot": "MAIN_HAND",
        "layer": "MAIN_HAND_WEAPON",
        "renderer_family": "functional_handheld_one_hand_weapon",
        "handheld_required": True,
        "handheld_grip_anchor": [0.80, 0.88],
        "mirror_for_handheld": True,
        "zone": 1,
        "zone_key": "k26_30",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#2f7567", "#d8a35d", "#e9c47a"],
        "prompt": "New isolated bamboo-green lacquered one-hand blade intended for a real right-hand answer-screen grip, with warm wood grip and teal river cord; no character, no hand, no background, no text.",
    },
    "riverstone_sabre": {
        "type": "weapon",
        "rarity": "rare",
        "slot": "MAIN_HAND",
        "layer": "MAIN_HAND_WEAPON",
        "renderer_family": "functional_handheld_one_hand_weapon",
        "handheld_required": True,
        "handheld_grip_anchor": [0.18, 0.89],
        "mirror_for_handheld": False,
        "zone": 6,
        "zone_key": "k1_5",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#416b91", "#8da5b3", "#d3b16c"],
        "prompt": "New isolated river-polished slate sabre intended for a real right-hand answer-screen grip, with teal cord and stone pommel; no character, no hand, no background, no text.",
    },
    "moonstar_rapier": {
        "type": "weapon",
        "rarity": "epic",
        "slot": "MAIN_HAND",
        "layer": "MAIN_HAND_WEAPON",
        "renderer_family": "functional_handheld_one_hand_weapon",
        "handheld_required": True,
        "handheld_grip_anchor": [0.95, 0.91],
        "mirror_for_handheld": True,
        "zone": 9,
        "zone_key": "d5_6",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#314c98", "#dce8ff", "#f0c86e"],
        "prompt": "New isolated moon-silver one-hand rapier intended for a real right-hand answer-screen grip, with midnight-blue guard and tiny gold star inlay; no character, no hand, no background, no text.",
    },
    "emberline_cutlass": {
        "type": "weapon",
        "rarity": "rare",
        "slot": "MAIN_HAND",
        "layer": "MAIN_HAND_WEAPON",
        "renderer_family": "functional_handheld_one_hand_weapon",
        "handheld_required": True,
        "handheld_grip_anchor": [0.20, 0.84],
        "mirror_for_handheld": False,
        "zone": None,
        "zone_key": None,
        "source_classification": "SHOP_EXCLUSIVE",
        "palette": ["#183847", "#da6336", "#d7a14d"],
        "prompt": "New isolated emberline one-hand cutlass intended for a real right-hand answer-screen grip, with dark teal-black blade, ember-orange guard and copper flame accents; no character, no hand, no background, no text.",
    },
    "starglass_needle": {
        "type": "weapon",
        "rarity": "epic",
        "slot": "MAIN_HAND",
        "layer": "MAIN_HAND_WEAPON",
        "renderer_family": "functional_handheld_one_hand_weapon",
        "handheld_required": True,
        "handheld_grip_anchor": [0.20, 0.91],
        "mirror_for_handheld": False,
        "zone": None,
        "zone_key": None,
        "source_classification": "SHOP_EXCLUSIVE",
        "palette": ["#405ad1", "#87d7ff", "#e9efff"],
        "prompt": "New isolated slim starglass one-hand needle sword intended for a real right-hand answer-screen grip, with blue crystal blade, violet guard and silver star details; no character, no hand, no background, no text.",
    },
    "bamboo_scale_vest": {
        "type": "armor",
        "rarity": "common",
        "slot": "TORSO_ARMOR",
        "layer": "TORSO_ARMOR",
        "renderer_family": "functional_torso_armor",
        "handheld_required": False,
        "template_box": [0.28, 0.25, 0.72, 0.60],
        "zone": 3,
        "zone_key": "k16_20",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#628d5a", "#d7c28d", "#3e827c"],
        "prompt": "New isolated layered bamboo-slat torso vest over cream travel cloth with teal stitching; open neck, no character, no background, no text.",
    },
    "riverguard_coat": {
        "type": "armor",
        "rarity": "rare",
        "slot": "TORSO_ARMOR",
        "layer": "TORSO_ARMOR",
        "renderer_family": "functional_torso_armor",
        "handheld_required": False,
        "template_box": [0.28, 0.25, 0.72, 0.60],
        "zone": 5,
        "zone_key": "k6_10",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#385c78", "#b3c3c5", "#c8924b"],
        "prompt": "New isolated slate-blue quilted river travel coat with waterline hem, cream trim and brass clasp; open face and neck, no character, no background, no text.",
    },
    "foxtail_traveler_mantle": {
        "type": "armor",
        "rarity": "rare",
        "slot": "SHOULDER_MANTLE",
        "layer": "BACK_BODY",
        "renderer_family": "functional_torso_armor",
        "handheld_required": False,
        "template_box": [0.16, 0.22, 0.84, 0.52],
        "zone": 4,
        "zone_key": "k11_15",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#b96538", "#e0c291", "#6b7c5d"],
        "prompt": "New isolated rust-orange fox-tail shoulder mantle over a muted travel tunic with stitched map motifs; open head and hands, no character, no background, no text.",
    },
    "cloudstep_star_lamellar": {
        "type": "armor",
        "rarity": "epic",
        "slot": "TORSO_ARMOR",
        "layer": "TORSO_ARMOR",
        "renderer_family": "functional_torso_armor",
        "handheld_required": False,
        "template_box": [0.28, 0.25, 0.72, 0.60],
        "zone": 7,
        "zone_key": "d1_2",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#b9c8d0", "#334a89", "#d6b15e"],
        "prompt": "New isolated pale cloud-gray torso lamellar armor with deep-blue star plates and restrained gold edging; open collar, no character, no head, no hands, no background, no text.",
    },
    "weaveguard_vest": {
        "type": "armor",
        "rarity": "rare",
        "slot": "TORSO_ARMOR",
        "layer": "TORSO_ARMOR",
        "renderer_family": "functional_torso_armor",
        "handheld_required": False,
        "template_box": [0.28, 0.25, 0.72, 0.60],
        "zone": None,
        "zone_key": None,
        "source_classification": "SHOP_EXCLUSIVE",
        "palette": ["#40556a", "#d7c4a0", "#a37a4e"],
        "prompt": "New isolated woven defensive travel vest with cream and muted indigo textile panels and brass fasteners; open collar, no character, no head, no hands, no background, no text.",
    },
    "mirrorfall_mantle": {
        "type": "armor",
        "rarity": "epic",
        "slot": "TORSO_ARMOR",
        "layer": "TORSO_ARMOR",
        "renderer_family": "functional_torso_armor",
        "handheld_required": False,
        "template_box": [0.24, 0.22, 0.76, 0.52],
        "zone": None,
        "zone_key": None,
        "source_classification": "SHOP_EXCLUSIVE",
        "palette": ["#6687ad", "#d7e2ea", "#6653a9"],
        "prompt": "New isolated mirrorfall shoulder mantle with silver-blue layered cloth, reflective trim and deep-violet crystal clasp; open face and neck, no character, no head, no hands, no background, no text.",
    },
    "jade_river_bead": {
        "type": "accessory",
        "rarity": "common",
        "slot": "NECK_CHEST_ACCESSORY",
        "layer": "FRONT_ACCESSORY",
        "renderer_family": "functional_front_accessory",
        "handheld_required": False,
        "template_box": [0.37, 0.22, 0.63, 0.40],
        "zone": 2,
        "zone_key": "k21_25",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#1c6e67", "#72c3a3", "#d5ba72"],
        "prompt": "New isolated small faceted jade river bead on a dark teal cord, readable at mobile scale; no character, no background, no text.",
    },
    "constellation_focus_lens": {
        "type": "accessory",
        "rarity": "epic",
        "slot": "NECK_CHEST_ACCESSORY",
        "layer": "FRONT_ACCESSORY",
        "renderer_family": "functional_front_accessory",
        "handheld_required": False,
        "template_box": [0.37, 0.22, 0.63, 0.40],
        "zone": 8,
        "zone_key": "d3_4",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#1f2d58", "#d49a48", "#e1b35c"],
        "prompt": "New isolated amber focus lens in a navy star-map bezel with restrained gold points, worn at the chest; no character, no background, no text.",
    },
    "odyssey_star_compass": {
        "type": "accessory",
        "rarity": "legendary",
        "slot": "FRONT_ACCESSORY",
        "layer": "FRONT_ACCESSORY",
        "renderer_family": "functional_front_accessory",
        "handheld_required": False,
        "template_box": [0.37, 0.22, 0.63, 0.40],
        "zone": 10,
        "zone_key": "d7_plus",
        "source_classification": "ZONE_EXCLUSIVE",
        "palette": ["#b78338", "#4e8f82", "#315386"],
        "prompt": "New isolated compact brass star compass with jade center, blue enamel ring and engraved star points, designed as a small chest accessory; no character, no hand, no background, no text.",
    },
    "copper_jade_talisman": {
        "type": "accessory",
        "rarity": "rare",
        "slot": "FRONT_ACCESSORY",
        "layer": "FRONT_ACCESSORY",
        "renderer_family": "functional_front_accessory",
        "handheld_required": False,
        "template_box": [0.37, 0.22, 0.63, 0.40],
        "zone": None,
        "zone_key": None,
        "source_classification": "SHOP_EXCLUSIVE",
        "palette": ["#b66b43", "#4aa681", "#e0b75c"],
        "prompt": "New isolated compact copper-and-jade chest talisman on a short teal cord, with faceted green jade center; no character, no hand, no background, no text.",
    },
    "prism_focus_charm": {
        "type": "accessory",
        "rarity": "epic",
        "slot": "FRONT_ACCESSORY",
        "layer": "FRONT_ACCESSORY",
        "renderer_family": "functional_front_accessory",
        "handheld_required": False,
        "template_box": [0.37, 0.22, 0.63, 0.40],
        "zone": None,
        "zone_key": None,
        "source_classification": "SHOP_EXCLUSIVE",
        "palette": ["#573c9f", "#8a74e4", "#e2bd68"],
        "prompt": "New isolated prism focus chest charm with violet-blue faceted crystal, silver bezel and tiny gold star accent; distinct from a circular lens, no character, no hand, no background, no text.",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_icon(item_id: str, item: dict[str, Any]) -> str:
    """Return a transparent, text-free 256px icon with item-specific geometry."""
    a, b, c = item["palette"]
    if item["type"] == "weapon":
        if item_id == "bamboo_shadow_blade":
            shape = f'<path d="M28 177 L167 38 Q178 29 190 40 L199 49 L71 201 Q59 214 44 202 Z" fill="{a}" stroke="#17252b" stroke-width="8"/><path d="M164 47 L202 76 L184 98 L146 69 Z" fill="{b}" stroke="#17252b" stroke-width="8"/><path d="M34 180 L14 220 Q11 232 24 235 L62 214 Z" fill="{b}" stroke="#17252b" stroke-width="8"/><path d="M29 199 L57 218 M21 213 L45 230" stroke="{c}" stroke-width="8" stroke-linecap="round"/>'
        elif item_id == "riverstone_sabre":
            shape = f'<path d="M37 182 Q31 173 42 162 L169 37 Q181 27 191 39 L201 52 L74 203 Q63 214 51 204 Z" fill="{a}" stroke="#15242f" stroke-width="8"/><path d="M153 49 L197 72 L181 101 L138 76 Z" fill="{b}" stroke="#15242f" stroke-width="8"/><path d="M36 183 L14 222 Q10 236 26 237 L69 211 Z" fill="{c}" stroke="#15242f" stroke-width="8"/><circle cx="23" cy="226" r="12" fill="{b}" stroke="#15242f" stroke-width="6"/>'
        elif item_id == "moonstar_rapier":
            shape = f'<path d="M29 194 L178 34 Q187 25 196 35 L203 44 L63 211 Q50 223 37 210 Z" fill="{b}" stroke="#1b2854" stroke-width="7"/><path d="M161 47 L198 64 L185 86 L148 68 Z" fill="{a}" stroke="#1b2854" stroke-width="7"/><path d="M37 195 L14 224 Q10 236 24 236 L66 213 Z" fill="{a}" stroke="#1b2854" stroke-width="7"/><path d="M109 111 L137 83 M116 126 L145 96" stroke="{c}" stroke-width="5"/><path d="M28 214 L46 232" stroke="{c}" stroke-width="7"/>'
        elif item_id == "emberline_cutlass":
            shape = f'<path d="M48 188 Q42 179 52 169 L170 43 Q181 31 193 42 L202 54 L82 203 Q69 216 56 205 Z" fill="{a}" stroke="#25232c" stroke-width="8"/><path d="M153 49 L204 67 L190 101 L140 80 Z" fill="{b}" stroke="#25232c" stroke-width="8"/><path d="M41 190 L14 225 Q10 237 25 235 L80 207 Z" fill="{a}" stroke="#25232c" stroke-width="8"/><path d="M27 211 Q44 202 56 220" fill="none" stroke="{c}" stroke-width="7"/><path d="M178 58 L185 80 L201 89" fill="none" stroke="{b}" stroke-width="5"/>'
        elif item_id == "starglass_needle":
            shape = f'<path d="M41 204 L187 27 L198 34 L68 214 Q54 228 41 217 Z" fill="{b}" stroke="#28326e" stroke-width="7"/><path d="M161 57 L198 70 L186 94 L149 78 Z" fill="{a}" stroke="#28326e" stroke-width="7"/><path d="M42 204 L14 231 Q9 241 23 239 L70 218 Z" fill="{a}" stroke="#28326e" stroke-width="7"/><path d="M83 150 L118 107 M101 158 L136 115" stroke="{c}" stroke-width="5"/><circle cx="24" cy="234" r="7" fill="{c}"/>'
        else:
            shape = f'<path d="M31 179 L163 42 Q176 28 188 42 L198 54 L72 201 Q58 217 44 204 Z" fill="{a}" stroke="#241b1d" stroke-width="8"/><path d="M155 47 L205 70 L187 103 L137 78 Z" fill="{b}" stroke="#241b1d" stroke-width="8"/><path d="M37 184 L15 224 Q12 236 26 235 L71 210 Z" fill="{b}" stroke="#241b1d" stroke-width="8"/><path d="M28 207 L52 225" stroke="{c}" stroke-width="9" stroke-linecap="round"/>'
    elif item["type"] == "armor":
        if item_id == "bamboo_scale_vest":
            shape = f'<path d="M71 50 Q128 28 185 50 L208 92 L190 216 Q128 238 66 216 L48 92 Z" fill="{b}" stroke="#263b39" stroke-width="8"/><path d="M77 63 L179 63 L188 97 L68 97 Z" fill="{a}" stroke="#263b39" stroke-width="7"/><path d="M66 105 L190 105 M65 137 L191 137 M68 169 L188 169" stroke="{a}" stroke-width="15"/><path d="M87 62 L87 196 M128 62 L128 213 M169 62 L169 196" stroke="{c}" stroke-width="5"/>'
        elif item_id == "riverguard_coat":
            shape = f'<path d="M62 47 Q128 27 194 47 L214 89 L193 219 Q128 239 63 219 L42 89 Z" fill="{a}" stroke="#203343" stroke-width="8"/><path d="M67 53 Q128 83 189 53 L174 91 L128 105 L82 91 Z" fill="{b}" stroke="#203343" stroke-width="7"/><path d="M52 94 Q128 115 204 94 M49 167 Q128 187 205 167" stroke="{b}" stroke-width="9"/><path d="M128 104 L128 218" stroke="{c}" stroke-width="7"/><circle cx="128" cy="110" r="9" fill="{c}" stroke="#203343" stroke-width="5"/>'
        elif item_id == "cloudstep_star_lamellar":
            shape = f'<path d="M65 48 Q128 28 191 48 L211 88 L195 217 Q128 239 61 217 L45 88 Z" fill="{a}" stroke="#33405c" stroke-width="8"/><path d="M74 55 L182 55 L174 91 L128 104 L82 91 Z" fill="{b}" stroke="#33405c" stroke-width="7"/><path d="M62 103 L194 103 M62 138 L194 138 M66 173 L190 173" stroke="{b}" stroke-width="12"/><path d="M82 96 L82 199 M128 105 L128 221 M174 96 L174 199" stroke="{c}" stroke-width="6"/><path d="M110 72 L128 58 L146 72 L128 86 Z" fill="{c}" stroke="#33405c" stroke-width="4"/>'
        elif item_id == "weaveguard_vest":
            shape = f'<path d="M62 48 Q128 29 194 48 L210 88 L193 218 Q128 238 63 218 L46 88 Z" fill="{b}" stroke="#2e3d4e" stroke-width="8"/><path d="M66 55 L190 55 L175 93 L128 106 L81 93 Z" fill="{a}" stroke="#2e3d4e" stroke-width="7"/><path d="M65 110 L191 110 M62 151 L194 151 M67 191 L189 191" stroke="{a}" stroke-width="10"/><path d="M86 103 L86 203 M128 106 L128 222 M170 103 L170 203" stroke="{c}" stroke-width="6"/><circle cx="128" cy="112" r="8" fill="{c}" stroke="#2e3d4e" stroke-width="4"/>'
        elif item_id == "mirrorfall_mantle":
            shape = f'<path d="M43 76 Q75 40 107 57 Q128 70 149 57 Q181 40 213 76 L198 158 Q178 193 158 213 Q128 228 98 213 Q78 193 58 158 Z" fill="{a}" stroke="#3c4268" stroke-width="8"/><path d="M43 78 Q75 49 102 68 Q128 88 154 68 Q181 49 213 78" fill="none" stroke="{b}" stroke-width="17"/><path d="M61 123 Q128 143 195 123 M72 160 Q128 178 184 160" stroke="{b}" stroke-width="7"/><path d="M128 72 L139 88 L157 91 L143 103 L146 121 L128 112 L110 121 L113 103 L99 91 L117 88 Z" fill="{c}" stroke="#3c4268" stroke-width="5"/>'
        else:
            shape = f'<path d="M42 72 Q75 38 107 55 Q128 68 149 55 Q181 38 214 72 L200 150 Q179 184 158 208 Q128 225 98 208 Q77 184 56 150 Z" fill="{a}" stroke="#4c3029" stroke-width="8"/><path d="M42 76 Q75 47 102 65 Q128 86 154 65 Q181 47 214 76" fill="none" stroke="{b}" stroke-width="18"/><path d="M61 118 Q128 137 195 118 M72 153 Q128 169 184 153" stroke="{c}" stroke-width="7"/>'
    else:
        if item_id == "jade_river_bead":
            shape = f'<path d="M128 28 C87 57 70 89 128 125 C186 89 169 57 128 28 Z" fill="{b}" stroke="#17353b" stroke-width="8"/><path d="M80 57 Q128 92 176 57" fill="none" stroke="{a}" stroke-width="8"/><path d="M87 49 Q128 7 169 49" fill="none" stroke="{a}" stroke-width="7"/><path d="M128 125 L128 179" stroke="{a}" stroke-width="9"/><circle cx="128" cy="201" r="28" fill="{b}" stroke="#17353b" stroke-width="8"/><path d="M109 187 L147 215 M147 187 L109 215" stroke="{c}" stroke-width="5"/>'
        elif item_id == "foxfire_go_knot":
            shape = f'<path d="M128 37 C74 37 54 83 88 111 C112 130 144 113 168 135 C199 163 175 218 128 218 C81 218 57 163 88 135 C112 113 144 130 168 111 C202 83 182 37 128 37 Z" fill="none" stroke="{a}" stroke-width="18"/><circle cx="128" cy="128" r="27" fill="{c}" stroke="#7e352e" stroke-width="8"/><path d="M116 128 L140 128 M128 116 L128 140" stroke="#2b3b4b" stroke-width="6"/><circle cx="128" cy="40" r="10" fill="{b}" stroke="#7e352e" stroke-width="5"/>'
        elif item_id == "odyssey_star_compass":
            shape = f'<circle cx="128" cy="128" r="84" fill="{a}" stroke="#4f3a2a" stroke-width="9"/><circle cx="128" cy="128" r="61" fill="{c}" stroke="#4f3a2a" stroke-width="7"/><circle cx="128" cy="128" r="41" fill="{b}" stroke="#4f3a2a" stroke-width="5"/><path d="M128 68 L141 115 L188 128 L141 141 L128 188 L115 141 L68 128 L115 115 Z" fill="{a}" stroke="#f0d27b" stroke-width="5"/><circle cx="128" cy="128" r="12" fill="{b}" stroke="#4f3a2a" stroke-width="5"/>'
        elif item_id == "copper_jade_talisman":
            shape = f'<path d="M128 18 Q145 47 175 53 Q155 78 164 110 Q128 102 92 110 Q101 78 81 53 Q111 47 128 18 Z" fill="{a}" stroke="#5c3d30" stroke-width="8"/><path d="M128 74 L153 99 L143 139 L113 139 L103 99 Z" fill="{b}" stroke="#5c3d30" stroke-width="7"/><path d="M128 18 L128 7 M81 53 L69 46 M175 53 L187 46" stroke="{c}" stroke-width="7" stroke-linecap="round"/><path d="M128 139 L128 180" stroke="{a}" stroke-width="8"/><circle cx="128" cy="205" r="25" fill="{b}" stroke="#5c3d30" stroke-width="7"/>'
        elif item_id == "prism_focus_charm":
            shape = f'<path d="M128 22 L188 76 L166 173 L90 173 L68 76 Z" fill="{a}" stroke="#32295e" stroke-width="9"/><path d="M128 49 L160 79 L149 143 L107 143 L96 79 Z" fill="{b}" stroke="#32295e" stroke-width="7"/><path d="M128 22 L128 49 M68 76 L96 79 M188 76 L160 79" stroke="{c}" stroke-width="7"/><path d="M128 173 L128 205" stroke="{c}" stroke-width="8"/><circle cx="128" cy="218" r="11" fill="{c}" stroke="#32295e" stroke-width="5"/>'
        else:
            shape = f'<circle cx="128" cy="128" r="85" fill="{a}" stroke="#18223c" stroke-width="9"/><circle cx="128" cy="128" r="61" fill="#d99c4b" stroke="{c}" stroke-width="7"/><circle cx="128" cy="128" r="43" fill="#e9bf67" stroke="#18223c" stroke-width="5"/><path d="M128 85 L139 119 L174 119 L146 140 L157 174 L128 153 L99 174 L110 140 L82 119 L117 119 Z" fill="{b}" stroke="#18223c" stroke-width="4"/><path d="M128 43 L128 64 M213 128 L192 128 M128 213 L128 192 M43 128 L64 128" stroke="{c}" stroke-width="7" stroke-linecap="round"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" fill="none" role="img" aria-label="{item_id}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>
{shape}
</svg>
'''


def normalize_source(source: Path) -> Image.Image:
    image = Image.open(source).convert("RGBA")
    alpha = image.getchannel("A")
    # Remove isolated low-alpha generation haze while preserving antialiased edges.
    solid = alpha.point(lambda value: 255 if value >= 32 else 0)
    solid = solid.filter(ImageFilter.MaxFilter(5))
    cleaned = ImageChops.multiply(alpha, solid)
    image.putalpha(cleaned)
    rgb = image.convert("RGB")
    black = Image.new("RGB", image.size, (0, 0, 0))
    rgb = Image.composite(rgb, black, cleaned)
    return Image.merge("RGBA", (*rgb.split(), cleaned))


def fit_to_template(source: Image.Image, template_box: list[float]) -> Image.Image:
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("generated source has no visible alpha")
    cropped = source.crop(bbox)
    x0, y0, x1, y1 = template_box
    left = round(x0 * CANVAS[0])
    top = round(y0 * CANVAS[1])
    width = round((x1 - x0) * CANVAS[0])
    height = round((y1 - y0) * CANVAS[1])
    inset = 0.06
    max_width = max(1, round(width * (1 - 2 * inset)))
    max_height = max(1, round(height * (1 - 2 * inset)))
    scale = min(max_width / cropped.width, max_height / cropped.height)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    resized = cropped.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    paste_at = (left + (width - size[0]) // 2, top + (height - size[1]) // 2)
    canvas.alpha_composite(resized, paste_at)
    alpha = canvas.getchannel("A")
    rgb = Image.composite(canvas.convert("RGB"), Image.new("RGB", CANVAS, (0, 0, 0)), alpha)
    return Image.merge("RGBA", (*rgb.split(), alpha))


def fit_to_handheld(
    source: Image.Image,
    raw_grip_anchor: list[float],
    mirror: bool,
) -> tuple[Image.Image, tuple[int, int]]:
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("handheld source has no visible alpha")
    cropped = source.crop(bbox)
    # Product metadata records the grip in the original generated frame. Convert
    # it to the alpha-cropped source coordinates before fitting.
    source_width, source_height = source.size
    grip_x = (raw_grip_anchor[0] * source_width - bbox[0]) / max(1, bbox[2] - bbox[0])
    grip_y = (raw_grip_anchor[1] * source_height - bbox[1]) / max(1, bbox[3] - bbox[1])
    grip_x = min(1.0, max(0.0, grip_x))
    grip_y = min(1.0, max(0.0, grip_y))
    if mirror:
        cropped = cropped.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        grip_x = 1.0 - grip_x
    # The right-hand EQ-C anchor is fixed by the shared answer-screen frame.
    # The generated weapon is placed around that anchor, never baked into the
    # protagonist base and never replaced by a waist/back substitute.
    target_anchor = (800, 800)
    edge_margin = 24
    scale = min(
        750 / cropped.height,
        500 / cropped.width,
        (target_anchor[0] - edge_margin) / max(1, grip_x * cropped.width),
        (CANVAS[0] - target_anchor[0] - edge_margin) / max(1, (1.0 - grip_x) * cropped.width),
        (target_anchor[1] - edge_margin) / max(1, grip_y * cropped.height),
        (CANVAS[1] - target_anchor[1] - edge_margin) / max(1, (1.0 - grip_y) * cropped.height),
    )
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    resized = cropped.resize(size, Image.Resampling.LANCZOS)
    paste_at = (
        target_anchor[0] - round(grip_x * size[0]),
        target_anchor[1] - round(grip_y * size[1]),
    )
    if paste_at[0] < 0 or paste_at[1] < 0 or paste_at[0] + size[0] > CANVAS[0] or paste_at[1] + size[1] > CANVAS[1]:
        raise ValueError(f"handheld art would clip canvas at {paste_at} size {size}")
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(resized, paste_at)
    alpha = canvas.getchannel("A")
    rgb = Image.composite(canvas.convert("RGB"), Image.new("RGB", CANVAS, (0, 0, 0)), alpha)
    return Image.merge("RGBA", (*rgb.split(), alpha)), target_anchor


def build_review_matrix() -> None:
    columns = 4
    card_width, card_height = 370, 285
    matrix = Image.new("RGBA", (columns * 395 + 20, 4 * 320 + 20), "#f4f0e6")
    draw = ImageDraw.Draw(matrix)
    try:
        font = ImageFont.truetype("segoeui.ttf", 20)
        small = ImageFont.truetype("segoeui.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    for index, (item_id, item) in enumerate(PRODUCTS.items()):
        col, row = index % columns, index // columns
        x, y = 20 + col * 395, 20 + row * 320
        draw.rounded_rectangle((x, y, x + card_width, y + card_height), radius=18, fill="#fffdf7", outline="#d6cbb8", width=2)
        overlay = Image.open(OVERLAY_ROOT / f"{item_id}.png").convert("RGBA")
        visible = overlay.getchannel("A").getbbox()
        if visible:
            crop = overlay.crop(visible)
            crop.thumbnail((310, 215), Image.Resampling.LANCZOS)
            px = x + (card_width - crop.width) // 2
            py = y + 34 + (215 - crop.height) // 2
            matrix.alpha_composite(crop, (px, py))
        draw.text((x + 16, y + 12), item_id, fill="#1f2a35", font=small)
        draw.text((x + 16, y + 255), f'{item["rarity"]} {item["type"]} · {item["source_classification"]}', fill="#4e6470", font=small)
    matrix.convert("RGB").save(REVIEW_MATRIX_PATH, "PNG", optimize=True)


def main() -> int:
    PACKAGE.mkdir(parents=True, exist_ok=True)
    OVERLAY_ROOT.mkdir(parents=True, exist_ok=True)
    ICON_ROOT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for item_id, item in PRODUCTS.items():
        source = SOURCE_ROOT / f"{item_id}.png"
        if not source.exists():
            raise FileNotFoundError(source)
        overlay_path = OVERLAY_ROOT / f"{item_id}.png"
        icon_path = ICON_ROOT / f"{item_id}.svg"
        normalized = normalize_source(source)
        if item["handheld_required"]:
            final, handheld_anchor = fit_to_handheld(
                normalized,
                item["handheld_grip_anchor"],
                item["mirror_for_handheld"],
            )
        else:
            final = fit_to_template(normalized, item["template_box"])
            handheld_anchor = None
        final.save(overlay_path, "PNG", optimize=True, compress_level=9)
        icon_path.write_text(make_icon(item_id, item), encoding="utf-8", newline="\n")
        rows.append(
            {
                "item_id": item_id,
                "source_file": str(source.relative_to(ROOT)).replace("\\", "/"),
                "source_sha256": sha256(source),
                "generation_mode": "new_asset",
                "generation_prompt": item["prompt"],
                "overlay_path": f"/assets/hero/equipment/wearables/overlays/{item_id}.png",
                "icon_path": f"/assets/hero/equipment/functional/{item_id}.svg",
                "overlay_sha256": sha256(overlay_path),
                "icon_sha256": sha256(icon_path),
                "overlay_dimensions": list(Image.open(overlay_path).size),
                "overlay_alpha_bbox": list(Image.open(overlay_path).getchannel("A").getbbox() or ()),
                "type": item["type"],
                "rarity": item["rarity"],
                "slot": item["slot"],
                "layer": item["layer"],
                "renderer_family": item["renderer_family"],
                "handheld_required": item["handheld_required"],
                "source_classification": item["source_classification"],
                "zone": item["zone"],
                "zone_key": item["zone_key"],
                "template_box": item.get("template_box"),
                "handheld_anchor_px": list(handheld_anchor) if handheld_anchor else None,
                "front_grip_target_height_px": 240 if item["handheld_required"] else None,
                "presentation_roles": {
                    "shop_preview": f"/assets/hero/equipment/functional/{item_id}.svg" if item["source_classification"] == "SHOP_EXCLUSIVE" else None,
                    "zone_reward": f"/assets/hero/equipment/functional/{item_id}.svg" if item["source_classification"] == "ZONE_EXCLUSIVE" else None,
                    "full_body_overlay": f"/assets/hero/equipment/wearables/overlays/{item_id}.png",
                    "weapon_back_layer": f"/assets/hero/equipment/wearables/overlays/{item_id}.png" if item["type"] == "weapon" and not item["handheld_required"] else None,
                    "weapon_front_layer": None,
                    "handheld_weapon_layer": f"/assets/hero/equipment/wearables/overlays/{item_id}.png" if item["handheld_required"] else None,
                    "grip_compatible_asset": f"/assets/hero/equipment/wearables/overlays/{item_id}.png" if item["handheld_required"] else None,
                },
            }
        )
    build_review_matrix()
    report = {
        "schema": "go-odyssey.eq-e-art-production-qa.v1",
        "task": "GO_ODYSSEY_EQ_E_NEW_EQUIPMENT_WEAPON_ART_AND_ASSET_PRODUCTION_001",
        "generator": "openai_image_gen_new_asset_then_deterministic_pil_normalization",
        "frame": "PLAYER_FRAME_A_STANDARD_CHIBI",
        "canvas": list(CANVAS),
        "source_identity": "EQ-D canonical lock 426f9ee57481f697e71756110c946b51a74c9f6f",
        "registry_mutation": False,
        "renderer_mutation": False,
        "placeholder_count": 0,
        "items": rows,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"items": len(rows), "report": str(REPORT_PATH), "review_matrix": str(REVIEW_MATRIX_PATH)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
