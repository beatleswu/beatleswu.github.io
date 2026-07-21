"""Regression coverage for the Premium self-service cancellation entry."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
UPGRADE_HTML = REPO_ROOT / "upgrade.html"


def _read_upgrade_page():
    return UPGRADE_HTML.read_text(encoding="utf-8")


def test_premium_status_container_exists_next_to_upgrade_cta():
    html = _read_upgrade_page()
    cta = 'id="upgrade-btn"'
    container = 'id="already-premium" hidden aria-live="polite"'

    assert cta in html
    assert container in html
    assert html.index(cta) < html.index(container)


def test_active_subscription_can_render_cancel_entry_into_container():
    html = _read_upgrade_page()

    assert "const box=document.getElementById('already-premium');" in html
    assert "box.hidden=false;" in html
    assert "box.replaceChildren();" in html
    assert "s.subscription&&s.subscription.status==='active'" in html
    assert "I18n.t('up.sub.cancel')" in html
    assert "fetch('/api/pay/subscription/cancel',{method:'POST',credentials:'include'})" in html


def test_pending_or_manual_premium_does_not_render_cancel_button():
    html = _read_upgrade_page()

    active_condition = "s.subscription&&s.subscription.status==='active'"
    pending_condition = "s.subscription&&s.subscription.status==='pending'"
    assert active_condition in html
    assert pending_condition in html
    assert html.index(active_condition) < html.index(pending_condition)
