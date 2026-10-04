"""UI-NAV-063: one map-return CTA on the puzzle row, Guild in the Adventure nav slot.

Owner evidence (iPad landscape) showed two problems:

A. The puzzle action row rendered FIVE controls -- 返回地圖, 返回 E10 地圖,
   ◀ 上一題, 🔄 重試, 下一題 ▶ -- i.e. two concurrently visible map-return CTAs.
   Both resolved to the same place: #btn-return-map calls
   returnToAdventureMap(), which delegates to
   returnToAdventureMapAfterEncounter(), which is exactly what
   #btn-adventure-return's own onclick invokes, and both end at
   window.location.href='/?adventure=1'. The second control was redundant.

B. The Adventure page's bottom-nav slot 1 was 冒險 -- a no-op for a player
   already on Adventure. It now shows 公會 / Guild and navigates to the
   existing /curriculum Guild page.

#btn-adventure-return is a SHARED slot: Beginner Village owns it through
_setBeginnerVillagePostAnswerControls(). These tests hold the line that the
element, its handler and its i18n survive; only the E10-battle rendering of it
was removed.
"""

from pathlib import Path

from tests.support.sw_identity import (
    assert_static_runtime_identity_well_formed,
    read_static_runtime_identity,
)

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
LEFT_NAV = (ROOT / "js/e9/left_nav.js").read_text(encoding="utf-8")


def _function_block(name: str, end_name: str) -> str:
    start = INDEX.index("function " + name)
    end = INDEX.index("function " + end_name, start)
    return INDEX[start:end]


def _strip_js_line_comments(source: str) -> str:
    return "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("//")
    )


# ======================================================================
# A. Puzzle action row
# ======================================================================

def test_a1_battle_state_renders_exactly_one_map_return_cta():
    """In the E10 battle state the shared slot is no longer shown at all."""
    actions = _strip_js_line_comments(
        _function_block("_syncE10BattleActions", "showE10BattleExplanation")
    )
    # The removed branch: showing the shared slot while battleVisible.
    assert "back.style.display = 'inline-flex'" not in actions, (
        "the E10 battle state must not render a second map-return CTA"
    )
    # What remains: hide it unless Beginner Village owns it.
    assert "if (back && !isBeginnerVillageAdventureResult())" in actions
    assert "back.style.display = 'none';" in actions


def test_a2_action_row_keeps_the_owner_required_controls():
    row_start = INDEX.index('<div class="btn-row">')
    row = INDEX[row_start:INDEX.index("</div>", row_start)]
    assert 'id="btn-return-map"' in row
    assert 'data-i18n="index.boss.back_to_map"' in row
    assert 'onclick="prevQuestion()"' in row
    assert 'onclick="retryQuestion()"' in row or "重試" in row
    assert 'onclick="nextQuestion()"' in row


def test_a3_hardcoded_e10_map_label_is_gone_from_the_battle_path():
    actions = _strip_js_line_comments(
        _function_block("_syncE10BattleActions", "showE10BattleExplanation")
    )
    assert "返回 E10 地圖" not in actions, (
        "the redundant CTA's label must no longer be written by the battle path"
    )


def test_a4_return_map_control_and_target_are_unchanged():
    """返回地圖 must still invoke the same canonical action and destination."""
    assert 'id="btn-return-map"' in INDEX
    assert 'onclick="returnToAdventureMap()"' in INDEX
    delegate = _function_block("returnToAdventureMap", "returnToAdventureMapAfterEncounter")
    assert "returnToAdventureMapAfterEncounter();" in delegate
    after = _function_block("returnToAdventureMapAfterEncounter", "renderAdventureZoneMonster")
    assert "window.location.href = '/?adventure=1';" in after


def test_a5_removed_controls_destination_is_still_reachable():
    """The removed CTA had NO distinct destination -- it shared #btn-return-map's.

    Both call returnToAdventureMapAfterEncounter(), so nothing became
    unreachable; the surviving control goes to the identical URL.
    """
    removed_onclick = 'id="btn-adventure-return" onclick="returnToAdventureMapAfterEncounter()"'
    assert removed_onclick in INDEX, "the shared slot keeps its handler for Beginner Village"
    delegate = _function_block("returnToAdventureMap", "returnToAdventureMapAfterEncounter")
    assert "returnToAdventureMapAfterEncounter();" in delegate, (
        "the surviving CTA must resolve to the same function the removed one used"
    )


def test_a6_shared_slot_contract_survives_for_beginner_village():
    """The element, its handler and its i18n key must all still exist."""
    assert 'id="btn-adventure-return"' in INDEX, "the shared slot must not be deleted"
    village = _function_block(
        "_setBeginnerVillagePostAnswerControls", "showBeginnerVillageEncounterContinuation"
    )
    assert "document.getElementById('btn-adventure-return')" in village
    assert "I18n.t('adventure.newbie.return_map')" in village
    assert "back.style.display = active ? 'inline-flex' : 'none';" in village
    assert "'adventure.newbie.return_map'" in I18N, (
        "the i18n key must survive -- Beginner Village still consumes it"
    )


def test_a7_no_duplicate_map_return_listener():
    """Exactly one element declares each map-return handler."""
    assert INDEX.count('onclick="returnToAdventureMap()"') == 1
    assert INDEX.count('id="btn-adventure-return"') == 1
    assert INDEX.count('id="btn-return-map"') == 1


# ======================================================================
# B. Adventure bottom nav -> Guild
# ======================================================================

def test_b1_guild_entry_exists_and_targets_the_existing_guild_page():
    nav=_canonical_navigation()
    hub=next(x for x in nav['items'] if x['key']=='learning_hub')
    assert hub['target']=='/curriculum' and hub['labelKey']=='g009.nav.learning_hub'
    assert hub['icon']=='book'


