import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "js" / "game" / "encounter_presentation_framework_v1.js"
STYLES = ROOT / "css" / "e10" / "encounter_presentation_framework_v1.css"
INDEX = ROOT / "index.html"
MANIFEST = ROOT / "docs" / "planning" / "e10_encounter_presentation_framework_a023.json"
FIXTURE = ROOT / "tests" / "e2e" / "fixtures" / "a023_encounter_presentation_showcase.html"


def test_a023_manifest_is_cardinality_agnostic_and_has_four_tiers():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["scope"]["presentation_cardinality_agnostic"] is True
    assert manifest["scope"]["roster_size_assumption_count"] == 0
    assert manifest["scope"]["fully_unique_art_required_per_monster"] is False
    assert manifest["scope"]["color_swap_only_variant_acceptable"] is False
    assert [item["tier"] for item in manifest["tier_contract"]] == [
        "common", "rare", "elite", "battlefield_boss"
    ]
    assert len(manifest["prototype_set"]) == 4
    assert {item["tier"] for item in manifest["prototype_set"]} == {
        "common", "rare", "elite", "battlefield_boss"
    }


def test_lord_trial_and_authority_boundaries_are_explicit():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["lord_trial_separation"]["lord_trial_visual_authority_separate"] is True
    assert manifest["feedback_contract"]["presentation_can_authorize_damage"] is False
    assert manifest["feedback_contract"]["presentation_can_authorize_correctness"] is False
    assert manifest["feedback_contract"]["presentation_can_authorize_reward"] is False
    assert manifest["drop_reward_boundary"]["a023_infers_reward_truth"] is False


def test_shared_module_exposes_one_hp_framework_and_safe_tier_mapping():
    module_text = MODULE.read_text(encoding="utf-8")
    assert "renderHp" in module_text
    assert "decoratePanel" in module_text
    assert "chapter_boss: TIERS.ELITE" in module_text
    assert "book_boss: TIERS.BATTLEFIELD_BOSS" in module_text
    assert "lord_trial: TIERS.LORD_TRIAL" in module_text
    assert "damage" in module_text.lower()
    assert "grant" in module_text.lower()

    node_script = f"""
const framework = require({json.dumps(str(MODULE))});
const checks = [
  [framework.normalizeTier({{encounter_type:'normal'}}), 'common'],
  [framework.normalizeTier({{encounter_type:'rare'}}), 'rare'],
  [framework.normalizeTier({{encounter_type:'chapter_boss'}}), 'elite'],
  [framework.normalizeTier({{encounter_type:'book_boss'}}), 'battlefield_boss'],
  [framework.normalizeEncounter({{authority:'lord_trial'}}).tier, 'lord_trial'],
  [framework.normalizeHp(50, 100).percent, 50],
  [framework.normalizeHp('bad', 100).percent, null],
];
for (const [actual, expected] of checks) {{
  if (actual !== expected) throw new Error(String(actual) + ' !== ' + String(expected));
}}
console.log('A023_NODE_CONTRACT_PASS');
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "A023_NODE_CONTRACT_PASS" in result.stdout


def test_existing_encounter_surface_is_decorated_without_authority_replacement():
    index = INDEX.read_text(encoding="utf-8")
    adapter = (ROOT / "js" / "map_battle_v1_adapter.js").read_text(encoding="utf-8")
    assert "/css/e10/encounter_presentation_framework_v1.css?v=a023v1" in index
    assert "/js/game/encounter_presentation_framework_v1.js?v=a023v1" in index
    assert 'id="monster-panel" data-encounter-framework="pending"' in index
    assert "EncounterPresentationV1.decoratePanel" in index
    assert "state.monsterHp" in index
    assert "/api/adventure/map-battles/v1/" in adapter
    assert "showKillAnimation" in index


def test_fixture_is_review_only_and_uses_existing_art_not_roster_data():
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert 'data-a023-presentation-only="true"' in fixture
    assert "renderPrototypeGrid" in fixture
    assert "/assets/monsters/slime.svg" in fixture
    assert "/assets/monsters/mist_dryad.svg" in fixture
    assert "/assets/monsters/royal_knight.svg" in fixture
    assert "/assets/monsters/omega_idol.svg" in fixture
    assert "encounter_presentation_framework_v1.js" in fixture
    assert "encounter_presentation_framework_v1.css" in fixture
    assert "setInterval" not in fixture
    assert "/api/" not in fixture


def test_a023_styles_define_non_color_hierarchy_and_responsive_breakpoints():
    styles = STYLES.read_text(encoding="utf-8")
    for tier in ("common", "rare", "elite", "battlefield_boss"):
        assert f"encounter-tier-{tier}" in styles
    assert "border-style: double" in styles
    assert "border-width: 3px" in styles
    assert "max-width: 1100px" in styles
    assert "max-width: 700px" in styles
    assert "prefers-reduced-motion" in styles
