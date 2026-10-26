"""B3/B4 server flag truth-table acceptance contract, NOT full player E2E.

When flags say ON but the backend adapter is absent, HOLD is required.
No test below pretends a 409/503 makes a game mode playable.
"""
import itertools
import pytest

from g076_mode_gate import FLAGS, select_mode
from g076_mistakes_product import mode as mistakes_mode
from g076_daily_capability import daily_mode, DAILY_FLAGS


@pytest.mark.parametrize('privacy', ('off','on'))
@pytest.mark.parametrize('bits', tuple(itertools.product(('off','on'), repeat=len(FLAGS))))
def test_every_combination_with_no_registered_adapters(privacy,bits):
    env={'G076_ANSWER_PRIVACY_ENFORCED':privacy}
    env.update({key:bit for key,bit in zip(FLAGS.values(),bits)})
    assert len(FLAGS)==6
    for mode,key in FLAGS.items():
        observed=select_mode(env,mode,adapter_ready=False)
        expected='legacy' if privacy=='off' and env[key]=='off' else 'hold'
        assert observed.selected==expected
        assert observed.playable==(expected=='legacy')


@pytest.mark.parametrize('mode', tuple(FLAGS))
def test_exactly_one_secure_registered_mode_does_not_enable_any_other(mode):
    env={key:'off' for key in FLAGS.values()}
    env['G076_ANSWER_PRIVACY_ENFORCED']='off'
    env[FLAGS[mode]]='on'
    decision=select_mode(env,mode,adapter_ready=True)
    assert decision.selected=='steps' and decision.playable
    for other in FLAGS:
        if other!=mode:
            selected=select_mode(env,other,adapter_ready=False)
            assert selected.selected=='legacy'
    # The server adapter flag never switches the global privacy flag on.
    assert env['G076_ANSWER_PRIVACY_ENFORCED']=='off'


@pytest.mark.parametrize('mode', tuple(FLAGS))
@pytest.mark.parametrize('bad',('unknown','enabled','2','yes','none','-1'))
def test_bad_mode_flag_never_downgrades_to_legacy(mode,bad):
    env={'G076_ANSWER_PRIVACY_ENFORCED':'off',FLAGS[mode]:bad}
    assert select_mode(env,mode,adapter_ready=True).selected=='hold'


@pytest.mark.parametrize('bad',('unknown','enabled','2','yes','none','-1'))
def test_bad_global_flag_never_downgrades_to_legacy(bad):
    env={'G076_ANSWER_PRIVACY_ENFORCED':bad}
    assert all(select_mode(env,m,adapter_ready=True).selected=='hold' for m in FLAGS)


def test_mistakes_mode_off_with_global_privacy_on_is_hold_not_playable():
    assert mistakes_mode({'G076_ANSWER_PRIVACY_ENFORCED':'on'})=='hold'
    assert mistakes_mode({})=='legacy'
    assert mistakes_mode({'G076_MISTAKES_STEPS_ENABLED':'on'})=='steps'


@pytest.mark.parametrize('bits',tuple(itertools.product(('off','on'),repeat=3)))
def test_daily_3_gate_preserves_independent_original_contract(bits):
    env=dict(zip(DAILY_FLAGS,bits))
    status=daily_mode(env)
    assert status==('legacy' if bits==('off','off','off') else
                    'steps' if bits==('on','on','on') else 'hold')


def test_unknown_mode_is_explicit_hold():
    assert select_mode({},'wallet',adapter_ready=True).selected=='hold'
