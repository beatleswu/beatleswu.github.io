# Go Odyssey｜G MASTER — P2 真實領主試煉 20 題 → 首通獎勵 → 第二區解鎖 → 重登入 E2E

日期：2026-10-19
來源基準：本機 Product candidate `candidate/go-product-integrated-20261019`，起點 SHA `817923d6a66ea0cf7f9c69038b5d1c3b8fe44980`。
範圍：僅 beatles 上新建一次性 Native PostgreSQL、隔離使用者／題庫、原始 Flask＋原版 index.html＋WGo＋伺服器授權；無 GitHub Push、無 Master Merge、無 Oracle Build／Deploy。

## 完成結論

**真正 20 題領主試煉與重賽防重發全流程 PASS。** 這次並非只跑 Boss endpoint，也不是改題數、硬造 review_log／伺服器結果、改寫 HOLD 或在瀏覽器攔截答題 API。所有通關與獎勵仍由原本 Product 授權程式及其資料庫交易負責。

1. 題目使用已存在的 `tests/fixtures/lord_trial_natural/questions.json`（30 題有效、可由 Lord judge 審核的合成 SGF），僅在一次性測試資料庫寫入可辨識的**合成身份登記收據**，不觸碰正式 Learning Core／SGF。
2. 新玩家首次執行 `POST /api/adventure/boss/start` 被正式 30% 覆蓋門檻拒絕；接著真 `/api/srs/practice/attempt` + `/api/srs/practice/answer` 完成 10 題伺服器判定 CORRECT 才允許開始。
3. 伺服器產生真簽發 Session 的 20 題亂序試煉，門檻為 **16／20**；答題前以 POST `/api/adventure/boss/finish` 宣稱 20／20 仍被拒絕 `incomplete_attempt`。
4. 真正依 Session qid 排序答題 20 次至 `/api/srs/review`，每題 `boss_answer.moves` 由原生 SGF 判題，不接受自己聲稱的 grade／correction／score 替代；伺服器反查 20 答對證據。
5. 通關 `/api/adventure/boss/finish` 返回 PASS，正式首通贈品是**棋具布包**（`item_id=back_pack`），依 F028 寫入 `player_wardrobe` 且只一筆；獎勵無 fallback 假金幣。
6. 經 Zone-star 獨立寫入，一區 `k26_30` 首星 1 顆，第二區 `k21_25` 的 `adventure_zone_unlocks` 正式落庫；`first_clear_projection.status=COMPLETED`、`converged=true`，不可以只看舊版 `stars` 但忽略投影未完成的 `PENDING`。
7. 新建真正 Flask Test Client Session（同一個隔離登入使用者，新的 Cookie），重查 Bootstrap，第一區 cleared 與第二區 unlocked 保留。
8. 新 Session 又開啟 20 題**完整重賽**，後端正式識別 `attempt_mode=replay`，仍 20／20 但 `reward.first_clear=false`、`entitlement_consumed=false`，`player_wardrobe`、Zone-star、下一區 unlock 的**行級主鍵及數量均不變**；Boss attempts 正確從 1 → 2；第三個新 Session 再次查詢仍正確。

## 原版玩家畫面驗收

- 桌面 Chrome：從世界地圖 `#e9-world-stage-primary-cta` 實際點「領主挑戰」→ 播放原版領主動畫 → 玩家可見的開始挑戰按鈕 → 原版 `index.html` 的 WGo 棋盤，用真正的滑鼠落子連續解出 **20／20 題**，每一題由原本 `submitSRS()` → `/api/srs/review` 送出，遊戲按原邏輯自動切下一題，最後**自行**呼叫真 `/api/adventure/boss/finish`。後端與資料庫確認：首通獎勵一筆、下一關可進入。
- Chrome 平板觸控模擬：同樣 20／20 真實 WGo 觸控 tap，一般玩家可見 CTA 與完整結算 PASS。這是**Chrome 觸控模擬，不是實際 iPad Safari**。
- 沒有 Playwright `page.route`、沒有手動呼叫 `submitSRS`、沒有偽造 Session 中的領主 Attempt，也沒有人工填入 review_log 或替遊戲呼叫最後 Boss finish。
- E9 World Stage 面板使用 `bossAvailable`（從伺服器 `boss_ready` 投影而來）表示可挑戰；舊測試開始曾錯把 E9 的 `boss_ready` 當欄位，後改為觀察正確 UI 權威，產品程式無修改。自動切題時須等待 WGo `currentNode.children` 已就緒，不能只觀察 `_bossIndex` 增加就立刻點下一個空棋盤。

## 獨立遷移與安全邊界