def test_b2_adventure_slot_is_swapped_for_guild_on_the_adventure_surface():
    nav=_canonical_navigation()
    assert len(nav['items'])==7
    assert nav['global'][0]['key']=='learning_hub'
    assert "itemsFor('global')" in LEFT_NAV
    assert "registry.get('guild')" not in LEFT_NAV


def test_b3_no_new_route_was_invented():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert "@app.route('/curriculum')" in app
    nav=_canonical_navigation()
    assert next(x for x in nav['items'] if x['key']=='learning_hub')['target']=='/curriculum'
    assert all(x['target']!='/guild' for x in nav['items'])


def test_b5_guild_is_not_marked_active_while_the_player_is_on_adventure():
    nav=_canonical_navigation()
    assert all('command' not in x for x in nav['items'])
    assert "window.location.pathname" in LEFT_NAV
    assert "'/curriculum'" in LEFT_NAV or 'new URL' in LEFT_NAV
    assert "aria-current" in LEFT_NAV


def test_b6_the_adventure_entry_itself_is_preserved_in_the_registry():
    nav=_canonical_navigation()
    assert all(x['target']!='/' for x in nav['items'])
    site=(ROOT/'site-nav.js').read_text(encoding='utf-8')
    assert 'href="/"' in site
    assert "g009.page.home" in site
    assert 'returnToAdventureMap' in INDEX


def test_b7_every_other_nav_item_is_untouched():
    nav=_canonical_navigation()
    assert [(x['key'],x['target']) for x in nav['items']]==[
        ('learning_hub','/curriculum'),('arena','/play'),('tavern','/community'),
        ('hero_hub','/hero?tab=hero'),('backpack','/inventory?e10=1'),('shop','/shop'),('premium','/upgrade')]
    hero=(ROOT/'hero.html').read_text(encoding='utf-8')
    assert hero.count('data-g009-hub-tab=')==5


def test_b8_one_tap_cannot_double_navigate():
    nav=_canonical_navigation()
    assert all('target' in x and 'command' not in x for x in nav['items'])
    assert "control = document.createElement(item.disabled || item.command ? 'button' : 'a')" in LEFT_NAV
    assert "control.setAttribute('href', item.target)" in LEFT_NAV
    assert "addEventListener('click'" not in LEFT_NAV


def test_b9_guild_uses_the_owner_supplied_icon_asset():
    nav=_canonical_navigation()
    hub=next(x for x in nav['items'] if x['key']=='learning_hub')
    assert hub['icon']=='book'
    assert 'aria-hidden="true"' in nav['book']
    assert 'data-e10-vs1f-icon' in nav['book']
    assert nav['icons']['pass']=='pass.webp'


# ======================================================================
# Language
# ======================================================================

def test_language_guild_label_is_exactly_as_requested():
    assert "'e10.nav.guild':" in I18N
    entry = I18N[I18N.index("'e10.nav.guild':"):]
    entry = entry[:entry.index("\n")]
    assert "zh: '公會'" in entry
    assert "en: 'Guild'" in entry


def test_language_existing_labels_are_not_regressed():
    assert "'e9.left_nav.adventure':" in I18N and "zh: '冒險'" in I18N
    assert "'nav.rpg.guild':" in I18N, "the pre-existing Adventure Guild label must survive"
    assert "'index.boss.back_to_map':" in I18N
    assert "'adventure.newbie.return_map'" in I18N


# ======================================================================
# Service worker
# ======================================================================

def test_service_worker_version_was_bumped_for_this_runtime_change():
    identity = assert_static_runtime_identity_well_formed(read_static_runtime_identity(ROOT))
    assert identity.sw_version != "v233-e10-question-loader-board-renderer-v1b-b5", (
        "the runtime changed, so the canonical cache version must move"
    )


def _canonical_navigation():
    """Execute the current registry, including ordering on every real placement."""
    import subprocess, json
    script = r"""
const fs=require('fs'),vm=require('vm');
const window={},document={querySelector:()=>({getAttribute:()=> 'e10-vs1f-integrated-world-map'})};
vm.runInNewContext(fs.readFileSync('js/e9/navigation_registry.js','utf8'),{window,document});
const r=window.E9.NavigationRegistry;
console.log(JSON.stringify({items:r.items,global:r.itemsFor('global'),desktop:r.itemsFor('desktop-primary'),mobile:r.itemsFor('mobile-primary'),book:r.icon('book'),icons:r.iconAssets}));
"""
    result=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def _world_contract(expression, width=820, height=1180, override=False):
    """Expose existing closure functions only in the VM, without editing runtime bytes."""
    import subprocess,json
    script=r"""
const fs=require('fs'),vm=require('vm');
const window={innerWidth:WIDTH,innerHeight:HEIGHT,E9:{isPortraitTabletOverride:()=>OVERRIDE},addEventListener:()=>{},matchMedia:()=>({matches:false})};
const document={querySelector:()=>({getAttribute:()=> 'e10-vs1f-integrated-world-map'}),addEventListener:()=>{}};
let source=fs.readFileSync('js/e9/world_stage.js','utf8');
source=source.replace('})(document);','window.__contract={resolveViewportClass,ctaContract,zoneBossProgressText,actionLabel,usesInlinePlayerMarkerSurface};})(document);');
vm.runInNewContext(source,{window,document,console,URL,navigator:{maxTouchPoints:0}});
const c=window.__contract;console.log(JSON.stringify(EXPRESSION));
""".replace('WIDTH',str(width)).replace('HEIGHT',str(height)).replace('OVERRIDE',json.dumps(override)).replace('EXPRESSION',expression)
    result=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)
