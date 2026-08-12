"""Generate the Owner-only E10 Zone 2 Phase 3 audition pack.

This is deliberately separate from the Zone 1 final-audio tooling and from
runtime assets.  It creates review candidates under ``_local_review`` only;
it never writes ``assets/e10/audio/zone2`` or a canonical manifest.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import shutil
import sys
from pathlib import Path

from mutagen.mp3 import MP3


REPO_ROOT = Path(__file__).resolve().parents[2]
ZONE1_TOOL = REPO_ROOT / "tools" / "e10_zone1_audio" / "generate_zone1_audio.py"
OUT_ROOT = REPO_ROOT / "tools" / "e10_zone2_audio" / "_local_review" / "zone2_audio_audition"

ZONE1_HERO_ZH = REPO_ROOT / "assets" / "e10" / "audio" / "zone1" / "dialogue" / "zone1_final_shot06_beat01_zh_hero.mp3"
ZONE1_HERO_EN = REPO_ROOT / "assets" / "e10" / "audio" / "zone1" / "dialogue" / "zone1_final_shot06_beat01_en_hero.mp3"

HERDER_LINE_ZH = "以前這片草原不是這樣的。自從蜂巢那邊出了問題，牠們就沒睡過一天安穩覺。"
HERO_LINE_ZH = "牠們在發抖。不是想攻擊我們。是在害怕什麼。"
LORD_LINE_ZH = "為什麼要在意平衡？吞噬一切，才是真正的自由。"
POST_CLEAR_LINE_ZH = "牠們不是我們的敵人。我們只是，遇到了同一場病。"
PROTAGONIST_LINES = [
    {"id": "HERO_SHOT02", "shot": 2, "line": HERO_LINE_ZH},
    {"id": "HERO_SHOT09", "shot": 9, "line": POST_CLEAR_LINE_ZH},
]

HERDER_CANDIDATES = [
    {
        "id": "HERDER_V1",
        "name": "Ling - Steady, Calm and Grounded",
        "voice_id": "Z8Aisvg1z70p27kGvkZZ",
        "locale": "zh-TW",
        "description": "Adult female, grounded and composed; distinct from the locked male Hero/Elder/Messenger voices.",
    },
    {
        "id": "HERDER_V2",
        "name": "Yui - Delicate, Graceful and Soothing",
        "voice_id": "kGjJqO6wdwRN9iJsoeIC",
        "locale": "zh-TW",
        "description": "Young-adult female, warm and concerned; auditioned for Herder only, not a Zone 1 recast.",
    },
    {
        "id": "HERDER_V3",
        "name": "Zack - Soft and Friendly",
        "voice_id": "DSyEP4HEaCKur8rFFOri",
        "locale": "zh-TW",
        "description": "Young-adult male with a softer Taiwanese-Mandarin read; separated from the locked Hero and Messenger IDs.",
    },
]

BGM_CANDIDATES = [
    {
        "id": "A1",
        "phase": "A",
        "label": "Discovery / flute-led",
        "length_ms": 30000,
        "prompt": "Instrumental fantasy game music for a warm golden grassland discovery, solo wooden flute, soft acoustic guitar, light strings and distant water, pastoral and magical with a subtle thread of unease, child-friendly, cinematic but restrained, no percussion, no vocals, loop-friendly, leaves clear headroom for dialogue",
    },
    {
        "id": "A2",
        "phase": "A",
        "label": "Discovery / harp and strings",
        "length_ms": 30000,
        "prompt": "Instrumental cinematic music for entering a bright golden fantasy grassland, gentle harp arpeggios, warm violin and cello, airy woodwind, curious and compassionate rather than triumphant, a faint environmental mystery, child-friendly, no vocals, no heavy drums, dialogue-friendly and loopable",
    },
    {
        "id": "A3",
        "phase": "A",
        "label": "Discovery / pastoral bells",
        "length_ms": 30000,
        "prompt": "Instrumental children's fantasy adventure discovery cue, soft marimba and celesta with pastoral flute, open grassland warmth, small suspended notes suggesting that frightened creatures need help, subtle unease but never horror, no vocals, no bombast, dialogue-friendly and loop-friendly",
    },
    {
        "id": "B1",
        "phase": "B",
        "label": "Escalation / low strings",
        "length_ms": 30000,
        "prompt": "Instrumental cinematic escalation for a bright fantasy grassland threatened by an infected honeycomb cave, low strings, restrained pulse, distant metallic wing shimmer and heroic anticipation, danger rising without horror or final-boss scale, child-friendly, no vocals, dialogue-friendly",
    },
    {
        "id": "B2",
        "phase": "B",
        "label": "Escalation / swarm tension",
        "length_ms": 30000,
        "prompt": "Instrumental fantasy adventure tension cue, layered pizzicato strings, muted hand percussion and a controlled buzzing shimmer, slimes fleeing toward a cave and a giant slime lord awakening, exciting but not frightening, no vocals, no giant final battle, clear space for a short creature voice",
    },
    {
        "id": "B3",
        "phase": "B",
        "label": "Escalation / heroic restraint",
        "length_ms": 30000,
        "prompt": "Instrumental heroic anticipation for a child-friendly fantasy confrontation with a colossal blue slime lord under a honeycomb cliff, warm brass-like synth pads, low cello pulse and restrained drums, brave and urgent but not militaristic or horror, no vocals, no overwhelming climax, dialogue-friendly",
    },
    {
        "id": "C1",
        "phase": "C",
        "label": "Recovery / warm piano",
        "length_ms": 30000,
        "prompt": "Instrumental warm recovery music after a fantasy slime lord is defeated, gentle piano, flute and soft strings, peaceful grassland returning to sunlight, compassionate small victory, no triumphal fanfare, no vocals, child-friendly, forward-looking and dialogue-friendly",
    },
    {
        "id": "C2",
        "phase": "C",
        "label": "Recovery / celesta and strings",
        "length_ms": 30000,
        "prompt": "Instrumental cinematic relief for a bright fantasy plain becoming peaceful again, celesta, harp and tender strings, calm slimes and warm evening air, modest victory with wonder and emotional release, not an ending or finale, no vocals, gentle loop-friendly cue",
    },
    {
        "id": "C3",
        "phase": "C",
        "label": "Recovery / journey horizon",
        "length_ms": 30000,
        "prompt": "Instrumental forward-looking fantasy journey cue after healing a golden slime plain, acoustic guitar, airy flute, soft strings and a small rising motif toward the next road, warm and hopeful, peaceful but unfinished, not finale music, no vocals, child-friendly and dialogue-friendly",
    },
]

SFX_CANDIDATES = [
    {
        "id": "AMBIENT_GRASSLAND",
        "kind": "ambient",
        "label": "Golden grassland bed",
        "duration": 12,
        "prompt": "Loopable golden fantasy grassland ambience, gentle wind through tall grass, distant stream and soft birds, a few harmless slime plops far away, warm daylight, no music, no voices, no buzzing close to the listener",
    },
    {
        "id": "SFX_FRIGHTENED_SLIME",
        "kind": "sfx",
        "label": "Frightened slime tremble",
        "duration": 2,
        "prompt": "Small frightened friendly slime whimper and trembling gelatin wobble, soft watery wobble, sympathetic and child-friendly, no speech, no attack sound, very short isolated sound effect",
    },
    {
        "id": "SFX_SLIME_MOVEMENT",
        "kind": "sfx",
        "label": "Normal slime movement",
        "duration": 2,
        "prompt": "Small friendly slime hopping across damp grass, two soft gelatinous plops and a light watery bounce, playful but natural, no music, no speech, isolated short sound effect",
    },
    {
        "id": "AMBIENT_BEE_DISTANT",
        "kind": "ambient",
        "label": "Distant bee swarm",
        "duration": 8,
        "prompt": "Distant bee swarm over a wide sunny fantasy plain, soft airy buzzing far from the listener, uneasy but not horror, wind and open space remain audible, no close stings, no music, loopable ambience",
    },
    {
        "id": "SFX_BEE_CLOSE",
        "kind": "sfx",
        "label": "Close bee pass",
        "duration": 3,
        "prompt": "A few bees rush close past the listener with a fast wing buzz and air movement, cinematic but not frightening, no sting, no music, isolated short sound effect",
    },
    {
        "id": "AMBIENT_HIVE_CAVE",
        "kind": "ambient",
        "label": "Infected hive cave",
        "duration": 10,
        "prompt": "Honeycomb-covered mountainside cave ambience, hollow stone air, slow wax drips, distant layered bee hum and a faint watery crystal pulse, sick environmental unease without horror, no music, no voices, loopable",
    },
    {
        "id": "SFX_LORD_EMERGENCE",
        "kind": "sfx",
        "label": "Swarm Lord emergence",
        "duration": 5,
        "prompt": "Colossal blue slime lord emerging from a honeycomb cave, liquid mass gathering with deep wet suction, bubbling crystal resonance and a restrained low swell, creature-only sound, no words, no human voice, cinematic reveal",
    },
    {
        "id": "SFX_LORD_MOVEMENT",
        "kind": "sfx",
        "label": "Swarm Lord movement",
        "duration": 4,
        "prompt": "Huge friendly-fantasy slime lord shifting its weight, heavy liquid body roll, wet elastic movement and small crystal droplets, powerful but not violent, no speech, isolated creature movement sound",
    },
    {
        "id": "SFX_LORD_RUMBLE",
        "kind": "sfx",
        "label": "Swarm Lord low rumble",
        "duration": 5,
        "prompt": "Deep liquid low rumble from a colossal slime creature, resonant watery throat-like vibration with distant honeycomb resonance, nonverbal creature vocal only, no human words, intimidating but tragic and child-friendly",
    },
    {
        "id": "SFX_LORD_DEFEAT",
        "kind": "sfx",
        "label": "Lord defeat collapse",
        "duration": 5,
        "prompt": "A giant blue slime lord gently collapses after defeat, large soft water splash, gelatin settling, a few crystal droplets and a quiet exhale-like bubble, emotional release, no explosion, no horror, isolated sound effect",
    },
    {
        "id": "SFX_CROWN_IMPACT",
        "kind": "sfx",
        "label": "Crown crest impact",
        "duration": 2,
        "prompt": "A translucent watery crown crest lightly strikes stone and rings with a soft crystal chime, brief liquid splash, magical but restrained, no music, isolated short sound effect",
    },
    {
        "id": "AMBIENT_PLAINS_RECOVERY",
        "kind": "ambient",
        "label": "Plains recovery",
        "duration": 10,
        "prompt": "Peaceful golden grassland recovery ambience after a sickness lifts, warm breeze, distant stream, calm small slime plops, a few gentle birds, no bees close by, no music, no voices, loopable",
    },
    {
        "id": "SFX_ROUTE_REVEAL",
        "kind": "sfx",
        "label": "Zone 3 route reveal stinger",
        "duration": 4,
        "prompt": "Soft magical route-reveal stinger for a fantasy world map, gentle crystal pulse, warm rising chime and a small forward-pointing shimmer, hopeful and restrained, not a victory fanfare, no music bed",
    },
    {
        "id": "SFX_SHUI_REACTION_A",
        "kind": "sfx",
        "label": "Water Spirit Horse reaction A",
        "duration": 3,
        "prompt": "Small juvenile water spirit horse reaction, airy liquid whicker with tiny glassy droplets and a soft breath, cute but not cartoonish, nonverbal creature only, no words, no full-sized horse neigh",
    },
    {
        "id": "SFX_SHUI_REACTION_B",
        "kind": "sfx",
        "label": "Water Spirit Horse reaction B",
        "duration": 3,
        "prompt": "Small blue water spirit companion gives a quiet concerned chirp made of water bubbles and a delicate crystalline shimmer, nonverbal, gentle and magical, no words, no human speech, no full-sized horse neigh",
    },
]


def _load_zone1_tool():
    spec = importlib.util.spec_from_file_location("e10_zone1_audio_tool", ZONE1_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {ZONE1_TOOL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _file_meta(path: Path, *, source: str | None = None, **extra: object) -> dict:
    data = path.read_bytes()
    result = {
        "file": path.name,
        "relative_path": path.relative_to(OUT_ROOT).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    try:
        result["duration_seconds"] = round(float(MP3(path).info.length), 3)
    except Exception:
        result["duration_seconds"] = None
    if source:
        result["source"] = source
    result.update(extra)
    return result


def _safe_generate(callable_, api_key: str, *args):
    try:
        return bool(callable_(api_key, *args))
    except Exception as exc:  # retain a structured failure for the Owner
        print(f"GENERATION_EXCEPTION={type(exc).__name__}:{exc}", file=sys.stderr)
        return False


def _write_owner_index(manifest: dict) -> None:
    rows = []
    for item in manifest.get("protagonist_reference", []):
        rows.append(("Locked Hero reference", item.get("locale", ""), item.get("relative_path"), "Unchanged Zone 1 byte; continuity reference only"))
    for item in manifest.get("protagonist_lines", []):
        rows.append(("Protagonist continuity", item["id"], item.get("file"), f"Shot {item['shot']} · locked Zone 1 Hero identity"))
    for item in manifest["herder_voice"]["candidates"]:
        rows.append(("Herder voice", item["id"], item.get("file"), item.get("description", "")))
    for item in manifest["bgm"]:
        rows.append((f"BGM {item['phase']}", item["id"], item.get("file"), item["label"]))
    for item in manifest["sfx_ambient"]:
        rows.append((item["kind"].upper(), item["id"], item.get("file"), item["label"]))

    audio_blocks = []
    for category, ident, file_name, note in rows:
        if not file_name:
            continue
        rel = html.escape(file_name)
        audio_blocks.append(
            f"<section><h3>{html.escape(category)} · {html.escape(ident)}</h3>"
            f"<p>{html.escape(note)}</p><audio controls preload=\"none\" src=\"{rel}\"></audio></section>"
        )

    html_doc = """<!doctype html>