- `app.init_db()` 不自動套用 `migrations/adventure_zone_star_progression_v1.py`。第一次隔離測試曾達成 Boss core first clear，但 Zone-star 因缺表轉為 PENDING，這**不是完整解鎖的合格狀態**。本輪測試 fixture 明確在一次性 PG 套用既有受控 `upgrade_zone_star` 後，獲得真正 `COMPLETED` 收據與物理落庫。
- 瀏覽器測試 fixture 也只在**隔離 PG** 裝入 B023 `companion_operations_v1`／`spirit_evolution_events_v1`，避免新玩家棋靈被正確 503 拒絕。沒有更改正式部署遷移政策，**上線前正式 Schema 必須獨立 preflight 核對**。
- 合成 PuzzleIdentity genesis 只註冊此 30 題已存在的合成題庫，符合正式 Practice v1 的身分檢查，沒有模擬正式來源簽章。
- 測試用 `CACHE_DB` 指向 pytest 一次性資料夾，避免原本 `/api/explain` 的相對 SQLite 快取殘留於 Product repo；任何漏出的測試快取不列入候選或 Commit。
- 本輪產品 `app.py`、`index.html`、`hero.html`、SRS／Lord 判題、獎勵與安全 Gate 均**不需修改**；新增的是可重跑的真玩家 E2E。

## 測試與證據

- `tests/test_20261019_lord_full_journey_native_pg.py`：共 **3／3 PASS**：正式後端 20 答題＋重賽＋新 Session、桌面玩家 WGo 20 題、Chrome 平板觸控 20 題。
- `tests/e2e/run_20261019_real_lord_20_wgo_browser.mjs`：真畫面 Playwright runner，每次從 Session 取真 Question、計算 WGo 交叉落點、等待伺服器回覆與畫面自動下一題、最後只讀驗證地圖結算。
- `docs/handoffs/GO_ODYSSEY_P2_REAL_LORD_20_PLAYER_AND_PG_20261019.xml`：實際 3 passed、0 failed、0 skipped JUnit 收據。
- `docs/handoffs/GO_ODYSSEY_P2_LORD_REGRESSION_20261019.xml`：領主、首通獎勵、限額、判題安全、拒絕偽造、持久化等相鄰回歸實際 **257 PASS、10 SKIP、0 FAIL**（共 267 件）。
- `docs/handoffs/GO_ODYSSEY_P2_REAL_LORD_20_PLAYER_AND_PG_R2_20261019.xml` 為 **1 FAIL、2 PASS** 的診斷收據。唯一失敗是 JS 在 PostgreSQL 首通已提交、但 Chrome 尚未收到 `/api/adventure/boss/finish` 回應時，先檢查 `bossFinishes` 陣列；HTTP 最終仍回 200，非權威結算或獎勵缺陷。保留 R2 供查核，不宣稱其通過。
- 修正非產品的 E2E runner：第 20 次真實 WGo 落子前先訂閱 `/api/adventure/boss/finish` 回應，明確 await 200 與 `passed=true`、`correct=20`、`total=20`、`first_clear_projection.status=COMPLETED`、`back_pack` 真正授權，再獨立向 DB 核查物理通關與解鎖。沒有跳過結算或直接呼叫 Boss finish。
- `docs/handoffs/GO_ODYSSEY_P2_REAL_LORD_20_PLAYER_AND_PG_R3_20261019.xml`：在獨立 KataGo 快取路徑與上述真實 HTTP 回應同步後，最終 **3 PASS、0 FAIL、0 SKIP**，同時確認 Product 根目錄沒有殘留 `katago_cache.db`。

## 接續與 Owner Gate

- Product **候選**的「領主 20 題 → 首通獎勵 → 下一關解鎖 → 重登入」已驗證；但**尚未驗證**真實正式站 Test02 與實體 iPad Safari，因此不得聲稱正式玩家 UAT／正式發布完成。
- 正式資料庫須只讀檢查 `adventure_zone_star_progression_v1`、`companion_operations_v1`、`spirit_evolution_events_v1`、首通收據及出貨來源治理，再經明確 Owner 批准受控遷移、正式來源採納、Build／必要 Docker 測試、回滾預演後才可能正式部署。
- 正式站 `godokoro.com`、GitHub `master` 不變；本輪不觸發 Push／GO_MERGE／GO_DEPLOY。V4 自主 Goal Loop 仍 **NO_GO**。

### A–F 狀態

A 棋靈選取／遷移候選 PASS，正式 Schema 待驗。
B 原版 WGo 連續 20 題＋後端 XP 等級既有通路 PASS，真 iPad 待驗。
C 領主 Session、拒絕偽造、首通一次性獎勵／重賽去重 PASS。
D Boss 首通、第一星、下一區解鎖、新 Session 保留 PASS。
E 月榜／排行榜與正式 Test02 重新登入待驗，未動。
F 商店／背包候選不變，Build／Docker／回滾／正式部署未授權。
