# Wave 2 Gate 2 P2 wearable source prompts

Generation mode: built-in `image_gen`, one source image per equipment identity. The approved
Apprentice, Mage, and Paladin P1 masters were supplied only as style, lighting, outline, and
body-proportion references. They were not edited and do not appear in the generated sources.

The tool returned a baked neutral checker preview rather than alpha. The review builder therefore
extracts the central outlined object, fills only accidental matte-colour holes, explicitly restores
the fox-mask eye openings, neutralizes RGB under alpha zero, and validates the resulting RGBA
cutouts. The generated RGB sources are retained beside the normalized outputs for review.

## `iron_sword`

> Redraw the canonical `iron_sword` as one isolated character-wearable sword. Preserve the simple
> silver/slate steel blade, dark blue-brown outline, brown leather grip, compact straight guard,
> utilitarian silhouette, and restrained soft upper-left lighting, but recompose it for body use
> rather than enlarging the 256px inventory icon. Front/near-front orthographic view, complete and
> uncropped, no character, hand, body, sheath, UI, text, stats, glow, particles, or rarity effects.

## `dragon_scale`

> Redraw the canonical `dragon_scale` as one reusable front-facing torso overlay for
> `PLAYER_FRAME_A_STANDARD_CHIBI`: a compact sleeveless blue scale cuirass from upper torso to
> waist, modest shoulder caps, deep navy edge structure, restrained gold neckline and lower trim.
> Use large mobile-readable scale planes and the P1 cel-soft character finish. No character,
> mannequin, helmet, gauntlets, boots, shield, weapon, UI, text, stats, glow, or rarity effects.

## `fox_mask`

> Redraw the canonical `fox_mask` as one reusable face-worn overlay for
> `PLAYER_FRAME_A_STANDARD_CHIBI`: compact lacquered ivory kitsune mask, warm reddish-brown outline,
> restrained red brow and cheek markings, integrated small fox ears, narrow eye openings, and a
> simple red nose/muzzle motif. Keep it as a mask rather than a helmet. No character, head, hair,
> hood, body, mannequin, UI, text, stats, glow, or rarity effects.

Shared constraints for all three prompts: polished chibi/anime RPG production art compatible with
the supplied P1 masters, clean single-object silhouette, controlled cel-soft shading, genuine
transparent-background intent, no watermark, and no character-specific identity cues.

## P2B `iron_sword` carry source

Use case: precise-object-edit. The existing `iron_sword` source was supplied as a style and
canonical-item reference only. Create one standalone carried presentation of the same sword,
fully sheathed in a simple dark brown leather and deep navy scabbard with matching silver fittings;
leave the recognizable silver guard and brown pommel/hilt visibly exposed. Preserve the original
blade identity, restrained blue-brown outline, materials, palette, and cel-soft lighting. Add only
a small reusable belt loop/strap near the sheath mouth so the object can sit at a character waist
or across a character back. Front/orthographic three-quarter product view, one complete centered
object, fully visible and uncropped, transparent background. This is one universal equipment asset
for `PLAYER_FRAME_A_STANDARD_CHIBI`, never character-specific. Avoid characters, bodies, hands,
faces, hair, armor, robes, mannequins, second weapons, UI, text, logos, glow, particles, rarity
effects, watermarks, and separate character variants.
