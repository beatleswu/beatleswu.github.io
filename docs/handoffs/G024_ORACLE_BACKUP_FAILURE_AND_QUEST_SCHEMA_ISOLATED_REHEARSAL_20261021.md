# G024｜Oracle 正式備份失敗真相＋ARM64 任務領獎 D015 Migration 隔離實測

**日期：2026-10-21。階段技術驗收 PASS；正式 GO_DEPLOY 仍 NO-GO。** 本工作只使用 beatles 已授權的 Oracle 唯讀 SSH 及全新私人 Docker/PostgreSQL；沒有將正式玩家資料複製至本機，沒有讀取正式玩家資料列、沒有碰正式 DB Schema、沒有執行 Oracle Deploy、沒有 GitHub Merge、沒有關閉正式 3D License Gate。

## 接續 G023，不重做既有流程

G023 已完成正式 Oracle Runtime `69dbe57aa535112b1759e3f3bdcf9ecbe1680efb`、真正前版 `2ce8c0bd29a29b841a52bc81c65b0d0881196ce6` 的 immutability SHA 及 linux/arm64 的隔離 G019 源映像 `sha256:6595b2636245656307039bd1d361b807ef0dbcc72b8500b9857c1744cc2d6f25`、264 OCI blobs / 7 source hashes / 真 imported Docker Python smoke PASS；G023 同時**只讀**發現正式 Oracle 缺 `quest_claims_v2`，因此發布維持 NO-GO。G024 直接排除**隔離 QA 層級的 Schema Migration 技術未知數**，並擴大正式 Backup 唯讀鑑識。

## G024：真正 linux/arm64 Image + 全新 disposable PostgreSQL 16，D015 升級驗收 PASS

