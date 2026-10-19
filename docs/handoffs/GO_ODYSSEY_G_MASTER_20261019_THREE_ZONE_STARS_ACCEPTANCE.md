# Go Odyssey — G MASTER 三顆關卡星數實戰驗收｜2026-10-19

## Owner 明確規則（不准偏離）
第二顆星 = 該關卡**全部可用題目總數**為分母，取得至少 **60% 不同題目的正確覆蓋率**，使用 ceiling，不能用「已作答題目」或「領主試煉的 20 題」作分母。
第一顆 = 領主試煉正式首次通關；第三顆 = 同一關卡全部題目正確覆蓋率 100%。第二、第三顆都需既有第一顆；不可先刷 3 顆再打領主。
在 30 題隔離題庫中：18／30 取得第二顆，30／30 取得第三顆。正式題庫分母取自伺服器動態配置，**並非所有關卡固定 30 題**。

## 已執行證明
- 本機分支：`candidate/go-product-integrated-20261019`；開始自 `817923d6a66ea0cf7f9c69038b5d1c3b8fe44980`，合成一次性 Native PostgreSQL。
- `tests/test_20261019_three_stars_real_map_pg.py`：真的經由 `/api/srs/practice/attempt`、`/api/srs/practice/answer` 通過首個領主准入門檻；由伺服器出 20 題並用真 `/api/srs/review` 逐題正式判定、結算 `/api/adventure/boss/finish`，領主 20／20 PASS 且首通 `first_clear_projection=COMPLETED`。
- 領主首通：Zone 1 (`k26_30`) 的獨立授權進度從 0→1 顆，下一區 `k21_25` 的 API `unlocked=true`。
- **30 道不同題目**，每一題均由正式 `POST /api/adventure/map-battles/v1/attempts` 簽發 Attempt/Nonce、由正式 `POST /api/adventure/map-battles/v1/answers` 伺服器判定 CORRECT，沒有測試碼直接呼叫 star writer、任意補 review_log、或偽造星數。
- 查驗門檻：地圖答題 1 題 → 1 顆；17／30 → **仍 1 顆**；18／30 → **2 顆**；19／30 → 2 顆；29／30 → 2 顆；30／30 → **3 顆**。兩個進位門檻沒有提前或超發。
- 真正 DB `adventure_zone_star_progress.earned_stars=3`，`adventure_zone_star_earnings` **剛好三筆**，star_number 1 來源 `authoritative_boss_clear`，star_number 2、3 來源 `authoritative_adventure_answer`，三個 event_id 唯一且不可反向重寫 Boss。
- 重送同一個已接受的 Attempt 與 Nonce，後端答覆 duplicate，**三筆 ledger 及 Boss attempts 均未變**。
- 新建 Flask Session Cookie，重新讀取第一區 `stars=3`、`zone_authority_stars=3`、cleared，第二區 `unlocked=true`；資料庫 ledger 不變。
- `tests/e2e/run_20261019_three_star_world_map_browser.mjs`：在**原版 `index.html`**、本地 Flask／Native PG 上真實啟動 Chrome，沒有修改 API 回應／DOM，也沒有 mock `fetch`，E9 地圖 Zone 1 顯示 **三個 is-earned 星槽、0 個 is-empty，ARIA 為 3／3**；原版 E9 Zone1 讀到 `zoneAuthorityStars=3`，伺服器 `zone_authority_stars=3`。
- 正式候選 Product 的星數演算法／判題／授權 Gate **零修改**；此次新增的是含玩家路徑的權威整合測試。

## 正式證據
`docs/handoffs/GO_ODYSSEY_P2_THREE_STAR_REAL_MAP_PG_AND_UI_R2_20261019.xml`：**1 PASS，0 FAIL，0 SKIP**；先前 `..._UI_20261019.xml` 是原版測試對「第二區 UI locked flag」做過度判斷產生的失敗診斷收據，不列入結案綠燈。

同輪領主前置關卡：`docs/handoffs/GO_ODYSSEY_P2_REAL_LORD_20_PLAYER_AND_PG_R3_20261019.xml`（3 PASS），相鄰安全回歸 `docs/handoffs/GO_ODYSSEY_P2_LORD_REGRESSION_20261019.xml`（257 PASS、10 SKIP、0 FAIL）。此處沒有把不同層次測試數直接相加。

## 需保留的真實界線
1. 隔離合成題庫只有第一區 30 題，因此 E9 對第二區是否「可實際遊玩」還可能有**獨立的內容／路線狀態限制**，不能只拿 `next.locked` 推翻伺服器 `unlocked=true`。這輪只正式判定 Zone1 三顆星的 E9 UI 與第二區 API entitlement，不聲稱 Zone2 UI 完整入場通過。
2. 合成題庫缺少部分真實 Monster identity，地圖答題過程曾在可選的 Monster／Quest 後處理寫入上記錄 `server Monster identity did not resolve for settlement`；這**沒有影響**正式 Map 答題、Zone-star 三筆 ledger 或 Boss 首通，但不得假稱全部 Monster／Quest 整合也已通過。
3. `adventure_zone_star_progression_v1`、B023 Companion operation 與 PuzzleIdentity 的受控隔離 schema fixture 沒有修改正式 DB release policy。正式環境還需獨立 schema preflight。
4. 對「答對 60%」此驗收按目前 Owner-locked code 的 **server-settled 正確 Adventure Map submissions** 作覆蓋事件，所有算式以**整個關卡題庫總數**作分母；一般練習與 Boss 的紀錄**不會不經 Map 授權便直接鑄造第二或第三顆星**。若 Owner 意圖也納入其他模式，需另行審查受控授權來源，不可只放寬觸發器。
5. 正式站 `godokoro.com`、GitHub `master`、Test02 玩家資料全未更改；未完成正式來源准入、Build、真 iPad Safari、回滾演練及 Owner GO_DEPLOY，**不准部署**。V4 自主 E2E 持續 **NO_GO**。

### A–F
A 棋靈候選不變；B 主角與 XP 已有真玩家候選 E2E；C 關卡答題防重發／星數 Ledger 冪等 PASS；D 領主首通→1星、關卡 60%→2星、100%→3星、地圖 3／3、重登入 PASS；E 排行／月榜 Test02 待驗；F 商店／背包與正式 Build 待 Gate。
