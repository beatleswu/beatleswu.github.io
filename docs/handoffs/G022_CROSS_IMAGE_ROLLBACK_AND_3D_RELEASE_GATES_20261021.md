# G022｜真正跨版 OCI 回退演練＋武器／裝備發布准入核對

2026-10-21，beatles 工作站，僅新隔離測試；**階段目標：G018 → G019 → G018 在相同測試 PostgreSQL16 上跨 Image 互換、維持玩家資料且前版與候選版都能載入原遊戲頁面；同時精確區分 source rights 與正式可販售／穿戴的 3D 資產發布權**。

**驗收範圍不是正式 Oracle 維護、上線或正式玩家資料災難復原。**

## 兩個真正 OCI 鏡像，均為此前獨立 Clean BuildKit/整包 SHA 審核並 Docker load 的 Product 候選

- **G018 較早的隔離候選**：source SHA `246decad0207228f6c9c87f0309610b5d8bbcdb8`，Image ID `sha256:497c03f970ff78745e91df9d6abcb7ba6166530479c0ff289120479c414788f4`，tag `go-odyssey:g018-246deca-verified-local`。這**不是已證實的 Oracle 現行正式影像**。
- **G019 新候選**：source SHA `15cbcdbe9c28b8f16107387e45cddb7c087f9627`，Image ID `sha256:eb169da6075c5e473108b6e43d27966c3c4017e378da8a92644aba3986db49b4`，tag `go-odyssey:g019-15cbcdb-verified-local`。沿用先前 264 OCI content SHA／7 runtime exact source audits。G020/G021/G022 都沒有改它的產品程式原碼。
- **只在 QA 合成來源切換**：G022 不合併 GitHub master、不啟用正式付費／交易／裝備旗標、不更動 Oracle、不測或寫正式玩家、沒有賦予權利未准入 GLB 正式 Product 身分。

## 新全隔離的真 PostgreSQL 跨版：三階段實際執行

新工作區 `D:\go-odyssey-g022-rollback-release-20261021`。Docker Compose Project `go-odyssey-g022-rollback-lab-20261021`，新的 `g022-private-pg` / `g022-private-app` volumes，app **只有 127.0.0.1:5098**，PostgreSQL 對主機不公開；舊 G021 App/PG 和 A1/R3 所有 Container/Volumes 不修改。參考於 G021 中實際 pg_dump -Fc 的測試備份，SHA-256 `c61d6f25089f2584a99945447da67384cd9aa85b11544842260f64e9204fba62`，將備份**僅複製到 G022 私有 DB 容器**，再 `pg_restore --exit-on-error --no-owner --no-privileges` 還原到完全新的 `go_odyssey_stage`，真 Select 715Coins/41XP、1份 purchase、1件 equipped 木劍。**原備份包含合成帳號密碼雜湊，只有本機保留，嚴禁放 Git、ZIP、聊天附件或生產站。**

三次切換都採 **同一個 G022 PostgreSQL 容器和原 volume**，只由 Docker Compose `up --no-build -d app` 重新建立 APP container，真正切換了 Image ID，不是換 JS、HTML 設定或 mock API。每次從新的 Chrome 登入兩個獨立 Flask signed Session，直接載入原課程、酒館、商店、背包和 Hero 並檢查相同的真 POSTGRES 資料和來源控制：

1. **G018 先啟動**：真正 G018 image + G022 restored PostgreSQL，`G022_REAL_OCI_IMAGE_SWAP_PERSISTENT_PG_PLAYER_READBACK_PASS`，**32 Browser assertions PASS**；原 Hero G008 WebGL Canvas 286px，沒有未准入 QA 模組。原 Shop/Coin false、完整的 41XP/715Coins、1 木劍 equipped、1 個 daily Quest 已 claim、1 個 Curriculum 委託 accepted、Tavern alltime41、第二簽 Session 一致。
2. **同一 DB 升級 G019**：用 `candidate-override.yml` 只將 image 和明確 source SHA 改為 **真 G019 OCI**、App container 真重建；Chrome 同樣 **32 PASS**、一樣的完整玩家資料，Shop 三開關仍 default OFF；原 Hero 真 Canvas。曾發現一個**瀏覽器測試實作**的偽陰性：兩次完全相同的登入若發生在同一秒，Flask deterministic timed signed Cookie bytes 可能相同，初版測試因此錯誤標為不同 Session；修正為兩次登入間超過一秒後重新測試，32 PASS。沒有因此修改 Product、資料庫或登入安全機制。
3. **同一 DB 回退 G018**：撤除 G019 override，`up -d --no-build app` 真正重建成 **G018 前版 Image ID**；Chrome 第三輪 **32 PASS**，XP41／Coins715／Quest、Curriculum、Tavern、已裝木劍全部保留。G022 App/DB 最終再次 Docker inspect 都 healthy，G022 App source 確實是 246deca；三個商店/裝備 server feature flags `false`，G022 loopback5098，不公開 DB host port。直接逐項查詢 G022 PG 和**未修改 G021 PG**五個統計（Coins/XP 715|41、Claim1、Purchase1、Equipped1、Workbench7）全部一致。證據檔 `G022_FINAL_PREDECESSOR_OCI_AND_BOTH_PG_HEALTH_20261021.json`。

