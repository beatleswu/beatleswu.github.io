#!/usr/bin/env bash
# G079 B1: fresh disposable PG DB + real app server + real Chrome driver, then shutdown/drop.
set -u
cd "$(dirname "$0")/../.."
OUT="${G079_EVIDENCE_DIR:-D:/g079-artifacts/a}"
mkdir -p "$OUT/chrome"
python -B tests/e2e/g079_mistakes_pg_browser_server.py > "$OUT/chrome_server.log" 2>&1 &
SERVER=$!
for i in $(seq 1 180); do
  grep -qE '"ready"|Traceback' "$OUT/chrome_server.log" && break
  sleep 1
done
if ! grep -q '"ready"' "$OUT/chrome_server.log"; then echo "server_not_ready"; kill $SERVER 2>/dev/null; exit 2; fi
node tests/e2e/g079_mistakes_pg_real_chrome.mjs > "$OUT/chrome_run.log" 2>&1
RC=$?
curl -s -X POST "http://127.0.0.1:${G079_BROWSER_PORT:-55491}/__g079/shutdown" > /dev/null
wait $SERVER
echo "chrome_exit=$RC"
grep -E '"stopped"' "$OUT/chrome_server.log"
exit $RC
