# Go Odyssey｜Owner 已核准第一關第二顆星補發｜正式執行交接 R2
日期：2026-10-19。正式寫入狀態：**未執行／未提交（Blocked by remote execution safety validation）**。

## 1. 核准範圍與來源
Owner 明確核准：只為第一關 (`k26_30`) 已完成領主首通、歷史正確題目可精確重建、答對不同題目達該關所有啟用題目 60% 的 13 位玩家，每人補發**第二顆星**。不補第三顆星、不修改 XP、金幣、領主通關紀錄、棋靈、商店、背包、獎品、已有正式答題事件或其他關卡。

曾經在 Oracle 正式資料庫**只讀**核對：
- 第一關正式題庫：1,939 題；第二星門檻 `ceil(1939 × 0.6)=1,164`。
- 第一關已通過領主：23 位；符合補發資格但缺第二顆星：13 位；另外 10 位未達 60%；需依賴保守估算才過門檻：0；需要第三星審查：0。
- 正式歷史基準：`BASELINE_READY`、`EXACT_RECONSTRUCTABLE`，歷史來源與真正 `mbv1` Answer 題號分別去重再合併。不可將舊紀錄冒充新的地圖答題獎勵。
- 匿名乾跑收據：`docs/handoffs/GO_ODYSSEY_P1_ZONE1_HISTORICAL_SECOND_STAR_PROD_DRYRUN_20261019.json`；題庫 SHA-256 `5dd5ccf622873128fd7d9a66877acb60b58b84d00e333f222751b452c1d37248`；批次 SHA-256 `279efb96aba3fc515250c32134f391d4d989b7409fd6bce2f739b0bfc982eb12`。再次執行前若任一數字或 digest 異動，停止，不得擴大授權範圍。

## 2. 已存在的 Oracle 完整備份
- 路徑（僅 Oracle 主機可讀，禁止公開分享或附檔上傳）：`/home/ubuntu/.go-odyssey-secure-backups/owner-approved-zone1-second-star-20261019/go_odyssey_before_13_stars_20261019.dump`
- 檔案大小 19,909,706 bytes；權限 `-rw-------`、owner `ubuntu`。
- SHA-256：`77237595ff4aea9f946a13e2ffc44e436c825a74f6c7bc7f2e88acc28216effe`。
- 已用 PostgreSQL `pg_restore -l` **驗證 custom-format 備份可列目錄**；尚未進行全量還原演練，因此不得宣稱已完成實際復原測試。
- 本輪 2026-10-19 用**只讀指令**重新驗證 SHA 與檔案權限，結果一致。
- 正式維護執行前的獨立執行器仍需重新驗證 backup SHA、儲存權限與復原策略；正式備份不得被覆蓋。

## 3. 源碼與隔離驗證
候選位於 `D:\go-odyssey-sixroute-20261019\g`，分支 `candidate/go-product-integrated-20261019`，上一個已提交候選起點 `1fd49f8daea33e8819094a6115e098f4fcf04266`。

- `tools/incident_019b_historical_second_star_catchup.py`：匿名、只讀的 `--dry-run` 核對，及封閉式、須由外部受控交易管理的核准補發函式。保留 exact-only、來源 SHA 與 batch SHA、13 人數、交易 advisory lock／row lock、單批重跑 NO-OP、名單異動拒絕。
- `migrations/adventure_zone_star_historical_catchup_v1.py`：**額外的獨立稽核紀錄表**，每位核准玩家保存補發前是否已有 authority row、補發前星數與更新時間、批次證據。不可在正常 `app.init_db()` 自動安裝。
- `tools/incident_019b_owner_scoped_production_apply_20261019.py`：一次性維護主程式，要求明確 Owner 核准範圍、事先鎖定的 digest 與備份雜湊、受控單交易。交易**提交前**比對原 23 位狀態、13 位恰好升至第二星、另外 10 位不變、無第三星、歷史稽核 exactly 13 筆、XP／coins／leaderboard 以外的其他關聯遊戲表不變、Boss／Wardrobe／review rows 無變化；之後以**新的唯讀 DB session**查證。本工具尚未放入或執行於正式容器。
- `tests/test_20261019_owner_exact_historical_star_catchup_pg.py`：8 個原授權／稽核單元整合案例。
- `tests/test_20261019_star_owner_apply_runner_native_pg.py`：對**實際一次性維護主程式**在 loopback-only disposable PostgreSQL 演練 dryrun 整筆回滾、完整 13 人提交＋新 Session 驗收、Owner scope 錯誤拒絕；不連線正式資料庫。
- `docs/handoffs/GO_ODYSSEY_P1_HISTORICAL_STAR_OWNER_APPROVAL_RUNNER_R2_20261019.xml`：本輪累積 20 PASS、0 FAIL 的單獨證據，包括原版三顆星規則回歸（以 JUnit 實際結果為準）。