**正反向共 96 項有效原始 Chrome 驗收、0 未預期持久資料遺失**；保留三個階段 Machine Browser Receipt：`G022_G018_INITIAL_BROWSER_20261021.json`、`G022_G019_BROWSER_20261021.json`、`G022_G018_BROWSER_20261021.json`。每輪 `verdict=G022_REAL_OCI_IMAGE_SWAP_PERSISTENT_PG_PLAYER_READBACK_PASS`、32 checks、0 JS errors、0 API500、0 unintended API writes；前版／候選版的官方 Product 原 HTML 實際載入。這是一個比之前 G021 同版本三個開關 OFF/ON/OFF 真 Container 略高一階的**前後不同 Docker Image 的資料相容性＋切換回退測試**。

## 3D 武器／裝備的正式准入仍嚴守獨立授權

直接讀取實際 source catalog 和來源二進位，獨立執行 audit `G022_RIGHTS_AND_QA_RELEASE_GATES_STAY_NOT_ADMITTED_PASS`：

- **Formal9 替代 4 件：** iron_sword、fox_fang、riverstone_sabre、bamboo_shadow_blade。已選定 CC0-1.0 權利清楚，**4/4 本機 GLB SHA256 與權威來源 mapping 完全吻合**；但 `RIGHTS_CLEARED_RELEASE_NOT_ADMITTED`，`EQUIP_ENABLED/SHOP_ENABLED/PURCHASE_ENABLED/DROP_ENABLED/PLAYER_SELECTABLE/RELEASE_ENABLED/PRODUCTION_ASSET_ADMISSION` 均 false。不能把權利許可誤當作已被 Owner 核准正式商品上架。
- **D007 原有 12 件：** G009 candidate presentation Owner admission ≠ 法定／正式遊戲 Release，12件的 `release_eligibility=NOT_CLEARED`、`equip_capability=false`；原始 wooden_sword 的遊戲購買/裝備 API 通過不代表該 D007 GLB 可發布。
- **P022 28來源裝備**：P038 12 個歷史已校正 Mesh（8主手、4副手）＋16原 FBX 衍生 GLB（包含箭矢3，箭矢不是 server equip SKU），本次正式 `Product_release_admitted=0`。先前 10/12 P038 GLB 與 D007 歷史素材重複，**不能把這些數字相加稱作 44 件不同武器或 44 件可販售正式裝備**。權利和來源的原官方包使用範圍仍要逐件核對，實體 iPad Safari／真正雙手、弓箭動作/碰撞也未全面通過。
- **9 項既有 canonical 遊戲道具**在 G019 可透過已驗證的購買、持有、裝備伺服器權威流程運作，但遊戲經濟功能不自動賦予其配對未准入 GLB 的正式發行權。這是一項獨立阻擋，不應關掉 D007/Formal9 的 Release Gate 來換取「看起來武器已經啟用」。
- Machine ledger `G022_FORMAL_WEAPON_RIGHTS_AND_P022_28_QA_NONRELEASE_AUDIT_20261021.json`，有來源準確個數與正式准入 0 件，不放 QA GLB 真正二進位。

## 狀態及下一個可執行階段

G022 **技術 PASS** 代表：在隔離 PG 合成資料上，真正已驗來源的前版 OCI 能服務原網站、升級到新候選後能保持玩家資料、再退回前版也能保持玩家資料；且正式商品/3D權利阻擋仍遵守、不作偽造 release。它不代表 **Oracle 先前生產實際影像 ID** 已被辨識／執行前版回退，不代表生產資料備份與還原演練、已完成真實 iPad Safari Owner UAT、10區全部正式題庫已被驗收或 P022/P038 已允許正式全啟用。

正式發布仍須 Owner 分別核准 **GO_MERGE 和 GO_DEPLOY**，此前需補：
- 由授權入口**只讀確認 Oracle godokoro.com 目前實際 Running Image SHA、Database 憑證治理及真實 Backup 路徑**，編出正式 GO/NO-GO source pinning + operation rollback guide；不能拿 G018 當已證實的 Oracle 前版。
- Owner 在實體 iPad Safari 上測試已提供的真正玩家流及 3D 模型視覺（Chrome touch 只能模擬）。
- 按上述 manifest 對額外 3D 裝備逐件取得 source/usage rights、精確 server SKU/slot/rigging 與 Owner 正式 Product Release Admission；沒有許可時上線候選必須**保持那些 GLB 功能禁用**。可把非 3D 被阻擋的其他遊戲功能作為獨立部署候選，但不能誤宣稱「所有武器裝備已開放」。

## 來源／證據
- G022 隔離 workstation：`D:\go-odyssey-g022-rollback-release-20261021`，內含前版/候選的兩份 Compose、來源 Audit、實際 Browser 三份、相容性與最後 State SQL Report。**資料庫原始 dump 僅留 G021 工作區且絕不入 Git 或外部 ZIP**。
- G022 只新增本報告與 `tests/test_g022_release_admission_and_image_rollback_contract.py`（不改正式 Product runtime/DB/OCI）。正式 Go Odyssey G MASTER 在 Notion/共用 handoff index 後續應引用實際 staging hashes。
