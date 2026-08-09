# E10 Zone 1 (Newbie Village) Local Audio Tooling

Local-only tooling for generating ElevenLabs voice audio for the canonical
Zone 1 (`k26_30`) bilingual cinematic. **This must be run on the Owner's
local Windows machine, in the canonical repo/worktree** — the remote Claude
Web sandbox cannot reach `api.elevenlabs.io` (egress policy blocks it), and
this tool must never be run there.

## Scope

- Sprint: `E10-Z1-AUDIO-PRODUCTION-001`.
- No deploy. No Production contact. No SGF Engine / Codex involvement.
- This tool only generates local review assets. It never touches
  `deploy/*`, `sw.js`, or any canonical asset manifest, and it never marks
  anything as a production asset automatically.

## Files

- `zone1_beat_manifest.json` — mechanical extraction of every spoken beat
  in the shipped Zone 1 cinematic (shot, beat, phase, speaker, locale,
  exact canonical text, `voice_id` placeholder, proposed output filename).
  Do not hand-edit dialogue text here — the source of truth is `index.html`
  (`getIntroFilmLocaleConfig` → `k26_30`); if the script ever changes,
  re-extract instead of editing this file directly.
- `casting_candidates.json` — Owner-editable casting sheet. Fill in a
  `voice_id` per role x locale to enable that line in `--audition`. Leave
  `voice_id: null` to skip it.
- `generate_zone1_audio.py` — the CLI (stdlib-only, no extra pip installs).
- `_local_review/` — generated audio lands here (git-ignored). Never
  auto-promoted to a canonical asset path.

## Credential handling (read this before running anything)

- The tool reads `ELEVENLABS_API_KEY` **only** from the current process
  environment. It never reads `secret_key.txt`, `.env`, or any other file
  for the key.
- The key is never printed, logged, or written to disk by this tool.
- Do not paste the key into chat, into this repo, or into any commit.
- Unset the variable when you're done for the session (command below).

## Windows PowerShell usage

Run these from a PowerShell prompt in the canonical repo/worktree root.

**1. Set the key for the current process only** (not saved to your profile,
not visible to other processes, cleared when you close the window):

```powershell
$env:ELEVENLABS_API_KEY = Read-Host -Prompt "ElevenLabs API key" -AsSecureString |
    ConvertFrom-SecureString -AsPlainText
```

This prompts you interactively and does not echo the key to the screen or
to shell history.

**2. Read-only connectivity check** (verifies the key works, lists voice/model
access; makes no paid calls):

```powershell
python tools\e10_zone1_audio\generate_zone1_audio.py --check
```

Expected output is structured text only:

```
SELECTED_MODEL_ID=eleven_v3
ELEVENLABS_API_REACHABLE=YES
VOICE_API_ACCESS=YES
MODEL_API_ACCESS=YES
AVAILABLE_VOICE_COUNT=<n>
AVAILABLE_MODEL_COUNT=<n>
SELECTED_MODEL_PRESENT=YES
SELECTED_MODEL_SUPPORTS_TTS=YES
```

If `SELECTED_MODEL_PRESENT` or `SELECTED_MODEL_SUPPORTS_TTS` comes back `NO`,
do not run `--audition` yet — either the configured model isn't available on
this account or it doesn't support text-to-speech.

**3. Model selection.** The audition (and future full-generation) model is
governed by `audio_config.model_id` in `casting_candidates.json`, not
hard-coded in the script. It defaults to `eleven_v3`. Change it there if the
Owner wants a different model, then re-run `--check` to confirm it's valid
before auditioning.

**4. Fill in casting.** Edit `tools\e10_zone1_audio\casting_candidates.json`
and set a `voice_id` for each of the 4 roles (Narrator/`anna`,
Elder/`elder`, Hero/`hero`, Messenger/`runner`) in both `en` and `zh-TW`
(or just the ones you want to audition first).

**5. Generate the casting audition sample** (only the 8 minimal lines, not
full Zone 1):

```powershell
python tools\e10_zone1_audio\generate_zone1_audio.py --audition
```

The configured model is printed before generation starts
(`SELECTED_MODEL_ID=...`). Output goes to
`tools\e10_zone1_audio\_local_review\audition\`. Review it there — nothing
is copied into `assets/` or any canonical manifest by this tool.

**6. When you're done for the session, remove the key from the process:**

```powershell
Remove-Item Env:\ELEVENLABS_API_KEY
```

## Not yet enabled

`--generate-tts`, `--generate-sfx`, and `--generate-music` are present as
reserved flags but currently print a `NOT_YET_ENABLED` notice and send no
request. Full-line TTS generation, sound effects, and music are gated on
Owner approval of the casting/BGM direction from the audition step above.