<html lang="zh-Hant"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>E10 Zone 2 Audio Audition</title>
<style>body{font:16px system-ui,sans-serif;max-width:760px;margin:0 auto;padding:16px;background:#fffaf0;color:#24180d}section{padding:12px 0;border-bottom:1px solid #dbc8a6}audio{width:100%}small{color:#6f5a43}</style>
<h1>E10 Zone 2 Audio Audition</h1>
<p>Phase 3 candidates only. Nothing here is runtime-canonical. Listen in order on iPad or desktop.</p>
<p><small>Locked V2 spoken lines: Shot 2 Hero · Shot 4 Herder · Shot 7 Swarm Lord nonverbal treatment · Shot 9 Hero. English dialogue is intentionally not generated in this gate.</small></p>
""" + "\n".join(audio_blocks) + "</html>\n"
    (OUT_ROOT / "index.html").write_text(html_doc, encoding="utf-8")


def _write_shot_map(manifest: dict) -> None:
    herder = ", ".join(item.get("id", "") for item in manifest["herder_voice"]["candidates"])
    bgm = {phase: ", ".join(item["id"] for item in manifest["bgm"] if item["phase"] == phase) for phase in ("A", "B", "C")}
    hero = ", ".join(item.get("id", "") for item in manifest.get("protagonist_lines", []))
    lines = [
        "# E10 Zone 2 provisional shot audio map — Phase 3 audition only",
        "",
        "`ZONE2_AUDIO_LOCK=PENDING_OWNER`; candidate IDs below are not runtime assets.",
        "English dialogue is intentionally deferred because Owner locked the supplied V2 dialogue, not a new English localization.",
        "",
        "| Shot | Script / speaker | Voice candidate(s) | BGM candidates | Ambient / SFX candidates | Notes |",
        "|---:|---|---|---|---|---|",
        f"| 1 | Silent arrival | none | {bgm['A']} | `AMBIENT_GRASSLAND`, `SFX_SHUI_REACTION_A/B` | Warm plains establishment; Shui remains nonverbal |",
        f"| 2 | Hero: `{HERO_LINE_ZH}` | `{hero}` + locked Zone 1 Hero reference (Roy) | {bgm['A']} | `SFX_FRIGHTENED_SLIME`, `SFX_SLIME_MOVEMENT`, `AMBIENT_GRASSLAND` | Exact V2 line; same locked Hero identity |",
        f"| 3 | Silent Herder arrival | `HERDER_V1/V2/V3` for comparison | {bgm['A']} | `SFX_SLIME_MOVEMENT`, `SFX_SHUI_REACTION_A/B` | Use only after Owner hears Herder candidates |",
        f"| 4 | Herder: `{HERDER_LINE_ZH}` | `HERDER_V1/V2/V3` | {bgm['A']} | `AMBIENT_BEE_DISTANT`, `AMBIENT_HIVE_CAVE`, `SFX_BEE_CLOSE` | Exact locked V2 line; full hive reveal |",
        f"| 5 | Silent escalation | none | {bgm['B']} | `AMBIENT_BEE_DISTANT`, `SFX_BEE_CLOSE`, `SFX_SHUI_REACTION_B` | Environmental escalation only |",
        f"| 6 | Silent Swarm Lord reveal | no human dialogue | {bgm['B']} | `AMBIENT_HIVE_CAVE`, `SFX_LORD_EMERGENCE`, `SFX_LORD_RUMBLE` | Giant slime creature vocal treatment |",
        f"| 7 | Challenge handoff; no automatic trial | no human dialogue; creature vocal only | {bgm['B']} | `SFX_LORD_RUMBLE`, `SFX_LORD_MOVEMENT`, `SFX_CROWN_IMPACT` | Swarm Lord stays a giant slime, not a bee/humanoid |",
        f"| 8 | Silent Lord defeat | none | {bgm['C']} | `SFX_LORD_DEFEAT`, `AMBIENT_PLAINS_RECOVERY` | No victory dialogue |",
        f"| 9 | Hero: `{POST_CLEAR_LINE_ZH}` | `{hero}` + locked Zone 1 Hero reference (Roy) | {bgm['C']} | `AMBIENT_PLAINS_RECOVERY`, `SFX_SHUI_REACTION_A` | Exact V2 line; same locked Hero identity |",
        f"| 10 | Silent forward route hook | none | {bgm['C']} | `SFX_ROUTE_REVEAL` | Not finale; route points toward Zone 3 |",
        "",
        f"HERDER_CANDIDATES={herder}",
        "PROTAGONIST_VOICE_CONTINUITY=locked Zone 1 Hero identity; reference bytes copied unchanged for listening only",
        "WATER_SPIRIT_HORSE_AUDIO_CONTINUITY=NONVERBAL; two subtle creature-reaction candidates only",
        "SWARM_LORD_VOICE_MODEL=creature-vocal/liquid low rumble; no TTS human dialogue",
    ]
    (OUT_ROOT / "shot_audio_map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_notes(manifest: dict) -> None:
    notes = """# Owner listening notes

## Scope

This folder is the Phase 3 audition pack for E10 Zone 2. It is intentionally
not a runtime package. No file is canonical, and no audio manifest under
`assets/e10/audio/zone2/` was created.

## Listening order

1. `voice/herder/` — compare HERDER_V1, V2, V3 using the identical locked V2
   Herder line. They are deliberately selected away from the locked Zone 1
   Hero, Elder, and Messenger IDs.
2. `voice/protagonist_zone2/` — the two Owner-approved V2 Hero lines rendered
   with the locked Zone 1 Hero identity, plus `voice/protagonist_reference/`
   unchanged Zone 1 references.
3. `bgm/A/`, `bgm/B/`, `bgm/C/` — select one direction per phase; all candidates
   are dialogue-friendly and not finale music.
4. `sfx_ambient/` — listen to the environmental palette and the key Lord/Shui
   cues. Swarm Lord is nonverbal; no human Lord TTS was generated.

## Owner decisions still pending

`HERDER_VOICE=`
`BGM_A=`
`BGM_B=`
`BGM_C=`
`SFX_PALETTE=`
`SHUI_REACTION=`
`SWARM_LORD_RUMBLE=`

After those choices, the next gate is `ZONE2_AUDIO_LOCK=YES`; only then may
selected bytes be prepared for canonical integration.
"""
    (OUT_ROOT / "audition_notes.md").write_text(notes, encoding="utf-8")


def main() -> int:
    z1 = _load_zone1_tool()
    api_key = z1.get_api_key()
    model_id = z1.get_model_id()

    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    for sub in ("voice/herder", "voice/protagonist_reference", "bgm/A", "bgm/B", "bgm/C", "sfx_ambient"):
        (OUT_ROOT / sub).mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "e10-zone2-audio-audition-v1",
        "status": "AUDITION_ONLY_OWNER_REVIEW_REQUIRED",
        "zone": "k21_25",
        "script_version": "OWNER_APPROVED_V2",
        "provider": "ElevenLabs",
        "model": model_id,
        "runtime_integrated": False,
        "canonical_manifest_created": False,
        "owner_audio_lock": False,
        "herder_voice": {"line_zh_tw": HERDER_LINE_ZH, "candidates": []},
        "protagonist_lines": [],
        "protagonist_reference": [],
        "water_spirit_horse": {"model": "NONVERBAL_CREATURE_REACTIONS", "candidates": []},
        "swarm_lord": {"model": "NONVERBAL_LIQUID_CREATURE_VOCAL", "human_dialogue_generated": False},
        "bgm": [],
        "sfx_ambient": [],
    }

    # Exact Zone 1 Hero bytes are copied only into the review pack for A/B
    # continuity listening; the source files and their manifests are untouched.
    for source, dest_name, locale in (
        (ZONE1_HERO_ZH, "protagonist_zone1_hero_zh_reference.mp3", "zh-TW"),
        (ZONE1_HERO_EN, "protagonist_zone1_hero_en_reference.mp3", "en"),
    ):
        dest = OUT_ROOT / "voice" / "protagonist_reference" / dest_name
        shutil.copyfile(source, dest)
        manifest["protagonist_reference"].append(_file_meta(dest, source=source.relative_to(REPO_ROOT).as_posix(), locale=locale, locked_identity=True))

    for candidate in HERDER_CANDIDATES:
        path = OUT_ROOT / "voice" / "herder" / f"{candidate['id'].lower()}.mp3"
        ok = _safe_generate(z1._text_to_speech, api_key, candidate["voice_id"], HERDER_LINE_ZH, model_id, path)
        record = {**candidate, "file": path.name if ok else None, "generated": ok, "settings": "NOT_RECORDED_IN_ZONE1_LOCK"}
        if ok:
            record.update(_file_meta(path, locale="zh-TW", script_line=HERDER_LINE_ZH))
            record["file"] = record["relative_path"]
        manifest["herder_voice"]["candidates"].append(record)

    for item in SFX_CANDIDATES:
        path = OUT_ROOT / "sfx_ambient" / f"{item['id'].lower()}.mp3"
        ok = _safe_generate(z1._sound_effect, api_key, item["prompt"], item["duration"], path)
        record = {**item, "file": path.name if ok else None, "generated": ok, "source": "ElevenLabs sound-generation"}
        if ok:
            record.update(_file_meta(path))
            record["file"] = record["relative_path"]
        manifest["sfx_ambient"].append(record)
        if item["id"].startswith("SFX_SHUI"):
            manifest["water_spirit_horse"]["candidates"].append(record)

    for item in BGM_CANDIDATES:
        path = OUT_ROOT / "bgm" / item["phase"] / f"{item['id'].lower()}.mp3"
        ok = _safe_generate(z1._music, api_key, item["prompt"], item["length_ms"], path)
        record = {**item, "file": f"bgm/{item['phase']}/{path.name}" if ok else None, "generated": ok, "source": "ElevenLabs music-generation"}
        if ok:
            record.update(_file_meta(path))
            record["file"] = record["relative_path"]
        manifest["bgm"].append(record)

    manifest["generation_summary"] = {
        "herder_expected": len(HERDER_CANDIDATES),
        "herder_generated": sum(bool(x.get("generated")) for x in manifest["herder_voice"]["candidates"]),
        "bgm_expected": len(BGM_CANDIDATES),
        "bgm_generated": sum(bool(x.get("generated")) for x in manifest["bgm"]),
        "sfx_ambient_expected": len(SFX_CANDIDATES),
        "sfx_ambient_generated": sum(bool(x.get("generated")) for x in manifest["sfx_ambient"]),
    }
    (OUT_ROOT / "audition_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_shot_map(manifest)
    _write_notes(manifest)
    _write_owner_index(manifest)

    print("ZONE2_SCRIPT_VERSION=OWNER_APPROVED_V2")
    print(f"HERDER_VOICE_CANDIDATES={manifest['generation_summary']['herder_generated']}/{manifest['generation_summary']['herder_expected']}")
    print(f"BGM_A_CANDIDATES={sum(x.get('generated') and x['phase']=='A' for x in manifest['bgm'])}/3")
    print(f"BGM_B_CANDIDATES={sum(x.get('generated') and x['phase']=='B' for x in manifest['bgm'])}/3")
    print(f"BGM_C_CANDIDATES={sum(x.get('generated') and x['phase']=='C' for x in manifest['bgm'])}/3")
    print(f"SFX_AUDITION_STATUS={manifest['generation_summary']['sfx_ambient_generated']}/{manifest['generation_summary']['sfx_ambient_expected']}")
    print(f"AUDITION_PACK={OUT_ROOT.resolve()}")
    complete = all(v == e for key, v, e in (("herder", manifest['generation_summary']['herder_generated'], manifest['generation_summary']['herder_expected']), ("bgm", manifest['generation_summary']['bgm_generated'], manifest['generation_summary']['bgm_expected']), ("sfx", manifest['generation_summary']['sfx_ambient_generated'], manifest['generation_summary']['sfx_ambient_expected'])))
    print(f"AUDITION_GENERATION={('PASS' if complete else 'PARTIAL')}")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
