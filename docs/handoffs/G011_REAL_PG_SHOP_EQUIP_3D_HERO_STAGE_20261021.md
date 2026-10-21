# G011｜真正 PG 購買 → 背包穿戴 → Hero WebGL 主手附掛 → 獨立登入持久化

**本機首輪階段目標：PASS**。在獨立 Git worktree `D:\go-odyssey-g010-3d-activation-20261021` 使用既有源碼的 native PostgreSQL 可銷毀 fixture，經原正式 Product 購買 API 與真 Chrome 操作，驗證全路徑；不是改寫已完成的 G010 M3 證據。

- 測試環境生成全新 native PostgreSQL cluster 和唯一 synthetic non-admin 帳戶，註冊 `player_appearance` 初始 apprentice，再由真 server entitlement lazy-bootstrap 權威 A1（不能任意指定未擁有角色）。
- 真實商城預設 OFF：`POST /api/shop/buy` 回 `409 SHOP_PURCHASE_DISABLED`，確認 1000 coins 不動。
- 僅在該 disposable pytest 進程啟用 `CANONICAL_COIN_SHOP_PURCHASE_ENABLED=1`、`EQUIPMENT_CANONICAL_LOADOUT_ENABLED=1`，且僅 **in-memory /shop + /inventory** 使用原測試 helper 開啟前端。磁碟正式 HTML、預設功能開關全未修改。
- 新 Chrome 真 DOM：精準 Owner 300 coins 的 wooden_sword 先由商城購買，重複 UI 點擊只有 1 筆真 API `POST /api/shop/buy`；點擊商城官方「前往背包」連結，於實際背包操作 `POST /api/player/inventory/equip`，伺服器 inventory 變成 equipped。
- 進入**原 Hero 真正 `/hero?tab=equipment`**（沒有截圖假造或攔截 API），G008 真實角色 GLB SHA 後啟用 Three.js WebGL；直接從既有共用 G009 attachment-host diagnostics 取得 **MAIN_HAND presentation_id = `WEAPON_628812E9B559`, child_count=1**，確認一個真正 render scene child 物件已掛載到角色手部。
- 新的獨立登入 session 再次進入原 Hero，仍能重建共用主手 GLB；背包仍顯示裝備、商店仍不讓買同一持有物件。真 PostgreSQL 權威校驗：1000 → **700 coins**，player_inventory 恰 1 owned/equipped wooden_sword，coin_purchase_operations=1、currency_log 負扣=1；全流程無新 XP、無 JS 頁面例外／API HTTP >=400。
- 測試完成後，現有 Product 預設 flag 驗證回復 OFF（只是 pytest monkeypatch scope，並未修改正式環境）；正式 API／商城 release policy、G009 舊 D007 **NOT_CLEARED** 木劍模型仍不得直接發布。**這不是授權該武器合法正式上線或其他 28 件都能穿戴。**
- 原始 machine receipt：`D:\go-odyssey-g010-3d-activation-evidence-20261021\G011_REAL_PG_SHOP_EQUIP_HERO_3D_20261021.json`。原始新增可重現測試 `tests/test_g011_real_pg_shop_3d_hero_e2e.py` 及 browser `tests/e2e/g011_real_pg_shop_equip_hero_browser.mjs`，本輪 `python -m pytest -xq --tb=short --show-capture=no tests/test_g011_real_pg_shop_3d_hero_e2e.py` **1 PASS / 0 FAIL，exit0**。對 G010 M3 已過測試並未重跑；只額外證明 M3 未包含的 G008/G009 主手真 3D Attachment 與 fresh-session 恢復。
- 暫未驗收的完整產品端：「4 Formal9 RIGHTS_CLEARED_RELEASE_NOT_ADMITTED」模型正式准入後真玩家穿戴／換手、「P038 8+4」正式映射與其餘 16 來源 Blender QA 替代、真 iPad Safari UAT、最新產品合併與 Oracle 正式部署。
- 未觸碰正式玩家、正式 master 合併或正式 Oracle；Go Merge & Go Deploy 各需 Owner 核准。
