# G020｜同一玩家跨全部主要遊戲系統：原 Product 頁面真 PG/Chrome 階段驗收

日期：2026-10-21。Owner 原定方向：優先實際可玩 Go Odyssey 主要流程及接近 godokoro.com 上線，不再重複 3D Gallery／尚未准入素材測試。階段獨立於 V4 自主執行架構。**G020 是隔離候選的 Product 一名玩家跨頁／跨獎勵 E2E，不是已經正式部署或全站上線驗收。**

## 接續與差異
- 直接沿用已獨立 Commit 且來源 OCI 核實的 G019 正式原網頁 Shop/Backpack 三重伺服器權威（source Commit 15cbcdbe9c28b8f16107387e45cddb7c087f9627；docs-only 60f494286560a1767ed6e0a8bfba34904e43335b）。
- G010 M5 歷史跑過真正玩家完整流程，**但是在原 Shop／Backpack 加上 loopback memory HTML override**。G020 把這個唯一殘留區別徹底排除，使用現行 committed app.py、shop.html、inventory.html、curriculum、community、hero 原正式路由，完全沒有 WSGI 原 HTML 替代、沒有模擬 API 寫入。
- 不重寫題目、獎勵、商城持有權、角色 3D、任務商店等已有實作；只新建 G020 跨路真測試與直接使用既有 G019 原頁入口。

## 真實可重現執行
主測試 tests/test_g020_original_product_one_player_full_journey_pg.py；單一 dispose-on-test-end 的本機 PostgreSQL fixture native DB 裡建立同一個非正式玩家 user_id 716020。parametrize 兩個**互相獨立新建 PG fixture、同一流程**的 UI 模式（desktop_mouse、chrome_tablet_touch），不是不同時間同一個資料庫。新 Node browsers：
- tests/e2e/g020_original_tavern_quest_ranking_browser.mjs：原 Tavern 頁真正領 Quest V2 獎勵與 server alltime leaderboard 寫回，跨第二 Flask signed Session 恢復，固定不重複。
- tests/e2e/g019_shipped_shop_backpack_purchase_equip_relogin.mjs（原 G019 已驗證）：原 Shop 的九種 canonical Equipment 中，木劍 300 Coins 真交易一次，再從原真連結到原 Backpack，真穿戴，再新 Session readback；原 G009 預設 browse latch 仍 true、沒有 memory HTML 代換。
- tests/e2e/g020_original_player_pages_readback_browser.mjs：真 Chrome 原 /curriculum（Quest Board & /api/curriculum/summary）、原 /community（Tavern 4 Tabs + leaderboard）、原 /hero?tab=equipment（G008 原 WebGL Canvas 及真伺服器 equipped Row，禁止 unadmitted G015/G018 QA 模組）、原 /inventory、後端 XP/Shop Coins，以及**另一個獨立簽署 Session**的 Curriculum/Tavern/Inventory/Coins/XP 讀回；每輪48項瀏覽器斷言，**無多餘 POST**。Desktop 真 Chrome 不是 Safari，touch 模擬也不代表 iPad 實機。

角色／遊戲流程：新玩家 Zone1 Lord 20 次真 SRS 判題並 first clear／Zone2 解鎖；Zone2 合成題庫 20 次由 server 逐題評分、怪物擊敗 Outbox 一次；Quest V2 daily:streak_correct 一次真正 claim，+20 XP/+15 Coins，重試不重複；原 Shop 1000+15=1015 Coins → 木劍扣300 → 715 Coins，購買 operation 與 currency log 正好一筆；原 Backpack 真 Equip 一筆；另有先前已合成持有的 xp_potion 直接經 authenticated /api/shop/use 使用，不假稱商城曾販售；Zone2 Lord 20 次真 SRS 判題／first star 持久化／Zone3 unlocked，結果與同一玩家 lifelong XP／leaderboard／原 Hero 背包真資料一致。合計**60 次真判題**，兩輪各自實證。

兩輪真 Browser 收據位於 beatles：
D:\go-odyssey-g010-3d-activation-evidence-20261021\G020_SINGLE_PLAYER_ALL6_REAL_PRODUCT_SURFACES_20261021.json
D:\go-odyssey-g010-3d-activation-evidence-20261021\G020_SINGLE_PLAYER_ALL6_REAL_PRODUCT_SURFACES_TOUCH_20261021.json
各有三次 Chrome 腳本結果、48 個逐項跨頁檢查名稱、遊戲源初始 XP207→227、Coins1015→715、Hero 原 canvas 286px 與 equipped wooden_sword、No QA model、獨立 signed Session、一致的 server ranking、0 JS／HTTP500／非預期寫入。

本輪權限／來源回歸：tests/test_g020_one_player_journey_contract.py，加原 G018 asset rights、G017 source rights、G009/C053 Shop and server loadout contract 共 **63 PASS／0 FAIL**。新雙模式主整合測試 **2 PASS／0 FAIL**（來源最後執行時需核對實測 process exit）。

## 品質與正式不滿足項
- 真 PostgreSQL + 來源程式執行，並非已經在 Oracle 或 Docker image 對外網域執行全部授權流程。G019 的本機 source-matched OCI 已驗證264 blobs、7 shipped source files、Docker load、no-network readonly Python smoke；**G020 沒改 Product runtime source，因此不會假裝另造新的正式 Build/部署**。G020 不得將 G019 offline smoke 當成全站 Image+PG 的 E2E 已認證。
- 本測試只在現行範圍 Zone1／Zone2／Zone3 unlock 的合成題庫證明玩家主要路徑；不是所有10區或所有正式題庫/裝備動作完成，Quest Board 為實際 API/原頁讀回但沒有此輪 30 題 commission 再領獎；該功能此前在獨立 sandbox R3 有歷史 E2E。不得偷換「已完整發售」。
- 原 Canonical CoinShop、Loadout、新 G019 裝備介面 Release 三鍵全部 default OFF，測試中只用 monkeypatch；P022/P038/D007 old 模型或 Formal9 仍未獲正式 Product 3D legal Release Admission。原 nine gameplay SKU 的購買成功不代表未准入舊 GLB 可以上架。
- No formal Github master GO_MERGE; No Oracle godokoro.com GO_DEPLOY; No production player data writes. Owner 實體 iPad Safari UAT、正式題庫內容來源權限、正式設備／法務/備份 rollback/Database 遷移與實際 Oracle 回歸屬另外上線必要程序。

下一技術階段應以 G019 已經被真正 build／驗 SHA 的 OCI 啟動一個**新隔離 PostgreSQL Container**，對容器內完整 Product 再作可回滾 smoke/安全測試；若通過並完成 Owner 審核，再依明確獨立 GO_MERGE、GO_DEPLOY 決策進入正式網域。此項 G020 尚未認定完成。
