"""Static contract tests for Adventure/Battlefield encounter separation."""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


def test_adventure_helper_and_renderer_precede_battlefield_fetch():
    helper = INDEX.index("function _isAdventureZonePractice")
    renderer = INDEX.index("function renderAdventureZoneMonster")
    init = INDEX.index("function initMonsterForQuestion")
    branch = INDEX.index("if (_isAdventureZonePractice())", init)
    fetch = INDEX.index("fetch('/api/monster/status'", init)
    assert helper < renderer < init < branch < fetch
    assert "q.monster_type" in INDEX[renderer:init]
    assert "q.monster_name" in INDEX[renderer:init]
    assert "q.monster_avatar" in INDEX[renderer:init]


def test_adventure_mode_guards_both_answer_paths():
    assert "data.monster && !_isAdventureZonePractice()" in INDEX
    assert "d.monster&&!_isAdventureZonePractice()" in INDEX


def test_adventure_renderer_uses_i18n_context_marker_and_daily_reset_hides_it():
    renderer = INDEX.index("function renderAdventureZoneMonster")
    reset = INDEX.index("async function startDailyTraining")
    assert "I18n.t('index.battle.adventure_encounter')" in INDEX[renderer:reset]
    assert "I18n.t('index.battle.fighting')" in INDEX[reset:reset + 600]
    assert INDEX.count("id=\"monster-context-label\"") == 0


def test_avatar_rendering_uses_safe_dom_assignment_and_asset_validation():
    start = INDEX.index("function monsterArtSrc")
    end = INDEX.index("function updateMonsterUI", start)
    block = INDEX[start:end]
    assert "document.createElement('img')" in block
    assert "img.src = monsterArtSrc" in block
    assert "el.replaceChildren(img)" in block
    assert "innerHTML" not in block
    assert "javascript:" not in block.lower()
    assert "startsWith('/assets/')" not in block
    assert "^\\/assets\\/[A-Za-z0-9._/-]+\\.png$" in block


def test_daily_training_clears_adventure_context():
    start = INDEX.index("async function startDailyTraining")
    assert "_adventureActiveQuestions = null;" in INDEX[start:start + 500]


def test_zone_resolver_prioritizes_enterable_selected_then_recommended():
    start = INDEX.index("function adventureActiveZone")
    block = INDEX[start:start + 500]
    assert "_adventureSelected(z) && _adventureCanEnter(z)" in block
    assert "_adventureRecommended(z) && _adventureCanEnter(z)" in block
    assert block.index("_adventureSelected") < block.index("_adventureRecommended")


def test_adventure_i18n_key_and_sw_version():
    assert "index.battle.adventure_encounter" in I18N
    assert "Adventure Encounter" in I18N
    assert "冒險遭遇" in I18N
    assert re.search(r"const VERSION\s*=\s*'v193-e9-adventure-navigation-fix'", SW)


def test_ten_zone_keys_are_defined():
    for key in ("k26_30", "k21_25", "k16_20", "k11_15", "k6_10", "k1_5",
                "d1_2", "d3_4", "d5_6", "d7_plus"):
        assert key in INDEX


def test_battlefield_status_remains_daily_only_fetch():
    init = INDEX.index("function initMonsterForQuestion")
    fetch = INDEX.index("fetch('/api/monster/status'", init)
    assert "return;" in INDEX[init:fetch]
    assert INDEX.count("fetch('/api/monster/status'") == 1
