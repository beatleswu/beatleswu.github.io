"""Server-owned Daily protocol selection. No DB, schema or reward writes."""

DAILY_FLAGS = (
    'G076_ANSWER_PRIVACY_ENFORCED',
    'G076_NONMAP_STEPS_ENABLED',
    'G076_DAILY_STEPS_ENABLED',
)


def daily_mode(environ):
    # Treat unrecognized configuration as HOLD rather than accidentally
    # disclosing full SGF or admitting a legacy reward writer.
    values = [str(environ.get(key, '')).strip().lower() for key in DAILY_FLAGS]
    if all(value in ('', '0', 'false', 'off') for value in values):
        return 'legacy'
    if all(value in ('1', 'true', 'on') for value in values):
        return 'steps'
    return 'hold'


def create_capability_blueprint(environ):
    from flask import Blueprint, jsonify, session
    bp = Blueprint('g076_daily_capability', __name__)

    @bp.after_request
    def no_store(response):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Vary'] = 'Cookie'
        return response

    @bp.get('/api/g076/daily/capability')
    def capability():
        uid = session.get('user_id')
        if type(uid) is not int or uid < 1:
            return jsonify(error='authentication_required'), 401
        mode = daily_mode(environ)
        if mode == 'hold':
            return jsonify(mode=mode, error='daily_configuration_hold'), 409
        return jsonify(mode=mode)

    return bp
