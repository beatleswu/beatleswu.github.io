# E10 Zone 1 (Newbie Village) Local Audio Tooling

Local-only tooling for generating ElevenLabs voice audio for the canonical
Zone 1 (`k26_30`) bilingual cinematic. **This must be run on the Owner's
local Windows machine, in the canonical repo/worktree** — the remote Claude
Web sandbox cannot reach `api.elevenlabs.io` (egress policy blocks it), and
this tool must never be run there.

## Owner one-click audition (recommended)

雙擊 `Run_Audition_Set_A.cmd`（或補選用 `Run_Audition_Set_B.cmd`）→ 輸入 API Key → 等待資料夾自動開啟 → 試聽

No Git, PowerShell commands, JSON editing, or voice IDs required for normal
use. One one-time step is needed to get the launchers onto your machine the
first time (or after a PR update); after that, every audition run is
double-click only.

**One-time setup** (only needed once, or again after this PR updates):

```powershell
git pull origin claude/e10-z1-audio-production-001
```

**AUDITION SET A** — full 8-role x 2-locale casting comparison (16 files):

1. Double-click `tools\e10_zone1_audio\Run_Audition_Set_A.cmd`.
2. Paste/type your ElevenLabs API key when prompted (input is masked — it
   is never displayed, logged, or written to disk; it only lives in that
   one PowerShell window and is cleared when the window finishes).
3. Wait — it runs a read-only connectivity/model check, then generates
   AUDITION SET A (16 comparison MP3s, `eleven_v3`, no full Zone 1
   dialogue, no BGM/SFX).
4. The `audition_set_a` folder opens automatically in Explorer.
5. Listen and pick.

**AUDITION SET B** — recast only the roles you rejected from Set A (currently
zh-TW Elder, zh-TW Hero, English Hero; up to ~9 files):

1. Double-click `tools\e10_zone1_audio\Run_Audition_Set_B.cmd`.
2. Same masked API key prompt as above.
3. Wait — it runs the same connectivity check, then searches the ElevenLabs
   Voice Library live for new candidates matching each pending role's
   character brief (this account's original voice pool is exhausted for
   these roles), adds up to 3 matches per role to the account, and
   generates one sample per candidate. This step needs a live search, so it
   can take longer than Set A.
4. The `audition_set_b` folder opens automatically in Explorer.
5. Listen and pick.

Set B never regenerates Set A and never touches a role already locked in
`casting_candidates.json` — see "Casting lock state" below.

Both are safe to re-run any time — each run clears out its own previous
output folder first and regenerates fresh, so old and new comparison takes
never mix. See the matching `.ps1` file for what each does step by step;
error messages are in Chinese with an English detail line underneath.

## Casting lock state

`casting_candidates.json` tracks two states per role x locale slot:

- **Locked** (`"locked": true`, real `voice_id`) — Owner-approved. No tool
  in this directory will ever overwrite a locked slot's `voice_id` or
  candidates; `--audition-set-b` explicitly skips any locked slot it
  encounters. Currently locked: zh-TW Narrator (Anna Su), zh-TW Messenger
  (Yui), English Narrator (Amelia), English Elder (Daniel), English
  Messenger (Liam).
- **Pending** (`"locked": false`, `voice_id: null`) — awaiting a decision.
  Currently pending: zh-TW Elder, zh-TW Hero (canon: must be male), English
  Hero (canon: must sound clearly younger than the rejected Will/Charlie).
  `--audition-set-b` writes its live search results into that slot's
  `recast_candidates` array (not `voice_id`) so nothing is silently decided
  — the Owner still has to choose after listening.

## Scope

- Sprint: `E10-Z1-AUDIO-PRODUCTION-001`.
- No deploy. No Production contact. No SGF Engine / Codex involvement.
- This tool only generates local review assets. It never touches
  `deploy/*`, `sw.js`, or any canonical asset manifest, and it never marks
  anything as a production asset automatically.

## Files

- `Run_Audition_Set_A.cmd` / `Run_Audition_Set_A.ps1` — the one-click
  Owner launcher for Set A (see above). The `.cmd` is a thin double-click
  wrapper; the `.ps1` does the real work (masked key prompt, `--check`,
  `--audition-set-a`, opens the output folder).
