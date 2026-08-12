"""Build a single-file iPad-friendly copy of the Herder re-audition pack."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tools" / "e10_zone2_audio" / "_local_review" / "zone2_audio_audition" / "herder_reaudition"
MANIFEST = OUT / "reaudition_manifest.json"


def _data_url(path: Path) -> str:
    return "data:audio/mpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for candidate in manifest["candidates"]:
        context = OUT / Path(candidate["context_audio"]).name
        phrase = OUT / Path(candidate["phrase_audio"]).name
        if not context.is_file() or not phrase.is_file():
            raise SystemExit(f"missing re-audition audio for {candidate['id']}")
        rows.append(
            "<section class='card'>"
            f"<h2>{html.escape(candidate['id'])} — {html.escape(candidate['label'])}</h2>"
            f"<p>{html.escape(candidate['description'])}</p>"
            f"<p><b>牧者 context（書面台詞保持原文）：</b> {html.escape(candidate['written_dialogue'])}</p>"
            f"<audio controls preload='metadata' src='{_data_url(context)}'></audio>"
            f"<p><b>發音檢查：</b> {html.escape(candidate['written_phrase'])} → <code>jiào / ㄐㄧㄠˋ</code></p>"
            f"<audio controls preload='metadata' src='{_data_url(phrase)}'></audio>"
            "<p class='note'>TTS-only：為控制讀音將最後的「覺」以同音「叫」送入 TTS；書面台詞沒有更改。</p>"
            "</section>"
        )
    frozen = "".join(
        f"<li>{html.escape(name)} — {item['sha256']} ({item['bytes']} bytes), preserved</li>"
        for name, item in manifest["frozen_approved_assets"].items()
    )
    page = """<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Zone 2 Herder re-audition (embedded)</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.55;margin:0;background:#fbf8f0;color:#26231f}main{max-width:760px;margin:auto;padding:18px}.card{background:#fff;border-radius:14px;padding:16px;margin:14px 0;box-shadow:0 2px 12px #0001}audio{width:100%;margin:8px 0}.note{font-size:.9em;color:#6a6258}code{font-size:1.05em}</style></head><body><main>
<h1>Zone 2 牧者 V4–V6 re-audition</h1><p>這是單檔 iPad audition pack。A3/B3/C3、Shui 2 與其他已核准音效維持凍結。</p>
<h2>Frozen approved bytes</h2><ul>__FROZEN__</ul>__ROWS__
<p class='note'>所有音檔嵌在本 HTML；仍是 audition-only，尚未 Audio Lock 或 runtime 整合。模型：__MODEL__。</p>
</main></body></html>"""
    page = page.replace("__FROZEN__", frozen).replace("__ROWS__", "".join(rows)).replace("__MODEL__", html.escape(manifest["model"]))
    output = OUT / "herder_reaudition_embedded.html"
    output.write_text(page, encoding="utf-8")
    print(f"EMBEDDED_REAUDITION_PACK={output.resolve()}")
    print(f"EMBEDDED_AUDIO_CONTROLS={page.count('<audio controls')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
