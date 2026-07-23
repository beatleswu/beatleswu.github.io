import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_catalog_is_read_only_main_and_daily_only():
    text = read("js/e9/quest_definitions.js")
    assert "daily.complete_daily_challenge" in text
    assert "main.earn_first_zone_star" in text
    assert "weekly" not in text.lower()
    assert "rewardCoins" not in text
    assert "claimEndpoint" not in text


def test_evaluator_is_pure_and_fail_closed():
    text = read("js/e9/quest_evaluator.js")
    assert "function evaluateQuest" in text
    assert "fetch(" not in text
    assert "localStorage" not in text
    assert "state: 'unavailable'" in text


def test_quest_board_uses_lifecycle_and_canonical_routes():
    text = read("js/e9/quest_board.js")
    assert "createQuestStore" in text
    assert "registerCleanup" in text
    assert "window.location" not in text
    assert "dailyChallenge: '/daily-challenge'" in text
    assert "adventure: '/?adventure=1'" in text


def test_markup_has_accessible_main_daily_board_without_weekly():
    text = read("components/adventure/right_cards.html")
    assert "data-e9-quest-board" in text
    assert 'role="tablist"' in text
    assert 'data-e9-quest-tab="main"' in text
    assert 'data-e9-quest-tab="daily"' in text
    assert "weekly" not in text.lower()


def test_static_manifest_contains_quest_assets_and_i18n_keys():
    manifest = json.loads(read("deploy/build-manifest.json"))
    files = json.dumps(manifest)
    for asset in ("js/e9/quest_definitions.js", "js/e9/quest_evaluator.js", "js/e9/quest_store.js", "js/e9/quest_board.js", "css/e9/quests.css"):
        assert asset in files
    i18n = read("i18n.js")
    for key in ("e9.quest.title", "e9.quest.completed", "e9.quest.main.earn_first_zone_star.title", "e9.quest.daily.complete_daily_challenge.title"):
        assert key in i18n


def test_asset_version_was_bumped_for_static_quest_files():
    assert "e9-q1-quest-board" in read("js/e9/feature_flags.js")
    assert "v203-e9-zone-name-i18n-fix" in read("sw.js")
