# Go Odyssey | G MASTER — 正式第一關歷史第二顆星補發準備（2026-10-19）

## 狀態

**只讀正式資料核對完成；受控補發邏輯已於一次性 PostgreSQL 實測；正式補發尚未執行。**
分支：`candidate/go-product-integrated-20261019`，起始 `72ce19d860fae00536830f22bdf38b641234ad1b`。
嚴禁由這份文件、普通 ChatGPT 指令或測試的授權常數自行認定正式 GO_MERGE／GO_DEPLOY／Production DB WRITE 已核准。正式執行需獨立 Owner 批准與現場交易／備份／稽核 Gate。

## Owner 已確認的規則

- 第一區 `k26_30` 現有啟用題庫共 **1,939 道**，第二顆星門檻 `ceil(1939 × 60%) = 1,164` 道**不同的正確題目**。分母是關卡全部可用題目，不是已作答題數、不是領主 20 題。
- 第一顆星必須有伺服器持久化的領主首通，第二顆星只對達 60% 的玩家補足；**絕不補第三顆（100%）**、不修改領主首通紀錄、 XP、金幣或其他獎勵。
- 新版日常 Map 星數仍需要真伺服器判題；**歷史補發必須獨立標記來源**，不能假造今日 `mbv1` 答題／`authoritative_adventure_answer` 星數授予紀錄。

## Oracle 正式站「唯讀」雙重核查

正式資料 `users`／`adventure_boss_progress`／`adventure_historical_mastery`／`adventure_zone_star_progress` 等，透過 `docker exec go-odyssey-app python - --dry-run` 使用 psycopg2 **read-only transaction** 核對。程式只使用 SELECT，沒有移動／複製其他玩家的私人紀錄至聊天或交付文件。

- 第一關 Boss 首通 **23** 人、達到歷史＋伺服器 Map 正確覆蓋率 60% 的 **13** 人；這 13 人目前均缺第二顆星。
- 13 位資格證據均在 `GRANDFATHERED_LEGACY_CONTINUITY_V1`、`BASELINE_READY` 中標示 `EXACT_RECONSTRUCTABLE`，需要以 `CONSERVATIVE_GRANDFATHERED` 推估才過門檻的 **0** 人。
- 此批第三星達標／需獨立審查 **0** 人。
- 客戶端仍看到 1 星，是歷史連續性已可讀、但獨立第二星授予 尚未反映於 `adventure_zone_star_progress` 的跨版本契約落差。環境未設 `GO_ADVENTURE_RETROACTIVE_MILESTONE_POLICY`，預設 **HOLD**。
- 不承諾目前正式帳號已收到任何補發；本輪沒有 Oracle DB DDL／UPDATE／INSERT、沒有 GitHub 推送／Merge，也沒有網站部署。

匿名乾跑收據：
`docs/handoffs/GO_ODYSSEY_P1_ZONE1_HISTORICAL_SECOND_STAR_PROD_DRYRUN_20261019.json`

必要雙重比對欄位：
- `pool_count=1939`
- `second_star_required=1164`
- `cleared_users=23`
- `candidates_missing_second_star=13`
- `conservative_records_needed_for_candidate=0`
- `potential_100pct_review_only=0`
- `pool_sha256=5dd5ccf622873128fd7d9a66877acb60b58b84d00e333f222751b452c1d37248`
- `candidate_digest=279efb96aba3fc515250c32134f391d4d989b7409fd6bce2f739b0bfc982eb12`

這些 digest 綁定當次真實題庫與匿名輸出的批次名單／覆蓋數。正式獨立 Owner 批准之前應再次查核，任一 SHA 或名單數變動即停止。

## 本機候選已新增的程式

