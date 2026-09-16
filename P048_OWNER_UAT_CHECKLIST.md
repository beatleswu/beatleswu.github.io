# P048 Owner visual UAT checklist

## Open the preview

- Local: http://127.0.0.1:8048/p048_3d_shop_preview.html?preview=1
- LAN / iPad: http://192.168.0.237:8048/p048_3d_shop_preview.html?preview=1

The LAN server is bound to `0.0.0.0:8048` and returned HTTP 200 from the
machine. No canonical, Product, Commerce, ownership, equipment, DB, merge, or
deploy action is performed by this page.

## Suggested review path

1. Start with the default A1 Basic Adventurer in 3/4 view. Drag with a mouse
   or one finger to rotate.
2. Cycle HEAD through Beanie, Top Hat, Frog Hat, Santa Hat, Sunglasses, then
   back to None. Confirm only one presentation is visible at a time.
3. Show and hide B02 Backpack. Inspect the 3/4 and Back views.
4. Select C01 Bunny. Then select C04 Corgi and compare Idle, Walk, and Attack.
5. Trigger V01 Confetti twice to inspect the bounded retrigger behavior.
6. Use Front, 3/4, Side, and Back. Use Reset presentation to return to the
   A1 baseline.
7. Repeat the most important checks on iPad landscape, iPad portrait, and
   mobile portrait.

## Acceptance questions

- Is A1 centered and readable in every view?
- Do mouse and touch rotation feel natural?
- Does each of the five HEAD presentations sit correctly without duplicates?
- Does B02 attach as a presentation-only BACK item and show/hide cleanly?
- Does C01 behave as a rigid-transform companion?
- Do C04 Idle, Walk, and Attack look like distinct segmented playback?
- Does V01 read as a Victory effect and retrigger without a visible leak?
- Are controls usable without horizontal overflow on the target device?
- Is it clear that Preview is not Own and does not purchase/equip anything?

## Governance state

```text
OWNER_VISUAL_UAT=NOT_RUN
MERGE=NO
DEPLOY=NO
PRODUCTION_MUTATION=NO
```

Record Owner feedback separately after the Owner has inspected the live
preview. Do not treat the automated/browser evidence as Owner acceptance.
