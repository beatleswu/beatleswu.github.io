#!/bin/bash
# ── entrypoint.sh ──────────────────────────────────────────────
# 容器啟動時自動將 SQLite 資料庫指向持久化目錄 /app/data/，
# 確保容器重建或更新時用戶資料不會遺失。
# ───────────────────────────────────────────────────────────────

DATA_DIR=/app/data
mkdir -p "$DATA_DIR"
mkdir -p "$DATA_DIR/tts_cache"

# 需要持久化的檔案清單
PERSISTENT_FILES="srs.db go_learning.db go_app.db go_game.db secret_key.txt"

for f in $PERSISTENT_FILES; do
  # 如果持久化目錄中還沒有這個檔案，從 image 複製初始版本過去
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

# TTS 快取目錄也指向持久化路徑
rm -rf /app/assets/tts_cache
ln -sf "$DATA_DIR/tts_cache" /app/assets/tts_cache

echo "[entrypoint] 資料持久化設定完成，啟動應用程式..."
exec "$@"
