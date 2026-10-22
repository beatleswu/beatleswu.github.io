# G043｜Owner 核准 C01 Bunny／C04 Corgi 獨立補充 Static 發布

2026-10-22｜正式 GitHub master基準 `dcf56dcc58e3a2bd15565998bb31c622f66b6eeb`。本文件只記錄這次 **2 GLB＋1 PNG 補充資產准入及隔離候選**，不是正式 Oracle 部署成功收據。

## Owner 的准入範圍

Owner 回覆「授權」，承接上一輪單獨要求 G043 的 Bunny、Corgi 兩個 GLB 與一張 PNG 材質，作為**獨立 Supplemental Static 資產包**准入。原正式 Hero 47＋Companion formal18 18＋Formal9 4＝**69 個正式 GLB 一個都不改**。原 G010 source evidence `docs/handoffs/G010_P048_C01_C04_IMAGE_CLOSURE_20261021.json` 仍如實紀錄當時 `release_admission:false`，不能改寫歷史。

最新 `deploy/g043-bonus-companion-supplemental-static-pack-manifest.json` 把批准限於：
- `assets/3d_shop/p048/companion/C01/animal-bunny.glb` — 131568 bytes, SHA256 `94b654915d9de70071bcf0bfa13de379a3ba4fdfeb231f0fec49335232cbc821`
- `assets/3d_shop/p048/companion/C04/Corgi.glb` — 73516 bytes, SHA256 `95cd2c4d53d70ee9dd2e1329dcb6de7d4a725301d504a4f2f00ecb34dc1a0851`
- `assets/3d_shop/p048/companion/C01/Textures/colormap.png` — 10915 bytes, SHA256 `2f6d0032e51c2d49b13b8e689d59eb39aa3ee6c32f2a1851213e11fc7593177d`

共 **215999 bytes**（exact sizes and hashes verified against original source before pack creation）。原 `assets/3d_shop/p048/runtime_manifest.json` 的 C01/C04 既有 pet_key runtime ownership gate 保持不變；**不新增寵物、玩家擁有權、貨幣道具、購買、給予或正式DB寫入**。靜態可取用的模型檔 != 玩家有權取得或裝備。

## 正式發布整合

`deploy/live-static-asset-inventory.json` 的 `required_subtrees.entries` 加**唯一一筆**指向新的 Supplemental Manifest。靜態發布由既有 `package-static-release.ps1`／`New-StaticReleaseBundle` 根據manifest嚴格驗每一byte的 size/SHA，把三檔放入同一次Generation；不允許目錄全量copy、額外GLB/PNG或 wildcard。原雙渠道 App fallback bytes 不動。原 `tests/deployment/test_g009_dual_delivery_closure.py` 保留 formally 69 total GLB，另精確驗兩bonus GLB；`test_image_content_boundary.py` 納入新的獨立清單，且保留 image-only support 例外原樣。新 `test_g043_bonus_supplemental_static_pack.py` 提供正例/篡改內容、檔案數、玩家權限和69數目不變的負例。現有 required GitHub CI 精確 23檔 scope，還須比對整份舊 inventory 除唯一新條目外完全相同，並重驗三檔與舊證據實體bytes，原 `app.py`、`hero.html`、69GLB 與已知 Oracle rollback檔必須字節不變。

**流程分界**：本隔離 Product 候選將產生新的 Git SHA。即使補充包的 Public Asset admission已授權，G043 PR正式合併 `GO_MERGE` 及新SHA的 `GO_DEPLOY_WITH_BOUNDED_RECOVERY` 仍須各自具體Owner Gate；之前產品2ae01985的部署核准不得直接用來部署未知新SHA。完整官方 BUILD_APP 1695+ JUnit在乾淨受治理新Gate必須真PASS、靜態TAR 2346個文件全部SHAPASS、Oracle dry-run/backup/rollback/真機UAT必要條件都通過，才可正式發版。正式Players DB NO_WRITE、QuestV2/D015 migration OFF。
