# Go Odyssey｜G MASTER 真實冒險 WGo 答題 → XP／主角升級 → 地圖進度 E2E｜2026-10-19

## 範圍、起點與結論

- **起點本機候選**：`767d697ff3cc7e2ff2ce9fb3697171c9a16d5b2d`
- **結果**：隔離 PostgreSQL + 真實 Flask + 正式候選 `index.html` + 原版 WGo + 冒險 Map Battle V1 + 英雄殿 `hero.html` 的桌面 Chrome 與觸控模擬全程 PASS。
- 這次主要補上原先缺乏的**真正玩家路徑整合／瀏覽器驗收**，確認既有產品程式能完成該流程；**沒有為了測試成功而改寫產品的答題、判題、XP、冒險進度或安全門檻**。
- 所有資料使用當次一次性、local-only PostgreSQL，新建隔離帳號、新建合規 SGF 題目；**不是正式 Test02，也不是真正 iPad／Safari 操作**。

## 真實完整流程

1. Chrome 載入候選 `/?zone=k26_30&adventure=1&resume=1&lang=zh`，登入狀態使用本機 Flask 簽發的隔離使用者 Session。
2. 真正的原始 `index.html`、WGo 棋盤、Map Battle V1 載入，後端簽發 Attempt、Nonce、Battle State。
3. 若原始開場動畫蓋住棋盤，按玩家可見的「略過動畫」，依畫面按「開始修行」；**不直接改 DOM、取消 Gate 或呼叫產品內部答題函式**。
4. 用 Playwright 真正滑鼠點擊（或平板版觸控 tap）WGo 的 D4：WGo 觸控／滑鼠輸入 → 原始 Map Battle Adapter → Flask `POST /api/adventure/map-battles/v1/answers` → 伺服器判定 CORRECT → PostgreSQL 持久化。
5. **XP 119 → 134**、**LV1 → LV2**、等級內 XP **14／160**、新手村答對題數 **0 → 1**、已見題數 **0 → 1**；普通答題不得假冒領主通關。
6. 重新整理 `index.html`，後端 XP、Hero 與冒險結果保留。
7. 實際導向原版 `/hero?tab=character`，等待正式候選 `hero.html` 自行讀取 API，DOM 顯示 **LV2、14／160 XP、總計 134 XP、9%**。未人工呼叫顯示函式。

另以原有 Map Battle Adapter 在本機真實 HTTP／PG 上測試同一答案重送，伺服器標示 Duplicate，**review_log 仍為一筆且沒有第二次增加 XP**；新建 Flask Session 仍讀到相同升級與地圖狀態。

## 實際驗收

- `tests/test_20261019_adventure_answer_level_e2e.py`：**4／4 PASS**，含原生 Flask API 直接交叉比對、真實 Adapter Chrome 點擊測試、真實 `index.html` WGo 滑鼠 E2E、真實 `index.html` WGo Chrome 平板觸控模擬 E2E。**不是 iPad Safari**。
- Chrome 原版正式遊戲畫面：桌面與平板觸控模擬各 **8／8 UI／資料庫驗收 PASS**；真實 Adapter 測試頁 **5／5 PASS**。**兩組瀏覽器檢查均屬上述 4 個 pytest 案例，不應加總冒充更多獨立測試**。
- Map Battle、Adventure、XP、英雄、棋靈相關回歸 **135 PASS、2 SKIP、0 FAIL**。
- 先前 2 項失敗並非產品回歸：`tests/test_map_battle_legacy_adapter.py` 原期待舊 `SRS.review(currentQ.id,grade` 字串，現為 `SRS.review(publicCommand?.question_id ?? currentQ.id,grade` 並由 `ReviewTransport` 管理提交。已更新兩個靜態斷言並以 **43／43 PASS** 重新驗證，沒有變更產品答題分流。
- `git diff --check`、JavaScript 語法檢查另行執行。

證據：
- `docs/handoffs/GO_ODYSSEY_P1_REAL_WGO_ADVENTURE_20261019.xml`（完整 4 測試）
- `docs/handoffs/GO_ODYSSEY_P1_MAP_RUNTIME_FINAL_REGRESSION_R2_20261019.xml`（135 PASS／2 SKIP）
- 原始 Selenium/Playwright 與 server 對帳列印內容由 pytest 4 案例測試腳本提供，未留存登入 Cookie／Token。
- 最初 Map Battle 回歸 R1 有 2 個過期靜態斷言失敗，保留 R2 綠燈收據，但**不虛稱第一輪 R1 成功**。

## 本輪具體檔案

- 新增 `tests/test_20261019_adventure_answer_level_e2e.py`
- 新增 `tests/e2e/run_20261019_real_map_answer_browser.mjs`
- 新增 `tests/e2e/run_20261019_real_index_adventure_probe.mjs`（含真實玩家可見的開場故事跳過流程、真 WGo 觸控／滑鼠事件）
- 修正 `tests/test_map_battle_legacy_adapter.py` 的兩個過時靜態斷言
- 新增上述驗收 XML 和本交接
- **本輪無需修改** `app.py`、`index.html`、`hero.html` 或安全 Gate 來通過完整玩家流程。候選保留原有 `767d697` 的主角 XP 顯示修復。

## 尚未結案的觀察與 Owner Gate

- 隔離新玩家首頁載入時，`POST /api/pet/choose` 回 **503**（兩次）；`/api/pet/status` 可讀，冒險主鏈仍通過。**未查明該隔離環境缺失的具體 Companion operation schema/migration，不能據此判定正式站也有相同問題；絕不繞過 Companion Gate 使其假成功。** 列為獨立後續工作。
- 此次是 1 題普通冒險答題並升級，**不是**完整 20 題領主戰通關或 Boss first-clear 獎勵 E2E。
- 真實 iPad Safari 的實體觸控驗收、正式站 Test02 登入／月榜重新登入、來源准入／正式 Build／Docker 發布檢查／回滾演練仍待 Owner Gates。
- 正式 GitHub master、Oracle `godokoro.com` 不得受本輪本機測試或測試 Commit 影響；**禁止 Push、GO_MERGE、GO_DEPLOY**，直到 Owner 授權。
- V4 自主 Goal Loop 尚未通過新目標連續 Codex → Docker → Claude 的授權自主 E2E：保持 **NO_GO**。

### A–F 簡要進度
A 棋靈與 GLB 360 候選保留；隔離棋靈初次選取 503 待查，Test02 待驗。
B 玩家真正 WGo 作答 → XP、LV2 → Hero 畫面 **候選 E2E PASS**。
C 任務防重發已修，實際 Map Battle 重送驗證成功。
D 冒險地圖正確入帳進度，未誤通關 **候選 E2E PASS**；真正 iPad 待驗。
E 排行榜與月榜候選保留，正式 Test02 重新登入待驗。
F 商店／背包候選保留，正式來源准入與部署 Gate 未開始。
