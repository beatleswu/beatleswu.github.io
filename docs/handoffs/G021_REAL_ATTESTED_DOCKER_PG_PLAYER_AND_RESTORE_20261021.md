# G021｜已驗 SHA 的 Docker 實體容器＋全新 PostgreSQL＋Chrome 遊戲流程／備份還原

日期：2026-10-21（beatles，僅隔離 QA）。階段驗收 **G021 技術 PASS**；Godokoro 正式 Release/Oracle Deployment **NO-GO**。

## 真正改變的驗收層級

G020 已用真 Chrome、一次性 *原生 PostgreSQL fixture* 跑過同一玩家遊戲流程，但不能代表實際 OCI。G021 不修改產品原碼，直接使用 G019 經獨立 BuildKit 建出、264 個 OCI blob 和七個正式 runtime 檔案 SHA 一致、已真正 docker load 的不可變映像：

- **Image ID**：sha256:eb169da6075c5e473108b6e43d27966c3c4017e378da8a92644aba3986db49b4
- **實際 Product 源 SHA**：15cbcdbe9c28b8f16107387e45cddb7c087f9627
- 本機 tag：go-odyssey:g019-15cbcdb-verified-local；未 push、未 merge master／Oracle deploy。
- 現有保護 Product 21a2c84a、RC3 fce7c05a 不改。
- **新 Docker Compose 完全隔離**：go-odyssey-g021-isolated-e2e-20261021。全新 PostgreSQL16、專屬 g021-private-pg 和 g021-private-app Volume，新私人 network，app 只綁 **127.0.0.1:5097**、PostgreSQL **沒有任何對主機公開的埠**。以既有測試問卷唯讀掛載和受保護來源 assets 唯讀掛載運作。不同的 A1 和 R3 舊容器均保持健康，沒動它們任何 DB/Volumes。GO_ODYSSEY_ACCEPTANCE_MODE=1、PRODUCTION=0、發佈關閉、映像與接受來源 SHA 綁定，付款均 TEST。所有真正玩家資料未讀／寫。

## 首次乾淨資料庫啟動的真實阻擋及排除

第一次在**全空 PostgreSQL**開啟 G019 app 時確實 FAIL：啟動自我驗證拋出 `migrations.sgf_admin_workbench_v1.SchemaMismatch`，缺少七張工作台資料表：sgf_workbench_reports、sgf_workbench_review_items、sgf_workbench_staged_repairs、sgf_workbench_batches、sgf_workbench_batch_items、sgf_workbench_audit、sgf_workbench_direct_versions。不是跳過測試或把初始化失敗誤報健康。

在新 G021 資料庫、app container 尚未成功啟動前，以**映像內現有受治理 Migration**（不是任意重新建表）執行：

`docker compose --env-file [既有隔離測試憑證檔] -f compose.yml run --rm --no-deps --entrypoint python app -m migrations.sgf_admin_workbench_v1 --apply`

輸出 created 七張、missing 0、valid true。後續真正使用相同已驗證原 OCI app image 啟動、DB/app 各 healthy；程式來源 SHA 無改。G021 對此訂明：**正式全新資料庫建置前必須先執行受治理 Migration 並驗證，否則上線阻擋會重現**。這個步驟是 staging 完成，不等於已在 Oracle 正式執行 migration。

G021 機器來源鑑證另驗證：運行中的 app 容器 Image ID == 既有 G019 SHA、來源/acceptance SHA 一致、正確 loopback 和獨立 Volume、無 DB host port，來源 `migrations/sgf_admin_workbench_v1.py` 在映像與 Git 的 SHA256 完全相同（a8f099808fcdc29ca3542160e78125abdb9c1600d53cd2f79d94b4d8d549e0c5）。Stage machine receipt：`G021_HEALTHY_ATTESTED_IMAGE_AFTER_ROLLBACK_20261021.json`。

## 新 Docker 映像真正可玩：同一名全新合成玩家

以專用 read-only 問卷資料 57 題、PG player_id=1、預設 1000Coins/0XP 執行（全部是實體 G019 container）：

