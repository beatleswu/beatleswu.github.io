# G030｜69 款已規劃 3D 資產公開展示啟用（isolated acceptance）

日期：2026-10-22。Owner 本輪明確要求「主要目標就是啟用這些 3d 資產」，並已糾正「69 GLB 因不是既有正式站資產就不能公開」的過廣推論。

## 正式範圍與真實模型

原有 G009 exact SHA 與 GLB bytes 完全保留：Hero 47 (Future30 33、D007 Head/Back 6、non-retired original equipment 8)、Companion formal_18 18、Formal9 4，總數恰 69 款 canonical Static GLB。另保留 P048 既有兩款 bonus preview；Hero 頁面的選單從 63 款提升為 71 款，其中原本缺席的 8 款 non-retired 裝備現在可選，透過嚴格 retired-id 排除與 SHA-256 browser 檢查呈現。

此功能僅為實際 WebGL 模型載入、旋轉與視覺展示。**公開 3D 視覺展示不會授予 item ownership，也不會啟用 Shop 購買、物品掉落、角色選取或 Equip。** D007 原有 NOT_CLEARED／equip_capability=false 不改；G011 P022/P038 私有 QA 模型不加入正式公開清單，歷史 G011 91 款內部 QA 計數維持原樣。

Formal9 的四款是 Owner 已於 2026-09-28 4/4 選定且記錄 CC0-1.0 RIGHTS_CLEARED 的替換模型。本輪依 Owner 2026-10-22 公開視覺展示目的增設獨立 `PUBLIC_3D_PREVIEW_ADMITTED=true`（JS runtime+schema mirror）與 `public_3d_preview_admission=true`（Static pack manifest），3D viewer fail-closed 核驗這一欄；**舊的 `RELEASE_ENABLED=false`、`PRODUCTION_ASSET_ADMISSION=false` 與 `RIGHTS_CLEARED_RELEASE_NOT_ADMITTED` 仍保留做為玩家產品准入/其他功能權限的原有狀態，不冒充全面放行。** 其餘 D007 舊的條目仍 NOT_CLEARED、不可裝備。

五款 J-Toastie CC-BY-3.0 帽飾商用來源在 Hero 實際畫面新增清楚的作者／來源／授權連結。所有 GLB 完整位元組及 SHA、原證據、V4 歷史零改寫。

## 已實際完成，不是文件取代驗收

- beatles 的隔離 Git worktree：`D:\go-odyssey-g030-3d-activation-20261022`，起點 GitHub master `283dc22b8e1685732443d781074b6f4216ca3dea`，獨立 branch `g030-3d-public-assets-20261022`。
- 真實 Chrome headless + WebGL + GLTFLoader，從 loopback 靜態服務逐一載入、SHA-256 核對及渲染 **71/71 項**，包含全部 69 canonical GLB + 兩個既有 bonus。完成 **85 個檢查 PASS**，HTTP errors 0、JS errors 0，包含觸控友善的 Canvas Pointer / 拖曳後圖像像素改變／資源釋放及重開。加入 PUBLIC_3D_PREVIEW_ADMITTED 的最終版本再跑一次也是 **71/71、85 PASS**。
- G030 69 GLB manifest SHA / GLB magic header/length，Python regression。歷史 G010/G009 與 G025/G026 不改 QA 意義。實際瀏覽器機器證據存於 `D:\go-odyssey-g030-evidence-20261022\G030_3D_ALL_71_REAL_WEBGL_BROWSER_20261022.json`；不將實驗證據覆寫早先 G010/G011 收據。
- 本階段沒有修改任何 GLB byte、沒有正式玩家 DB 讀寫或權限發放、沒有重啟生產服務。

## 下一個必要 Owner Gate

正式 GitHub master merge `GO_MERGE` **需這次 G030 的獨立明確核准**（此前 G027/G028 針對其他限定範圍的批准不可自動重複使用），必須走現有 GitHub ruleset 的 `g009-source-snapshot`，不得跳過。合併後要以新的正式 master source SHA 重建官版 ARM64 Image + Static，完成真機 iPad Safari UAT；僅在部署前所有既有安全 Gate 都滿足時才可依前次有條件 GO_DEPLOY 授權執行。當前 Oracle 生產仍是舊版，NO_DEPLOY / 玩家資料 NO_WRITE。