**補發操作只修改**：`adventure_zone_star_progress` 核准玩家 zone1 的 `earned_stars` 至 2，與新增的 `adventure_zone_star_historical_catchup_receipts` 歷史補發審計行。**不寫** `adventure_zone_star_earnings` 真地圖／Boss 授予紀錄，不修改其他角色／貨幣／獎品資料。

## 4. 阻擋與不可越過的正式 Gate
上次在對 Oracle 準備最後的維護執行時，遠端操作觸發外部**安全檢查封鎖**。因此本輪只允許本機讀取／測試與正式 Oracle 的唯讀核對、備份 SHA 檢查。**沒有以其他遠端命令、資料庫路徑或容器操作改寫正式資料**，不得透過另一路繞過封鎖。

在授權執行環境可正常通過原安全檢查之前，這項維護必須保持 **NO_WRITE**。保留 Owner 已核准的 13 人修正範圍，但仍須由正式發版治理確認程式碼 SHA、經過可信執行授權的 DB 權限、資料庫備份與 rollback 演練，才可按原核准範圍啟動。

此 Owner 核准不涵蓋 GitHub master 合併、Oracle 產品 Docker image 發布、Go Odyssey Product 網站部署、Test02 其他資料或 V4 自主執行權。

### 執行後才可宣稱完成的核對
1. 新的 DB 唯讀 Session 顯示 **13 位** zone1 authority exactly 2、原先另外 10 位 unchanged（仍未達 60%）、無 zone1 第三顆星。
2. 13 筆獨立歷史補發收據，包含每人的**前狀態與更新時間**，全部固定同一批次 SHA、沒有重複。
3. 全部 Boss 首通、XP／coins／Wardrobe／Inventory／review entries 前後完全一致。
4. `beatles` 本人在正式網站登出、登入或重新整理，地圖第一關展示 2／3。取得**實測結果**之前，仍應答覆「正式站 beatles 尚未完成補星」。

### A–F 狀態
A 棋靈 Product 候選不變；B 主角／XP 候選不變；C 歷史補發一次性交易、重試及外部 Gate 隔離驗證 PASS；D 正式 13 人補星交易**未提交**、實際玩家 UAT 待測；E 排行榜與月榜未改；F GitHub／Oracle Product Build／Deploy 未獲此授權，V4 Goal Loop NO_GO。


## 2026-10-19 追加：正式執行來源准入定位

- 已在 Oracle 正式 App 容器以**唯讀**檢查下列三個路徑：`/app/tools/incident_019b_owner_scoped_production_apply_20261019.py`、`/app/tools/incident_019b_historical_second_star_catchup.py`、`/app/migrations/adventure_zone_star_historical_catchup_v1.py`，結果全部 **ABSENT**。這是可獨立驗證的正式維護程式來源／准入缺口；不應改用臨時 SQL 或 stdin 注入程式迴避來源治理。
- 本機已建立 `GO_ODYSSEY_13_STAR_OWNER_AUTHORIZED_SOURCE_MANIFEST_20261019.json`，含三個實際源碼檔案 SHA-256、候選 Commit `50fdc2e9cea3c338c55207025626c1018c44a03c`、補發範圍、正式備份雜湊及 20/20 隔離驗收證據。**檔案雜湊不是獨立數位簽章，manifest 不是可信執行許可**。
- 同日用正式 App 現行題庫與歷史資料再次執行**無寫入 dry-run**，固定 23／13／1,939／1,164／0／0 及 candidate digest `279efb96aba3fc515250c32134f391d4d989b7409fd6bce2f739b0bfc982eb12` **全部未漂移**。該檢查只是 SELECT，沒有安裝／運行三份補發程式。
- Windows PowerShell 初始化時出現的 `PSSecurityException` 來自 **profile.ps1** 的載入限制；同一命令中的只讀 SSH／測試仍可繼續執行。**不能單憑這項訊息聲稱正式維護執行許可已拒絕或已核准**；真正缺少的准入是被授權執行環境對本機三份檔案的可信來源核驗、獨立正式維護動作 Gate 與可稽核執行程序。
- 下一步僅在正式可信執行環境依既有 Owner 核准範圍對三份原始碼進行 SHA／來源稽核和准入，重查備份，再執行同交易驗收。**不得**把 Product 的資料維護簡化為未核對來源的遠端一次性 Python／SQL，亦不得將此項授權擴充為網站部署。
- PostgreSQL full dump 僅作事故復原證據；**不能在遊戲仍有新玩家進度時直接整庫覆蓋還原**。此批精確回滾應優先使用獨立 audit receipt 中的補發前狀態，走另行核准的受控補償交易，並確認沒有玩家在補發後取得後續正常星數。
- **仍無正式 COMMIT**。正式 `beatles` 星數繼續以一顆為準，直到經新的唯讀 DB 連線與玩家畫面實測確認。
