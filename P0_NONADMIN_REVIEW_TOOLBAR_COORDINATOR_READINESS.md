# P0 non-admin review toolbar coordinator readiness

## Decision

`CLASSIFICATION=UI_AUTHORIZATION_VISIBILITY_LEAK`

The server-side privileged mutation boundary is intact. The candidate makes
the smallest scoped correction: privileged review controls are absent from a
non-admin live DOM and remain available to an authorized admin after strict
bootstrap. Product behavior outside toolbar visibility is unchanged.

## Scope checks

- `app.py` changed: `NO`
- DB/schema/migrations changed: `NO`
- D1 changed: `NO` (`E10_MAP_BATTLE_V1_MODE=global` remains)
- Lane C changed: `NO`
- P051-C1 included: `NO`
- Zone5 included: `NO`
- MBV1 retirement: `NO`
- app image rebuild: `NO`
- Production mutation at this checkpoint: `NO`

## Handoff

The implementation and focused regressions are ready for the normal governed
canonical admission followed by static-only packaging/promotion. After public
promotion, request Owner verification on the real `test01` answer page:

```text
World Map -> Continue Adventure -> answer page
Expected: 管理審題工具列整排消失
Preserve: 返回地圖 / 上一題 / 重試 / 下一題
```

`READY_FOR_OWNER_NONADMIN_TOOLBAR_UAT=YES` applies only after public static
promotion. `OWNER_UAT=NOT_RUN` and `INCIDENT_END=NOT_SET` remain true here.

