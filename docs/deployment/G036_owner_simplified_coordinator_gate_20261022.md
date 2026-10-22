# G036｜修復 Owner 簡化來源政策與正式發布協調器的連接

2026-10-22。正式 Production 委任產品版本：`2ae01985ab716eb0175b292888ffdea570c80ca6`，G030 69 個 GLB 與 360° 功能已合併、Safari Owner UAT PASS；G031 ARM64/Static 原生包、G032 真 Oracle preflight 等全部 PASS。

**本輪真實故障，不可隱匿**：已經 Owner 明確核准 `GO_DEPLOY_WITH_BOUNDED_RECOVERY 2ae01985`，執行原始 `deploy-coordinated-release.ps1 -Execute`，但協調器未傳 `-OwnerSimplifiedPolicy`、也只向 BUILD_APP 傳舊 `-ExpectedGitSha`。原 `build-release-image.ps1` 預設歷史外部主機模式因此 fail-closed `EXTERNAL_GOVERNANCE_AUTHORITY_REQUIRED`，協調器記錄 `STOPPED_OWNER_DECISION_REQUIRED`、`stop_phase=BUILD_APP`、`phases_completed=[PRECHECK]`、三次明確停住、`mutation_occurred=false`，正式網站未更動。原始機器收據 `D:\go-odyssey-g031-master2ae-artifacts-20261022\G035_OWNER_APPROVED_COORDINATED_DEPLOY_RAW_20261022.log`。

**已存在正式 Owner 許可**：自 2026-10-21 Owner 已取消額外獨立簽署主機的發布強制前置，`build-release-image.ps1` 真已實作 `-OwnerSimplifiedPolicy -GateSourceSha <exact-gate-sha> -ProductSourceSha <exact-product-sha>`，實際驗證 Git source control-plane-only ancestry、工作樹完全 clean、六路 E10、部署 QA、baseline、真 Docker。Static `package-static-release.ps1` 也已有 `-GateSourceSha/-ProductSourceSha` 支援。原 coordinator 才是未接線處。

**G036 修復原則**：只給 coordinator 加明確選用的 `-OwnerSimplifiedPolicy`，不改舊外部模式預設／不假造外部可信主機身份。需真分開 Gate HEAD SHA 與 Product `2ae01985`；啟動前 `Assert-TrackedTreeClean`、`Assert-CompleteWorktreeClean`、`Assert-ReleaseSourceSeparation` fail-closed 真執行，產品與 Gate 祖先關係及只限 `scripts/release/`、`tests/deployment/`、`docs/deployment/` 等原 allowlist。BUILD_APP 向正式 script 傳 `-OwnerSimplifiedPolicy -GateSourceSha <current gate HEAD> -ProductSourceSha 2ae...`，PACKAGE_STATIC 也傳確切分離 SHA，保留官方 BUILD_APP 所有原始測試和安全檢查。其它 10 phases 與 baseline exact pair/rollback、bounded retry、不寫玩家 PG 等全部不改。Dry Run 報告 gate 和 product SHA。

**治理**：不得在本輪未正式合併之前拿未審核 Gate script 直接部署。須單獨 GitHub PR＋現有 `g009-source-snapshot` required CI 核對精確 control-plane diff；必要時 Owner 另核准 G036 控制面 GO_MERGE，再從乾淨 GitHub 來源執行原有 bounded Recovery 對原 Product SHA `2ae01985`。即使 GO_DEPLOY 目標已獲明確核准，也不可跳過正式 CI 或 source integrity gate。


The actual separated Gate/Product Dry Run found that the required source CI path
.github/workflows/g009-source-snapshot.yml was classified as a Product diff.
PowerShell and Python both normalize it to github/workflows/g009-source-snapshot.yml,
which the prior exact-source allowlists omit. This patch adds ONLY that
required CI workflow to both allowlists; all other .github workflow paths,
GLBs and core app source must still be rejected. The GitHub exact diff scope
is six control-plane files.
