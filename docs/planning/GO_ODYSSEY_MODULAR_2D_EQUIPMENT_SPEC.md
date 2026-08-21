# GO ODYSSEY — Static Modular 2D Equipment Contract

Status: Owner review contract
Frame authority: `PLAYER_FRAME_A_STANDARD_CHIBI`
Canvas: `1056x1408 RGBA`
Item × character bespoke redraw target: `0`

This contract turns the P2/P3 wearable experiments into a repeatable static
2D production boundary. It defines where an asset may be designed, how it is
composed, and which evidence is required before an item is promoted from
inventory art to a wearable presentation. It does not mass-produce art and it
does not change gameplay authority.

Machine-readable sources:

- [templates.json](rpg_modular_2d_equipment/templates.json)
- [visibility_matrix.json](rpg_modular_2d_equipment/visibility_matrix.json)
- [template_qa.json](rpg_modular_2d_equipment/template_qa.json)
- [renderer_compatibility.json](rpg_modular_2d_equipment/renderer_compatibility.json)
- [template diagrams](rpg_modular_2d_equipment/templates.svg)
- [safe-zone diagram](rpg_modular_2d_equipment/safe_zones.svg)
- [layer contract diagram](rpg_modular_2d_equipment/layer_contract.svg)
- [six-character template QA sheet](rpg_modular_2d_equipment/template_qa.svg)

## 1. Immutable product boundary

The renderer is a presentation-only projection:

```text
player_inventory.equipped
        ↓ server response
presentation registry + wearable template
        ↓ deterministic composition
Hero / Profile / Backpack visual preview
```

The following remain authoritative and are not copied into art metadata:

| Concern | Authority |
| --- | --- |
| Ownership | `player_inventory` |
| Equipped state | `player_inventory.equipped` |
| Effects and combat values | server `EQUIPMENT_DEFS` |
| Character identity | `player_appearance.character_key` |
| Client combat authority | `NO` |
| Wearable rendering gameplay delta | `0` |

No wearable asset, template, mask, or client renderer may write inventory,
effects, coins, prices, drops, XP, Premium, payment, or combat state.

## 2. Canonical frame and normalized zones

Every template uses the same normalized coordinate system over
`PLAYER_FRAME_A_STANDARD_CHIBI`. The origin is top-left and coordinates are
fractions of the `1056x1408` canvas. The contract zones are in
[templates.json](rpg_modular_2d_equipment/templates.json).

| Zone | Normalized extent | Contract |
| --- | --- | --- |
| `FACE_SAFE_ZONE` | x `0.40–0.60`, y `0.085–0.205` | Non-face equipment must never enter eyes/nose/mouth area. |
| `HAIR_ZONE` | x `0.32–0.68`, y `0.035–0.29` | Preserve hair/hood unless a reusable mask is declared. |
| `NECK_ZONE` | x `0.43–0.57`, y `0.205–0.29` | Keep jaw/neck transition readable; robes use an open collar. |
| `TORSO_ZONE` | x `0.31–0.69`, y `0.25–0.58` | Primary torso overlay region. |
| `SHOULDER_ZONE` | x `0.18–0.82`, y `0.25–0.43` | Mantles and armor volume may use this region. |
| `WAIST_ZONE` | x `0.28–0.72`, y `0.43–0.62` | Sheaths, belt items, and charms attach here. |
| `HAND_ZONE` | left/right rects in `0.12–0.30` and `0.70–0.88` | No fake grip; preserve open-hand reading. |
| `BACK_ZONE` | x `0.30–0.70`, y `0.16–0.58` | Back-mounted assets stay behind the base character. |

`FACE_SAFE_ZONE` is a reusable clearance rule, not a character-specific art
fix. The only exception is `FACE_ACCESSORY`, where face intersection is
intentional and must be declared by the template.

## 3. Canonical wearable templates

The ten templates are the only approved starting points for future wearable
art. Each template specifies an anchor, bounding box, face/neck/shoulder/waist
limits, layer, occlusion behavior, and mobile rule.

| Template | Intended use | Primary layer | Face policy |
| --- | --- | --- | --- |
| `WEAPON_WAIST` | sword, short blade, sheath | `BACK_WEAPON` | Must clear face and neck. |
| `WEAPON_BACK` | long blade or unusual long weapon | `BACK_WEAPON` | Must clear face; blade behind body. |
| `FOREARM_GEAR` | claw, gauntlet, forearm item | `FRONT_BODY` | Must not fake finger grip. |
| `TORSO_ARMOR` | cuirass, scale armor | `TORSO_ARMOR` | Shared face clearance and jaw readability. |
| `ROBE_OVERLAY` | robe or cloth body layer | `TORSO_ARMOR` | Open V/low collar; face-safe clearance. |
| `SHOULDER_MANTLE` | fur, cape, void mantle | `BACK_BODY` plus optional front segment | Central neck opening; preserve head silhouette. |
| `FACE_ACCESSORY` | mask or face identity item | `HEAD_FACE` | May cover face by design; hair mask required where needed. |
| `NECK_CHEST_ACCESSORY` | pendant, amulet, brooch | `FRONT_ACCESSORY` | May enter lower neck only; never face-safe zone. |
| `WAIST_ACCESSORY` | charm or belt item | `FRONT_ACCESSORY` | Attach to waist; preserve hands and proportions. |
| `BACK_ACCESSORY` | non-weapon back item | `BACK_BODY` | Behind base; reusable body/hair/backpack mask only. |

