#!/bin/bash
# ── entrypoint.sh ──────────────────────────────────────────────
# 容器啟動時自動將需要持久化的檔案指向持久化目錄 /app/data/，
# 確保容器重建或更新時資料不會遺失。
#
# srs.db / go_learning.db 已於 DEPLOY-GOV-2E 移出：srs.db 內含真實使用者
# 資料（users/friendships/game_results/teacher_student...），且未被目前
# app.py/scheduler.py 以 sqlite3.connect() 開啟；go_learning.db 的兩張表
# （zones/grimoires）已由 app.py 直接建於 PostgreSQL，確認過時。兩者都不
# 再從 image 複製、不再納入此清單 -- entrypoint 不得為它們產生種子資料。
# ───────────────────────────────────────────────────────────────

DATA_DIR=/app/data
mkdir -p "$DATA_DIR"
mkdir -p "$DATA_DIR/tts_cache"

# 需要持久化的檔案清單（僅限非使用者資料的執行期產物）
PERSISTENT_FILES="go_app.db go_game.db secret_key.txt"

for f in $PERSISTENT_FILES; do
  # 如果持久化目錄中還沒有這個檔案，從 image 複製初始版本過去；
  # 若持久化目錄中已存在，絕不用 image 內容覆寫（保留既有資料）。
  if [ ! -f "$DATA_DIR/$f" ]; then
    if [ -f "/app/$f" ]; then
      echo "[entrypoint] 初始化: 複製 $f → $DATA_DIR/$f"
      cp "/app/$f" "$DATA_DIR/$f"
    fi
  fi
  # 刪除 image 內的複本，改用 symlink 指向持久化目錄
  rm -f "/app/$f"
  ln -sf "$DATA_DIR/$f" "/app/$f"
done

# assets/ 不再內建於 image（見 Dockerfile 的 App Image / Content Boundary
# 註解）；TTS 快取目錄仍需存在以供執行期寫入，故在此建立掛載點目錄，
# 不假設 /app/assets 已由 image COPY 建立。
mkdir -p /app/assets
rm -rf /app/assets/tts_cache
ln -sf "$DATA_DIR/tts_cache" /app/assets/tts_cache

echo "[entrypoint] 資料持久化設定完成，啟動應用程式..."
exec "$@"
