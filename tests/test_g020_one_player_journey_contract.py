"""G020 candidate guard: one identity across real Product pages, zero HTML
substitution, no license or release shortcuts and synthetic native PG only.
"""
from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]
T=(ROOT/"tests/test_g020_original_product_one_player_full_journey_pg.py").read_text(encoding="utf8")
CHROME=(ROOT/"tests/e2e/g020_original_player_pages_readback_browser.mjs").read_text(encoding="utf8")
G019=(ROOT/"docs/handoffs/G019_CANONICAL_EQUIPMENT_PUBLIC_UI_RELEASE_CANDIDATE_20261021.md").read_text(encoding="utf8")
def test_G020_only_original_page_runtime_without_html_shim():
 ast.parse(T)
 assert "_activate_preview_only_in_memory" not in T
 assert "app.app.wsgi_app,threaded=True" in T
 assert '"g019_shipped_shop_backpack_purchase_equip_relogin.mjs"' in T
 assert '"g020_original_tavern_quest_ranking_browser.mjs"' in T
 assert '"g020_original_player_pages_readback_browser.mjs"' in T
 assert "m2_player" in T
def test_G020_all_feature_domains_one_native_pg_quest_reward_and_purchase():
 for needle in [
   "upgrade_progress", "upgrade_claim", "upgrade_coin", "upgrade_slot",
   "seed_lord_eligibility", "/api/adventure/boss/start",
   "/api/adventure/boss/finish", "/api/srs/review",
   "ZONE2_POOL[:20]", "/api/quests/v2", "QUEST_V2_RUNTIME_ENABLED",
   "G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG",
   "good(after_shop,\"/api/shop/catalog\")[\"coins\"]==715",
   "zone3_unlocked", "wallet_debits==1",
   "g019_real_backpack_equip_writes",
   "monkeypatch.delenv(app.G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG",
 ]:
  assert needle in T,needle
def test_G020_real_browser_checks_school_quest_tavern_hero_persistence():
 for needle in [
  '"/curriculum"','"/api/curriculum/summary"','"/api/quest-board"',
  '"/community"','"challenges","reviews","friends","leaderboard"',
  '"/api/quests/v2"','"/api/community/leaderboard"',
  '"/hero?tab=equipment"','"#g008-future30-hero-stage"',
  '"/api/player/inventory"','"/api/xp/status"','"/api/shop/catalog"',
  'window.__G018_P022_INPAGE_QA_PROOF__','writes.length===0',
  'differentSignedSession:true','chrome_tablet_touch',
 ]:
  assert needle in CHROME,needle
def test_G020_never_promote_unlicensed_3d_or_prod_data():
 app=(ROOT/"app.py").read_text(encoding="utf8")
 shop=(ROOT/"shop.html").read_text(encoding="utf8")
 assert "const G009_SHOP_BROWSE_PREVIEW_ONLY = true;" in shop
 assert "g019ServerApprovedEquipmentUi" in shop
 assert "G019_APPROVED_EQUIPMENT_SHOP_UI_ENABLED" in app
 assert "default=False" in app
 assert "formal_product_release" not in T
 assert "GO_DEPLOY" not in T and "GO_MERGE" not in T
 assert "P022" not in (ROOT/"app.py").read_text(encoding="utf8")[-95000:]
 assert "does NOT set any flag in production" not in G019 or "不是正式發布" in G019