新的專用 Compose project `go-odyssey-g024-quest-migration-lab-20261021`，路徑 `D:\go-odyssey-g024-predeploy-migration-20261021`；新的 PG Volume、只在私人 Docker network 運作，**PG 不對主機公開**。QA worker 使用**真正 G023 BuildKit linux/arm64 image**，read-only filesystem、只掛載本輪測試 Python script，\`PRODUCTION=0\`、正式 App 三個 Shop／Equip Release flags 均 OFF，不連 Oracle。

資料來源：G021 原本只由 synthetic tester 產生的 `pg_dump -Fc`，SHA256 `c61d6f25089f2584a99945447da67384cd9aa85b11544842260f64e9204fba62`，不是 Oracle 備份；raw dump 含測試帳號 Hash，**僅本機使用，永不入 Git/ZIP**。先將它 `pg_restore` 到 G024 私有 PG，真 SELECT 初始 715 Coins／41 XP、1 筆日任務已領、1 次購買、1 件已穿戴木劍與 7 張 Workbench 資料表。

使用 `migrations.quest_claim_v1` 原正式候選 `upgrade/validate_schema/downgrade_for_isolated_test`：

1. **只在 disposable 合成 DB** 移除一張原本確實存在且已含 1 筆 synthetic claim 的 `quest_claims_v2`，模擬 G023 只讀觀察的「正式 DB 尚缺該表」，沒對正式 DB 做任何 DDL。
2. `upgrade(dry_run=True)`：確實標記缺表、**沒有建立或改動**；執行正式的 `upgrade`：得到 12 欄、精確主鍵／兩項 UNIQUE、`idx_quest_claims_v2_user_period` 與 Postgres 型別，升級 validate=True。
3. 再次執行升級：`created=[]`，idempotent；另外真 INSERT 一筆合成 Claim，重複「相同任務期間／不同 operation」與「不同任務／相同 operation」均受 Postgres UNIQUE 拒絕，原 Claim 保留。
4. 維護完整的非 Quest User Snapshot：**715|41、Users1、Purchase1、Equipped1、Workbench7**，升級前後完全一致。
5. 使用**全新第二個合成 restored DB**，再從同一個有 SHA 的原始合成 PG 備份 `pg_restore --exit-on-error`，原日任務紀錄仍有 1 筆；第二個乾淨 QA 資料庫重演上述**16／16 項全通過**，最終比對原備份和新升級資料庫的 5 類 SQL SELECT 全一致。測試中刻意先刪除舊合成日任務 1 筆以模擬不存在的表，並非「正式資料遺失」；原始備份另已獨立還原以供比對。
6. 機器收據 `D:\go-odyssey-g024-predeploy-migration-20261021\G024_ARM64_QUEST_D015_MIGRATION_AND_RESTORE_EVIDENCE_20261021.json`：`G024_REAL_ARM64_QUEST_D015_MIGRATION_FULL_TEST_PASS`、16個斷言、原始備份 SHA、獨立恢復 SQL 證據。

**本技術通過的界線**：原正式 Oracle 沒有遷移、沒有驗證所有正式表 schema/fingerprint，也沒批准 DDL，不能直接在玩家 DB 套用這份隔離操作；正式變更必須先取得可回復的正式資料備份、Schema 影響審查與 Owner 權限。

## G024：Oracle 真 Backup Timer 的重點實測，正式備份 Gate 仍 NO-GO

先前 G023 在四個指定備份資料夾發現 Go Odyssey player DB 備份候選0，不能因此說完全沒有備份。G024 擴大了遠端唯讀檔名／mtime/bytes 掃描（不讀內容）：先後掃過 9,004 目錄與 158,716 個檔名，hit 到兩個 294,087,521 bytes 的 `.tar.gz` 候選，**其大小剛好與 G023 驗過的當前 App Image release archive 相同**，所以它們不能證明 Postgres player DB 可還原。這個廣域掃描實際達到明確的 `bounded_walk_limit_reached`；因此結論只限「搜尋範圍內未證實可恢復的 DB 備份」，不能宣稱全主機或 Oracle Cloud off-host snapshots 不存在。

真正重要的新證據是 Oracle **Systemd 原生排程**：
- `godokro-backup-daily.service`：**2026-10-21 00:00–00:10 UTC 最新執行 FAIL**，`Result=exit-code`，`ExecMainStatus=1`。當天 sanitized journal 8筆，含明確失敗事件兩筆；沒有可被歸類為空間不足／權限拒絕／dump 失敗的訊息，**不能猜根因**。
- `godokro-backup-weekly.service`：**2026-10-18 03:30–03:31 UTC 執行 Success Exit 0**。並不等於 Postgres 備份可用、off-host 保留與獨立 DB 恢復完成。
- 兩項服務的唯一腳本 SHA 一致：`30490db056e3dde120df3684d6586c17a31a98039ce16646d9acec2a11256264`。唯讀腳本文字分析顯示直接 Tar/OCI snapshot 線索，但**找不到直接 `pg_dump` / PG_DATA 資料夾參照**，亦不能排除間接 nested scripts 或 volume-level snapshot。**未讀原始備份檔、密碼、環境變數、player row 或原始日誌行**。
- Cron binary 不存在（`crontab` 查核無法做），Systemd timer 有 `dpkg-db-backup.timer`（OS package backup，不是 Go Odyssey Player DB），以及以上 daily/weekly 兩服務。由此應正式把「每日備份紅燈」列為**獨立 NO-GO**，先以授權方式檢查其日誌根因及實際備份物件完整性，修復或替代方案經 Owner 審核，並做真正**可重建的最新正式資料庫備份＋另一環境完整恢復**，才可進入 Schema Migration / GO_DEPLOY。

唯讀證據：
- `G024_ORACLE_PROD_BACKUP_READONLY_INVENTORY_20261021.json`（明確紀錄搜尋達到上限及誤分類候選的限制）；
- `G024_ORACLE_BACKUP_TIMERS_READONLY_EVIDENCE_20261021.json`（Systemd service 真狀態、script SHA、受限 Journal 摘要）；
- `G024_ORACLE_DAILY_BACKUP_FAILURE_READONLY_EVIDENCE_20261021.json`（當日 8 筆 sanitized messages 僅分類，不輸出原始 log）。

## 從 G024 走向正式發布：必須遵守的順序

1. 保留既有 Oracle app `69dbe57a` 與真正前版 `2ce8c0bd`，不要拿 G018 當正式 predecessor；新 G019 ARM64 是隔離來源，不是正式 master build。
2. 解決 **Daily backup FAIL** 的原因，辨識 Daily/Weekly 真正包含的 PG 範圍、backup retention/off-site encryption，並在另外的隔離 DB/Volume 真 `pg_restore` 或整卷 restore；**不要只憑「timer successful」做 GO**。
3. 確認正式執行環境 Static 來源 `e53a4775` 與現行 Runtime `69dbe57a` 的精確版本對應、資產清單及 App/Shop/Inventory 路由權威，再確定正式發布包的 source/static pair。
4. 規劃並授權正式 D015 Schema Migration（要有備份、最小 DB DDL、驗證與回退測試），不得因 QA 16 PASS 擅自跑 production SQL。
5. 只發布正式來源/素材已准入的內容，完成 Owner 實體 iPad Safari UAT 與 10 區發布範圍。兩個 Gate **GO_MERGE** 與 **GO_DEPLOY** 必須分開取得 Owner 明確核准；本輪二者全未進行。

**G024 階段完成的驗收是「真正 ARM64+PG 模擬正式缺表的 additive Migration 整體可行性 16 PASS、原合成 DB 另行完整還原成功，並發現正式每日備份服務真失敗」；正式放行仍 NO-GO，正式資料庫未碰。**
