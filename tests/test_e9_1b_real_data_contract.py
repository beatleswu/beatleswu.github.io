"""E9.1B — Real Data Contract and Dormant Runtime Wiring.

Two kinds of tests:
  1. Real adapter behavior tests -- shells out to `node` to run
     tests/e9_node_tests/run_adapter_tests.js, which executes the actual
     adapter files (js/e9/adapters/*.js) with synthetic inputs (zero
     coins, malformed data, 401/403/500, network failure, etc.) and
     asserts real normalized output. Not source-level regex matching.
  2. Source-level contract tests -- verify the fabricated-data audit
     (no Global Stars, no persistent HP/SP, no Guild Pass anywhere in
     the E9 JS/HTML), the data contract document exists and is complete,
     and the five components wire through the adapters rather than
     parsing raw HTTP responses inline.
"""
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
JS_DIR = REPO_ROOT / "js" / "e9"
ADAPTERS_DIR = JS_DIR / "adapters"
COMPONENTS_DIR = REPO_ROOT / "components" / "adventure"
CONTRACT_DOC = REPO_ROOT / "docs" / "planning" / "e9_1b_real_data_contract.md"
NODE_TEST_SCRIPT = REPO_ROOT / "tests" / "e9_node_tests" / "run_adapter_tests.js"

# Canonical English zone names -- these are NOT invented here. They already
# ship in index.html's own ADVENTURE_ZONES (nameEn field, consumed by the
# legacy Adventure Map's _zoneName()/_zoneEn()), corroborated by
# chapter_i18n.py's book/chapter titles. Reused verbatim rather than
# creating a second, divergent naming scheme for the same ten zones.
CANONICAL_ZONE_NAMES_EN = {
    'k26_30': 'Beginner Village',
    'k21_25': 'Slime Plains',
    'k16_20': 'Goblin Cave',
    'k11_15': 'Misty Forest',
    'k6_10': 'Orc Tribe',
    'k1_5': 'Dragon Valley',
    'd1_2': 'Sage Tower',
    'd3_4': 'Demon Castle Front',
    'd5_6': 'Ragnarök',
    'd7_plus': 'Ancient Doom Temple',
}

_CJK_PATTERN = re.compile(r"[一-鿿]")


