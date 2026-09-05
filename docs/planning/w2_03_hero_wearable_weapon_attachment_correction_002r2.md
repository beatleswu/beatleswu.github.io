# W2-03 Hero Wearable Weapon Attachment Correction 002R2

## Bounded correction

This change addresses the Owner-confirmed `wooden_sword` floating presentation
only. The existing transparent normalized-frame artwork is retained; its
presentation metadata now places it as a smaller, body-relative hip carry:

- mode: `CARRIED_AT_HIP`;
- offset: `x=-12%`, `y=-7%`;
- scale: `0.95` around the normalized frame center;
- layer/occlusion: `BACK_WEAPON`.

The renderer applies this transform only when it is present in the registry and
within a bounded numeric range. The base Hero is still composited above the
weapon, so the belt/hip placement reads as attached instead of floating beside
the open hand.

## Preserved results and exclusions

- `dragon_scale` armor compositing is unchanged and remains accepted.
- `lucky_stone` accessory compositing is unchanged and remains accepted.
- `cloth_robe` and `fox_pelt` remain held for separately approved replacement
  art; neither is modified or rendered by this task.
- `xp_amulet` remains `HOLD_FOR_AUTHORITY`; it is not made canonically
  equippable.
- `go_stone_black` remains `INVENTORY_ONLY` and has no wearable projection.
- No new art, Hero anatomy redraw, gameplay authority, inventory mutation,
  Shop/Loadout change, database change, payment change, or Production access
  was performed.

## Proof contract

The browser scaffold uses a server-backed fixture read model and exercises:

1. no functional equipment;
2. `wooden_sword` only;
3. `wooden_sword + dragon_scale + lucky_stone`.

Each state is captured at desktop, iPad portrait, and mobile portrait. The
focused assertions verify the exact `CARRIED_AT_HIP` transform, `BACK_WEAPON`
occlusion marker, server projection authority, preserved armor/accessory
layers, and absence of gameplay authority.

## Status

`PASS_W2_03_WEAPON_ATTACHMENT_READY_FOR_OWNER_VISUAL_REVIEW`