- `Run_Audition_Set_B.cmd` / `Run_Audition_Set_B.ps1` — the matching
  one-click launcher for Set B (recast pending roles via a live Voice
  Library search, `--audition-set-b`). Both `.cmd` files are ASCII-only
  with CRLF line endings and both `.ps1` files have a UTF-8 BOM — required
  for Windows `cmd.exe`/PowerShell 5.1 compatibility, enforced by
  `.gitattributes` and `tests/test_e10_zone1_audio_launcher_windows_compat.py`
  (see git history for the Windows live-test failure this fixed).

- `zone1_beat_manifest.json` — mechanical extraction of every spoken beat
  in the shipped Zone 1 cinematic (shot, beat, phase, speaker, locale,
  exact canonical text, `voice_id` placeholder, proposed output filename).
  Do not hand-edit dialogue text here — the source of truth is `index.html`
  (`getIntroFilmLocaleConfig` → `k26_30`); if the script ever changes,
  re-extract instead of editing this file directly.
- `casting_candidates.json` — the casting sheet, with an explicit lock
  state per role x locale slot (see "Casting lock state" above). Used by
  `--audition`, `--audition-set-a`, and `--audition-set-b`.
- `audition_set_a.json` — fixed 16-line A/B comparison list (2 candidates
  per role x locale) used only by `--audition-set-a`. Comparison aid only;
  does not affect `casting_candidates.json`.
- `audition_set_b_recast_briefs.json` — per-pending-role Voice Library
  search filters (language/gender/age), a character brief, and the
  exclude-list of every voice_id already locked or rejected in Set A, used
  only by `--audition-set-b`.
- `generate_zone1_audio.py` — the CLI (stdlib-only, no extra pip installs).
- `_local_review/` — generated audio and voice-discovery output land here
  (git-ignored). Never auto-promoted to a canonical asset path.

## Credential handling (read this before running anything)

- The tool reads `ELEVENLABS_API_KEY` **only** from the current process
  environment. It never reads `secret_key.txt`, `.env`, or any other file
  for the key.
- The key is never printed, logged, or written to disk by this tool.
- Do not paste the key into chat, into this repo, or into any commit.
- Unset the variable when you're done for the session (command below).

## Advanced / manual usage (for reference)

The one-click launcher above covers normal Owner use. The steps below are
what it runs under the hood, kept here for debugging or for running the
tool's other modes (`--list-voices`, the single-set `--audition`) by hand.
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

**4. Browse available voices** (read-only; no audio generated):

```powershell
python tools\e10_zone1_audio\generate_zone1_audio.py --list-voices
```

Prints a compact table (name, voice_id, category, language/accent, gender,
age, description) for every voice on the account, to help pick candidates
for `casting_candidates.json`. Add `--json` to also save a local review copy:

```powershell
python tools\e10_zone1_audio\generate_zone1_audio.py --list-voices --json
```

This writes `tools\e10_zone1_audio\_local_review\voices.json` (git-ignored).
`--list-voices` never writes to `casting_candidates.json` — casting choices
are still made by hand in step 5.

### One-command voice discovery

If `ELEVENLABS_API_KEY` is already set in your current PowerShell session
(step 1), this single line pulls the latest tool from this PR's branch and
writes the voice-discovery artifact, printing nothing but its path (no
table, no counts, no key):

```powershell
git fetch origin claude/e10-z1-audio-production-001; git checkout claude/e10-z1-audio-production-001; git pull origin claude/e10-z1-audio-production-001; python tools\e10_zone1_audio\generate_zone1_audio.py --list-voices --json --quiet
```

The only output is the absolute path to `voices.json`, e.g.:

```
C:\path\to\repo\tools\e10_zone1_audio\_local_review\voices.json
```

Send that file back for casting analysis — you do not need to open or edit
it yourself.

