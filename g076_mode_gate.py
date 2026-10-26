"""G076 per-mode SERVER feature gate contract; no routes, writes or DDL.

Do not infer readiness from a flag alone. The integrator must supply verified
server-side runtime adapter readiness (not browser headers/query/body/cookies).
Legacy is safe for unconverted modes only with the global privacy gate OFF.
Unknown and partial flag combinations fail closed. HOLD does NOT mean PLAYABLE.
"""
from dataclasses import dataclass

FLAGS = {
    'mistakes': 'G076_MISTAKES_STEPS_ENABLED',
    'rating': 'G076_RATING_STEPS_ENABLED',
    'grimoire': 'G076_GRIMOIRE_STEPS_ENABLED',
    'friend_challenge': 'G076_FRIEND_STEPS_ENABLED',
    'lord': 'G076_LORD_STEPS_ENABLED',
    'guild': 'G076_GUILD_STEPS_ENABLED',
}
TRUE = frozenset({'1','true','on'})
FALSE = frozenset({'','0','false','off'})

@dataclass(frozen=True)
class ModeGate:
    mode: str
    selected: str  # legacy / steps / hold
    reason: str

    @property
    def playable(self):
        return self.selected in ('legacy', 'steps')


def _parse(raw):
    value = str(raw if raw is not None else '').strip().lower()
    if value in TRUE:
        return True
    if value in FALSE:
        return False
    return None


def select_mode(environ, mode, *, adapter_ready=False):
    """Server-side decision only. Never pass a browser-provided adapter_ready."""
    if mode not in FLAGS:
        return ModeGate(str(mode), 'hold', 'unknown_mode')
    privacy = _parse(environ.get('G076_ANSWER_PRIVACY_ENFORCED', ''))
    selected = _parse(environ.get(FLAGS[mode], ''))
    if privacy is None or selected is None:
        return ModeGate(mode, 'hold', 'invalid_flag')
    if not selected:
        if privacy:
            return ModeGate(mode, 'hold', 'privacy_on_unmigrated')
        return ModeGate(mode, 'legacy', 'default_off')
    if adapter_ready is not True:
        return ModeGate(mode, 'hold', 'trusted_adapter_missing')
    # An independent mode may enforce answer privacy without enabling a site-
    # wide flag. Its OWN server must project only the board when it is ON.
    return ModeGate(mode, 'steps', 'verified_server_adapter')
