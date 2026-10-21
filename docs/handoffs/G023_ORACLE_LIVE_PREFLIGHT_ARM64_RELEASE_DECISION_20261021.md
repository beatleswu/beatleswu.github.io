# G023｜Oracle 正式現況唯讀驗證＋真正 ARM64 候選建置：技術 PASS、正式部署 NO-GO

2026-10-21，G MASTER，beatles 授權裝置。**本階段已完成有原始證據的 Release GO/NO-GO 判定；不是 GitHub 合併、Oracle 部署、正式玩家資料寫入或回退。**

## 這次比前 G022 多了什麼實際成果

G022 在本機隔離 PostgreSQL 證明 G018→G019→G018，**但 G018 不是真正 Oracle 上一版**。G023 直接透過 beatles 原授權 `oracle_godoyssey` SSH，在遠端只執行 Docker inspect、正式發布檔 SHA、靜態來源 manifest SHA、磁碟統計及單一 **BEGIN READ ONLY／information_schema** 結構查核；遠端沒有檔案或 DB 寫入，沒有查看正式玩家資料或容器密碼。使用的獨立工具 `D:\go-odyssey-g023-live-preflight-20261021\oracle_readonly_probe.py` 經 SSH stdin 傳入 ephemeral python3，遠端不落地腳本。來源回報：`G023_ORACLE_LIVE_READONLY_METADATA_20261021.json`，UTC 2026-10-21 12:49。修正了探查程式一開始沒有處理 UTF-8 BOM 和猜錯 TAR 檔名造成的假陰性，最終正式檔 SHA 已重新核對通過。

**真 Oracle 同一時間的權威現況（不是文件推測）：**

| 環境項目 | 2026-10-21 正式即時稽核 |
|---|---|
| App `go-odyssey-app` | running / healthy；映像 `go-odyssey-app:69dbe57a` |
| Scheduler `go-odyssey-scheduler` | running；**與 App 相同 immutable image ID** |
| 當前正式 Image ID | `sha256:c1e30ff40ca21633fc543c717032550536304d0772838528442d27502302dd8e` |
| 當前原始碼 SHA | `69dbe57aa535112b1759e3f3bdcf9ecbe1680efb` |
| **真正正式上一版** | `go-odyssey-app:2ce8c0bd`，Image `sha256:f9b8dcba43a1f55927993d230699c9b4d7ec7f88cc99edb98a0d4e2743bf6071`，來源 `2ce8c0bd29a29b841a52bc81c65b0d0881196ce6`，仍留在 **Oracle 本機 Docker** 且 ID 比對一致 |
| 當前發布紀錄 | `/opt/go-odyssey/releases/go-odyssey-app_69dbe57a.deployment.json`，SHA `d6dc4dafc8d7fd365514723636e2009f72cbdc5d0820dede5b5983ba8ae90b9b` |
| 當前真正發布包 | `go-odyssey-app-69dbe57a-linux-arm64.tar.gz`，294087521 bytes；SHA `4e7d3c176e61319d7ecdab921078d7b64cc581ea5da83d23583ba95587053670`，**重新完整雜湊且與紀錄一致** |
| PostgreSQL | 16-alpine、healthy；資料 Volume `go-odyssey_pg-data`，無公開 host DB port |
| 靜態資產 current | `20260920-034411-e53a4775-v242-zone4-storyboard-pwa-parity`，靜態來源 SHA `e53a477524af60b6b3a87dfe30b983089c137d80`，manifest SHA `2dbf2619e906a02ed06e050021005ecd727b09db143f5cc34d2e3ab0525ff3a1`，2158 文件 |
| 主機磁碟 | 18.63 GiB 可用，已使用約 87.2%；要另外確保發版過程/備份保留餘量 |
| 公開唯讀 HTTP | `/healthz`、`/login`、`/` 回 HTTP 200；沒有用正式玩家帳號登入 |

