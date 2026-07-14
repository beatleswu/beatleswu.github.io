"""Guard against the 2026-07-14 incident recurring: every zone's intro-film
cinematic in index.html references a recorded narration MP3 via audioSrc.
Those files went missing on Production (references reached master without
the assets ever being committed there), which combined with a zero-delay
failure-advance bug to make cinematics flash and disappear.

This test enforces asset completeness independently of the runtime
failure-handling fix (tests/e2e/run_intro_film_narration_contract.mjs) --
that suite fakes window.Audio and never touches the filesystem, so it
would not have caught the missing-files half of the incident by itself.
"""
import re
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
INDEX_HTML = REPO_ROOT / "index.html"

AUDIO_SRC_RE = re.compile(r"audioSrc:\s*'(/assets/storyboards/[^']+\.mp3)'")

# No exceptions: as of this fix, every currently-referenced narration file
# is restored and tracked. If a future asset genuinely cannot be restored,
# add its exact path here with a comment explaining why -- do not use a
# wildcard/prefix pattern, and do not silently widen this set.
KNOWN_MISSING_ASSETS = frozenset()


def _referenced_audio_paths():
    html = INDEX_HTML.read_text(encoding="utf-8")
    paths = AUDIO_SRC_RE.findall(html)
    assert paths, "expected at least one audioSrc reference in index.html -- regex may be stale"
    return paths


def test_every_referenced_audio_path_is_unique_and_well_formed():
    paths = _referenced_audio_paths()
    assert len(paths) == len(set(paths)), "duplicate audioSrc references found"
    for p in paths:
        assert p.startswith("/assets/storyboards/"), f"unexpected audioSrc location: {p}"
        assert p.endswith(".mp3"), f"unexpected audioSrc extension: {p}"


def test_every_referenced_audio_path_resolves_to_a_tracked_nonempty_file():
    paths = _referenced_audio_paths()
    missing = []
    empty = []
    for rel in paths:
        if rel in KNOWN_MISSING_ASSETS:
            continue
        p = REPO_ROOT / rel.lstrip("/")
        if not p.is_file():
            missing.append(rel)
            continue
        if p.stat().st_size == 0:
            empty.append(rel)
    assert not missing, f"audioSrc references files not present in the repo: {missing}"
    assert not empty, f"audioSrc references zero-byte files: {empty}"


def test_known_missing_assets_are_still_exactly_referenced():
    # If KNOWN_MISSING_ASSETS is ever populated again, every entry in it
    # must correspond to a real, currently-referenced audioSrc -- an empty
    # or stale exception list must not silently linger.
    if not KNOWN_MISSING_ASSETS:
        return
    referenced = set(_referenced_audio_paths())
    stale = KNOWN_MISSING_ASSETS - referenced
    assert not stale, f"KNOWN_MISSING_ASSETS contains paths no longer referenced by index.html: {stale}"
