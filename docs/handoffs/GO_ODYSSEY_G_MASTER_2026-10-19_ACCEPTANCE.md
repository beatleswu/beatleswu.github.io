# Go Odyssey G MASTER — 2026-10-19 第一階段整合候選交付

> 產出日期：2026-10-19（台灣時間）；性質：本機六路整合候選／非正式站驗收／非部署授權

## 1. 基準與真實環境

- 正式網站：https://godokoro.com
- Oracle 實查：`go-odyssey-app`、`go-odyssey-scheduler` 仍執行 `go-odyssey-app:69dbe57a`；主容器 healthy。PostgreSQL、Nginx 正常。
- 交接正式來源 commit：`69dbe57aa535112b1759e3f3bdcf9ecbe1680efb`。
- GitHub `beatleswu/beatleswu.github.io` 的 `master` 實查為 `0f14f95c4fd9f70fcbdaa929b8fed3a4a9316463`，不等同 Oracle 正式容器來源。
- 保留月榜原始本機候選：`feature/monthly-leaderboard-rewards-20261018` @ `00e9120d3cab59d88bd0fe1f2aaafb74bad15412`。未推送遠端、未合併 master。
- 六路基底一律 `00e9120`，本機獨立工作樹 `D:\go-odyssey-sixroute-20261019\a` 至 `f`；總控整合 `D:\go-odyssey-sixroute-20261019\g`。
- G 整合程式碼 HEAD（交付報告 Commit 前）：`2b60bfe021a5633837f991044317d4e8042cb776`，14 個相對 `00e9120` 的新增／修改檔案，工作樹無未提交修改。

## 2. 六路實際成果與寫入權

| 路 | 原始路線 Commit | 僅寫入檔案 | 成果 |
|---|---|---|---|
| A | `9f328948eb740e89c70c0273e3612a7bb2d81fb5` | `hero.html`, `tests/e2e/run_20261019_companion_ui.mjs` | 餵食 single-flight、防連點、操作 ID、戰鬥棋靈 ID、飽食滿文案 |
| B | `641be4f3d53caf81e797beae10fca0154658cdb5` | `js/g009_hero_hub_batch_a.js`, `tests/test_20261019_hero_level_presentation.py` | 玩家等級與圍棋棋力區分；功能裝備／純外觀辨別 |
| C | `858429fd6cfeda4f7e029d1bb00711ab310cad65` | `curriculum.html`, `tests/test_20261019_quest_progress_ui.py` | 已練習不等於精通；30–50 題每十題里程碑 |
| D | `0fe725576a6a430c48a95d5b94345d1f68dca32f` | `js/e9/world_stage.js`, `components/adventure/world_stage.html`, `css/e9/reference_world_map.css`, `tests/test_20261019_map_unlock_ui.py` | 已通關與三星分離，權威狀態導向繼續冒險 |
| E | `aef7549559c74899be6963b12a5cb2000210602d` | `tests/test_20261019_monthly_postgres.py` | 保留既有 9 檔月榜獎勵實作，新增可拋棄 PostgreSQL 真實結算測試 |
| F | `4921af3c50542d67dc38a56f58d43e392c154f46` | `shop.html`, `inventory.html`, `tests/test_20261019_shop_nav_ui.py` | 食物目前不可購買正確提示；背包直達角色、棋靈、榮譽 |

以上六路 Commit 已依序 Cherry-pick 到 `candidate/go-product-integrated-20261019`，整合無衝突；G 內的 SHA 會與原路線 SHA 不同。

## 3. 重新執行的驗證與限制

- 最終 G 合併 HEAD `2b60bfe`：`python -m pytest -q -p no:cacheprovider` 指定六路測試、新舊月榜、棋靈等測試：**134 passed, 2 skipped, 6 deselected**，exit 0。
- 最終 G：`node --test tests/e2e/run_20261019_companion_ui.mjs`：**12 passed**；D037 既有 Node 切換測試：**10 passed**。
- `git diff --check 00e9120 HEAD` exit 0；合併工作樹乾淨。
- E 路的真實本機 PostgreSQL（17.10）測試包含首次 2026-11-01 00:10（Asia/Taipei）、當月至少 150 道不同正確題、前 50 名與同分較早達標、Test 帳號不排除、金幣／碎片／徽章／稱號／通知、碎片使用、重新執行冪等、發獎失敗整期回滾後可重試，以及週榜不受影響。E 測試合計 **89 passed、6 deselected**（5 項新 PostgreSQL 測試通過）。
- 合成資料演練不代表正式玩家資料；本機 PostgreSQL 17 與正式 PostgreSQL 16 仍存在環境差異。
- F 路包含 4 項合成 API Chromium runtime 測試、手機／桌面寬度檢查；不能代替正式站登入端到端驗收。
- 尚未取得 6 項既有 Docker 專項測試結果；不得將其標示 PASS。