The full field-level contract is in `templates.json`; the SVG diagram is a
review aid, not a second authority.

## 4. Layer contract

The deterministic composition order is:

```text
BACK_WEAPON / BACK_BODY
        ↓
CHARACTER_BASE
        ↓
TORSO_ARMOR / ROBE_OVERLAY
        ↓
FRONT_BODY / FRONT_ACCESSORY
        ↓
HEAD_FACE
        ↓
HAIR_FRONT_MASK
        ↓
allowed visual FX only
```

Rules:

1. A static weapon is `WAIST_SHEATHED` first and `BACK_MOUNTED` only when its
   silhouette makes waist carry unsuitable.
2. `HAND_HELD` is not a static wearable mode. A held pose belongs to a future
   combat/cinematic pose system.
3. A back item is rendered behind the character base unless a small declared
   hilt/shoulder foreground segment is needed.
4. Armor and robe overlays use the shared face-safe clearance geometry.
5. A face accessory may cover the face only through `FACE_ACCESSORY` and never
   changes gameplay identity or effects.

## 5. Mask contract

Masks are reusable frame-level occlusion tools, not item × character art.

| Mask | Applies to | Rule |
| --- | --- | --- |
| `FACE_SAFE_ZONE_CLEARANCE` | all non-face armor/body overlays | Remove overlay alpha from the normalized core face zone. |
| `HAIR_FRONT_MASK` | face accessories and back weapons when needed | Restore bangs/hair front over the wearable. |
| `BODY_OCCLUSION_MASK` | back weapons/accessories | Keep the base torso between rear asset and front silhouette. |
| `FRONT_HAND_MASK` | only if a future pose proves it necessary | Never use it to fake an open hand gripping a static weapon. |
| `SHOULDER_FOREGROUND_MASK` | shoulder mantles | Reusable shoulder segment; no character-specific redraw. |

If an item requires a unique mask for every character, it fails the modular
scalability gate. A reusable mask may be introduced only with a six-character
matrix and a documented reason.

## 6. Fifteen-item visibility policy

The current matrix deliberately does not force all items into a wearable
interpretation:

| Policy | Count | Meaning |
| --- | ---: | --- |
| `VISIBLE_WEARABLE` | 4 | Reference evidence supports deterministic projection. |
| `VISIBLE_IF_SUPPORTED` | 10 | Template-compatible, but needs item-specific six-character promotion QA. |
| `INVENTORY_ONLY` | 1 | Keep gameplay item; do not invent visual lore or a wearable. |

The complete item-by-item matrix is
[visibility_matrix.json](rpg_modular_2d_equipment/visibility_matrix.json).
`go_stone_black` is intentionally `INVENTORY_ONLY`; its canonical Go-stone
identity is not converted into an arbitrary charm or pendant.

## 7. Art-production workflow

Required:

```text
select canonical template
        → design inside template bounding box and zones
        → export true-alpha CHARACTER_WEARABLE_ART
        → deterministic normalized renderer placement
        → six-character QA at desktop and mobile scale
        → promote visibility only after evidence passes
```

Forbidden:

```text
generate arbitrary item art
        → enlarge inventory icon
        → move pixels until one character looks acceptable
        → claim universal support
```

Inventory icons remain `INVENTORY_ITEM_ART`. They are not wearable assets.
The current P2/P3 assets remain reference evidence; this contract does not
regenerate the 15-item set.

## 8. Six-character template gate

The first formal reference set is intentionally small:

- `iron_sword` → `WEAPON_WAIST`
- `dragon_scale` → `TORSO_ARMOR`
- `fox_mask` → `FACE_ACCESSORY`
- `cloth_robe` → `ROBE_OVERLAY`

These four references produce 24 character/template cells across:
`apprentice`, `mage`, `paladin`, `trail_apprentice`, `night_runner`, and
`constellation_apprentice`.

Required evidence per cell:

- no non-face face-zone occlusion;
- no white-box, matte, or alpha residue;
- no fake hand grip;
- stable mobile readability;
- identity preservation;
- zero bespoke item × character redraws.

The accepted evidence is recorded in
[template_qa.json](rpg_modular_2d_equipment/template_qa.json) and visualized
in [template_qa.svg](rpg_modular_2d_equipment/template_qa.svg).

## 9. Renderer compatibility

The existing `js/rpg_wave2_wearable_renderer.js` remains compatible with this
contract after one narrow presentation-only guard: `INVENTORY_ONLY` registry
entries are skipped. It already consumes server-projected equipped IDs,
resolves presentation metadata from the registry, composes the approved layer
order, and fails closed to base art for unsupported characters. No gameplay,
ownership, effect, or database path changes are part of this contract.

The compatibility mapping and authority audit are in
[renderer_compatibility.json](rpg_modular_2d_equipment/renderer_compatibility.json).
`wearable_visibility`, `template_id`, and `mask_policy` are presentation
metadata only. They must never duplicate ownership, equipped state, effects,
prices, drops, or combat authority.

## 10. Gate outcome

This contract is ready for Owner review. It does not authorize:

- mass production of the remaining wearable art;
- new equipment IDs;
- gameplay/effect changes;
- combat poses;
- DB migration;
- Production deployment;
- merging PR #392.

`PR392=KEEP_DRAFT`
`MERGE=NO`
`DEPLOY=NO`
