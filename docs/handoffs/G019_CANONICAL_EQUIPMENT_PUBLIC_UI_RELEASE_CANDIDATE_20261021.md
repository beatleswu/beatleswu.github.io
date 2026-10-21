# G019｜受控正式頁面商城／背包整合
2026-10-21｜Product 隔離候選；不是正式發布授權。

## 階段性目標
修復 G010 M3 的主要差距：以前玩家真實購買、穿戴、換裝、重新登入只在 loopback 記憶體改寫的 Shop／Backpack HTML 上驗證。G019 已在磁碟上的原版 shop.html、inventory.html 和 app.py 建立受伺服器核准的正式操作入口；預設關閉，不改 11/11 遊戲 UI、正式玩家資料、舊 P022/P038 3D 資產准入。

## 對伺服器的嚴格依賴
三個都要真正由伺服器 enable，否則一般頁面仍只讀：
- 原 CANONICAL_COIN_SHOP_PURCHASE_ENABLED（default OFF）
- 原 EQUIPMENT_CANONICAL_LOADOUT_ENABLED（default OFF）
- 新 G019_APPROVED_EQUIPMENT_SHOP_UI_ENABLED（default OFF）

由 Flask 正式登入的 /api/shop/catalog 輸出 approved_equipment_purchase_ui_enabled；只在完整九種 canonical server Equipment offer 存在，且全部三鍵 ON 才 true。登入 /api/auth/me 的 g019_equipment_actions_ui_enabled 同時綁三個 server flags。瀏覽器不能經 URL query、localStorage 或加上 synthetic ID 寫入持有權。

原 Shop 的 G009 固定瀏覽預設保留，G019 只允許「九項伺服器權威裝備 offer」的 exact ID、正整數價格、各一個正式 owner 狀態在原商品面板打開購買；其他 R1 consumables、PetFood、Gacha、外觀和未准入 P022/P038 仍舊不可購買。原可重送 purchase_operation_id、原 server-authoritative 扣 Coins/庫存/ownership 路徑不改。原 Backpack 一般介面則只在 /api/auth/me 驗證後顯示原本存在但被 G009 視覺鎖隱藏的 Equip/Unequip 按鈕；所有 canonical_equippable 權威和實際 POST /api/player/inventory/equip 不變。

## 本階段全新原始執行結果
1. 真 native PostgreSQL fresh synthetic player，原版 /shop 和原版 /inventory 的 Chrome（非以 G010 M3 記憶體改寫的 HTML）端到端：先驗證正常 OFF 與 409，僅測試程序開三個旗標；正式九件 offer 完整確認，原 Shop 購買 Wooden Sword 300 coins，900→600 coins，只有一筆 POST /api/shop/buy、一筆持有紀錄、一筆 durable debit，原 Shop 跳轉背包連結正確；原 Backpack 真 POST /api/player/inventory/equip 一次，另簽 Flask Session 確認同一人裝備與 Coins 持久化，瀏覽器 JS／API errors 0。NEW 1 PASS／0 FAIL。原始收據在 beatles：D:\go-odyssey-g010-3d-activation-evidence-20261021\G019_SHIPPED_SHOP_BACKPACK_REAL_PG_20261021.json。
2. 另外新的合成 PG user 與 Chrome 預設關閉測試：四組 server flag 組合（全關／backend 兩鍵 ON 但 UI release OFF／UI release ON 但 Loadout OFF／UI release ON 但 CoinShop OFF）皆證實原 Shop 沒有任何可見可按的購買按鈕、原 Backpack Equip 仍隱藏關閉、0 client write、0 JS error。NEW 1 PASS／0 FAIL。原始收據：D:\go-odyssey-g010-3d-activation-evidence-20261021\G019_4_DEFAULT_OFF_REAL_ORIGINAL_UI_20261021.json。
3. 六組 Shop／背包／G009 視覺契約／Loadout 原測試 62 PASS／0 FAIL。唯一舊測試對「購買入口永遠只有 G009」的字串假設已在 test_shop_c_ui_honesty_launch_ux.py 更新為明確 G019 server approved Equipment exception；原其他 Shop 入口仍必須完全 default OFF，不削弱後端權威。

## 未完成與 Owner Gate
這是一個確切完成的「原 Product 正常商城、背包受控操作」技術階段；不是整個遊戲已正式 Release。原 Nine gameplay Equipment 不能以此宣稱舊 D007 NOT_CLEARED 的 3D 模型可發布；P022/P038 及 Formal9 先前資產的 legal release gate 不動、no SKU promotion。還需 Curriculum／Tavern／Quest／整個玩家流程、Owner 實體 iPad Safari UAT、正式來源治理、部署前 backup rollback、完整 Product candidate Build／安全審核。沒有 GO_MERGE（GitHub master 合併）、沒有 GO_DEPLOY（Oracle godokoro.com 部署）、沒有正式玩家資料寫入，這三項都不能由「繼續」推定授權。
