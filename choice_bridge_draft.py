"""G070 question-choice-v1 draft. Deliberately not registered in Flask.

No verified corpus choice schema/provider exists. Even a requested enable must
fail closed. Never parse LB as choices, issue attempts, judge or persist results.
"""

CHOICE_SCHEMA = 'question-choice-v1'
CHOICE_ADAPTER_ENABLED = False


class ChoiceBridgeUnavailable(ValueError):
    def __init__(self, code, status):
        super().__init__(code)
        self.code, self.status = code, status


def reject_unavailable_choice(*, user_id, entitled, requested_enabled=False):
    """Future caller supplies existing session/entitlement, never body claims.

    This is only a denial adapter, not an authorization or HTTP implementation.
    It intentionally takes no question/answer/nonce payload to avoid disclosure.
    """
    if not user_id:
        raise ChoiceBridgeUnavailable('login_required', 401)
    if entitled is not True:
        raise ChoiceBridgeUnavailable('question_forbidden', 403)
    if not requested_enabled:
        raise ChoiceBridgeUnavailable('feature_off', 404)
    raise ChoiceBridgeUnavailable('verified_choice_schema_unavailable', 503)