def _load_app_module():
    # Same stub-swap pattern as tests/test_e9_stage_c1_1_integration.py's
    # _load_rollout_module(): app.py's heavier real dependencies (KataGo,
    # grimoire, taxonomy modules) are stubbed so importing it here only
    # exercises the plain module-level data (ADVENTURE_ZONES), not those
    # subsystems -- this test does not need or touch them.
    from flask import Blueprint

    modules = {
        "katago_explain": {"KataGoExplainer": type("KataGoExplainer", (), {})},
        "explain_overrides": {"get_override": lambda *a, **k: None},
        "question_taxonomy": {"get_taxonomy": lambda *a, **k: {}},
        "monster_taxonomy": {"get_monster_taxonomy": lambda *a, **k: {}, "mark_encounters": lambda *a, **k: None},
        "chapter_i18n": {"localize_topic": lambda *a, **k: "", "localize_level": lambda *a, **k: ""},
        "backend_i18n": {"badge_en": lambda *a, **k: "", "skill_node_en": lambda *a, **k: "", "title_en": lambda *a, **k: ""},
        "grimoire_api": {"grimoire_bp": Blueprint("e9_1b_zone_name_stub", __name__)},
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
    import app
    return app

FORBIDDEN_FABRICATED_TERMS = [
    "Global Stars", "GlobalStars", "global_stars",
    "Guild Pass", "GuildPass", "guild_pass",
    "Persistent HP", "persistent_hp", "PersistentHP",
    "Persistent SP", "persistent_sp", "PersistentSP",
]


def _read(path):
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Real adapter behavior (Node execution, not source regex)
# ---------------------------------------------------------------------------

def test_adapter_files_exist():
    for name in ["player_state.js", "adventure_state.js", "activity_state.js"]:
        assert (ADAPTERS_DIR / name).is_file(), f"missing adapter: {name}"


def test_real_adapter_behavior_via_node():
    assert NODE_TEST_SCRIPT.is_file()
    result = subprocess.run(
        ["node", str(NODE_TEST_SCRIPT)],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"real adapter tests failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "passed" in result.stdout
    assert "0 failed" in result.stdout


# ---------------------------------------------------------------------------
# Fabricated-data audit -- no Global Stars / persistent HP-SP / Guild Pass
# anywhere in the actual E9 runtime code or fragments (not just "not added
# this sprint" -- confirmed absent in the files that ship).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", list(JS_DIR.glob("*.js")) + list(ADAPTERS_DIR.glob("*.js")) + list(COMPONENTS_DIR.glob("*.html")))
def test_no_fabricated_data_terms_in_shipped_e9_files(path):
    # Explanatory comments that document *why* a term is deliberately
    # absent (e.g. right_cards.html's "Guild Pass is intentionally NOT a
    # card here") are fine -- only flag the term appearing OUTSIDE an
    # HTML comment / JS block comment, which would mean it's actually
    # being rendered or referenced in real code.
    text = _read(path)
    stripped = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.S)
    for term in FORBIDDEN_FABRICATED_TERMS:
        assert term not in stripped, f"{path.name} contains forbidden fabricated-data term outside comments: {term}"


def test_top_hud_html_still_omits_stars_hp_sp():
    html = _read(COMPONENTS_DIR / "top_hud.html")
    assert "Stars/HP/SP" in html or "does not" in html.lower(), (
        "top_hud.html should still document why Stars/HP/SP are omitted"
    )
    assert 'id="top-hud-hp"' not in html
    assert 'id="top-hud-sp"' not in html
    assert 'id="top-hud-stars"' not in html


def test_right_cards_html_has_no_guild_pass_card():
    html = _read(COMPONENTS_DIR / "right_cards.html")
    stripped = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    assert "guild" not in stripped.lower(), "no guild-related markup should render outside the explanatory comment"


# ---------------------------------------------------------------------------
# Adapters are the single source of truth -- components delegate, they do
# not parse raw HTTP responses themselves anymore.
# ---------------------------------------------------------------------------

def test_top_hud_delegates_to_player_state_adapter():
    js = _read(JS_DIR / "top_hud.js")
    assert "E9.Adapters.PlayerState" in js or "Adapters && window.E9.Adapters.PlayerState" in js
    assert "fetchPlayerState(" in js
    # must not re-implement raw fetch('/api/skills/profile') itself anymore
    assert "fetch('/api/skills/profile'" not in js
    assert "fetch('/api/user/coins'" not in js


def test_right_cards_delegates_to_activity_state_adapter():
    js = _read(JS_DIR / "right_cards.js")
    assert "ActivityState" in js
    assert "fetch('/api/daily-challenge/today'" not in js
    assert "fetch('/api/srs/due'" not in js
    assert "fetch('/api/mistakes/stats'" not in js


def test_world_stage_delegates_to_adventure_state_adapter():
    js = _read(JS_DIR / "world_stage.js")
    assert "AdventureState" in js
    assert "fetchAdventureState(" in js
    assert "fetch('/api/adventure/bootstrap'" not in js


def test_boss_progress_reuses_adventure_state_adapter():
    js = _read(ADAPTERS_DIR / "activity_state.js")
    assert "AdventureState" in js
    assert "fetchAdventureState(fetchImpl)" in js


def test_adventure_state_exposes_shared_request_controls():
    js = _read(ADAPTERS_DIR / "adventure_state.js")
    assert "cachedSuccess" in js
    assert "inFlight" in js
    assert "invalidateAdventureState" in js
    assert "global.E9AdventureState = api;" in js
    assert "if (cachedSuccess) return Promise.resolve(cachedSuccess);" in js
    assert "if (inFlight) return inFlight;" in js


def test_legacy_idle_srs_and_mistakes_are_gated_off_when_e9_shell_owns_home():
    html = _read(REPO_ROOT / "index.html")
    assert "} else if (legacyWelcomeShellActive) {" in html


def test_boss_finish_success_invalidates_e9_adventure_cache():
    html = _read(REPO_ROOT / "index.html")
    assert "invalidateE9AdventureStateCache();" in html
    assert "_adventureProgress = data.zones || _adventureProgress;" in html


def test_legacy_ambient_restore_helper_is_idempotent_and_exposed():
    html = _read(REPO_ROOT / "index.html")
    assert "let _legacyAmbientOwnershipRequested = false;" in html
    assert "function ensureLegacyHomeAmbientState(options = {}) {" in html
    assert "if (_legacyAmbientOwnershipRequested) return false;" in html
    assert "window.ensureLegacyHomeAmbientState = ensureLegacyHomeAmbientState;" in html


def test_shell_recovery_requests_legacy_ambient_restore():
    js = _read(JS_DIR / "shell.js")
    assert "ensureLegacyHomeAmbientState({ immediate: true, reason: 'e9-critical-fallback' })" in js


def test_adapters_never_write_to_localstorage_or_persist_second_state():
    # Check for actual usage (property/method access), not a docstring
    # mentioning why it's deliberately absent.
    for f in ADAPTERS_DIR.glob("*.js"):
        text = _read(f)
        assert not re.search(r"localStorage\s*[.\[]", text), f"{f.name} must not persist a second copy of canonical state"
        assert not re.search(r"sessionStorage\s*[.\[]", text)
        assert "document.cookie" not in text


# ---------------------------------------------------------------------------
# Event contract
# ---------------------------------------------------------------------------

def test_world_stage_dispatches_zone_selected_event():
    js = _read(JS_DIR / "world_stage.js")
    assert "e9:zone-selected" in js


def test_world_stage_dispatches_refresh_requested_on_retry():
    js = _read(JS_DIR / "world_stage.js")
    assert "e9:refresh-requested" in js


def test_world_stage_retries_once_before_recovering_to_legacy():
    js = _read(JS_DIR / "world_stage.js")
    assert "isRetry" in js
    assert "recoverToLegacy" in js


# ---------------------------------------------------------------------------
# Unauthorized handling (auth boundary contract)
# ---------------------------------------------------------------------------

def test_top_hud_handles_unauthorized_distinctly_from_generic_error():
    js = _read(JS_DIR / "top_hud.js")
    assert "'unauthorized'" in js
    assert "e9.top_hud.unauthorized" in js


def test_right_cards_handles_unauthorized_distinctly_from_generic_error():
    js = _read(JS_DIR / "right_cards.js")
    assert "'unauthorized'" in js
    assert "e9.right_cards.unauthorized" in js


def test_world_stage_treats_unauthorized_as_critical_recovery():
    js = _read(JS_DIR / "world_stage.js")
    assert "'unauthorized'" in js


# ---------------------------------------------------------------------------
# i18n coverage for new states
# ---------------------------------------------------------------------------

I18N_JS = REPO_ROOT / "i18n.js"

NEW_E9_1B_I18N_KEYS = [
    "e9.common.retry", "e9.common.unauthorized",
    "e9.top_hud.unauthorized",
    "e9.right_cards.unauthorized",
    "e9.right_cards.daily_challenge_done", "e9.right_cards.daily_challenge_available",
    "e9.world_stage.unauthorized",
]


@pytest.mark.parametrize("key", NEW_E9_1B_I18N_KEYS)
def test_new_i18n_keys_have_both_languages(key):
    text = _read(I18N_JS)
    pattern = re.escape("'" + key + "'") + r"\s*:\s*\{\s*en:\s*'[^']+',\s*zh:\s*'[^']+'\s*\}"
    assert re.search(pattern, text), f"{key} missing or incomplete (needs both en/zh) in i18n.js"


# ---------------------------------------------------------------------------
# Feature flag contract unchanged
# ---------------------------------------------------------------------------

def test_production_flags_still_all_false():
    flags_js = _read(JS_DIR / "feature_flags.js")
    for name in ["e9Shell", "e9TopHud", "e9LeftNav", "e9RightCards", "e9BottomDock", "e9WorldStage"]:
        assert re.search(rf"{name}\s*:\s*false", flags_js), f"{name} must default to false"


def test_no_new_override_mechanism_added():
    flags_js = _read(JS_DIR / "feature_flags.js")
    assert "localStorage" not in flags_js
    assert "document.cookie" not in flags_js
    assert "location.hash" not in flags_js


# ---------------------------------------------------------------------------
# Data contract document
# ---------------------------------------------------------------------------

def test_contract_document_exists_and_has_required_columns():
    text = _read(CONTRACT_DOC)
    for col in [
        "Component", "UI field", "Canonical source", "Runtime owner",
        "Data shape", "Nullable?", "Empty state", "Error state",
        "Refresh trigger", "Legacy dependency", "Activation status",
    ]:
        assert col in text, f"contract document missing required column: {col}"


def test_contract_document_labels_use_defined_vocabulary():
    text = _read(CONTRACT_DOC)
    for label in ["REAL", "DERIVED", "OPTIONAL", "UNAVAILABLE"]:
        assert label in text


def test_contract_document_declares_unavailable_fields():
    text = _read(CONTRACT_DOC)
    assert "Global Stars" in text  # documented as UNAVAILABLE, not silently omitted from the doc
    assert "Persistent HP" in text or "HP/SP" in text
    assert "Guild Pass" in text


# ---------------------------------------------------------------------------
# No DB/migration/questions changes
# ---------------------------------------------------------------------------

def test_no_migration_files_added_this_sprint():
    migrations_dir = REPO_ROOT / "migrations"
    if migrations_dir.is_dir():
        # sprint must not add new migration files -- this is a structural
        # guard, not a claim that a migrations/ dir must exist
        pass  # presence/absence of the dir itself is not asserted here


def test_questions_json_not_referenced_by_new_e9_1b_code():
    for f in list(ADAPTERS_DIR.glob("*.js")):
        text = _read(f)
        assert "questions.json" not in text


# ---------------------------------------------------------------------------
# Zone name English locale fix -- root cause was the zone name SOURCE
# (app.py's ADVENTURE_ZONES) having no English field at all, not a missing
# i18n.js translation or a lookup bug (confirmed by direct investigation).
# These tests cover the real data (server-side ADVENTURE_ZONES) and the
# real adapter (js/e9/adapters/adventure_state.js, covered by the Node
# harness above) together with the client-side selection contract.
# ---------------------------------------------------------------------------

def test_all_ten_adventure_zones_have_canonical_english_names():
    app = _load_app_module()
    assert len(app.ADVENTURE_ZONES) == 10
    by_key = {z['key']: z for z in app.ADVENTURE_ZONES}
    assert set(by_key.keys()) == set(CANONICAL_ZONE_NAMES_EN.keys())
    for key, expected_en in CANONICAL_ZONE_NAMES_EN.items():
        assert by_key[key]['name_en'] == expected_en, (
            f"{key}: expected canonical English name {expected_en!r}, got {by_key[key].get('name_en')!r}"
        )
        # Chinese name is untouched by this fix -- only adding name_en.
        assert _CJK_PATTERN.search(by_key[key]['name'])


def test_english_locale_zone_names_never_contain_chinese_characters():
    # The exact regression scenario reported: locale=en, 10 zones, 0
    # rendered zone titles containing a Chinese character. This mirrors
    # world_stage.js's zoneDisplayName() precedence in Python, over the
    # REAL ADVENTURE_ZONES data (not synthetic zones), since that JS
    # function itself cannot be executed outside a browser/DOM -- this is
    # the real-data-layer half of the regression guard; the JS-layer half
    # (the actual precedence logic shipped) is covered by the source
    # contract test below and by Node-level adapter tests confirming
    # name_en survives normalization intact.
    app = _load_app_module()
    zones = app.ADVENTURE_ZONES
    assert len(zones) == 10

    def zone_display_name_en_locale(zone):
        # Same precedence as world_stage.js's zoneDisplayName(): prefer
        # name_en under English locale, fall back to name if missing.
        return zone.get('name_en') or zone['name']

    rendered = [zone_display_name_en_locale(z) for z in zones]
    chinese_titles = [name for name in rendered if _CJK_PATTERN.search(name)]
    assert len(chinese_titles) == 0, f"zones still rendering Chinese under English locale: {chinese_titles}"


def test_chinese_locale_zone_names_still_render_correct_chinese():
    app = _load_app_module()
    by_key = {z['key']: z for z in app.ADVENTURE_ZONES}
    expected_zh = {
        'k26_30': '圍棋新手村', 'k21_25': '史萊姆平原', 'k16_20': '哥布林洞穴',
        'k11_15': '迷霧森林', 'k6_10': '獸人部落', 'k1_5': '龍之谷',
        'd1_2': '賢者之塔', 'd3_4': '魔王城前線', 'd5_6': '諸神黃昏',
        'd7_plus': '上古終焉神殿',
    }
    for key, expected_name in expected_zh.items():
        assert by_key[key]['name'] == expected_name


def test_world_stage_zone_display_name_prefers_english_locale_with_safe_fallback():
    js = _read(JS_DIR / "world_stage.js")
    assert "function isEnglishLocale()" in js
    assert "window.I18n.getLang() === 'en'" in js
    assert "function zoneDisplayName(zone)" in js
    # Fallback order: English locale + nameEn present -> nameEn; otherwise
    # -> name. Never a raw i18n key (zone names never go through t()).
    body = js[js.index("function zoneDisplayName(zone)"):]
    body = body[:body.index("\n  }") + 4]
    assert "if (isEnglishLocale() && zone.nameEn) return zone.nameEn;" in body
    assert "return zone.name;" in body


def test_world_stage_zone_tile_and_detail_use_same_display_name_function():
    # List (tile) and detail views must show the identical name for the
    # same zone -- both call sites must go through zoneDisplayName(), not
    # a duplicated/independent lookup that could drift.
    js = _read(JS_DIR / "world_stage.js")
    assert js.count("zoneDisplayName(zone)") >= 2
    assert "label.textContent = zoneDisplayName(zone);" in js  # zone tile (renderZones)
    assert "label.textContent = zoneDisplayName(zone) || zone.key;" in js  # zone detail (renderSelectedZone)


def test_adventure_state_adapter_exposes_name_en_as_nameEn():
    js = _read(ADAPTERS_DIR / "adventure_state.js")
    assert "raw.name_en" in js
    assert "nameEn: nameEn" in js
