"""G076 bounded containment for modes without a trusted settlement adapter.

Integration HOLD: install immediately after Flask construction, before other
request hooks. This module registers no routes, issues no pretend attempts,
and writes no identity, SRS, XP, mastery or reward state. Legacy behaviour is
preserved only while both the global privacy gate and the mode's own gate
(g076_mode_gate.select_mode) validly select legacy; anything else fails closed.

Grimoire cannot safely reuse the SRS settlement: its writer commits its own
mastery/cache/progress changes. Friend Challenge likewise owns reward writes.
Until those writers accept owned, nonce-bound server verdicts atomically,
deny their unsafe entry points rather than trusting any client claim.
"""

import os
from types import MappingProxyType

from flask import jsonify, request

from g076_mode_gate import select_mode
from g076_question_privacy import privacy_enforced


# Match both canonical rules and endpoint identities. Endpoint matching also
# covers a coordinator adding a URL alias for the same legacy view function.
_RULE_MODES = MappingProxyType({
    '/api/grimoire/training/daily': 'grimoire',
    '/api/training/contaminated': 'grimoire',
    '/api/training/answer': 'grimoire',
    '/api/challenges/friend/<int:cid>/answer': 'friend_challenge',
})
_ENDPOINT_MODES = MappingProxyType({
    'grimoire.api_training_daily': 'grimoire',
    'grimoire.api_training_contaminated': 'grimoire',
    'grimoire.api_training_answer': 'grimoire',
    'friend_challenge_answer': 'friend_challenge',
})
_EXTENSION = 'g076_othermode_authority'


def install_othermode_guard(app):
    """Install the containment hook once, at application construction time.

    Register before any other app request hook so denied requests cannot run
    a preceding writer. Flask rejects installation after serving has started.
    No body/query/header/session value grants an exemption, including premium,
    admin, claimed verdicts, nonces or client-selected mode/source labels.
    Unknown routes retain Flask's normal 404/405 behaviour. This is bounded
    containment, not a site-wide answer-leak or security-admission claim.
    """
    if _EXTENSION in app.extensions:
        return
    if app.before_request_funcs.get(None):
        raise RuntimeError('g076_othermode_guard_must_be_installed_first')

    @app.before_request
    def g076_othermode_before_request():
        if request.url_rule is None:
            return None
        mode = (_RULE_MODES.get(request.url_rule.rule)
                or _ENDPOINT_MODES.get(request.endpoint))
        if mode is None:
            return None
        # G079: legacy transport is allowed ONLY when this mode's own gate
        # selects 'legacy' (its flag validly OFF and global privacy validly
        # OFF). A malformed mode or privacy value parses to HOLD and must not
        # fall through to the unprotected legacy writer; a validly ON mode
        # serves its own server-owned route instead of this legacy entry.
        if (not privacy_enforced(os.environ)
                and select_mode(os.environ, mode).selected == 'legacy'):
            return None
        # Also deny HEAD and OPTIONS: no endpoint executes and no response
        # suggests this mode is ready. Never read or echo the request body.
        response = jsonify({
            'ok': False,
            'error': 'othermode_authority_unavailable',
            'code': 'othermode_authority_unavailable',
            'mode': mode,
            'retryable': False,
        })
        response.status_code = 409
        response.headers['Cache-Control'] = 'no-store'
        return response

    app.extensions[_EXTENSION] = g076_othermode_before_request
