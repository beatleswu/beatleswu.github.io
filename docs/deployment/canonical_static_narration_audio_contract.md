# Canonical Static Narration Audio Contract

Status: current
Added: 2026-07-15
Companion to: [canonical_static_release_contract.md](canonical_static_release_contract.md)

## Why this exists

`deploy/canonical-image-pack-manifest.json` governs everything staged under
`assets/` in a static release generation. Its own `$schema_note` documents
deliberately excluding "audio/\*, video/\*, and non-image artifacts... 90 mp3
voice files" from that pack, and it is validated image/\*-MIME-only
(`tests/test_release_fix_a3_canonical_image_pack.py::test_manifest_contains_only_image_mime_types`,
`tests/test_release_fix_a2_asset_closure.py`). That is a real, tested
contract — not an oversight — and must not be weakened to smuggle audio
files into it.

The 2026-07-14 narration incident (PR #107) restored 90 storyboard
narration MP3 files referenced by `index.html`'s intro-film cinematics, and
fixed the code that made a missing narration file collapse a cinematic to
milliseconds. But a first static-release preflight for that fix found the
built package contained **zero** of those 90 files — the image-only
manifest correctly, by design, refused to stage them, and nothing else
staged them either. This contract closes that gap without touching the
image manifest's contract.

## What was added

- **`deploy/canonical-audio-pack-manifest.json`** — the audio-pack
  counterpart to the image manifest. Same shape (`path`, `size`, `sha256`,
  `mime`, provenance fields), scoped to `audio/mpeg` only, exactly the 90
  files currently referenced by `index.html`'s `audioSrc` values.
- **A second `required_subtrees` entry** in
  `deploy/live-static-asset-inventory.json`, prefix `assets/storyboards/`,
  pointing at the audio manifest. The pre-existing `assets/` → image-manifest
  entry is unchanged and stays first.
- **`tests/test_release_fix_a4_canonical_audio_pack.py`** — mirrors the
  image pack's test coverage (hash/size verification, MIME purity, path
  hygiene, no duplicates, deterministic ordering) plus disjointness checks
  against the image manifest and an exact-match check against
  `index.html`'s current `audioSrc` references.

## Why a second manifest, not one shared manifest

`scripts/release/ReleaseTooling.psm1`'s `New-StaticReleaseBundle` already
iterates `required_subtrees.entries` generically — it reads whichever
closure manifest each entry names and stages exactly the `path`/`sha256`
pairs it lists, with no type-specific logic. Nothing in the packaging code
required a single shared manifest; the image-only *test* contract is what
would have broken. Two disjoint manifests (zero shared paths, verified by
`test_inventory_subtree_prefixes_are_disjoint_in_file_membership`) preserve
both contracts independently: the image pack stays image-only and fully
tested as such, and the audio pack gets its own equally strict, equally
tested closure.

## Keeping this in sync

If a future zone adds or removes narration files, update
`deploy/canonical-audio-pack-manifest.json` in the same PR as the
`index.html` `audioSrc` change, and re-run
`tests/test_release_fix_a4_canonical_audio_pack.py::test_manifest_exactly_matches_currently_referenced_audio_paths`
— it fails closed on either direction of drift (referenced-but-not-staged,
or staged-but-unreferenced).