**5. Casting state.** `tools\e10_zone1_audio\casting_candidates.json` tracks
5 locked (Owner-approved) and 3 pending role x locale slots — see "Casting
lock state" above. To manually change a locked slot's voice (overriding a
previous approval), you must explicitly set `"locked": false` first, then
edit `voice_id`; no automated mode will ever do this for you. Step 6/6b below
let you compare candidates by ear before deciding on a pending slot.

**6. Generate AUDITION SET A** (a fixed 16-line A/B comparison: 2 candidate
voices per role x locale, each reading the same canonical sample line — not
the full 28-beat Zone 1 dialogue, and no BGM/SFX):

```powershell
python tools\e10_zone1_audio\generate_zone1_audio.py --audition-set-a
```

Output goes to `tools\e10_zone1_audio\_local_review\audition_set_a\`, one
MP3 per candidate with a comparison-friendly filename (e.g.
`zh_narrator_anna_su.mp3` vs `zh_narrator_ling.mp3`). The exact 16-item list
and reasoning live in `audition_set_a.json`. These are local review-only
files — they don't touch `casting_candidates.json` or any canonical asset.

### One-command AUDITION SET A

If `ELEVENLABS_API_KEY` is already set in your session (step 1), this single
line pulls the latest tool from this PR's branch and generates the full
comparison set:

```powershell
git fetch origin claude/e10-z1-audio-production-001; git checkout claude/e10-z1-audio-production-001; git pull origin claude/e10-z1-audio-production-001; python tools\e10_zone1_audio\generate_zone1_audio.py --audition-set-a
```

When it finishes, open the folder it printed
(`tools\e10_zone1_audio\_local_review\audition_set_a\`) — all 16 comparison
MP3s are there together.

**6b. Generate AUDITION SET B** (recast only the pending roles, via a live
Voice Library search -- see `audition_set_b_recast_briefs.json`):

```powershell
python tools\e10_zone1_audio\generate_zone1_audio.py --audition-set-b
```

Output goes to `tools\e10_zone1_audio\_local_review\audition_set_b\`. This
mode also writes discovered candidates into each pending slot's
`recast_candidates` in `casting_candidates.json` (never `voice_id`, never a
locked slot). Since it depends on a live Voice Library search this sandbox
cannot test, a failed search or add-to-library call prints a clear
`VOICE_LIBRARY_SEARCH_FAILED` / `ADD_TO_LIBRARY_FAILED` diagnostic instead of
failing silently -- if you see one, share the exact console output. As of
this fix, that diagnostic includes more than just the HTTP status:

```
ADD_TO_LIBRARY_FAILED name='Some Voice' http_status=401 classification=AUTHENTICATION_ERROR elevenlabs_error_type='invalid_api_key' elevenlabs_error_message='...' request_id='req_...'
```

`classification` is one of `AUTHENTICATION_ERROR` (the key itself is
invalid/missing), `AUTHORIZATION_ERROR` (the key is valid but lacks
permission for this action -- check the key's permissions in the
ElevenLabs dashboard include voice-library write access, not just
read/TTS), `VOICE_SLOT_LIMIT`, `PLAN_RESTRICTION`, or `OTHER`. This never
prints the key itself -- only what ElevenLabs' own error response said.

**7. Once you've picked final voices**, update `casting_candidates.json`
accordingly (if different from the current top picks) and generate the
single per-role-locale casting sample (8 lines, not the full 28-beat Zone 1
dialogue):

```powershell
python tools\e10_zone1_audio\generate_zone1_audio.py --audition
```

The configured model is printed before generation starts
(`SELECTED_MODEL_ID=...`). Output goes to
`tools\e10_zone1_audio\_local_review\audition\`. Review it there — nothing
is copied into `assets/` or any canonical manifest by this tool.

**8. When you're done for the session, remove the key from the process:**

```powershell
Remove-Item Env:\ELEVENLABS_API_KEY
```

## Not yet enabled

`--generate-tts`, `--generate-sfx`, and `--generate-music` are present as
reserved flags but currently print a `NOT_YET_ENABLED` notice and send no
request. Full-line TTS generation, sound effects, and music are gated on
Owner approval of the casting/BGM direction from the audition step above.