正式部署紀錄包含真正前版 image 身分，且這次直接 Docker inspect 驗證它**現在仍存在**。但只有映像在主機，不代表新 G019 版本已能直接用那個影像回退：需正式版本配對/資料庫備份、正式操作 runbook 與獨立 Owner Gate。

## G023 解決的 ARM64 部署技術阻擋

G019/G021/G022 已通過的原 OCI 是 **`linux/amd64`**，Oracle 正式為 **`linux/arm64`**。G023 新增使用 beatles 既有 Docker Buildx 的真正 `--platform linux/arm64`，從**未更動 Product runtime 的隔離候選來源**全新建置 261 步；原 Runtime source SHA 保持 `15cbcdbe9c28b8f16107387e45cddb7c087f9627`。

- **真 ARM64 OCI**：`D:\go-odyssey-g023-live-preflight-20261021\G023_G019_ARM64_ISOLATED_CANDIDATE_20261021.tar`，292071936 bytes，SHA-256 `65a7896387e25791ff4a616631d2e8ca8e2a3185936a94ad21cc4b14464362be`。
- Oracle 正確平台：**linux/arm64**；真 OCI manifest＋實際 `docker load` 影像 ID：`sha256:6595b2636245656307039bd1d361b807ef0dbcc72b8500b9857c1744cc2d6f25`。
- 獨立實測 **264／264 個 OCI blob SHA 完整比對**、七個 Product runtime source SHA 比對 Git 原始碼 7／7、Release 隱私排除 QA／密鑰 PASS。
- **真 Docker load** 成功；`docker run --platform linux/arm64 --rm --network none --read-only --tmpfs /tmp` 真 ARM64 受隔離容器執行 Python／Flask／gevent／psycopg2，檢查原 Shop、Backpack、default-off G019 source 與私有 QA 模組排除 **exit0 PASS**。證據 `G023_ARM64_FULL_OCI_SOURCE_INTEGRITY_20261021.json`、`G023_REAL_ARM64_IMPORTED_DOCKER_SMOKE_20261021.json`。
- 這份是在 beatles 的**隔離技術候選**，不是正式 GitHub merged master 的 Build，也未作正式 Release 簽章、Oracle copy、ARM64+正式 Production DB 的登入端到端測試；不能拿這些技術 PASS 取代 GO_MERGE／GO_DEPLOY。

## 目前阻擋正式 GO_DEPLOY 的事項（全部留原位，不越權繞過）

1. **真正式 PG 的 Quest V2 Claim 表缺少**：以 PostgreSQL `BEGIN READ ONLY` 查 10 個應用關鍵名稱，已發現 `coin_purchase_operations`、`player_inventory`、SGF Workbench 七張表皆存在，但 **`quest_claims_v2` 不存在**。現行 G019 `migrations/quest_claim_v1.py` 明確定義 `TABLE_NAME = "quest_claims_v2"`。必須先確認正式版本差異、schema/fingerprint、遷移評估與事前完整備份，獲批後使用受治理 Migration，再進正式應用切換，**不可在 G023 直接修改正式資料庫**。
2. **尚沒有可驗證的正式 Player DB 備份／還原證據**：唯讀檢查 `/opt/go-odyssey/backups`、`/opt/go-odyssey/backup`、`/opt/go-odyssey/releases/backups` 等四處已知路徑，找到的 36 個檔案均在系統 `/var/backups`，**Go Odyssey 應用指定目錄中符合副檔名的備份候選 0**。這**不代表一定沒有 off-host block-volume snapshot、其他路徑或 Oracle 控制台備份**，只能判定「正式 DB 可復原性未建立證據」。完成備份來源、時間、加密、保存期、位置、恢復到獨立 DB/Volume、實際恢復結果與 SHA 後才能釋放本 Gate。
3. **目前正使用混合來源 static/runtime**：Oracle Runtime SHA `69dbe57a` 與靜態來源 `e53a4775` 不同；當前 static generation 有 inventory.html，其 SHA `4bb8f019...` 與現行 Runtime `c992326e...` 不同，未確定在所有公開路由實際由誰服務。Repo `deploy/known-production-rollback-pairs.json` 沒有這個**當前精準來源配對**（只有較舊 9 月版本配對）。G019 會變更 Shop/Backpack，必須使用正式 static release + runtime identity 完整符合的 source pairing，確認原玩家真正收到核准新 UI，不能只更新 APP image。
4. **正式來源審核與兩個不同 Owner Gate**：讀到 GitHub `master` 的即時 SHA `0f14f95c4fd9f70fcbdaa929b8fed3a4a9316463`；本機隔離 Runtime `15cbcdbe` 尚未正式 `GO_MERGE` 採納。正式 Merge 經批准後，才由**已合併的精確 master SHA**重新出有簽章、有來源證據的 linux/arm64 Build、產出正式部署 manifest；必要的正式 `GO_DEPLOY` 是另一個單獨 Owner 授權。不能沿用本地隔離 ARM64 tar 偽稱已簽署的正式 Build。
5. **發布內容、素材與 Owner 實機**：P022 28 件、D007 12 件與 Formal9 4 件素材中尚未正式准入的 3D GLB，不得因經過模型/背包 QA 就上架。真 iPad Safari Owner 測試及全10區正式題庫/正式畫面、任務發布範圍仍要確認，且未取得現在 Oracle 執行環境的合成帳號正式 UAT 授權。可選**核心功能先上線而未准入資產繼續 fail-closed**，但也必須核准核心功能內容與上述其他部署安全關卡。

