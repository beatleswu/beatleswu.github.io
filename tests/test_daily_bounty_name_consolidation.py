from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_player_facing_daily_bounty_i18n_values():
    i18n = read("i18n.js")
    assert "'nav.daily':        { en: '📜 Daily Bounty', zh: '📜 每日懸賞令' }" in i18n
    assert "'e9.right_cards.daily_challenge_title': { en: 'Daily Bounty', zh: '每日懸賞令' }" in i18n
    assert "'inv.earn2.t': { en: 'Daily Bounty', zh: '每日懸賞令' }" in i18n
    assert "'skills.source.daily':     { en: 'Daily Bounty'" in i18n
    assert "'bdg.sec.daily_challenge':   { en: 'Daily Bounty'" in i18n


def test_player_facing_templates_use_bounty_name():
    for name in ("index.html", "badges.html", "curriculum.html", "hero.html", "inventory.html", "mistakes.html", "stats.html", "components/adventure/right_cards.html"):
        text = read(name)
        assert "每日挑戰" not in text
    assert "Daily Challenge" not in read("components/adventure/right_cards.html")


def test_profile_and_backend_badge_copy_use_bounty_name():
    profile = read("profile.html")
    backend = read("backend_i18n.py")
    assert "Daily Bounty" in profile
    assert "daily challenge" not in backend
    assert "Daily Bounty" in backend


def test_internal_daily_challenge_contracts_are_preserved():
    app = read("app.py")
    assert "daily_challenge_log" in app
    assert "get_or_create_daily_challenge" in app
    assert "/api/daily-challenge/today" in read("daily_challenge.html")
    assert "/api/daily-challenge/submit" in read("daily_challenge.html")


def test_daily_training_and_daily_quest_terms_are_not_rebranded():
    index = read("index.html")
    assert "startDailyTraining" in index
    assert "/api/quests/today" in index
