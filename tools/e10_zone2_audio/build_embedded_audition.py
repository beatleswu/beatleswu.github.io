"""Build a self-contained iPad-friendly copy of the local audition page."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "tools" / "e10_zone2_audio" / "_local_review" / "zone2_audio_audition"


def main() -> None:
    manifest = json.loads((PACK / "audition_manifest.json").read_text(encoding="utf-8"))
    rows = []
    items = []
    items.extend(("Locked Hero reference", x.get("locale", ""), x.get("relative_path"), "Unchanged Zone 1 byte; continuity reference only") for x in manifest.get("protagonist_reference", []))
    items.extend(("Herder voice", x["id"], x.get("relative_path"), x.get("description", "")) for x in manifest["herder_voice"]["candidates"])
    items.extend(("Protagonist continuity", x["id"], x.get("relative_path"), f"Shot {x['shot']} · locked Zone 1 Hero identity") for x in manifest.get("protagonist_lines", []))
    items.extend(("BGM " + x["phase"], x["id"], x.get("relative_path"), x["label"]) for x in manifest["bgm"])
    items.extend((x["kind"].upper(), x["id"], x.get("relative_path"), x["label"]) for x in manifest["sfx_ambient"])
    for category, ident, rel, note in items:
        if not rel:
            continue
        path = PACK / rel
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        rows.append(
            f"<section><h3>{html.escape(category)} · {html.escape(ident)}</h3>"
            f"<p>{html.escape(note)}</p><audio controls preload=\"none\" src=\"data:audio/mpeg;base64,{encoded}\"></audio></section>"
        )
    page = """<!doctype html><html lang="zh-Hant"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>E10 Zone 2 Audio Audition (Embedded)</title>
<style>body{font:16px system-ui,sans-serif;max-width:760px;margin:0 auto;padding:16px;background:#fffaf0;color:#24180d}section{padding:12px 0;border-bottom:1px solid #dbc8a6}audio{width:100%}small{color:#6f5a43}</style>
<h1>E10 Zone 2 Audio Audition</h1><p>Self-contained Phase 3 review pack. It can be opened directly on iPad or desktop; no network or runtime is required.</p>
<p><small>Owner-approved V2 only. Candidates are not canonical. `ZONE2_AUDIO_LOCK=PENDING_OWNER`.</small></p>
""" + "\n".join(rows) + "</html>\n"
    (PACK / "owner_audition_embedded.html").write_text(page, encoding="utf-8")
    print(f"EMBEDDED_AUDITION_HTML={PACK / 'owner_audition_embedded.html'}")
    print(f"EMBEDDED_AUDITION_BYTES={(PACK / 'owner_audition_embedded.html').stat().st_size}")


if __name__ == "__main__":
    main()