## 後續正式發布 Runbook（為將來 Owner 授權而預備，G023 絕不執行）

**Read-only Gate：** 確認當前正式 App＋Scheduler 來源與 Image ID `69dbe57a / c1e30...`、真正上一版 `2ce8c0bd / f9b8...`、靜態 Generation `e53a...`、實際 Player DB schema、磁碟容量、外部題庫與 Nginx 路由；生產相關 SHA 要重讀最新狀態，不沿用過期快照。

**完整備份 Gate：** 在另行授權下取得正式 DB 一致性快照與 off-host 保留紀錄，包含正式 Compose/環境指紋與靜態 generation/image，恢復到隔離資料庫成功；不將任何玩家資料與憑證複製到 ChatGPT 或 GitHub。本階段沒有執行或核准任何正式 DB 備份命令。

**來源與 Schema Gate：** 精確定版 G019+學習/任務/酒館，Owner 決定正式允許的 3D Model 清單；先合併已獨立驗收的新功能到 master，跑完正式題庫、Migration plan/schema diff、靜態清單/來源 SHA 對照、arm64 source-matched build/授權核對，再在已有可還原正式備份後允許 Schema migration。

**正式 Build/Deploy Gate：** `GO_MERGE` 與 `GO_DEPLOY` 分開核准。只能由正式 canonical GitHub merge/source、`linux/arm64` 產物及原 deployment tooling 完成。修改 app 先檢健康，再切 scheduler，核對 Swagger/Quest/WGo/Shop/Backpack/3D Hero、靜態 Service Worker 與公開網站；失敗時依正式正確的 `2ce8c0bd` + static version 精確配對/正式 DB 容量與 schema 相容性執行受治理 rollback，**不允許假設 G018 就是 Oracle 上一版**。

**本輪判定：G023 技術預檢 PASS，正式發布 NO-GO。** 階段性目標「真正讀回 Oracle 現況、找到正確上一版、找出部署阻擋、完成 ARM64 相容候選技術驗證、交付可執行 Gate Matrix」已完成；剩餘是正式 Owner 決策及須另受控執行的 Production 作業。未有 Oracle 新部署、未合併 master、未打開正式購買旗標、未寫入正式玩家資料。

本輪權威 machine release-gate：`docs/handoffs/G023_ORACLE_PRODUCTION_SOURCE_LOCK_20261021.json`。遠端原始 sanitized 觀測及臨時 ARM64 tar/proof 只留 beatles `D:\go-odyssey-g023-live-preflight-20261021`；上述重要內容應同步總控 Notion 與 append-only 交接索引。
