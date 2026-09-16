# P048 actual runtime visual evidence

All captures below come from the P048 Three.js WebGL runtime, not static
mockups. The Local/LAN interactive preview is the primary Owner artifact:

- Local: http://127.0.0.1:8048/p048_3d_shop_preview.html?preview=1
- LAN: http://192.168.0.237:8048/p048_3d_shop_preview.html?preview=1

## Desktop · 1280×800

| Evidence | Capture |
| --- | --- |
| A1 baseline | [baseline.png](artifacts/p048_visual_evidence/desktop/baseline.png) |
| HEAD cycle | [Beanie](artifacts/p048_visual_evidence/desktop/head-1.png), [Top Hat](artifacts/p048_visual_evidence/desktop/head-2.png), [Frog Hat](artifacts/p048_visual_evidence/desktop/head-3.png), [Santa Hat](artifacts/p048_visual_evidence/desktop/head-4.png), [Sunglasses](artifacts/p048_visual_evidence/desktop/head-5.png) |
| B02 Backpack | [backpack.png](artifacts/p048_visual_evidence/desktop/backpack.png) |
| C01 Bunny | [c01-idle.png](artifacts/p048_visual_evidence/desktop/c01-idle.png) |
| C04 timeline | [idle](artifacts/p048_visual_evidence/desktop/c04-idle.png), [walk](artifacts/p048_visual_evidence/desktop/c04-walk.png), [attack](artifacts/p048_visual_evidence/desktop/c04-attack.png) |
| V01 / retrigger | [v01-active-retrigger.png](artifacts/p048_visual_evidence/desktop/v01-active-retrigger.png) |
| Mouse rotation | [mouse-rotated.png](artifacts/p048_visual_evidence/desktop/mouse-rotated.png) |
| Views | [Front](artifacts/p048_visual_evidence/desktop/view-front.png), [3/4](artifacts/p048_visual_evidence/desktop/view-three-quarter.png), [Side](artifacts/p048_visual_evidence/desktop/view-side.png), [Back](artifacts/p048_visual_evidence/desktop/view-back.png) |

## Responsive surfaces

| Surface | Capture | Result |
| --- | --- | --- |
| iPad landscape · 1180×820 | [ipad-landscape.png](artifacts/p048_visual_evidence/ipad-landscape.png) | one renderer, controls usable, no overflow, zero JS/WebGL errors |
| iPad portrait · 820×1180 | [ipad-portrait.png](artifacts/p048_visual_evidence/ipad-portrait.png) | stacked layout, one renderer, no overflow, zero JS/WebGL errors |
| Mobile touch · 390×844 | [mobile-touch.png](artifacts/p048_visual_evidence/mobile-touch.png) | actual touch drag recorded, one renderer, no overflow |
| Mobile portrait · 390×844 | [mobile-portrait.png](artifacts/p048_visual_evidence/mobile-portrait.png) | stacked layout, controls usable, no overflow, zero JS/WebGL errors |

The Owner-facing page starts at A1 / 3/4 / no attachments. Selectors are
lazy-loaded, so the default-OFF non-preview page remains at zero model
requests. V01 timing is explicitly presented as runtime `PROPOSED_ONLY`.

Owner UAT is still `NOT_RUN`.