1. `tools/incident_019b_historical_second_star_catchup.py`
   - CLI **只提供 `--dry-run`**；程式從部署的 `app.py` AST 讀取正式關卡 books，從 `data/questions.json` 計算全部啟用題目與 SHA，連線 PostgreSQL 強制 read-only，只輸出匿名摘要。
   - 純函式 `build_readonly_plan` 只納入 Frozen／Ready baseline 的 `EXACT_RECONSTRUCTABLE` + 當前真正 server-settled `mbv1` 正確事件，逐題去重，不讓 conservatively reconstructed 的遺失時間線推估假充資格。
   - `apply_owner_approved_plan` 是**僅供獨立批准的執行器呼叫**的 Python 核心，CLI 不曝露 `--apply`。要求簽核批次 SHA、確切 13 人名單數及 Owner Gate 傳入；transaction advisory lock + Boss row FOR UPDATE + DB 唯一性 constraint 防併發；如曾有真地圖第二星則拒絕偽造補星。
   - 同批次重複執行識別 `ALREADY_APPLIED`，不重新 UPDATE。若資料／SHA／來源或玩家數變更則 fail-closed，所有變更由外部交易管理一次 commit／rollback。
2. `migrations/adventure_zone_star_historical_catchup_v1.py`
   - 獨立加法式 audit receipt table `adventure_zone_star_historical_catchup_receipts`；不從 `app.init_db()` 自動執行，不修改 `adventure_zone_star_earnings` 對 `authoritative_adventure_answer` 和 `authoritative_boss_clear` 的限定，**絕不把歷史補發編成新答對題目的事件**。
   - 單批逐位 player/zone/star_number=2 一筆 immutable source audit，紀錄 pool SHA、baseline、不同正確題目數、batch ID、cohort digest 和 receipt digest；與正式星數更新**同一交易**完成。
3. `tests/test_20261019_owner_exact_historical_star_catchup_pg.py`
   - 用本機 loopback-only native PostgreSQL 建立合成 23 人／13 人 60% 門檻／10 人未達標情境。
   - 驗證 read-only dryrun 無任何資料寫入、無 Owner Gate 會拒絕、受控 migration + 補 13 人每人恰好第二星、不偽造 map/boss award ledger、英雄／Adventure bootstrap 新 Session 顯示 2 星、第三星不誤發、舊 boss row 不修改、批次重複執行 no-op、錯誤批次／題庫不匹配停止、交易失敗完整回滾、conservative 不會偷偷加入。
   - Native PG 單獨測試 **8/8 PASS**；最終應附獨立 pytest receipt 及相鄰 star authority 回歸。

## 仍須核准後才可以正式補發

真正正式異動需另走受控階段：
1. 確認 Oracle 資料庫快照/備份、一次性 SQL runner 主體、DDL 與權限；獨立 Owner 授權「**僅第一區 13 位有 EXACT 歷史證據者各補 1 顆第二星**」及 audit migration。這不是一般網站部署自動授權。
2. 執行前重新唯讀 dryrun，強制比對 **1939／1164／23／13／0／0**、題庫 SHA、批次 SHA，發生任何異動或第三星情況立即停止且回報。
3. 先在獨立測試資料庫執行並檢查 rowcount、獨立 audit receipt、前後 Boss 清除／所有 XP、coin、wardrobe 未變，再由獨立授權執行器於受控 transaction 上線。
4. 寫入後 read-only 驗證 13 位為 Zone1 exactly **2/3**、不誤發第三星、未達 60% 的 10 位仍為 1 星，刷新／登入時 world map 讀回，檢查固定的稽核 digest；異常走正式 DBA 備援與補償流程。

目前 **尚未執行本節**；不得因此聲稱正式 beatles 帳號已成為 2 星。

### A–F
A 棋靈候選不變；B 主角成長候選不變；C 來源分離與幂等測試 PASS；D 第一關補第二星候選機制隔離 PASS、正式 13 人待獨立 Owner Gate；E 排行/月榜不變；F Build/部署仍未獲准，V4 自主 E2E 維持 NO_GO。