## 4. 29 項清單：候選修正 vs 未結案

**A 棋靈**
- C01 P1 切換沒變化：正式站實際前端事件／API／持久化尚未驗證；既有獨立切換測試 PASS。
- C02 P1 拍拍沒有親密度或 XP：未修；需要正式站事件、冷卻與資料核對。
- C03 P1 餵食未觸發：候選 UI 已加護欄，正式站尚未部署及實測。
- C04 P2 餵食防連點：**候選完成，12 項行為測試通過**。
- C05 P2 飽食滿效果說明：**候選完成**（仍可消耗食物、XP／親密度受到伺服器規則限制）。
- C06 P1 棋靈解鎖條件：尚未統一完整條件及文案。

**B 主角**
- H01 P1 玩家／英雄／棋力顯示：**候選完成所屬角色頁標示**；跨全部介面 LV44／LV30 核對未結。
- H02 P1 升級屬性、血量、技能、外觀呈現：未結。
- H03 P1 潛能點 3／0 的正式規則：待核對，未任意變更。
- H04 P2 功能裝備 vs 外觀：**候選完成部分呈現**；正式 UI 待驗。
- H05 P1 棋靈戰鬥技能：未結。

**C 任務**
- Q01 P1 已練習 vs 已精通：**候選完成**，不虛構精通演算法。
- Q02 P1 初學者每日任務可完成性：待驗；正式站 Quest V2 關閉。
- Q03 P2 長委託中途進度：**候選完成**。
- Q04 P2 獎勵集中回饋：待整合。
- Q05 P2 完成後推薦下一步：未完整結案。

**D 冒險**
- A01 P1 迷霧區具體條件：未結。
- A02 P1 通關 vs 三星：**候選完成**。
- A03 P1 Goblin Cave 星級訓練入口：未結。
- A04 P2 繼續冒險入口：**候選完成**；實機仍待 UAT。
- Go／Stay 疑似導向問題：回歸查證，未確認有 Bug。

**E 排行榜**
- R01 P1 段位榜 XP 與棋力混淆：未結。
- R02 P1 舊版及社群月榜來源與計分說明：未結。
- R03 P1 月榜獎勵：**既有候選保留 + PostgreSQL 演練 PASS**，正式整合發布尚未授權。
- R04 P1 碎片使用：**本機 DB／API 演練 PASS**，正式頁面兌換待驗。
- R05 P2 同分先達標：**測試已覆蓋**，玩家文案待改善。
- R06 P2 個人名次與下一名差距：未結。

**F 商店**
- S01 P1 Coming Soon vs 食物取得：**候選完成**。
- S02 P2 獎勵後快速導覽：**候選完成背包入口**；其他頁面尚待一致性確認。
- S03 P1 功能旗標對應正式站實際可用性：部分文案完成，正式站全面盤點未結。

## 5. 六項正式站端到端驗收：仍未結案

1. Test02 出戰棋靈切換、餵食、拍拍、冷卻、重新登入與持久化（未驗證正式部署候選）。
2. 正確解題 → XP／金幣 → 主角成長 → 冒險進度（未完整跨系統測試）。
3. 任務重複請求、刷新與重試防重複（未完整正式站 E2E）。
4. 月榜結算 → 金幣、碎片、徽章、稱號 → 通知及重新登入（**本機真 PG 演練過，正式站待驗**）。
5. 登入 Test02 與顯示暱稱 Test 的身份對應（待證實）。
6. 真實 iPad 地圖、棋盤落子及觸控；A010 Owner Real iPad Map UAT 仍為 Pending。

## 6. 發布門檻與下一步

- 狀態：**六路可整合候選完成；非 production-ready／非正式 E2E acceptance**。
- 尚未推送 GitHub，未正式合併，未 Build 正式發布映像，未變更 Oracle 正式站，未存取或修改其他玩家帳號。
- 正式 Release 必須重新核對 GitHub 與 Oracle 來源、完成受信任來源與簽章驗證、指定 PowerShell/Docker 測試矩陣、資料庫 migration 及發獎交易／回滾、靜態資產、必要的真實帳號／iPad UAT，再取得 Owner GO_MERGE／GO_DEPLOY 授權；任一門檻失敗即停止。
- 不混入 V4/R15 Supervisor 自動開發工程。
- 優先處理剩餘 P1：正式棋靈互動與 Test02 身份、主角升級與戰鬥技能、初心者任務、霧區解鎖及 Goblin Cave、榜單定位與獎勵顯示，再進入 Build／正式站驗收。