1. **全站實際 Chrome 冒煙**：新 synthetic login、原 /curriculum/Quest Board、原 Tavern 四 Tabs、Hero、Backpack、Shop，以及 server source identity、XP、Coins/Quest 讀回，**39 PASS，0 JS/500、0 非預期寫入**；當時三個功能／商店 UI 旗標全 OFF。
2. **實際 WGo 棋盤三次動作**：原地圖畫布桌面滑鼠一次、Chrome 模擬平板觸控兩次；三筆不重複的 `POST /api/adventure/map-battles/v1/answers` 全 status 200、server CORRECT、PG progression applied。source question IDs 970001／970002／970003；XP 0→6→12→21，認證獨立 Session 讀回。
3. **真 Tavern Quest V2 領獎**：在原 Community 頁真的點 Claim `daily:streak_correct`，**一個** POST，XP21→41、Coins1000→1015、alltime leaderboard41，第二個 signed Session 維持一致（24項 stage assertions）。再提交**三次不同 nonce 重複請領**均 duplicate true，XP41/Coins1015 和週／月／終生排行榜維持不變（22個斷言）。
4. **原 Curriculum 學習委託**：真點 Quest Board 接受一次 `life_death::LV1::1-30`，server Accepted 及獨立 Session 讀回，**沒有誤發未完成的 30 題佣金**，XP／Coins 不增加（15個斷言）。
5. 僅在**這個隔離 Compose app**使用第二份 QA override，開原 `CANONICAL_COIN_SHOP_PURCHASE_ENABLED`、`EQUIPMENT_CANONICAL_LOADOUT_ENABLED`、`G019_APPROVED_EQUIPMENT_SHOP_UI_ENABLED`；映像程式與 PG Volume 保持完全相同。實際重新建立 G019 app container 後，同一 PG 合成玩家使用原 Shop（非 mock HTML）以 300 Coins 購買伺服器正式列出的 Wooden Sword，只有一次 durable `POST /api/shop/buy`，原 Backpack 按鈕再唯一 `POST /api/player/inventory/equip`，Coins1015→715。獨立登入 Session 於原 Hero 真 G008 WebGL、Curriculum、Quest Board、Tavern、Shop、Backpack 讀得 **41 XP、715 Coins、任務已請領、學習委託已接受、木劍真 equipped**。**30 個真正 Docker image／Chrome／PG 斷言 PASS，0 page JS errors**；未准入 G015/G018 私有 QA 模型沒有出現。

以上和 G020 完全不同：此次 HTTP 是已用 `docker load` 真正啟動的 attested OCI image，PostgreSQL 是真正在不同 Docker DB 容器內運作，所有 Action 由真 authenticated Flask server 判斷；沒有模擬 API 或覆寫正式 HTML。QA browser script 的源碼仍留在新隔離 workspace，未進 Docker image，沒有在原 Product 提交源碼改動。

## 備份驗證、資料還原與功能回退

- 已使用真正 PostgreSQL16 `pg_dump -Fc` 在 G021 資料庫做一致性備份，copy 至 **僅 beatles 本機隔離工作區** `D:\go-odyssey-g021-container-e2e-20261021\g021-synthetic-stage-backup.dump`，**347,708 bytes、SHA256 c61d6f25089f2584a99945447da67384cd9aa85b11544842260f64e9204fba62**。它包含測試帳號的密碼雜湊，因此**只存本機，嚴禁入 Git、ZIP 或對外傳輸**。
- 同一隔離 DB Container 中另外建立 **go_odyssey_g021_restore_qa** 空資料庫，經真 `pg_restore --exit-on-error` 完整還原，exit0；重新查詢「Coins/XP 715|41、使用者1、領獎1、購買1、穿戴木劍1、Workbench tables7」等**六個完整資料庫快照欄位，與來源資料庫逐項相同**，PASS。收據 `G021_RESTORED_BACKUP_INTEGRITY_20261021.json`。
- 已撤除 QA enable override，以**不加 override 的原 Compose**重建同一 G019 App Container，Postgres Volume 不動、app + db 再度 healthy。三個 Shop／Equip／G019 UI 旗標實際均返回 false，正常原 Shop 無可按購買、原 Backpack 裝備操作隱藏，取消權限後用 POST 直接購買真 HTTP409，無扣款。重新登入的另一 signed Session 仍讀得 XP41、Coins715、木劍已裝備、Tavern alltime41、每日任務已請領及學習委託已接取。**24 項實際 Chrome/Flask 預設關閉／持久化斷言 PASS**，收據 `G021_FLAG_ROLLBACK_LIVE_PG_PERSISTENCE_20261021.json`。
- 這裡完成的是**資料庫備份與獨立 DB 還原演練＋同 image 的功能旗標回退**，而**不是正式 Oracle 主機上一個前版 image 的回滾演練或正式 players DB 災難復原**。正式上線仍必須另外驗收。

## 驗收邊界與下一階段

G021 技術 PASS：**真可信 BuildKit OCI Source／實際 Docker app／全新 PG16／真 Chrome 原頁面跨路遊玩、G019 default-OFF/ON/再次 OFF、PG 備份與分離 DB 還原**。但 **NO GO_DEPLOY、NO GO_MERGE**：未准入 P022/P038/D007/Formal9 3D 正式法律審核未完成；目前只測試 Stage synthetic question content/Zone k26_30、未完成正式10區全部內容、Owner 實體 iPad Safari UAT、Oracle 伺服器現有資料備份／前版映像回滾、正式來源審核。不能將測試環境的私有資料（包括 stage.env 和 synthetic PG backup）部署或封存到 Git。

G021 隔離路徑 `D:\go-odyssey-g021-container-e2e-20261021`。新的 Product branch G020 Commit `a417f258a0d44b0cfa6b8cc412798c8e8b98faf8` 仍是**程式 runtime 未改**、可重新使用同 G019 source-matched OCI；本 G021 只有測試部署編排、來源證明與文件。所有 QA Compose 只綁 127.0.0.1:5097 和自己的兩個 Volume、三旗標已回 Default-OFF。

**下一階段（非自動啟動正式部署）**：在取得 Owner 的必要 GO_MERGE／GO_DEPLOY 前，完成正式 Release admission、實機 Safari、Oracle 正式備份與 Rollback 演練和來源准入；請保留新已驗證 G021 QA 正常 OFF 狀態，不要退回重建從零的 QA。
